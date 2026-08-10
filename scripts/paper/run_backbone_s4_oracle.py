#!/usr/bin/env python3
"""I4: S4 conversion ceiling — inject gold into S3 shortlist, re-run S4-b only.

Offline probe. Does NOT go through run_backbone_v1 (which asserts no gold leak).
Reuses the same BackboneSelectFree prompt + cached LLM client pattern.

Usage:
  PYTHONPATH=src:scripts:scripts/paper \\
    python3 scripts/paper/run_backbone_s4_oracle.py \\
      --reuse-from logs/backbone_v1/diagnosisarena/e7_k3_comp_k5 \\
      --subset data/benchmarks/diagnosisarena/subsets/d2_seq100_v1 \\
      --dataset diagnosisarena --out-arm r4_i4_s4_oracle \\
      --workers 25 --limit 0
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from agentclinic_tree_dx.backbone import BackbonePipeline  # noqa: E402
import baseline_common as bc  # noqa: E402

OUT_ROOT = ROOT / "logs" / "backbone_v1"


def load_stage(reuse_dir: Path, cid: str) -> dict[str, Any]:
    p = reuse_dir / "case_stages" / f"{cid}.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def inject_gold_shortlist(shortlist: list[str], gold: str) -> list[str]:
    # put gold first if absent; keep length <=5 by dropping last
    out = [gold] + [x for x in shortlist if x.strip().lower() != gold.strip().lower()]
    return out[: max(5, len(shortlist))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse-from", type=Path, required=True)
    ap.add_argument("--subset", type=Path, required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out-arm", default="r4_i4_s4_oracle")
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    args = ap.parse_args()

    reuse = Path(args.reuse_from)
    out_ds = {
        "diagnosisarena": "diagnosisarena",
        "diagnosisarena_heldout": "diagnosisarena_heldout",
        "diagnosisarena_heldout200b": "diagnosisarena_heldout200b",
        "medcasereasoning": "medcasereasoning",
        "medcasereasoning_v2": "medcasereasoning_v2",
        "medcasereasoning_200b": "medcasereasoning_200b",
    }.get(args.dataset, args.dataset)
    out_dir = OUT_ROOT / out_ds / args.out_arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)
    (out_dir / "cache").mkdir(exist_ok=True)

    cases = bc.load_runtime_cases(
        dataset="diagnosisarena" if "diagnosisarena" in args.dataset or args.dataset == "da" else "medcasereasoning",
        subset_dir=Path(args.subset),
        case_ids=list(args.case_id or []),
        limit=int(args.limit or 0),
    )
    # gold map
    gold_map = {}
    for c in cases:
        cid = str(c.get("source_id") or c.get("id") or "")
        gold_map[cid] = str(
            c.get("gold")
            or c.get("_gold_text")
            or c.get("Final Diagnosis")
            or ""
        )

    cache_path = out_dir / "cache" / "backbone_llm.json"
    from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

    client = RobustLLMClient(
        model=args.model, call_timeout=240, max_retries=5, timeout_retry_cap=2, temperature=0.0
    )
    llm = bc.SimpleCachedLLM(client, cache_path, args.model)
    pipe = BackbonePipeline(
        llm,
        select_variant="b",
        max_k=5,
        entrance="llm_ddx",
        s2_k=3,
        s2_mode="complement",
    )

    # Offline probe: allow gold injection into shortlist (not a gold-* payload key for LLM).
    # Strip oracle metadata before any LLM call by keeping it only on disk docs.

    def one(case: dict) -> dict:
        cid = str(case.get("source_id") or case.get("id"))
        stage_path = out_dir / "case_stages" / f"{cid}.json"
        if stage_path.is_file():
            return json.loads(stage_path.read_text())
        prior = load_stage(reuse, cid)
        stages = dict(prior.get("stages") or {})
        s3 = dict(stages.get("s3") or {})
        short = list(s3.get("shortlist") or [])
        gold = gold_map.get(cid) or ""
        if not gold:
            return {"case_id": cid, "error": "no_gold"}
        injected = inject_gold_shortlist(short, gold)
        s3["shortlist"] = injected
        s3["oracle_injected"] = True
        s3["oracle_gold"] = gold
        stages["s3"] = s3
        # call S4 only via pipe.run with reuse of s1/s2/s3
        vignette = str(case.get("case_text") or case.get("vignette") or "")
        # BackbonePipeline.run expects specific kwargs — use internal select path
        result = pipe.run(
            vignette=vignette,
            question="What is the most likely diagnosis?",
            case_id=cid,
            reuse_stages={"s1": stages.get("s1"), "s2": stages.get("s2"), "s3": s3},
        )
        doc = {
            "case_id": prior.get("case_id") or cid,
            "source_id": cid,
            "champion": result.champion,
            "ordered_diagnoses": list(result.ordered_diagnoses),
            "stages": result.stages,
            "oracle": True,
            "gold": gold,
            "llm_calls": result.llm_calls,
        }
        stage_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        return doc

    preds = []
    with ThreadPoolExecutor(max_workers=int(args.workers)) as ex:
        futs = {ex.submit(one, c): c for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            doc = fut.result()
            cid = str(doc.get("source_id") or "")
            preds.append(
                {
                    "arm": args.out_arm,
                    "case_id": doc.get("case_id") or cid,
                    "source_id": cid,
                    "dataset": out_ds,
                    "list_k": 2,
                    "ordered_diagnoses": doc.get("ordered_diagnoses")
                    or [doc.get("champion")]
                    if doc.get("champion")
                    else [],
                    "top2_diagnoses": (doc.get("ordered_diagnoses") or [doc.get("champion"), ""])[:2],
                    "oracle": True,
                }
            )
            if i % 20 == 0:
                print(f"[oracle] {i}/{len(cases)}")

    pred_path = out_dir / "predictions.jsonl"
    with pred_path.open("w", encoding="utf-8") as f:
        for p in sorted(preds, key=lambda x: int(x["source_id"]) if str(x["source_id"]).isdigit() else x["source_id"]):
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    # conversion: champion matches gold
    sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
    import disagreement_census as dcc  # noqa: E402

    hits = 0
    n = 0
    for p in preds:
        gold = gold_map.get(str(p["source_id"])) or ""
        champ = (p.get("ordered_diagnoses") or [None])[0] or ""
        if not gold:
            continue
        n += 1
        if dcc.match(str(champ), gold):
            hits += 1
    summary = {
        "arm": args.out_arm,
        "n": n,
        "s4_conversion_given_gold_in_shortlist": hits / n if n else None,
        "hits": hits,
        "reuse_from": str(reuse),
        "note": "Gold was force-injected into S3 shortlist; measures S4 ranking conversion ceiling.",
    }
    (out_dir / "oracle_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
