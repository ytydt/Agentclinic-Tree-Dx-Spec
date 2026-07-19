#!/usr/bin/env python3
"""Evaluate promising A variants with the frozen legacy AB downstream chain.

The production metric path is reused verbatim from
``eval_l2_branch_generation_ab._downstream_one``:
true-F2 evidence -> per-parent local annotator/champion -> joint arbiter.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

import eval_l2_branch_generation_ab as legacy
import evaluate_l2_a_variant_matrix as matrix_inputs
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "logs/l2_a_variant_legacy_ab_v1"
DEFAULT_GENERATION = ROOT / "logs/l2_a_variant_matrix_v1/generation"
DEFAULT_FINAL_AUDIT = (
    ROOT / "logs/l2_a_variant_matrix_v1/judge/final_audit.json"
)
DEFAULT_OLD_RECORDS = (
    ROOT / "logs/l2_branch_generation_ab_v1/evaluation/records.json"
)
DEFAULT_UNIFIED = (
    ROOT / "logs/l2_a_variant_matrix_v1/evaluation"
    / "arm_performance_unified_reanalysis.json"
)
CONTROL_MAP = {"C-prod": "C", "A-raw": "A"}
DEFAULT_ARMS = ("C-prod", "A-raw", "A1", "A2", "A4", "A6", "A10")
STABLE_A_ARMS = frozenset({"A-raw", "A1", "A2", "A3", "A4", "A5"})


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy._atomic_json(path, payload)


def select_candidate_arms(
    unified: Mapping[str, Any],
    *,
    threshold_arm: str = "A-raw",
) -> list[str]:
    rows = {str(row["arm"]): row for row in unified.get("rows") or ()}
    threshold = float(rows[threshold_arm]["top2_pct"])
    candidates = [
        arm for arm, row in rows.items()
        if arm.startswith("A")
        and arm != threshold_arm
        and float(row["top2_pct"]) >= threshold
    ]
    order = {arm: index for index, arm in enumerate(matrix_inputs.HEADLINE_ARMS)}
    return ["C-prod", threshold_arm, *sorted(candidates, key=order.get)]


def _trace_path(generation_dir: Path, arm: str, replicate: int, case_id: str) -> Path:
    return (
        generation_dir / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _record_path(output_dir: Path, arm: str, replicate: int, case_id: str) -> Path:
    return (
        output_dir / "evaluation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _live_l2_ids(tree: Mapping[str, Any]) -> set[str]:
    return {
        str(branch_id)
        for branch_id, branch in (tree.get("branches") or {}).items()
        if int(branch.get("level") or 0) == 2
        and str(branch.get("level_role") or "") != "partial_flow_fallback"
    }


def _acceptable_ids(
    *,
    arm: str,
    replicate: int,
    case_id: str,
    gold_index: Mapping[str, Any],
    final_audit: Mapping[str, Any],
) -> tuple[set[str], str]:
    if arm == "C-prod":
        row = gold_index["by_ab_key"].get(("C", replicate, case_id))
        return {
            str(value) for value in (row or {}).get("acceptable_l2") or ()
        }, "frozen_C_stable_ids"
    if arm in STABLE_A_ARMS:
        row = gold_index["by_ab_key"].get(("A", replicate, case_id))
        return {
            str(value) for value in (row or {}).get("acceptable_l2") or ()
        }, "frozen_A_stable_ids"
    match = final_audit["gold_match_by_occurrence"].get(
        (arm, replicate, case_id),
    )
    if not isinstance(match, Mapping):
        return set(), "tier3_proxy_semantic_gold_absent"
    return {
        str(value) for value in match.get("acceptable_branch_ids") or ()
    }, "tier3_proxy_semantic_gold"


def _quality(
    final_audit: Mapping[str, Any],
    arm: str,
    replicate: int,
    case_id: str,
) -> dict[str, Any]:
    row = final_audit["quality_by_occurrence"].get(
        (arm, replicate, case_id),
    )
    if not isinstance(row, Mapping):
        return {
            "leaf_clean_rate": None,
            "leaf_parent_invalid_rate": None,
            "semantic_duplicate_excess_rate": None,
        }
    return {
        "leaf_clean_rate": row.get("leaf_clean_rate"),
        "leaf_parent_invalid_rate": row.get("leaf_parent_invalid_rate"),
        "semantic_duplicate_excess_rate": row.get(
            "semantic_duplicate_excess_rate"
        ),
    }


def _import_controls(path: Path) -> list[dict[str, Any]]:
    source = _read(path).get("records") or ()
    output = []
    reverse = {value: key for key, value in CONTROL_MAP.items()}
    for row in source:
        arm = reverse.get(str(row.get("arm") or ""))
        if arm is None:
            continue
        output.append({
            **dict(row),
            "arm": arm,
            "evaluation_provenance": "frozen_legacy_ab_record",
        })
    return output


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    values = [
        float(row[key]) for row in rows if row.get(key) is not None
    ]
    return statistics.fmean(values) if values else None


def _aggregate(
    records: Sequence[Mapping[str, Any]],
    arms: Sequence[str],
    *,
    bootstrap: int,
) -> dict[str, Any]:
    arm_rows = {}
    for arm in arms:
        rows = [row for row in records if row["arm"] == arm]
        arm_rows[arm] = {
            "n": len(rows),
            "gold_l2_coverage": _mean(rows, "gold_l2_coverage"),
            "actual_top1": _mean(rows, "actual_top1"),
            "actual_top2": _mean(rows, "actual_top2"),
            "actual_rr": _mean(rows, "actual_rr"),
            "oracle_top2": _mean(rows, "oracle_top2"),
            "local_champion": _mean(rows, "local_champion"),
            "leaf_burden": _mean(rows, "leaf_burden"),
            "leaf_clean_rate": _mean(rows, "leaf_clean_rate"),
            "leaf_parent_invalid_rate": _mean(
                rows, "leaf_parent_invalid_rate",
            ),
            "semantic_duplicate_excess_rate": _mean(
                rows, "semantic_duplicate_excess_rate",
            ),
            "production_e2e_llm_calls": _mean(
                rows, "production_e2e_llm_calls",
            ),
        }
    comparisons = {
        arm: legacy.paired_cluster_bootstrap(
            records,
            "A-raw",
            arm,
            metrics=(
                "gold_l2_coverage", "actual_top1",
                "actual_top2", "actual_rr",
            ),
            n_boot=bootstrap,
        )
        for arm in arms if arm != "A-raw"
    }
    baseline = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in records if row["arm"] == "A-raw"
    }
    transitions = {}
    for arm in arms:
        if arm == "A-raw":
            continue
        current = {
            (str(row["case_id"]), int(row["replicate"])): row
            for row in records if row["arm"] == arm
        }
        transitions[arm] = {}
        for metric in ("gold_l2_coverage", "actual_top1", "actual_top2"):
            gain = []
            loss = []
            for key in sorted(set(baseline) & set(current)):
                before = bool(baseline[key].get(metric))
                after = bool(current[key].get(metric))
                if after and not before:
                    gain.append({"case_id": key[0], "replicate": key[1]})
                elif before and not after:
                    loss.append({"case_id": key[0], "replicate": key[1]})
            transitions[arm][metric] = {
                "gain_count": len(gain),
                "loss_count": len(loss),
                "net": len(gain) - len(loss),
                "gains": gain,
                "losses": loss,
            }
    return {
        "arms": arm_rows,
        "comparisons_vs_a_raw": comparisons,
        "transitions_vs_a_raw": transitions,
    }


def _write_summary_tsv(
    path: Path,
    metrics: Mapping[str, Any],
    arms: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "arm", "n", "coverage_pct", "top1_pct", "top2_pct", "mrr_pct",
        "oracle_top2_pct", "local_champion_pct", "leaf_burden",
        "clean_pct", "parent_invalid_pct", "duplicate_excess_pct",
        "delta_top1_pp", "delta_top2_pp", "top2_ci95_low_pp",
        "top2_ci95_high_pp", "top2_gain_count", "top2_loss_count",
        "production_calls_per_cell",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for arm in arms:
            row = metrics["arms"][arm]
            comparison = metrics["comparisons_vs_a_raw"].get(arm) or {}
            top2_comparison = comparison.get("actual_top2") or {}
            top2_ci = top2_comparison.get("ci95") or (None, None)
            transition = (
                metrics["transitions_vs_a_raw"].get(arm, {})
                .get("actual_top2", {})
            )
            writer.writerow({
                "arm": arm,
                "n": row["n"],
                "coverage_pct": round(100 * row["gold_l2_coverage"], 1),
                "top1_pct": round(100 * row["actual_top1"], 1),
                "top2_pct": round(100 * row["actual_top2"], 1),
                "mrr_pct": round(100 * row["actual_rr"], 1),
                "oracle_top2_pct": round(100 * row["oracle_top2"], 1),
                "local_champion_pct": round(
                    100 * row["local_champion"], 1,
                ),
                "leaf_burden": round(row["leaf_burden"], 3),
                "clean_pct": (
                    round(100 * row["leaf_clean_rate"], 1)
                    if row["leaf_clean_rate"] is not None else None
                ),
                "parent_invalid_pct": (
                    round(100 * row["leaf_parent_invalid_rate"], 1)
                    if row["leaf_parent_invalid_rate"] is not None else None
                ),
                "duplicate_excess_pct": (
                    round(100 * row["semantic_duplicate_excess_rate"], 1)
                    if row["semantic_duplicate_excess_rate"] is not None
                    else None
                ),
                "delta_top1_pp": round(
                    100 * (
                        comparison.get("actual_top1", {}).get("delta") or 0
                    ),
                    1,
                ),
                "delta_top2_pp": round(
                    100 * (top2_comparison.get("delta") or 0), 1,
                ),
                "top2_ci95_low_pp": (
                    round(100 * top2_ci[0], 1)
                    if top2_ci[0] is not None else None
                ),
                "top2_ci95_high_pp": (
                    round(100 * top2_ci[1], 1)
                    if top2_ci[1] is not None else None
                ),
                "top2_gain_count": transition.get("gain_count"),
                "top2_loss_count": transition.get("loss_count"),
                "production_calls_per_cell": round(
                    row["production_e2e_llm_calls"], 3,
                ),
            })


def _evaluation_contract(
    args: argparse.Namespace,
    *,
    final_audit: Mapping[str, Any],
    gold_index: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "chain": "true_f2_local_joint",
        "model": args.model,
        "temperature": args.temperature,
        "legacy_code_hashes": legacy._code_hashes(),
        "prompt_hashes": legacy._prompt_hashes(),
        "final_audit_hash": final_audit["payload"]["fixture_hash"],
        "gold_fixture_hash": stable_hash(gold_index["payload"]),
        "finding_fixture_hash": legacy._sha256(args.finding_fixture),
        "control_records_hash": legacy._sha256(args.old_records),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    generation_manifest = _read(args.generation_dir / "manifest.json")
    unified = _read(args.unified_performance)
    selected = (
        select_candidate_arms(unified)
        if args.arms == "auto"
        else [value.strip() for value in args.arms.split(",") if value.strip()]
    )
    if tuple(selected) != tuple(DEFAULT_ARMS) and args.arms == "auto":
        raise ValueError(
            f"candidate set drift: expected {DEFAULT_ARMS}, got {selected}"
        )
    unsupported = set(selected) - set(generation_manifest["arms"])
    if unsupported:
        raise ValueError(f"generation traces unavailable: {sorted(unsupported)}")
    final_audit = matrix_inputs.load_final_audit(args.final_audit)
    if not final_audit.get("available"):
        raise ValueError(f"final audit unavailable: {final_audit['blockers']}")
    gold_index = matrix_inputs.load_gold_index(args.gold_fixture)
    evaluation_contract = _evaluation_contract(
        args,
        final_audit=final_audit,
        gold_index=gold_index,
    )
    evaluation_contract_hash = stable_hash(evaluation_contract)
    finding_doc, finding_cases = legacy.competition._fixture_cases(
        args.finding_fixture
    )
    runtime_cases = {
        str(case["id"]): case for case in legacy._runtime_cases(args)
    }
    frozen_l1, full_l1 = legacy._load_l1_inputs(args)
    case_ids = [
        case_id for case_id in generation_manifest["case_ids"]
        if case_id in runtime_cases
    ]
    tasks = [
        (arm, replicate, case_id)
        for arm in selected if arm not in CONTROL_MAP
        for replicate in range(1, int(generation_manifest["replicates"]) + 1)
        for case_id in case_ids
    ]

    def evaluate_one(task: tuple[str, int, str]) -> dict[str, Any]:
        arm, replicate, case_id = task
        output_path = _record_path(
            args.output_dir, arm, replicate, case_id,
        )
        trace = _read(
            _trace_path(args.generation_dir, arm, replicate, case_id),
        )
        if args.resume and output_path.is_file():
            existing = _read(output_path)
            if (
                existing.get("source_tree_hash") == trace.get("tree_hash")
                and existing.get("legacy_chain") == "true_f2_local_joint"
                and existing.get("evaluation_contract_hash")
                == evaluation_contract_hash
            ):
                return dict(existing)
        if stable_hash(trace.get("tree") or {}) != trace.get("tree_hash"):
            raise ValueError(f"{arm}/{case_id}/r{replicate}: tree hash drift")
        acceptable, gold_provenance = _acceptable_ids(
            arm=arm,
            replicate=replicate,
            case_id=case_id,
            gold_index=gold_index,
            final_audit=final_audit,
        )
        live_ids = _live_l2_ids(trace["tree"])
        live_acceptable = acceptable & live_ids
        adjudication = {"acceptable_l2": sorted(live_acceptable)}
        downstream = legacy._downstream_one(
            args=args,
            trace=trace,
            adjudication=adjudication,
            case=runtime_cases[case_id],
            finding_asset=finding_cases[case_id],
            frozen_l1=frozen_l1[(replicate, case_id)],
            full_l1=full_l1[(replicate, case_id)],
        )
        l1_count = sum(
            int(branch.get("level") or 0) == 1
            for branch in (trace["tree"].get("branches") or {}).values()
        )
        record = {
            "arm": arm,
            "replicate": replicate,
            "case_id": case_id,
            "tree_hash": trace["tree_hash"],
            "source_tree_hash": trace["tree_hash"],
            "legacy_chain": "true_f2_local_joint",
            "evaluation_contract_hash": evaluation_contract_hash,
            "gold_provenance": gold_provenance,
            "acceptable_l2": sorted(acceptable),
            "live_acceptable_l2": sorted(live_acceptable),
            "gold_l2_coverage": bool(live_acceptable),
            "actual_top1": downstream["actual"]["top1"],
            "actual_top2": downstream["actual"]["top2"],
            "actual_rr": downstream["actual"]["rr"],
            "oracle_top1": downstream["oracle"]["top1"],
            "oracle_top2": downstream["oracle"]["top2"],
            "oracle_rr": downstream["oracle"]["rr"],
            "l1_route": downstream["l1_route"],
            "l1_route_top2": downstream["l1_route_top2"],
            "local_top1": downstream["local_top1"],
            "local_champion": downstream["local_champion"],
            "l2_count": len(live_ids),
            "leaf_burden": len(live_ids) / l1_count if l1_count else None,
            "downstream_calls": downstream.get("calls") or {},
            "oracle_capability_llm_calls": int(
                (downstream.get("oracle_calls") or {}).get("requested") or 0
            ),
            "production_e2e_llm_calls": int(
                (downstream.get("production_calls") or {}).get("requested")
                or 0
            ),
            **_quality(final_audit, arm, replicate, case_id),
        }
        _write(output_path, record)
        return record

    if args.workers == 1:
        generated_records = [evaluate_one(task) for task in tasks]
    else:
        generated_records = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(evaluate_one, task) for task in tasks]
            for future in as_completed(futures):
                generated_records.append(future.result())
        generated_records.sort(
            key=lambda row: (
                str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
            )
        )
    controls = _import_controls(args.old_records)
    controls = [
        row for row in controls
        if row["arm"] in selected and row["case_id"] in case_ids
    ]
    # Attach current Tier-3 quality without changing frozen legacy performance.
    for row in controls:
        row.update(_quality(
            final_audit,
            row["arm"],
            int(row["replicate"]),
            str(row["case_id"]),
        ))
    records = sorted(
        [*controls, *generated_records],
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ),
    )
    expected = len(selected) * len(case_ids) * int(
        generation_manifest["replicates"]
    )
    if len(records) != expected:
        raise ValueError(f"record count mismatch: {len(records)} != {expected}")
    metrics = _aggregate(records, selected, bootstrap=args.bootstrap)
    summary = {
        "asset_kind": "l2_a_variant_legacy_ab_evaluation",
        "schema_version": 1,
        "analysis_status": "research_only",
        "legacy_chain": (
            "true-F2 evidence -> per-parent local annotator/champion "
            "-> joint arbiter"
        ),
        "selection_rule": "unified same-harness Top-2 >= A-raw point estimate",
        "selected_arms": selected,
        "generation_manifest_hash": generation_manifest["manifest_hash"],
        "evaluation_contract": evaluation_contract,
        "evaluation_contract_hash": evaluation_contract_hash,
        "final_audit_hash": final_audit["payload"]["fixture_hash"],
        "final_audit_human_signed_off": bool(
            final_audit["payload"].get("human_signed_off")
        ),
        "finding_fixture_hash": stable_hash(finding_doc),
        "record_count": len(records),
        "metrics": metrics,
        "call_accounting": {
            "production_requested_variants": sum(
                int(row.get("production_e2e_llm_calls") or 0)
                for row in generated_records
            ),
            "oracle_requested_variants": sum(
                int(row.get("oracle_capability_llm_calls") or 0)
                for row in generated_records
            ),
        },
    }
    evaluation_dir = args.output_dir / "evaluation"
    _write(evaluation_dir / "records.json", {
        "asset_kind": "l2_a_variant_legacy_ab_records",
        "schema_version": 1,
        "records": records,
    })
    _write(evaluation_dir / "summary.json", summary)
    _write_summary_tsv(
        evaluation_dir / "summary.tsv", metrics, selected,
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--generation-dir", type=Path, default=DEFAULT_GENERATION)
    parser.add_argument("--final-audit", type=Path, default=DEFAULT_FINAL_AUDIT)
    parser.add_argument("--old-records", type=Path, default=DEFAULT_OLD_RECORDS)
    parser.add_argument("--unified-performance", type=Path, default=DEFAULT_UNIFIED)
    parser.add_argument("--gold-fixture", type=Path, default=legacy.DEFAULT_ADJUDICATION)
    parser.add_argument("--finding-fixture", type=Path, default=legacy.DEFAULT_FINDING_FIXTURE)
    parser.add_argument("--base-output-dir", type=Path, default=legacy.DEFAULT_BASE_OUTPUT)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--arms", default="auto")
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.bootstrap < 1:
        parser.error("--workers and --bootstrap must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run(args)
    print(json.dumps({
        "selected_arms": summary["selected_arms"],
        "record_count": summary["record_count"],
        "output": str(args.output_dir / "evaluation/summary.json"),
        "analysis_status": summary["analysis_status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
