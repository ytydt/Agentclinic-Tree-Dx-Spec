#!/usr/bin/env python3
"""Re-select from an existing compact/mosaic arm with evidence-X3 (1 call/case)."""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx import near_dedup as nd  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from run_backbone_v1 import SUBSETS  # noqa: E402
from run_compact_forest_aphhm import notes_from_mosaic  # noqa: E402
from run_compact_forest_v1 import notes_from_stages  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"
PROMPT = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts" / "aphhm_c_frontier_selector_candev.txt"
).read_text(encoding="utf-8")


def _load(d: Path, cid: str) -> dict:
    for key in (cid, cid.lstrip("0") or "0"):
        p = d / "case_stages" / f"{key}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        if cid.isdigit():
            p2 = d / "case_stages" / f"{int(cid)}.json"
            if p2.is_file():
                return json.loads(p2.read_text(encoding="utf-8"))
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--from-arm", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--x3-evidence", action="store_true")
    ap.add_argument("--x3-oracle-gold", action="store_true")
    args = ap.parse_args()

    ds_key = args.dataset
    subset = SUBSETS[ds_key]
    if ds_key.startswith("medcasereasoning"):
        ds_name, out_ds = "medcasereasoning", ds_key
    elif ds_key.startswith("diagnosisarena_heldout"):
        ds_name, out_ds = "diagnosisarena", ds_key
    else:
        ds_name, out_ds = "diagnosisarena", "diagnosisarena"

    src = OUT_ROOT / out_ds / args.from_arm
    out_dir = OUT_ROOT / out_ds / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)

    cases = bc.load_runtime_cases(
        dataset=ds_name, subset_dir=subset, limit=int(args.limit or 0)
    )
    client = RobustLLMClient(
        model=args.model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
    )
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "reselect_llm.json", args.model)

    def one(case: Mapping[str, Any]) -> dict:
        cid = str(case.get("source_id") or case.get("case_id") or "")
        vignette = str(case.get("vignette") or "")
        gold = str(case.get("_gold_text") or case.get("gold") or "").strip()
        doc = _load(src, cid)
        if not doc:
            return {"source_id": cid, "error": "missing"}
        stages = doc.get("stages") or {}
        if stages.get("registry") is not None and stages.get("mode") == "compact_forest_v1":
            short, notes = notes_from_stages(stages)
        else:
            short, notes = notes_from_mosaic(doc)
        x3_meta: dict[str, Any] = {}
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
            PROMPT,
            {"vignette": vignette[:6000], "shortlist": short[:6], "candidate_notes": notes[:6]},
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
            "stages": {**stages, "frontier_selector": raw, "x3": x3_meta, "reselect_from": args.from_arm},
        }
        (out_dir / "case_stages" / f"{cid}.json").write_text(
            json.dumps(out_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return {"source_id": cid, "champion": champ, "ordered_diagnoses": ordered}

    preds = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(one, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            preds.append(r)
            if i % 25 == 0 or i == len(cases):
                print(f"  [{i}/{len(cases)}] {r.get('source_id')} -> {r.get('champion')}")
    (out_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in preds) + "\n", encoding="utf-8"
    )
    print(json.dumps({"arm": args.arm, "n": len(preds), "out": str(out_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
