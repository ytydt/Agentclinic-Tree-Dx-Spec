#!/usr/bin/env python3
"""Run the APHHM-C pipeline.

Modes: c4 | c4_noaxisbias | c4_nogap | c4_noverifier | legacy_champion
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
from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    AXIS_MODES,
    CONCEPT_CONTRACTS,
    MODES,
    SELECTOR_ORDERS,
    AphhmCPipeline,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
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
    ap.add_argument("--dataset", required=True, choices=list(SUBSETS.keys()))
    ap.add_argument("--arm", required=True)
    ap.add_argument("--mode", choices=list(MODES), default="c4")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--unique-budget", type=int, default=10)
    ap.add_argument(
        "--concept-contract", choices=list(CONCEPT_CONTRACTS), default="v1"
    )
    ap.add_argument("--axis-mode", choices=list(AXIS_MODES), default="conditioned")
    ap.add_argument("--max-facts", type=int, default=12)
    ap.add_argument("--axis-lambda", type=float, default=0.5)
    ap.add_argument("--max-calls", type=int, default=0)
    ap.add_argument(
        "--stances",
        default="commit,coverage,mechanism",
        help="comma-separated generation stances, used by --mode multistance",
    )
    ap.add_argument(
        "--near-dedup-shortlist",
        action="store_true",
        help="Collapse near-duplicate labels on the selector shortlist (R6 X3)",
    )
    ap.add_argument(
        "--group-near-dedup",
        action="store_true",
        help="Collapse near-duplicates inside each stance group before nomination",
    )
    ap.add_argument(
        "--enforce-group-quota",
        action="store_true",
        help="Seat the highest-ranked member of any stance group the tournament "
        "reply left silent, then re-adjudicate (contract fix, +1 call when used)",
    )
    ap.add_argument(
        "--strict-identity",
        action="store_true",
        help="Merge concepts on morphological equality only; a generator-claimed "
        "alias no longer folds a parent and a child into one concept",
    )
    ap.add_argument(
        "--quarantine-direction-conflicts",
        action="store_true",
        help="Withdraw both directions when one fact is asserted as support and "
        "contradict for the same candidate, and log the edge (design 9.3 item 2)",
    )
    ap.add_argument(
        "--typed-selector-cards",
        action="store_true",
        help="Hand the selector typed fact cards (polarity/time/specificity/"
        "reliability) instead of bare for/against strings (design 9.3 item 5)",
    )
    ap.add_argument(
        "--pair-edge-audit",
        action="store_true",
        help="Zero-call disputed-edge audit over the frozen shortlist, inserted "
        "before the selector; adds no candidate and removes none (design 9.3 item 3)",
    )
    ap.add_argument(
        "--selector-order",
        choices=list(SELECTOR_ORDERS),
        default="generation",
        help="Presentation order of the selector shortlist. ORDER_COUNTERFACTUAL_V1 "
        "arm: the candidate set is unchanged, only its order moves",
    )
    ap.add_argument("--near-dedup-jaccard", type=float, default=0.4)
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--mcr-judge-workers", type=int, default=50)
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
    cached = bc.SimpleCachedLLM(client, out_dir / "cache" / "aphhm_c_llm.json", args.model)
    pipe = AphhmCPipeline(
        cached,
        mode=args.mode,
        unique_budget=args.unique_budget,
        max_facts=args.max_facts,
        axis_lambda=args.axis_lambda,
        max_calls=args.max_calls or None,
        concept_contract=args.concept_contract,
        axis_mode=args.axis_mode,
        stances=[x.strip() for x in args.stances.split(",") if x.strip()],
        near_dedup_shortlist=bool(args.near_dedup_shortlist),
        group_near_dedup=bool(args.group_near_dedup),
        near_dedup_jaccard=float(args.near_dedup_jaccard),
        enforce_group_quota=bool(args.enforce_group_quota),
        strict_identity=bool(args.strict_identity),
        quarantine_direction_conflicts=bool(args.quarantine_direction_conflicts),
        typed_selector_cards=bool(args.typed_selector_cards),
        pair_edge_audit=bool(args.pair_edge_audit),
        selector_order=str(args.selector_order),
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
            "unique_budget": args.unique_budget,
            "concept_contract": args.concept_contract,
            "axis_mode": args.axis_mode,
            "stances": pipe.stances,
            "near_dedup_shortlist": pipe.near_dedup_shortlist,
            "group_near_dedup": pipe.group_near_dedup,
            "near_dedup_jaccard": pipe.near_dedup_jaccard,
            "enforce_group_quota": pipe.enforce_group_quota,
            "strict_identity": pipe.strict_identity,
            "quarantine_direction_conflicts": pipe.quarantine_direction_conflicts,
            "typed_selector_cards": pipe.typed_selector_cards,
            "pair_edge_audit": pipe.pair_edge_audit,
            "selector_order": pipe.selector_order,
            "max_facts": args.max_facts,
            "axis_lambda": args.axis_lambda,
            "max_calls": pipe.max_calls,
            "created_at": _utc(),
            "schema_version": "aphhm_c_v1",
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
            if prior.get("prediction"):
                return prior["prediction"]
        t0 = time.time()
        result = pipe.run(case_id=cid, vignette=str(case["vignette"]))
        pred = result.as_prediction(arm=args.arm, source_id=source_id, dataset=out_ds)
        pred["wall_s"] = round(time.time() - t0, 3)
        _atomic_json(
            stage_path,
            {
                "case_id": cid,
                "source_id": source_id,
                "champion": result.champion,
                "ordered_diagnoses": result.ordered_diagnoses,
                "llm_calls": result.llm_calls,
                "stages": result.stages,
                "metrics": result.metrics,
                "prediction": pred,
                "created_at": _utc(),
            },
        )
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
                    f"calls={pred.get('cost', {}).get('llm_calls')} "
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
    mm = [p.get("aphhm_c_metrics") or {} for p in preds]

    def avg(key: str) -> Any:
        vals = [float(m[key]) for m in mm if isinstance(m.get(key), (int, float))]
        return (sum(vals) / len(vals)) if vals else None

    summary = {
        "arm": args.arm,
        "mode": args.mode,
        "dataset": out_ds,
        "n_predictions": len(preds),
        "n_errors": len(errors),
        "llm_calls_total": sum(calls),
        "llm_calls_mean": (sum(calls) / len(calls)) if calls else None,
        "structural": {
            "resolved_duplicates_max": max(
                [int(m.get("resolved_duplicates") or 0) for m in mm] or [0]
            ),
            "unexplained_disappearance_total": sum(
                int(m.get("unexplained_disappearance") or 0) for m in mm
            ),
            "ledger_final_inversion_total": sum(
                int(m.get("ledger_final_inversion") or 0) for m in mm
            ),
        },
        "means": {
            k: avg(k)
            for k in (
                "n_facts",
                "n_decisive_facts",
                "n_families",
                "n_concepts",
                "n_active_concepts",
                "p3_completeness",
                "p4_admitted_cells",
                "p5_shared_phenotype_vetoes",
                "p5_scope_error_vetoes",
                "axis_uncovered_high_specific",
                "gap_concepts",
                "frontier_n",
                "protected_n",
                "verifier_applied_cells",
            )
        },
        "gap_lane_rate": (
            sum(1 for m in mm if m.get("axis_gap_lane_used")) / len(mm) if mm else None
        ),
        "verifier_rate": (
            sum(1 for m in mm if m.get("verifier_reason")) / len(mm) if mm else None
        ),
        "errors": errors,
        "finished_at": _utc(),
    }
    _atomic_json(out_dir / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "errors"}, indent=2), flush=True)

    if args.score and preds:
        if ds_name == "medcasereasoning":
            score_mcr(out_dir, subset / "cases.parquet", workers=args.mcr_judge_workers)
        else:
            score_da(out_dir, subset, args.model)
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
