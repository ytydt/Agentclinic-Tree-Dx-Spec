#!/usr/bin/env python3
"""Evaluate A4+A14 and A4+A17 under unified and legacy-rich endpoints."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

import eval_l2_a_variant_legacy_ab as legacy_variants
import eval_l2_branch_generation_ab as legacy
import evaluate_l2_a_variant_matrix as matrix
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash


ROOT = Path(__file__).resolve().parents[1]
COMBOS = {
    "A4+A14": {"terminal_arm": "A14", "prior_temperature": 1.0},
    "A4+A17": {"terminal_arm": "A17", "prior_temperature": 2.0},
}
ARMS = ("A-raw", "A4", "A4+A14", "A4+A17")
DEFAULT_OUTPUT = ROOT / "logs/l2_a4_downstream_combinations_v1"
DEFAULT_GENERATION = ROOT / "logs/l2_a_variant_matrix_v1/generation"
DEFAULT_DOWNSTREAM = ROOT / "logs/l2_a_variant_matrix_v1/downstream_full"
DEFAULT_MATRIX_RECORDS = (
    ROOT / "logs/l2_a_variant_matrix_v1"
    / "evaluation_tier3_proxy/evaluation/records.json"
)
DEFAULT_LEGACY_RECORDS = (
    ROOT / "logs/l2_a_variant_legacy_ab_v1/evaluation/records.json"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy._atomic_json(path, payload)


def _unwrap_downstream(path: Path) -> Mapping[str, Any]:
    payload = _read(path)
    record = payload.get("record") if isinstance(payload, Mapping) else None
    return record if isinstance(record, Mapping) else payload


def _generation_trace(
    generation_dir: Path, replicate: int, case_id: str, source_arm: str = "A4",
) -> Mapping[str, Any]:
    return _read(
        generation_dir / "traces" / source_arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _downstream_trace(
    downstream_dir: Path, replicate: int, case_id: str, source_arm: str = "A4",
) -> Mapping[str, Any]:
    return _unwrap_downstream(
        downstream_dir / "traces" / source_arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _acceptable_ids(
    gold_index: Mapping[str, Any], replicate: int, case_id: str,
) -> set[str]:
    row = (gold_index.get("by_ab_key") or {}).get(("A", replicate, case_id))
    return {str(value) for value in (row or {}).get("acceptable_l2") or ()}


def _live_l2_ids(tree: Mapping[str, Any]) -> set[str]:
    return {
        str(branch_id)
        for branch_id, branch in (tree.get("branches") or {}).items()
        if int(branch.get("level") or 0) == 2
        and str(branch.get("level_role") or "") != "partial_flow_fallback"
    }


def _normalise_control(
    row: Mapping[str, Any], *, endpoint: str,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "arm": str(row["arm"]),
        "case_id": str(row["case_id"]),
        "replicate": int(row["replicate"]),
        "gold_l2_coverage": bool(row.get("gold_l2_coverage")),
        "actual_top1": bool(row.get("actual_top1")),
        "actual_top2": bool(row.get("actual_top2")),
        "actual_rr": float(
            row.get("actual_rr")
            if row.get("actual_rr") is not None
            else row.get("mrr_at_2") or 0.0
        ),
        "oracle_top2": bool(
            row.get("oracle_top2")
            if row.get("oracle_top2") is not None
            else row.get("oracle_parent_f4_local_top2")
        ),
        "local_champion": (
            bool(row.get("local_champion"))
            if row.get("local_champion") is not None else None
        ),
        "leaf_burden": row.get("leaf_burden"),
        "leaf_clean_rate": row.get("leaf_clean_rate"),
        "leaf_parent_invalid_rate": row.get("leaf_parent_invalid_rate"),
        "semantic_duplicate_excess_rate": row.get(
            "semantic_duplicate_excess_rate"
        ),
        "production_e2e_llm_calls": row.get("production_e2e_llm_calls"),
        "gold_rank": row.get("gold_rank"),
        "ranking": list(row.get("ranking") or ()),
    }


def build_unified_records(
    *,
    matrix_records: Mapping[str, Any],
    generation_dir: Path,
    downstream_dir: Path,
    gold_index: Mapping[str, Any],
) -> list[dict[str, Any]]:
    controls = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in matrix_records.get("records") or ()
        if str(row.get("arm")) in {"A-raw", "A4"}
    }
    output = []
    for source_arm in ("A-raw", "A4"):
        for arm, replicate, case_id in sorted(controls):
            if arm != source_arm:
                continue
            generation = _generation_trace(
                generation_dir, replicate, case_id, source_arm,
            )
            downstream = _downstream_trace(
                downstream_dir, replicate, case_id, source_arm,
            )
            acceptable = _acceptable_ids(gold_index, replicate, case_id)
            live_ids = _live_l2_ids(generation["tree"])
            baseline = downstream.get("baseline") or {}
            ranking = matrix.extract_ranking(baseline, source_arm)
            metrics = matrix.score_ranking(
                ranking, acceptable, gold_absent=False, l2_ids=live_ids,
            )
            champion_ids = {
                str(value) for value in baseline.get("champion") or ()
            }
            quality = controls[(source_arm, replicate, case_id)]
            output.append({
                "endpoint": "unified_direct",
                "arm": source_arm,
                "case_id": case_id,
                "replicate": replicate,
                "gold_l2_coverage": metrics["gold_l2_coverage"],
                "actual_top1": metrics["actual_top1"],
                "actual_top2": metrics["actual_top2"],
                "actual_rr": metrics["mrr_at_2"],
                "oracle_top2": matrix.oracle_parent_f4_top2(
                    downstream, acceptable,
                ),
                "local_champion": bool(acceptable & champion_ids),
                "leaf_burden": quality.get("leaf_burden"),
                "leaf_clean_rate": quality.get("leaf_clean_rate"),
                "leaf_parent_invalid_rate": quality.get(
                    "leaf_parent_invalid_rate"
                ),
                "semantic_duplicate_excess_rate": quality.get(
                    "semantic_duplicate_excess_rate"
                ),
                "production_e2e_llm_calls": None,
                "gold_rank": metrics["gold_rank"],
                "ranking": ranking,
                "source_tree_arm": source_arm,
                "terminal_arm": "baseline",
                "parent_prior_temperature": 1.0,
            })
    a4_keys = sorted(
        (replicate, case_id)
        for arm, replicate, case_id in controls
        if arm == "A4"
    )
    for replicate, case_id in a4_keys:
        generation = _generation_trace(generation_dir, replicate, case_id)
        downstream = _downstream_trace(downstream_dir, replicate, case_id)
        acceptable = _acceptable_ids(gold_index, replicate, case_id)
        live_ids = _live_l2_ids(generation["tree"])
        quality = controls[("A4", replicate, case_id)]
        oracle_top2 = matrix.oracle_parent_f4_top2(downstream, acceptable)
        for combo, spec in COMBOS.items():
            terminal_arm = str(spec["terminal_arm"])
            arm_payload = (downstream.get("arms") or {}).get(terminal_arm) or {}
            ranking = matrix.extract_ranking(arm_payload, terminal_arm)
            metrics = matrix.score_ranking(
                ranking, acceptable, gold_absent=False, l2_ids=live_ids,
            )
            champion_ids = {
                str(value) for value in arm_payload.get("champion") or ()
            }
            output.append({
                "endpoint": "unified_direct",
                "arm": combo,
                "case_id": case_id,
                "replicate": replicate,
                "gold_l2_coverage": metrics["gold_l2_coverage"],
                "actual_top1": metrics["actual_top1"],
                "actual_top2": metrics["actual_top2"],
                "actual_rr": metrics["mrr_at_2"],
                "oracle_top2": oracle_top2,
                "local_champion": bool(acceptable & champion_ids),
                "leaf_burden": quality.get("leaf_burden"),
                "leaf_clean_rate": quality.get("leaf_clean_rate"),
                "leaf_parent_invalid_rate": quality.get(
                    "leaf_parent_invalid_rate"
                ),
                "semantic_duplicate_excess_rate": quality.get(
                    "semantic_duplicate_excess_rate"
                ),
                "production_e2e_llm_calls": None,
                "gold_rank": metrics["gold_rank"],
                "ranking": ranking,
                "source_tree_arm": "A4",
                "terminal_arm": terminal_arm,
                "parent_prior_temperature": spec["prior_temperature"],
            })
    return sorted(
        output,
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ),
    )


def _legacy_contract(
    args: argparse.Namespace,
    *,
    generation_manifest: Mapping[str, Any],
    gold_index: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "chain": (
            "A4 tree -> dynamic F4 local ordinal annotator -> "
            "one champion per active parent -> legacy rich joint arbiter"
        ),
        "a17_parent_prior_temperature": 2.0,
        "model": args.model,
        "temperature": args.temperature,
        "combination_harness_hash": legacy._sha256(Path(__file__)),
        "legacy_code_hashes": legacy._code_hashes(),
        "prompt_hashes": legacy._prompt_hashes(),
        "generation_manifest_hash": generation_manifest["manifest_hash"],
        "gold_fixture_hash": stable_hash(gold_index["payload"]),
        "finding_fixture_hash": legacy._sha256(args.finding_fixture),
        "legacy_control_records_hash": legacy._sha256(args.legacy_records),
    }


def build_legacy_records(
    args: argparse.Namespace,
    *,
    gold_index: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    generation_manifest = _read(args.generation_dir / "manifest.json")
    contract = _legacy_contract(
        args, generation_manifest=generation_manifest, gold_index=gold_index,
    )
    contract_hash = stable_hash(contract)
    source_records = _read(args.legacy_records).get("records") or ()
    controls = [
        _normalise_control(row, endpoint="legacy_rich_joint")
        for row in source_records
        if str(row.get("arm")) in {"A-raw", "A4"}
    ]
    control_by_key = {
        (str(row["arm"]), int(row["replicate"]), str(row["case_id"])): row
        for row in controls
    }
    finding_doc, finding_cases = legacy.competition._fixture_cases(
        args.finding_fixture
    )
    runtime_cases = {
        str(case["id"]): case for case in legacy._runtime_cases(args)
    }
    frozen_l1, full_l1 = legacy._load_l1_inputs(args)
    case_ids = [
        str(case_id) for case_id in generation_manifest["case_ids"]
        if str(case_id) in runtime_cases
    ]
    replicates = range(1, int(generation_manifest["replicates"]) + 1)

    def evaluate_cell(replicate: int, case_id: str) -> list[dict[str, Any]]:
        generation = _generation_trace(args.generation_dir, replicate, case_id)
        if stable_hash(generation.get("tree") or {}) != generation.get("tree_hash"):
            raise ValueError(f"A4/{case_id}/r{replicate}: tree hash drift")
        acceptable = _acceptable_ids(gold_index, replicate, case_id)
        live_ids = _live_l2_ids(generation["tree"])
        live_acceptable = acceptable & live_ids
        adjudication = {"acceptable_l2": sorted(live_acceptable)}
        quality = control_by_key[("A4", replicate, case_id)]
        rows = []
        for index, (combo, spec) in enumerate(COMBOS.items()):
            output_path = (
                args.output_dir / "legacy_traces" / combo
                / f"r{replicate:02d}__{case_id}.json"
            )
            if args.resume and output_path.is_file():
                existing = _read(output_path)
                if (
                    existing.get("evaluation_contract_hash") == contract_hash
                    and existing.get("source_tree_hash")
                    == generation.get("tree_hash")
                ):
                    rows.append(dict(existing))
                    continue
            call_args = SimpleNamespace(**vars(args))
            # A17 must reuse A14's exact dynamic selectors/local annotations.
            call_args.resume = bool(args.resume or index > 0)
            call_args.output_dir = (
                args.output_dir / "runtime" / contract_hash
            )
            downstream = legacy._downstream_one(
                args=call_args,
                trace=generation,
                adjudication=adjudication,
                case=runtime_cases[case_id],
                finding_asset=finding_cases[case_id],
                frozen_l1=frozen_l1[(replicate, case_id)],
                full_l1=full_l1[(replicate, case_id)],
                local_mode="dynamic",
                parent_prior_temperature=float(spec["prior_temperature"]),
            )
            row = {
                "endpoint": "legacy_rich_joint",
                "arm": combo,
                "case_id": case_id,
                "replicate": replicate,
                "source_tree_arm": "A4",
                "source_tree_hash": generation["tree_hash"],
                "terminal_arm": spec["terminal_arm"],
                "evaluation_contract_hash": contract_hash,
                "gold_l2_coverage": bool(live_acceptable),
                "actual_top1": downstream["actual"]["top1"],
                "actual_top2": downstream["actual"]["top2"],
                "actual_rr": downstream["actual"]["rr"],
                "gold_rank": downstream["actual"]["rank"],
                "oracle_top2": downstream["oracle"]["top2"],
                "local_champion": downstream["local_champion"],
                "local_champion_ids": downstream["local_champion_ids"],
                "local_mode": downstream["local_mode"],
                "parent_prior_temperature": downstream[
                    "parent_prior_temperature"
                ],
                "leaf_burden": quality.get("leaf_burden"),
                "leaf_clean_rate": quality.get("leaf_clean_rate"),
                "leaf_parent_invalid_rate": quality.get(
                    "leaf_parent_invalid_rate"
                ),
                "semantic_duplicate_excess_rate": quality.get(
                    "semantic_duplicate_excess_rate"
                ),
                "production_e2e_llm_calls": int(
                    (downstream.get("production_calls") or {}).get("requested")
                    or 0
                ),
                "production_e2e_model_calls": int(
                    (downstream.get("production_calls") or {}).get("model")
                    or 0
                ),
                "oracle_capability_llm_calls": int(
                    (downstream.get("oracle_calls") or {}).get("requested")
                    or 0
                ),
            }
            _write(output_path, row)
            rows.append(row)
        if len(rows) == 2:
            left, right = rows
            if left.get("local_champion_ids") != right.get("local_champion_ids"):
                raise ValueError(
                    f"{case_id}/r{replicate}: A14/A17 local champions drift"
                )
        return rows

    tasks = [
        (replicate, case_id)
        for replicate in replicates for case_id in case_ids
    ]
    generated = []
    if args.workers == 1:
        for task in tasks:
            generated.extend(evaluate_cell(*task))
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(evaluate_cell, *task) for task in tasks]
            for future in as_completed(futures):
                generated.extend(future.result())
    selected_controls = [
        row for row in controls if str(row["case_id"]) in set(case_ids)
    ]
    records = sorted(
        [*selected_controls, *generated],
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ),
    )
    expected = len(ARMS) * len(case_ids) * len(list(replicates))
    if len(records) != expected:
        raise ValueError(f"legacy record count mismatch: {len(records)} != {expected}")
    return records, {
        "evaluation_contract": contract,
        "evaluation_contract_hash": contract_hash,
        "finding_fixture_hash": stable_hash(finding_doc),
    }


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = [
        float(row[key]) for row in rows if row.get(key) is not None
    ]
    return statistics.fmean(values) if values else None


def _transitions(
    records: Sequence[Mapping[str, Any]], baseline_arm: str, arm: str,
) -> dict[str, Any]:
    baseline = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in records if row["arm"] == baseline_arm
    }
    current = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in records if row["arm"] == arm
    }
    output = {}
    for metric in ("gold_l2_coverage", "actual_top1", "actual_top2"):
        gains, losses = [], []
        for key in sorted(set(baseline) & set(current)):
            before = bool(baseline[key].get(metric))
            after = bool(current[key].get(metric))
            item = {"case_id": key[0], "replicate": key[1]}
            if after and not before:
                gains.append(item)
            elif before and not after:
                losses.append(item)
        output[metric] = {
            "gain_count": len(gains),
            "loss_count": len(losses),
            "net": len(gains) - len(losses),
            "gains": gains,
            "losses": losses,
        }
    return output


def aggregate(
    records: Sequence[Mapping[str, Any]], *, bootstrap: int,
) -> dict[str, Any]:
    arm_metrics = {}
    for arm in ARMS:
        rows = [row for row in records if row["arm"] == arm]
        arm_metrics[arm] = {
            "n": len(rows),
            "coverage": _mean(rows, "gold_l2_coverage"),
            "top1": _mean(rows, "actual_top1"),
            "top2": _mean(rows, "actual_top2"),
            "mrr": _mean(rows, "actual_rr"),
            "oracle_top2": _mean(rows, "oracle_top2"),
            "local_champion": _mean(rows, "local_champion"),
            "leaf_burden": _mean(rows, "leaf_burden"),
        }
    comparisons = {}
    transitions = {}
    for baseline in ("A-raw", "A4"):
        comparisons[baseline] = {
            arm: legacy.paired_cluster_bootstrap(
                records, baseline, arm,
                metrics=(
                    "gold_l2_coverage", "actual_top1",
                    "actual_top2", "actual_rr",
                ),
                n_boot=bootstrap,
            )
            for arm in ARMS if arm != baseline
        }
        transitions[baseline] = {
            arm: _transitions(records, baseline, arm)
            for arm in ARMS if arm != baseline
        }
    return {
        "arms": arm_metrics,
        "comparisons": comparisons,
        "transitions": transitions,
    }


def _write_tsv(path: Path, summaries: Mapping[str, Any]) -> None:
    fields = [
        "endpoint", "arm", "n", "coverage_pct", "top1_pct", "top2_pct",
        "mrr_pct", "oracle_top2_pct", "local_champion_pct",
        "delta_top2_vs_a_raw_pp", "ci95_vs_a_raw_low_pp",
        "ci95_vs_a_raw_high_pp", "delta_top2_vs_a4_pp",
        "ci95_vs_a4_low_pp", "ci95_vs_a4_high_pp",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for endpoint, summary in summaries.items():
            for arm in ARMS:
                metrics = summary["arms"][arm]
                vs_raw = (
                    summary["comparisons"]["A-raw"].get(arm, {})
                    .get("actual_top2", {})
                )
                vs_a4 = (
                    summary["comparisons"]["A4"].get(arm, {})
                    .get("actual_top2", {})
                )
                raw_ci = vs_raw.get("ci95") or (None, None)
                a4_ci = vs_a4.get("ci95") or (None, None)
                pct = lambda value: (
                    round(100 * value, 1) if value is not None else None
                )
                writer.writerow({
                    "endpoint": endpoint,
                    "arm": arm,
                    "n": metrics["n"],
                    "coverage_pct": pct(metrics["coverage"]),
                    "top1_pct": pct(metrics["top1"]),
                    "top2_pct": pct(metrics["top2"]),
                    "mrr_pct": pct(metrics["mrr"]),
                    "oracle_top2_pct": pct(metrics["oracle_top2"]),
                    "local_champion_pct": pct(metrics["local_champion"]),
                    "delta_top2_vs_a_raw_pp": pct(vs_raw.get("delta")),
                    "ci95_vs_a_raw_low_pp": pct(raw_ci[0]),
                    "ci95_vs_a_raw_high_pp": pct(raw_ci[1]),
                    "delta_top2_vs_a4_pp": pct(vs_a4.get("delta")),
                    "ci95_vs_a4_low_pp": pct(a4_ci[0]),
                    "ci95_vs_a4_high_pp": pct(a4_ci[1]),
                })


def run(args: argparse.Namespace) -> dict[str, Any]:
    gold_index = matrix.load_gold_index(args.gold_fixture)
    unified_records = build_unified_records(
        matrix_records=_read(args.matrix_records),
        generation_dir=args.generation_dir,
        downstream_dir=args.downstream_dir,
        gold_index=gold_index,
    )
    legacy_records, legacy_meta = build_legacy_records(
        args, gold_index=gold_index,
    )
    expected = len(ARMS) * 51
    if len(unified_records) != expected:
        raise ValueError(
            f"unified record count mismatch: {len(unified_records)} != {expected}"
        )
    summaries = {
        "unified_direct": aggregate(
            unified_records, bootstrap=args.bootstrap,
        ),
        "legacy_rich_joint": aggregate(
            legacy_records, bootstrap=args.bootstrap,
        ),
    }
    payload = {
        "asset_kind": "l2_a4_downstream_combination_evaluation",
        "schema_version": 1,
        "analysis_status": "research_only",
        "arms": list(ARMS),
        "combination_contract": {
            "A4+A14": (
                "A4 tree + dynamic F4 local ranking + one champion per parent"
            ),
            "A4+A17": (
                "A4+A14 + parent-prior temperature 2.0; local champions fixed"
            ),
        },
        "record_counts": {
            "unified_direct": len(unified_records),
            "legacy_rich_joint": len(legacy_records),
        },
        "summaries": summaries,
        "legacy_meta": legacy_meta,
    }
    _write(args.output_dir / "evaluation/summary.json", payload)
    _write(args.output_dir / "evaluation/records.json", {
        "asset_kind": "l2_a4_downstream_combination_records",
        "schema_version": 1,
        "records": [*unified_records, *legacy_records],
    })
    _write_tsv(args.output_dir / "evaluation/summary.tsv", summaries)
    return payload


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--generation-dir", type=Path, default=DEFAULT_GENERATION)
    parser.add_argument("--downstream-dir", type=Path, default=DEFAULT_DOWNSTREAM)
    parser.add_argument("--matrix-records", type=Path, default=DEFAULT_MATRIX_RECORDS)
    parser.add_argument("--legacy-records", type=Path, default=DEFAULT_LEGACY_RECORDS)
    parser.add_argument("--gold-fixture", type=Path, default=legacy.DEFAULT_ADJUDICATION)
    parser.add_argument("--finding-fixture", type=Path, default=legacy.DEFAULT_FINDING_FIXTURE)
    parser.add_argument("--base-output-dir", type=Path, default=legacy.DEFAULT_BASE_OUTPUT)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.bootstrap < 1:
        parser.error("--workers and --bootstrap must be positive")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload = run(args)
    print(json.dumps({
        "output": str(args.output_dir / "evaluation/summary.json"),
        "record_counts": payload["record_counts"],
        "analysis_status": payload["analysis_status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
