#!/usr/bin/env python3
"""Backtest promising A14/A15/A17 arms on the legacy rich-joint endpoint."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

import eval_l2_a4_downstream_combinations as combo_utils
import eval_l2_branch_generation_ab as legacy
import evaluate_l2_a_variant_matrix as matrix
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash


ROOT = Path(__file__).resolve().parents[1]
ARM_SPECS = {
    "A14": {"champions_per_parent": 1, "prior_temperature": 1.0},
    "A15": {"champions_per_parent": 2, "prior_temperature": 1.0},
    "A17": {"champions_per_parent": 1, "prior_temperature": 2.0},
}
ARMS = ("A-raw", "A14", "A15", "A17")
DEFAULT_OUTPUT = ROOT / "logs/l2_promising_downstream_legacy_v1"
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


def _acceptable(
    gold_index: Mapping[str, Any], replicate: int, case_id: str,
) -> set[str]:
    row = (gold_index.get("by_ab_key") or {}).get(("A", replicate, case_id))
    return {str(value) for value in (row or {}).get("acceptable_l2") or ()}


def _unified_records(
    args: argparse.Namespace,
    *,
    gold_index: Mapping[str, Any],
) -> list[dict[str, Any]]:
    matrix_rows = _read(args.matrix_records).get("records") or ()
    quality = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in matrix_rows if str(row.get("arm")) == "A-raw"
    }
    output = []
    for replicate, case_id in sorted(quality):
        generation = combo_utils._generation_trace(
            args.generation_dir, replicate, case_id, "A-raw",
        )
        downstream = combo_utils._downstream_trace(
            args.downstream_dir, replicate, case_id, "A-raw",
        )
        acceptable = _acceptable(gold_index, replicate, case_id)
        live_ids = combo_utils._live_l2_ids(generation["tree"])
        oracle_top2 = matrix.oracle_parent_f4_top2(downstream, acceptable)
        payloads = {
            "A-raw": downstream.get("baseline") or {},
            **{
                arm: (downstream.get("arms") or {}).get(arm) or {}
                for arm in ARM_SPECS
            },
        }
        for arm, payload in payloads.items():
            ranking = matrix.extract_ranking(payload, arm)
            metrics = matrix.score_ranking(
                ranking, acceptable, gold_absent=False, l2_ids=live_ids,
            )
            champions = {
                str(value) for value in payload.get("champion") or ()
            }
            row = quality[(replicate, case_id)]
            output.append({
                "endpoint": "unified_direct",
                "arm": arm,
                "case_id": case_id,
                "replicate": replicate,
                "gold_l2_coverage": metrics["gold_l2_coverage"],
                "actual_top1": metrics["actual_top1"],
                "actual_top2": metrics["actual_top2"],
                "actual_rr": metrics["mrr_at_2"],
                "gold_rank": metrics["gold_rank"],
                "oracle_top2": oracle_top2,
                "local_champion": bool(acceptable & champions),
                "local_champion_ids": sorted(champions),
                "leaf_burden": row.get("leaf_burden"),
                "ranking": ranking,
            })
    return sorted(
        output,
        key=lambda row: (
            str(row["arm"]), int(row["replicate"]), str(row["case_id"]),
        ),
    )


def _contract(
    args: argparse.Namespace,
    *,
    generation_manifest: Mapping[str, Any],
    gold_index: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "chain": (
            "A-raw tree -> dynamic F4 local ordinal -> one/two champions "
            "-> legacy rich joint arbiter"
        ),
        "arm_specs": ARM_SPECS,
        "model": args.model,
        "temperature": args.temperature,
        "harness_hash": legacy._sha256(Path(__file__)),
        "legacy_code_hashes": legacy._code_hashes(),
        "prompt_hashes": legacy._prompt_hashes(),
        "generation_manifest_hash": generation_manifest["manifest_hash"],
        "gold_fixture_hash": stable_hash(gold_index["payload"]),
        "finding_fixture_hash": legacy._sha256(args.finding_fixture),
        "legacy_control_records_hash": legacy._sha256(args.legacy_records),
    }


def _legacy_records(
    args: argparse.Namespace,
    *,
    gold_index: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = _read(args.generation_dir / "manifest.json")
    contract = _contract(
        args, generation_manifest=manifest, gold_index=gold_index,
    )
    contract_hash = stable_hash(contract)
    controls = [
        combo_utils._normalise_control(row, endpoint="legacy_rich_joint")
        for row in (_read(args.legacy_records).get("records") or ())
        if str(row.get("arm")) == "A-raw"
    ]
    control_quality = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in controls
    }
    _, finding_cases = legacy.competition._fixture_cases(args.finding_fixture)
    runtime_cases = {
        str(row["id"]): row for row in legacy._runtime_cases(args)
    }
    frozen_l1, full_l1 = legacy._load_l1_inputs(args)
    case_ids = [
        str(value) for value in manifest["case_ids"]
        if str(value) in runtime_cases
    ]
    replicates = range(1, int(manifest["replicates"]) + 1)

    def evaluate_cell(replicate: int, case_id: str) -> list[dict[str, Any]]:
        generation = combo_utils._generation_trace(
            args.generation_dir, replicate, case_id, "A-raw",
        )
        if stable_hash(generation.get("tree") or {}) != generation.get("tree_hash"):
            raise ValueError(f"A-raw/{case_id}/r{replicate}: tree hash drift")
        acceptable = _acceptable(gold_index, replicate, case_id)
        live_ids = combo_utils._live_l2_ids(generation["tree"])
        live_acceptable = acceptable & live_ids
        adjudication = {"acceptable_l2": sorted(live_acceptable)}
        rows = []
        for index, (arm, spec) in enumerate(ARM_SPECS.items()):
            output_path = (
                args.output_dir / "legacy_traces" / arm
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
                champions_per_parent=int(spec["champions_per_parent"]),
            )
            quality = control_quality[(replicate, case_id)]
            row = {
                "endpoint": "legacy_rich_joint",
                "arm": arm,
                "case_id": case_id,
                "replicate": replicate,
                "source_tree_arm": "A-raw",
                "source_tree_hash": generation["tree_hash"],
                "evaluation_contract_hash": contract_hash,
                "gold_l2_coverage": bool(live_acceptable),
                "actual_top1": downstream["actual"]["top1"],
                "actual_top2": downstream["actual"]["top2"],
                "actual_rr": downstream["actual"]["rr"],
                "gold_rank": downstream["actual"]["rank"],
                "oracle_top2": downstream["oracle"]["top2"],
                "local_champion": downstream["local_champion"],
                "local_champion_ids": downstream["local_champion_ids"],
                "leaf_burden": quality.get("leaf_burden"),
                "local_mode": downstream["local_mode"],
                "champions_per_parent": downstream["champions_per_parent"],
                "parent_prior_temperature": downstream[
                    "parent_prior_temperature"
                ],
                "production_e2e_llm_calls": int(
                    (downstream.get("production_calls") or {}).get("requested")
                    or 0
                ),
                "production_e2e_model_calls": int(
                    (downstream.get("production_calls") or {}).get("model")
                    or 0
                ),
            }
            _write(output_path, row)
            rows.append(row)
        by_arm = {row["arm"]: row for row in rows}
        if by_arm["A14"]["local_champion_ids"] != by_arm["A17"][
            "local_champion_ids"
        ]:
            raise ValueError(f"{case_id}/r{replicate}: A14/A17 local drift")
        a14 = set(by_arm["A14"]["local_champion_ids"])
        a15 = set(by_arm["A15"]["local_champion_ids"])
        if not a14 <= a15:
            raise ValueError(f"{case_id}/r{replicate}: A15 lost A14 champion")
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
    }


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = [float(row[key]) for row in rows if row.get(key) is not None]
    return statistics.fmean(values) if values else None


def _transition(
    records: Sequence[Mapping[str, Any]], arm: str, metric: str,
) -> dict[str, Any]:
    baseline = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in records if row["arm"] == "A-raw"
    }
    current = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in records if row["arm"] == arm
    }
    gains, losses = [], []
    for key in sorted(set(baseline) & set(current)):
        before = bool(baseline[key].get(metric))
        after = bool(current[key].get(metric))
        item = {"case_id": key[0], "replicate": key[1]}
        if after and not before:
            gains.append(item)
        elif before and not after:
            losses.append(item)
    return {
        "gain_count": len(gains),
        "loss_count": len(losses),
        "net": len(gains) - len(losses),
        "gains": gains,
        "losses": losses,
    }


def aggregate(
    records: Sequence[Mapping[str, Any]], *, bootstrap: int,
) -> dict[str, Any]:
    arms = {}
    for arm in ARMS:
        rows = [row for row in records if row["arm"] == arm]
        arms[arm] = {
            "n": len(rows),
            "coverage": _mean(rows, "gold_l2_coverage"),
            "top1": _mean(rows, "actual_top1"),
            "top2": _mean(rows, "actual_top2"),
            "mrr": _mean(rows, "actual_rr"),
            "oracle_top2": _mean(rows, "oracle_top2"),
            "local_champion": _mean(rows, "local_champion"),
        }
    return {
        "arms": arms,
        "comparisons_vs_a_raw": {
            arm: legacy.paired_cluster_bootstrap(
                records, "A-raw", arm,
                metrics=(
                    "gold_l2_coverage", "actual_top1",
                    "actual_top2", "actual_rr",
                ),
                n_boot=bootstrap,
            )
            for arm in ARM_SPECS
        },
        "transitions_vs_a_raw": {
            arm: {
                metric: _transition(records, arm, metric)
                for metric in (
                    "gold_l2_coverage", "actual_top1", "actual_top2",
                )
            }
            for arm in ARM_SPECS
        },
    }


def _write_tsv(path: Path, summaries: Mapping[str, Any]) -> None:
    fields = [
        "endpoint", "arm", "n", "coverage_pct", "top1_pct", "top2_pct",
        "mrr_pct", "oracle_top2_pct", "local_champion_pct",
        "delta_top1_pp", "delta_top2_pp", "top2_ci95_low_pp",
        "top2_ci95_high_pp", "top2_gain_count", "top2_loss_count",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for endpoint, summary in summaries.items():
            for arm in ARMS:
                comparison = summary["comparisons_vs_a_raw"].get(arm) or {}
                top2 = comparison.get("actual_top2") or {}
                top1 = comparison.get("actual_top1") or {}
                ci = top2.get("ci95") or (None, None)
                transition = (
                    summary["transitions_vs_a_raw"].get(arm, {})
                    .get("actual_top2", {})
                )
                metric = summary["arms"][arm]
                pct = lambda value: (
                    round(100 * value, 1) if value is not None else None
                )
                writer.writerow({
                    "endpoint": endpoint,
                    "arm": arm,
                    "n": metric["n"],
                    "coverage_pct": pct(metric["coverage"]),
                    "top1_pct": pct(metric["top1"]),
                    "top2_pct": pct(metric["top2"]),
                    "mrr_pct": pct(metric["mrr"]),
                    "oracle_top2_pct": pct(metric["oracle_top2"]),
                    "local_champion_pct": pct(metric["local_champion"]),
                    "delta_top1_pp": pct(top1.get("delta")),
                    "delta_top2_pp": pct(top2.get("delta")),
                    "top2_ci95_low_pp": pct(ci[0]),
                    "top2_ci95_high_pp": pct(ci[1]),
                    "top2_gain_count": transition.get("gain_count"),
                    "top2_loss_count": transition.get("loss_count"),
                })


def run(args: argparse.Namespace) -> dict[str, Any]:
    gold_index = matrix.load_gold_index(args.gold_fixture)
    unified = _unified_records(args, gold_index=gold_index)
    legacy_records, legacy_meta = _legacy_records(
        args, gold_index=gold_index,
    )
    expected = len(ARMS) * 51
    if len(unified) != expected:
        raise ValueError(f"unified record count mismatch: {len(unified)} != {expected}")
    summaries = {
        "unified_direct": aggregate(unified, bootstrap=args.bootstrap),
        "legacy_rich_joint": aggregate(
            legacy_records, bootstrap=args.bootstrap,
        ),
    }
    payload = {
        "asset_kind": "l2_promising_downstream_legacy_evaluation",
        "schema_version": 1,
        "analysis_status": "research_only",
        "arms": list(ARMS),
        "arm_contract": ARM_SPECS,
        "record_counts": {
            "unified_direct": len(unified),
            "legacy_rich_joint": len(legacy_records),
        },
        "summaries": summaries,
        "legacy_meta": legacy_meta,
    }
    evaluation = args.output_dir / "evaluation"
    _write(evaluation / "summary.json", payload)
    _write(evaluation / "records.json", {
        "asset_kind": "l2_promising_downstream_legacy_records",
        "schema_version": 1,
        "records": [*unified, *legacy_records],
    })
    _write_tsv(evaluation / "summary.tsv", summaries)
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
    parser.add_argument("--workers", type=int, default=8)
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
