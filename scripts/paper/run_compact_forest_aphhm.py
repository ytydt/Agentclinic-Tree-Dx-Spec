#!/usr/bin/env python3
"""Scale runner: forest-geometry pool + APHHM candev selector (± near-dedup).

Default --reuse-from mosaic_forest_v1 (selector-only, 1 call/case) — the X1
acceptance configuration at arm scale. Use --regen to rebuild axes (≈4 calls).
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx import near_dedup as nd  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.mosaic import MosaicPipeline  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


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


def _resolve_spans(doc: dict, items: list[Any]) -> list[str]:
    stages = doc.get("stages") or {}
    id2 = {
        str(e.get("evidence_id")): str(e.get("raw_span") or "")
        for e in (stages.get("evidence") or [])
        if isinstance(e, dict) and e.get("evidence_id")
    }
    out = []
    for x in items or []:
        s = str(x or "").strip()
        if not s:
            continue
        out.append(id2[s] if s in id2 and id2[s] else s)
    return out


def notes_from_mosaic(doc: dict, max_n: int = 8) -> tuple[list[str], list[dict]]:
    stages = doc.get("stages") or {}
    reg = stages.get("registry") or []
    notes = []
    for c in reg:
        if not isinstance(c, dict):
            continue
        lab = str(c.get("preferred_label") or c.get("preferred_name") or c.get("name") or "").strip()
        if not lab:
            continue
        notes.append(
            {
                "label": lab,
                "for": _resolve_spans(
                    doc, list(c.get("support_spans") or c.get("supporting_evidence") or [])
                )[:4],
                "against": _resolve_spans(
                    doc,
                    list(c.get("contradict_spans") or c.get("contradicting_evidence") or []),
                )[:3],
                "score": c.get("score_logit", c.get("score")),
            }
        )
    # prefer frontier order / score
    frontier = stages.get("frontier") or []
    short: list[str] = []
    if frontier and isinstance(frontier[0], dict):
        for c in frontier:
            lab = str(c.get("preferred_label") or c.get("preferred_name") or c.get("name") or "")
            if lab:
                short.append(lab)
    if not short:
        ordered = [str(x) for x in (doc.get("ordered_diagnoses") or []) if str(x).strip()]
        short = ordered[:max_n]
    if not short:
        scored = sorted(
            notes,
            key=lambda n: (-(n["score"] if n["score"] is not None else float("-inf")), n["label"]),
        )
        short = [n["label"] for n in scored[:max_n]]
    by = {n["label"]: n for n in notes}
    notes_out = [by.get(s, {"label": s, "for": [], "against": []}) for s in short[:max_n]]
    return short[:max_n], notes_out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--arm", default="compact_forest_v0")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--near-dedup-shortlist", action="store_true")
    ap.add_argument(
        "--x3-evidence",
        action="store_true",
        help="evidence-consistent sibling dedupe before selector (no gold; not blind merge)",
    )
    ap.add_argument(
        "--x3-oracle-gold",
        action="store_true",
        help="drop near-gold non-gold siblings using case gold (eval-only)",
    )
    ap.add_argument(
        "--reuse-from",
        default="mosaic_forest_v1",
        help="Arm dir name under the dataset to reuse as pool (empty = regen)",
    )
    ap.add_argument("--regen", action="store_true", help="Ignore reuse-from; rebuild forest axes")
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
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)
    pool_dir = None if args.regen or not args.reuse_from else OUT_ROOT / out_ds / args.reuse_from

    cases = bc.load_runtime_cases(
        dataset=ds_name,
        subset_dir=subset,
        case_ids=list(args.case_id or []),
        limit=int(args.limit or 0),
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=240,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "compact_forest_llm.json", args.model)
    mosaic = MosaicPipeline(cached, mode="forest", max_calls=4) if (args.regen or not pool_dir) else None
    sel_prompt = (PROMPT_DIR / "aphhm_c_frontier_selector_candev.txt").read_text(encoding="utf-8")

    _atomic_json(
        out_dir / "manifest.json",
        {
            "arm": args.arm,
            "dataset": out_ds,
            "subset": str(subset),
            "model": args.model,
            "n_cases": len(cases),
            "reuse_from": None if args.regen else args.reuse_from,
            "near_dedup_shortlist": bool(args.near_dedup_shortlist),
            "x3_evidence": bool(args.x3_evidence),
            "x3_oracle_gold": bool(args.x3_oracle_gold),
            "created_at": _utc(),
            "schema_version": "compact_forest_v0_scale",
        },
    )

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(case.get("source_id") or case.get("case_id") or "")
        vignette = str(case.get("vignette") or "")
        mosaic_calls = 0
        stages: dict[str, Any] = {}
        doc: dict[str, Any] = {}
        if pool_dir is not None:
            doc = _load_stage(pool_dir, cid)
        if not doc and mosaic is not None:
            result = mosaic.run(case_id=str(case.get("case_id") or cid), vignette=vignette)
            mosaic_calls = int(result.llm_calls)
            stages = dict(result.stages or {})
            doc = {
                "ordered_diagnoses": list(result.ordered_diagnoses or []),
                "champion": result.champion,
                "stages": stages,
            }
        if not doc:
            return {"source_id": cid, "error": "no_pool", "ordered_diagnoses": []}
        short, notes = notes_from_mosaic(doc)
        x3_meta: dict[str, Any] = {}
        if args.near_dedup_shortlist:
            short = nd.dedupe_labels(short)
            by = {n["label"]: n for n in notes}
            notes = [by.get(s, {"label": s, "for": [], "against": []}) for s in short]
        gold = str(case.get("_gold_text") or case.get("gold") or "").strip()
        if args.x3_oracle_gold and gold:
            before = len(short)
            short = nd.x3_drop_near_siblings(short, gold)
            by = {n["label"]: n for n in notes}
            notes = [by.get(s, {"label": s, "for": [], "against": []}) for s in short]
            x3_meta = {"mode": "oracle_gold", "before": before, "after": len(short)}
        elif args.x3_evidence:
            before = len(notes)
            notes = nd.evidence_consistent_sibling_dedupe(notes)
            short = [n["label"] for n in notes]
            x3_meta = {"mode": "evidence", "before": before, "after": len(short)}
        raw = cached.call(
            "AphhmCFrontierSelector",
            sel_prompt,
            {
                "vignette": vignette[:6000],
                "shortlist": short[:6],
                "candidate_notes": notes[:6],
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
            "llm_calls": mosaic_calls + 1,
            "stages": {
                **(doc.get("stages") or {}),
                "mode": "compact_forest_v0",
                "frontier_selector": raw,
                "pool_source": str(pool_dir) if pool_dir else "regen_forest",
                "selector_family": "aphhm_c_candev",
                "near_dedup_shortlist": bool(args.near_dedup_shortlist),
                "x3": x3_meta,
            },
            "metrics": {"mosaic_calls": mosaic_calls, "selector_calls": 1},
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {
            "arm": args.arm,
            "case_id": case.get("case_id"),
            "source_id": cid,
            "ordered_diagnoses": ordered,
            "cost": {"llm_calls": out_doc["llm_calls"]},
        }

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            preds.append(r)
            if i % 50 == 0 or i == len(cases):
                print(f"  [{i}/{len(cases)}] {r.get('source_id')} -> {(r.get('ordered_diagnoses') or [''])[0]}")

    (out_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n", encoding="utf-8"
    )
    n_ok = sum(1 for p in preds if p.get("ordered_diagnoses"))
    print(json.dumps({"arm": args.arm, "n": len(preds), "n_ok": n_ok, "out": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
