"""Official DA mapper@1 + MCR Prompt-7 Acc (Gemini 2.5 Flash).

Uses parent paper scoring, not MedEinst Acc_base.

  PYTHONPATH=. python -m src.score_official --run-dir runs/... --parent ..
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prepare_parent_imports(parent: Path) -> None:
    paper = str(parent / "scripts" / "paper")
    src = str(parent / "src")
    for item in (paper, src):
        if item not in sys.path:
            sys.path.insert(0, item)


def score_da(run_dir: Path, parent: Path, *, model: str, workers: int) -> dict[str, Any]:
    _prepare_parent_imports(parent)
    import baseline_common as bc
    import baseline_mapper_score as mapper_score

    pred_dir = run_dir / "da"
    subset = parent / "data" / "benchmarks" / "diagnosisarena" / "subsets" / "d2_heldout200b_v1"
    cases = bc.load_runtime_cases(dataset="diagnosisarena", subset_dir=subset)
    summary = mapper_score.score_predictions_dir(
        pred_dir,
        cases,
        mode="typed_llm_disagreement_rag",
        model=model,
        dry_run=False,
        workers=workers,
    )
    _write_json(pred_dir / "mapper" / "summary.json", summary)
    return summary


def score_mcr(run_dir: Path, parent: Path, *, workers: int) -> dict[str, Any]:
    _prepare_parent_imports(parent)
    from build_baseline_eval_projection import build_baseline_eval_projections
    from run_ox_mcr_official_eval import run_eval
    from transfer_eval import judges

    pred_dir = run_dir / "mcr"
    parquet = (
        parent
        / "data"
        / "benchmarks"
        / "medcasereasoning"
        / "subsets"
        / "mcr_val_seq200b_v1"
        / "cases.parquet"
    )
    build_baseline_eval_projections(
        pred_dir,
        dataset="medcasereasoning",
        list_k=2,
        resume=True,
    )
    summary = run_eval(
        dataset="medcasereasoning",
        run_dir=pred_dir,
        subset_parquet=parquet,
        judge_kind="llm",
        build_projection=False,
        resume_scores=True,
        skip_reasoning_recall=True,
        workers=workers or int(judges.JUDGE_WORKERS),
        out_name="official_eval_llm",
        judge_model=judges.JUDGE_MODEL_SLUG,
    )
    _write_json(pred_dir / "mcr_eval_summary.json", summary)
    return summary


def _mcr_acc(summary: dict[str, Any]) -> Any:
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else summary
    if not isinstance(metrics, dict):
        return None
    return metrics.get("diagnostic_accuracy_single_trajectory")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--parent", default="..")
    parser.add_argument("--skip-da", action="store_true")
    parser.add_argument("--skip-mcr", action="store_true")
    parser.add_argument(
        "--mapper-model",
        default="meta-llama/llama-3.3-70b-instruct",
        help="DA mapper LLM (parent backbone default; not the Prompt-7 judge).",
    )
    parser.add_argument("--mapper-workers", type=int, default=25)
    parser.add_argument("--judge-workers", type=int, default=50)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    parent = Path(args.parent).resolve()
    out: dict[str, Any] = {
        "run_dir": str(run_dir),
        "da_endpoint": "mapper option@1 (typed_llm_disagreement_rag)",
        "da_mapper_model": args.mapper_model,
        "mcr_endpoint": "prompt7 diagnostic_hit",
        "mcr_judge_model": "google/gemini-2.5-flash",
        "mcr_judge_workers": args.judge_workers,
    }
    if not args.skip_da:
        print("[score] DA mapper@1 …", flush=True)
        da = score_da(
            run_dir,
            parent,
            model=args.mapper_model,
            workers=args.mapper_workers,
        )
        out["da"] = da
        print(json.dumps({"da": da}, indent=2), flush=True)
    if not args.skip_mcr:
        print("[score] MCR Prompt-7 gemini-2.5-flash …", flush=True)
        mcr = score_mcr(run_dir, parent, workers=args.judge_workers)
        metrics = mcr.get("metrics") if isinstance(mcr.get("metrics"), dict) else {}
        out["mcr"] = {
            "diagnostic_accuracy_single_trajectory": metrics.get(
                "diagnostic_accuracy_single_trajectory"
            ),
            "n_cases": mcr.get("n_cases_scored") or metrics.get("n_cases"),
            "n_hits": metrics.get("n_diagnostic_hits"),
            "judge_model": mcr.get("judge_model_slug") or mcr.get("judge_model"),
            "missing_gold": mcr.get("missing_gold"),
            "n_errors": mcr.get("n_errors"),
        }
        print(json.dumps({"mcr": out["mcr"]}, indent=2), flush=True)
    _write_json(run_dir / "official_scores.json", out)
    print("wrote", run_dir / "official_scores.json", flush=True)


if __name__ == "__main__":
    main()
