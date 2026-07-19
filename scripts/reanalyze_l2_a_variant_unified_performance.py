#!/usr/bin/env python3
"""Write same-harness A-variant performance after Tier-3 adjudication."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

import evaluate_l2_a_variant_matrix as matrix


ROOT = Path(__file__).resolve().parents[1]
ARMS = matrix.HEADLINE_ARMS


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _same_harness_control(
    arm: str,
    *,
    generation: Mapping[str, Any],
    downstream: Mapping[str, Any],
    gold: Mapping[str, Any],
) -> dict[str, Any]:
    source = matrix.AB_SOURCE_ARM[arm]
    rows = []
    replicates = range(
        1, int(generation["manifest"].get("replicates") or 3) + 1,
    )
    for case_id in sorted(
        generation["manifest"].get("case_ids") or (),
    ):
        for replicate in replicates:
            trace = generation["traces"].get((arm, replicate, case_id))
            record = downstream["records"].get((arm, replicate, case_id))
            gold_row = gold["by_ab_key"].get((source, replicate, case_id))
            if trace is None or record is None or gold_row is None:
                raise ValueError(
                    f"{arm}/{case_id}/r{replicate:02d}: missing source data"
                )
            acceptable = [
                str(value) for value in gold_row.get("acceptable_l2") or ()
            ]
            _, _, l2_ids = matrix._level_counts(trace.get("tree"))
            ranking = matrix.extract_ranking(record.get("baseline"), "baseline")
            scored = matrix.score_ranking(
                ranking,
                acceptable,
                gold_absent=False,
                l2_ids=l2_ids,
            )
            rows.append({
                "case_id": case_id,
                "replicate": replicate,
                **scored,
                "oracle": matrix.oracle_parent_f4_top2(record, acceptable),
                "empty_ranking": not bool(ranking),
            })
    n = len(rows)
    return {
        "n": n,
        "gold_fixture_arm": source,
        "coverage_count": sum(bool(row["gold_l2_coverage"]) for row in rows),
        "top1_count": sum(bool(row["actual_top1"]) for row in rows),
        "top2_count": sum(bool(row["actual_top2"]) for row in rows),
        "mrr_at_2": sum(float(row["mrr_at_2"]) for row in rows) / n,
        "oracle_f4_top2_count": sum(bool(row["oracle"]) for row in rows),
        "empty_ranking_count": sum(bool(row["empty_ranking"]) for row in rows),
        "records": rows,
    }


def _pct(value: float) -> float:
    return round(100.0 * value, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generation-dir",
        type=Path,
        default=ROOT / "logs/l2_a_variant_matrix_v1/generation",
    )
    parser.add_argument(
        "--downstream-dir",
        type=Path,
        default=ROOT / "logs/l2_a_variant_matrix_v1/downstream_full",
    )
    parser.add_argument("--gold-fixture", type=Path, default=matrix.DEFAULT_GOLD)
    parser.add_argument("--matrix-summary", type=Path, required=True)
    parser.add_argument("--matrix-records", type=Path, required=True)
    parser.add_argument("--gates", type=Path, required=True)
    parser.add_argument("--final-audit", type=Path, required=True)
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-tsv", type=Path, required=True)
    parser.add_argument("--output-transitions", type=Path, required=True)
    args = parser.parse_args()

    generation = matrix.load_generation_index(args.generation_dir)
    downstream = matrix.load_downstream_index(args.downstream_dir)
    gold = matrix.load_gold_index(args.gold_fixture)
    summary = _read(args.matrix_summary)
    record_rows = _read(args.matrix_records)["records"]
    gate_rows = _read(args.gates)["entry_gate"]["arms"]
    final_audit = _read(args.final_audit)
    calibration = _read(args.calibration_report)
    controls = {
        arm: _same_harness_control(
            arm, generation=generation, downstream=downstream, gold=gold,
        )
        for arm in matrix.CONTROL_ARMS
    }
    baseline = controls["A-raw"]
    baseline_top1 = baseline["top1_count"] / baseline["n"]
    baseline_top2 = baseline["top2_count"] / baseline["n"]
    baseline_coverage = baseline["coverage_count"] / baseline["n"]
    baseline_means = summary["arms"]["A-raw"]
    baseline_parent_invalid = float(
        baseline_means["leaf_parent_invalid_rate"]
    )
    baseline_duplicate = float(
        baseline_means["semantic_duplicate_excess_rate"]
    )
    rows = []
    for arm in ARMS:
        means = summary["arms"][arm]
        n = int(means["n"])
        source = controls.get(arm)
        if source is None:
            source = {
                "n": n,
                "gold_fixture_arm": (
                    "semantic_tier3_proxy" if arm in {
                        "A6", "A7", "A8", "A9", "A10",
                    } else "A"
                ),
                "coverage_count": round(float(means["gold_l2_coverage"]) * n),
                "top1_count": round(float(means["actual_top1"]) * n),
                "top2_count": round(float(means["actual_top2"]) * n),
                "mrr_at_2": float(means["mrr_at_2"]),
                "oracle_f4_top2_count": round(
                    float(means["oracle_parent_f4_local_top2"]) * n
                ),
                "empty_ranking_count": sum(
                    row["arm"] == arm and not row.get("ranking")
                    for row in record_rows
                ),
            }
        top1 = source["top1_count"] / source["n"]
        top2 = source["top2_count"] / source["n"]
        coverage = source["coverage_count"] / source["n"]
        oracle = source["oracle_f4_top2_count"] / source["n"]
        hard_gates_pass = bool(gate_rows[arm]["hard_gates_pass"])
        performance_gates_pass = (
            top2 >= baseline_top2
            and coverage >= baseline_coverage - 0.05
        )
        quality_waived = arm in matrix.PURE_DOWNSTREAM
        quality_gates_pass = quality_waived or (
            float(means["leaf_parent_invalid_rate"])
            <= 0.5 * baseline_parent_invalid
            and float(means["semantic_duplicate_excess_rate"])
            <= 0.5 * baseline_duplicate
        )
        entry_gate_pass = (
            hard_gates_pass
            and performance_gates_pass
            and quality_gates_pass
        )
        rows.append({
            "arm": arm,
            "gold_fixture_arm": source["gold_fixture_arm"],
            "n": source["n"],
            "coverage_count": source["coverage_count"],
            "coverage_pct": _pct(coverage),
            "top1_count": source["top1_count"],
            "top1_pct": _pct(top1),
            "top2_count": source["top2_count"],
            "top2_pct": _pct(top2),
            "mrr_at_2_pct": _pct(float(source["mrr_at_2"])),
            "oracle_f4_top2_count": source["oracle_f4_top2_count"],
            "oracle_f4_top2_pct": _pct(oracle),
            "leaf_burden": round(float(means["leaf_burden"]), 3),
            "leaf_clean_pct": _pct(float(means["leaf_clean_rate"])),
            "parent_invalid_pct": _pct(
                float(means["leaf_parent_invalid_rate"])
            ),
            "semantic_duplicate_excess_pct": _pct(
                float(means["semantic_duplicate_excess_rate"])
            ),
            "delta_top1_pp_vs_a_raw": round(
                100.0 * (top1 - baseline_top1), 1,
            ),
            "delta_top2_pp_vs_a_raw": round(
                100.0 * (top2 - baseline_top2), 1,
            ),
            "oracle_minus_top2_pp": round(100.0 * (oracle - top2), 1),
            "empty_ranking_count": source["empty_ranking_count"],
            "downstream_required_count": int(
                means["downstream_required_count"]
            ),
            "hard_gates_pass": hard_gates_pass,
            "performance_gates_pass": performance_gates_pass,
            "quality_gates_pass": quality_gates_pass,
            "quality_waived_pure_downstream": quality_waived,
            "entry_gate_pass": entry_gate_pass,
        })
    payload = {
        "asset_kind": "l2_a_variant_unified_performance_reanalysis",
        "schema_version": 2,
        "analysis_status": "research_only",
        "human_signed_off": bool(final_audit.get("human_signed_off")),
        "proxy_corrections": int(final_audit.get("proxy_corrections") or 0),
        "calibration_passed": bool(calibration.get("passed")),
        "calibration_metric_passed": bool(
            calibration.get("metric_passed")
        ),
        "denominator": baseline["n"],
        "comparator": "A-raw",
        "metric_contract": {
            "downstream_harness": str(args.downstream_dir),
            "ranking": "current downstream replay for every arm",
            "stable_gold": (
                "C-prod uses frozen C IDs; A-raw/A1-A5/A11-A17 use "
                "frozen A IDs"
            ),
            "regenerated_gold": (
                "A6-A10 use completed Tier-3 proxy semantic GoldMatch"
            ),
            "quality": "Tier-3 proxy final audit; research-only",
        },
        "rows": rows,
    }
    _write_json(args.output_json, payload)
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    by_arm_records = {
        arm: (
            controls[arm]["records"]
            if arm in controls
            else [row for row in record_rows if row["arm"] == arm]
        )
        for arm in ARMS
    }
    baseline_cells = {
        (str(row["case_id"]), int(row["replicate"])): row
        for row in by_arm_records["A-raw"]
    }
    transitions = {}
    for arm in ARMS:
        if arm == "A-raw":
            continue
        current_cells = {
            (str(row["case_id"]), int(row["replicate"])): row
            for row in by_arm_records[arm]
        }
        metrics = {}
        for metric in ("gold_l2_coverage", "actual_top1", "actual_top2"):
            gain = []
            loss = []
            for key in sorted(set(baseline_cells) & set(current_cells)):
                before = bool(baseline_cells[key].get(metric))
                after = bool(current_cells[key].get(metric))
                if after and not before:
                    gain.append({"case_id": key[0], "replicate": key[1]})
                elif before and not after:
                    loss.append({"case_id": key[0], "replicate": key[1]})
            metrics[metric] = {
                "gain_count": len(gain),
                "loss_count": len(loss),
                "net": len(gain) - len(loss),
                "gains": gain,
                "losses": loss,
            }
        transitions[arm] = metrics
    _write_json(args.output_transitions, {
        "asset_kind": "l2_a_variant_unified_case_transitions",
        "schema_version": 1,
        "analysis_status": "research_only",
        "comparator": "A-raw same-harness",
        "transitions": transitions,
    })
    print(json.dumps({
        "output_json": str(args.output_json),
        "output_tsv": str(args.output_tsv),
        "output_transitions": str(args.output_transitions),
        "arms": len(rows),
        "human_signed_off": payload["human_signed_off"],
        "calibration_passed": payload["calibration_passed"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
