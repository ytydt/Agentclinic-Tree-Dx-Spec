#!/usr/bin/env python3
"""OX/MCR official-style eval for baseline replicate directories.

Builds annotate/eval_projection from predictions.jsonl + trace.jsonl, then
reuses transfer_eval metrics (same as tree-system run_ox_mcr_official_eval).

LLM judge contract: conda gnn-llm + clashon + --workers 50
(see analysis/transfer_metrics_v1/judge_prompts/JUDGE_MODEL_CONTRACT.md).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_PAPER = ROOT / "scripts" / "paper"
sys.path.insert(0, str(_PAPER))
sys.path.insert(0, str(ROOT / "src"))

import baseline_common as bc  # noqa: E402
from build_baseline_eval_projection import (  # noqa: E402
    PROTOCOL_TAG,
    build_baseline_eval_projections,
    resolve_list_k,
)
from run_ox_mcr_official_eval import run_eval  # noqa: E402
from transfer_eval import judges  # noqa: E402

DEFAULT_OX_PARQUET = (
    ROOT / "data" / "benchmarks" / "open_xddx" / "subsets" / "ox_seq100_v1" / "cases.parquet"
)
DEFAULT_MCR_PARQUET = (
    ROOT
    / "data"
    / "benchmarks"
    / "medcasereasoning"
    / "subsets"
    / "mcr_val_seq100_v1"
    / "cases.parquet"
)
DEFAULT_RA_PARQUET = (
    ROOT
    / "data"
    / "benchmarks"
    / "rarearena"
    / "subsets"
    / "ra_rdc_seq100_v1"
    / "cases.parquet"
)


def _default_parquet(dataset: str) -> Path:
    ds = bc.normalize_dataset(dataset)
    if ds == bc.DATASET_MCR:
        return DEFAULT_MCR_PARQUET
    if ds == bc.DATASET_RAREARENA:
        return DEFAULT_RA_PARQUET
    return DEFAULT_OX_PARQUET


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--pred-dir",
        type=Path,
        required=True,
        help="baseline replicate dir with predictions.jsonl (+ trace.jsonl)",
    )
    ap.add_argument(
        "--dataset",
        default="open_xddx",
        choices=("open_xddx", "medcasereasoning", "rarearena", "ox", "mcr", "ra"),
    )
    ap.add_argument("--subset-parquet", type=Path, default=None)
    ap.add_argument("--judge", choices=("lexical", "llm"), default="lexical")
    ap.add_argument(
        "--list-k",
        type=int,
        default=0,
        help="pred_ddx length (0=read manifest; OX fair default 5)",
    )
    ap.add_argument("--resume-projection", action="store_true")
    ap.add_argument("--resume-scores", action="store_true")
    ap.add_argument("--nlg-metrics", action="store_true")
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--no-md", action="store_true")
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help="0 = contract default (50 for llm, 1 for lexical)",
    )
    ap.add_argument("--out-name", default="")
    ap.add_argument("--skip-reasoning-recall", action="store_true")
    ap.add_argument(
        "--skip-build-projection",
        action="store_true",
        help="assume annotate/eval_projection already exists",
    )
    args = ap.parse_args()

    ds = args.dataset
    if ds == "ox":
        ds = "open_xddx"
    elif ds == "mcr":
        ds = "medcasereasoning"
    elif ds == "ra":
        ds = "rarearena"
    ds = bc.normalize_dataset(ds)

    pred_dir = Path(args.pred_dir)
    if not (pred_dir / "predictions.jsonl").is_file():
        raise SystemExit("missing predictions.jsonl under %s" % pred_dir)

    list_k = resolve_list_k(pred_dir, int(args.list_k or 0))
    if ds == bc.DATASET_OPEN_XDDX:
        list_k = bc.validate_list_k(ds, list_k)

    parquet = Path(args.subset_parquet) if args.subset_parquet else _default_parquet(ds)
    if not parquet.is_file():
        raise SystemExit("missing subset parquet: %s" % parquet)

    if not args.skip_build_projection:
        build_baseline_eval_projections(
            pred_dir,
            dataset=ds,
            list_k=list_k,
            case_ids=list(args.case_id or []),
            resume=bool(args.resume_projection),
        )

    workers = int(args.workers)
    if workers <= 0:
        workers = int(judges.JUDGE_WORKERS) if args.judge == "llm" else 1

    # Never call tree --build-projection here.
    summary = run_eval(
        dataset=ds,
        run_dir=pred_dir,
        subset_parquet=parquet,
        judge_kind=args.judge,
        ddx_k=list_k,
        build_projection=False,
        nlg_metrics=bool(args.nlg_metrics),
        case_ids=list(args.case_id or []),
        write_md=not args.no_md,
        workers=workers,
        out_name=str(args.out_name or ""),
        resume_scores=bool(args.resume_scores),
        skip_reasoning_recall=bool(args.skip_reasoning_recall),
        projection_subdir="eval_projection",
    )

    # Augment summary with baseline protocol tags
    summary["pred_source"] = PROTOCOL_TAG
    summary["list_k"] = int(list_k)
    summary["sampling_protocol"] = "single_trajectory_v1"
    boundaries = list(summary.get("boundaries") or [])
    boundaries.extend(
        [
            "Baseline projection: %s (ordered list_k=%d; fair vs tree ddx_k)."
            % (PROTOCOL_TAG, list_k),
            "Not Dual-Inf / MCR paper reproduction; not mapper option_top1.",
            "single_trajectory_v1 ≠ official MCR 10-shot Acc.",
        ]
    )
    if args.judge == "llm":
        boundaries.append(
            "LLM eval contract: env=%s vpn=%s workers=%s"
            % (judges.JUDGE_ENV, judges.JUDGE_VPN, workers)
        )
    summary["boundaries"] = boundaries

    # Rewrite summary.json with augmented fields
    annotate = pred_dir / "annotate"
    eval_dir_name = (
        str(args.out_name).strip().strip("/")
        if args.out_name
        else ("official_eval_llm" if args.judge == "llm" else "official_eval")
    )
    summary_path = annotate / eval_dir_name / "summary.json"
    if summary_path.is_file():
        doc = json.loads(summary_path.read_text(encoding="utf-8"))
        doc["pred_source"] = PROTOCOL_TAG
        doc["list_k"] = int(list_k)
        doc["sampling_protocol"] = "single_trajectory_v1"
        doc["boundaries"] = boundaries
        if args.judge == "llm":
            doc["judge_env"] = judges.JUDGE_ENV
            doc["vpn"] = judges.JUDGE_VPN
            doc["workers"] = workers
        summary_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        summary = doc

    printable = {k: v for k, v in summary.items() if not str(k).startswith("_")}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if int(summary.get("n_errors") or 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
