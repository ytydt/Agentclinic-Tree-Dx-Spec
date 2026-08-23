#!/usr/bin/env python3
"""Run MOSAIC / IMPC pipelines.

Modes: lite | adaptive4 | adaptive4v2 | forest | impc
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.mosaic import MODES, MosaicPipeline  # noqa: E402
from run_backbone_v1 import SUBSETS, score_da, score_mcr  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
OUT_ROOT = ROOT / "logs" / "backbone_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()) + ["mcr"])
    ap.add_argument("--arm", required=True)
    ap.add_argument("--mode", choices=list(MODES), default="lite")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--score", action="store_true")
    ap.add_argument(
        "--legacy-containment-identity",
        action="store_true",
        help="Restore the pre-repair identity predicate, which folds a concept "
        "into any concept whose name it contains. Only for replaying an archived "
        "arm verbatim; it silently folded 561/452 concepts in Forest/IMPC",
    )
    ap.add_argument("--mcr-judge-workers", type=int, default=50)
    args = ap.parse_args()

    ds_key = "medcasereasoning" if args.dataset == "mcr" else args.dataset
    subset = SUBSETS[ds_key]
    if ds_key.startswith("medcasereasoning"):
        ds_name = "medcasereasoning"
        out_ds = ds_key
    elif ds_key.startswith("diagnosisarena_heldout"):
        ds_name = "diagnosisarena"
        out_ds = ds_key
    else:
        ds_name = "diagnosisarena"
        out_ds = "diagnosisarena"

    out_dir = OUT_ROOT / out_ds / args.arm
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "case_stages").mkdir(exist_ok=True)
    cache_path = out_dir / "cache" / "mosaic_llm.json"

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
    cached = bc.SimpleCachedLLM(client, cache_path, args.model)
    pipe = MosaicPipeline(
        cached,
        mode=args.mode,
        safe_identity=not bool(args.legacy_containment_identity),
    )

    _atomic_json(
        out_dir / "manifest.json",
        {
            "arm": args.arm,
            "mode": args.mode,
            "dataset": out_ds,
            "subset": str(subset),
            "model": args.model,
            "n_cases": len(cases),
            "workers": args.workers,
            "safe_identity": pipe.safe_identity,
            "created_at": _utc(),
            "schema_version": "mosaic_v2",
        },
    )

    preds: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def one(case: Mapping[str, Any]) -> dict[str, Any]:
        cid = str(case["case_id"])
        source_id = str(case.get("source_id") or cid)
        stage_path = out_dir / "case_stages" / f"{source_id}.json"
        if stage_path.is_file():
            prior = json.loads(stage_path.read_text(encoding="utf-8"))
            return prior.get("prediction") or {
                "arm": args.arm,
                "case_id": cid,
                "source_id": source_id,
                "ordered_diagnoses": [prior.get("champion")] if prior.get("champion") else [],
                "top2_diagnoses": [prior.get("champion")] if prior.get("champion") else [],
                "cost": {"llm_calls": prior.get("llm_calls") or 0},
            }
        t0 = time.time()
        result = pipe.run(case_id=cid, vignette=str(case["vignette"]))
        pred = result.as_prediction(arm=args.arm, source_id=source_id, dataset=out_ds)
        pred["wall_s"] = round(time.time() - t0, 3)
        doc = {
            "case_id": cid,
            "source_id": source_id,
            "champion": result.champion,
            "ordered_diagnoses": result.ordered_diagnoses,
            "llm_calls": result.llm_calls,
            "stages": result.stages,
            "metrics": result.metrics,
            "prediction": pred,
            "created_at": _utc(),
        }
        _atomic_json(stage_path, doc)
        return pred

    with ThreadPoolExecutor(max_workers=int(args.workers)) as pool:
        futs = {pool.submit(one, c): c for c in cases}
        done = 0
        for fut in as_completed(futs):
            case = futs[fut]
            done += 1
            try:
                pred = fut.result()
                preds.append(pred)
                print(
                    f"  [{done}/{len(cases)}] {case['case_id']} "
                    f"calls={pred.get('cost',{}).get('llm_calls')} "
                    f"-> {(pred.get('ordered_diagnoses') or [''])[0][:60]}",
                    flush=True,
                )
            except Exception as exc:
                errors.append(
                    {
                        "case_id": case["case_id"],
                        "error": f"{type(exc).__name__}: {exc}",
                        "trace": traceback.format_exc(),
                    }
                )
                print(f"  ERROR {case['case_id']}: {exc}", flush=True)

    preds.sort(key=lambda r: str(r.get("source_id") or r.get("case_id")))
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for p in preds:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    calls = [int((p.get("cost") or {}).get("llm_calls") or 0) for p in preds]
    summary = {
        "arm": args.arm,
        "mode": args.mode,
        "dataset": out_ds,
        "n_predictions": len(preds),
        "n_errors": len(errors),
        "llm_calls_total": sum(calls),
        "llm_calls_mean": (sum(calls) / len(calls)) if calls else None,
        "errors": errors,
        "finished_at": _utc(),
    }
    _atomic_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)

    if args.score and preds:
        if ds_name == "medcasereasoning":
            score_mcr(out_dir, subset / "cases.parquet", workers=args.mcr_judge_workers)
        else:
            score_da(out_dir, subset, args.model)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
