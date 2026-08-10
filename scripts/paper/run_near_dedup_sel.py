#!/usr/bin/env python3
"""Selector-only near-dedup acceptance on existing APHHM-C pools (800-scale).

Reuses case_stages from --pool-from, collapses near-duplicate labels on the
active shortlist (and optionally within stance groups for tournament arms),
then re-runs only the frontier selector / tournament.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx import near_dedup as nd  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_stage(d: Path, cid: str) -> dict:
    for key in (cid, cid.lstrip("0") or "0"):
        p = d / "case_stages" / f"{key}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        if cid.isdigit():
            p2 = d / "case_stages" / f"{int(cid)}.json"
            if p2.is_file():
                return json.loads(p2.read_text(encoding="utf-8"))
    return {}


def _lab(c: dict) -> str:
    return str(c.get("preferred_label") or c.get("preferred_name") or "").strip()


def build_notes(doc: dict) -> tuple[list[str], list[dict], dict[str, list[dict]]]:
    stages = doc.get("stages") or {}
    reg = [c for c in (stages.get("registry") or []) if isinstance(c, dict) and _lab(c)]
    # production selector_all_concepts: all active, generation order by concept_id
    reg = sorted(reg, key=lambda c: str(c.get("concept_id") or ""))
    notes = []
    for c in reg:
        notes.append(
            {
                "label": _lab(c),
                "for": list(c.get("support_spans") or [])[:4],
                "against": list(c.get("contradict_spans") or [])[:3],
                "stances": list(c.get("stances") or []),
            }
        )
    short = [n["label"] for n in notes]
    groups: dict[str, list[dict]] = {}
    for n in notes:
        stance = (n.get("stances") or ["unassigned"])[0]
        groups.setdefault(stance, []).append(
            {"label": n["label"], "for": n["for"], "against": n["against"]}
        )
    return short, notes, groups


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--arm", required=True)
    ap.add_argument("--pool-from", required=True, help="existing arm directory name")
    ap.add_argument("--mode", choices=("flat", "tournament"), default="flat")
    ap.add_argument("--group-near-dedup", action="store_true")
    ap.add_argument("--near-dedup-jaccard", type=float, default=0.4)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    ds_key = args.dataset
    subset = SUBSETS[ds_key]
    if ds_key.startswith("medcasereasoning"):
        ds_name, out_ds = "medcasereasoning", ds_key
    elif ds_key.startswith("diagnosisarena_heldout"):
        ds_name, out_ds = "diagnosisarena", ds_key
    else:
        ds_name, out_ds = "diagnosisarena", "diagnosisarena"

    out_dir = OUT_ROOT / out_ds / args.arm
    pool = OUT_ROOT / out_ds / args.pool_from
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)

    cases = bc.load_runtime_cases(dataset=ds_name, subset_dir=subset, case_ids=[], limit=int(args.limit or 0))
    client = RobustLLMClient(model=args.model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0)
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "near_dedup_sel.json", args.model)
    prompt_flat = (PROMPT_DIR / "aphhm_c_frontier_selector_candev.txt").read_text(encoding="utf-8")
    prompt_tourn = (PROMPT_DIR / "aphhm_c_frontier_selector_tournament.txt").read_text(encoding="utf-8")

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "arm": args.arm,
                "pool_from": args.pool_from,
                "mode": args.mode,
                "group_near_dedup": bool(args.group_near_dedup),
                "n_cases": len(cases),
                "created_at": _utc(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(case.get("source_id") or case.get("case_id") or "")
        vignette = str(case.get("vignette") or "")
        doc = _load_stage(pool, cid)
        if not doc:
            return {"source_id": cid, "error": "no_pool", "ordered_diagnoses": []}
        short, notes, groups = build_notes(doc)
        before = len(short)
        short = nd.dedupe_labels(short, jaccard=args.near_dedup_jaccard)
        by = {n["label"]: n for n in notes}
        notes = [by.get(s, {"label": s, "for": [], "against": []}) for s in short]
        if args.mode == "tournament":
            g_list = [{"group": g, "candidates": v} for g, v in groups.items()]
            if args.group_near_dedup:
                g_list = nd.dedupe_group_notes(g_list, jaccard=args.near_dedup_jaccard)
            # refresh short from groups
            short = []
            for g in g_list:
                for c in g["candidates"]:
                    lab = str(c.get("label") or "")
                    if lab and lab not in short:
                        short.append(lab)
            raw = cached.call(
                "AphhmCFrontierSelector",
                prompt_tourn,
                {"vignette": vignette[:6000], "shortlist": short, "groups": g_list},
            )
        else:
            raw = cached.call(
                "AphhmCFrontierSelector",
                prompt_flat,
                {
                    "vignette": vignette[:6000],
                    "shortlist": short[:10],
                    "candidate_notes": [
                        {"label": n["label"], "for": n.get("for"), "against": n.get("against")}
                        for n in notes[:10]
                    ],
                },
            )
        champ = str((raw or {}).get("champion") or "").strip()
        if champ not in short and short:
            champ = next((x for x in short if x.lower() == champ.lower()), short[0])
        ordered = [champ] + [x for x in short if x != champ][:4] if short else []
        out_doc = {
            "source_id": cid,
            "case_id": case.get("case_id"),
            "champion": champ,
            "ordered_diagnoses": ordered,
            "llm_calls": 1,
            "stages": {
                "mode": f"near_dedup_sel_{args.mode}",
                "pool_from": args.pool_from,
                "near_dedup": {"before": before, "after": len(short)},
                "frontier_selector": raw,
                "registry": [
                    {"preferred_label": n["label"], "support_spans": n.get("for"), "contradict_spans": n.get("against")}
                    for n in notes
                ],
            },
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {"source_id": cid, "ordered_diagnoses": ordered, "champion": champ}

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            preds.append(r)
            if i % 50 == 0 or i == len(cases):
                print(f"  [{i}/{len(cases)}] {r.get('source_id')} -> {r.get('champion')}")
    (out_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n", encoding="utf-8"
    )
    print(json.dumps({"arm": args.arm, "n": len(preds), "out": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
