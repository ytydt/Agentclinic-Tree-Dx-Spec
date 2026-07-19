#!/usr/bin/env python3
"""Explain why A-variant gains change under the legacy AB endpoint."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Optional, Sequence

import eval_l2_branch_generation_ab as legacy
import eval_l2_competition_strategies as competition
import eval_l2_joint_dynamic_pipeline as joint
import evaluate_l2_a_variant_matrix as matrix
import reanalyze_l2_a_variant_unified_performance as unified


ROOT = Path(__file__).resolve().parents[1]
ARMS = ("C-prod", "A-raw", "A1", "A2", "A4", "A6", "A10")
VARIANTS = ("A1", "A2", "A4", "A6", "A10")
DEFAULT_OLD = (
    ROOT / "logs/l2_a_variant_legacy_ab_v1/evaluation/records.json"
)
DEFAULT_MATRIX = (
    ROOT / "logs/l2_a_variant_matrix_v1"
    / "evaluation_tier3_proxy/evaluation/records.json"
)
DEFAULT_GENERATION = ROOT / "logs/l2_a_variant_matrix_v1"
DEFAULT_DOWNSTREAM = (
    ROOT / "logs/l2_a_variant_matrix_v1/downstream_full"
)
DEFAULT_OUTPUT = (
    ROOT / "logs/l2_a_variant_legacy_ab_v1/evaluation"
    / "endpoint_gap_analysis.json"
)
DEFAULT_TSV = (
    ROOT / "logs/l2_a_variant_legacy_ab_v1/evaluation"
    / "endpoint_gap_arm_summary.tsv"
)
DEFAULT_CASE_TSV = (
    ROOT / "logs/l2_a_variant_legacy_ab_v1/evaluation"
    / "endpoint_gap_case_cells.tsv"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy._atomic_json(path, payload)


def _index(rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    return {
        (str(row["case_id"]), int(row["replicate"])): dict(row)
        for row in rows
    }


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> float:
    return sum(float(row[key]) for row in rows) / len(rows)


def _load_unified(args: argparse.Namespace) -> dict[str, list[dict[str, Any]]]:
    generation = matrix.load_generation_index(args.generation)
    downstream = matrix.load_downstream_index(args.downstream)
    gold = matrix.load_gold_index(args.gold_fixture)
    matrix_rows = _read(args.matrix_records)["records"]
    output = {
        arm: unified._same_harness_control(
            arm,
            generation=generation,
            downstream=downstream,
            gold=gold,
        )["records"]
        for arm in ("C-prod", "A-raw")
    }
    output.update({
        arm: [dict(row) for row in matrix_rows if row["arm"] == arm]
        for arm in VARIANTS
    })
    return output


def _evidence_alignment(
    args: argparse.Namespace,
) -> dict[tuple[str, int], dict[str, Any]]:
    _, full_l1 = legacy._load_l1_inputs(
        SimpleNamespace(base_output_dir=args.base_output_dir)
    )
    _, fixture_cases = competition._fixture_cases(args.finding_fixture)
    output = {}
    for (replicate, case_id), record in sorted(full_l1.items()):
        old_f2 = joint.true_consumption_order(record)[:2]
        filter_run = next(
            row for row in fixture_cases[case_id]["filter_runs"]
            if int(row["replicate"]) == replicate
        )
        unified_f2 = [
            str(value) for value in filter_run["ranked_fact_ids"][:2]
        ]
        if old_f2 == unified_f2:
            category = "same_order"
        elif len(old_f2) == len(unified_f2) and set(old_f2) == set(unified_f2):
            category = "same_set_reordered"
        else:
            category = "different_set"
        output[(case_id, replicate)] = {
            "category": category,
            "legacy_true_consumption_f2": old_f2,
            "unified_filter_ranked_f2": unified_f2,
        }
    return output


def _loss_gate(row: Mapping[str, Any]) -> str:
    if not row["gold_l2_coverage"]:
        return "coverage_deleted"
    if not row["local_champion"]:
        return "local_champion_elimination"
    return "intergroup_rank_loss"


def _funnel(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = sum(bool(row["gold_l2_coverage"]) for row in rows)
    local = sum(bool(row["local_champion"]) for row in rows)
    top2 = sum(bool(row["actual_top2"]) for row in rows)
    oracle = sum(bool(row["oracle_top2"]) for row in rows)
    return {
        "coverage_count": coverage,
        "local_champion_count": local,
        "top2_count": top2,
        "oracle_top2_count": oracle,
        "local_given_coverage": local / coverage if coverage else None,
        "top2_given_coverage": top2 / coverage if coverage else None,
        "top2_given_local_champion": top2 / local if local else None,
        "oracle_given_coverage": oracle / coverage if coverage else None,
    }


def _gold_ticket_funnel(
    args: argparse.Namespace,
    arm: str,
    rows: Sequence[Mapping[str, Any]],
    gold_index: Mapping[str, Any],
) -> dict[str, Any]:
    values = []
    for row in rows:
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        trace = _read(
            args.generation / "generation/traces" / arm
            / f"r{replicate:02d}__{case_id}.json"
        )
        branches = trace["tree"]["branches"]
        if arm in ("C-prod", "A-raw"):
            source_arm = "C" if arm == "C-prod" else "A"
            fixture = gold_index["by_ab_key"][
                (source_arm, replicate, case_id)
            ]
            acceptable = {
                str(value) for value in fixture.get("acceptable_l2") or ()
            }
        else:
            acceptable = {
                str(value) for value in row.get("live_acceptable_l2") or ()
            }
        live = acceptable & set(branches)
        if not live:
            continue
        parents = {
            str(branches[value].get("parent") or "") for value in live
        }
        values.append({
            "id_tickets": len(live),
            "parent_tickets": len(parents),
            "local_champion": bool(row["local_champion"]),
            "top2": bool(row["actual_top2"]),
        })
    by_parent_count = {}
    for count in sorted({row["parent_tickets"] for row in values}):
        bucket = [row for row in values if row["parent_tickets"] == count]
        by_parent_count[str(count)] = {
            "n": len(bucket),
            "local_champion_rate": sum(
                row["local_champion"] for row in bucket
            ) / len(bucket),
            "top2_rate": sum(row["top2"] for row in bucket) / len(bucket),
        }
    return {
        "covered_n": len(values),
        "mean_acceptable_id_tickets": (
            sum(row["id_tickets"] for row in values) / len(values)
            if values else None
        ),
        "mean_acceptable_parent_tickets": (
            sum(row["parent_tickets"] for row in values) / len(values)
            if values else None
        ),
        "by_parent_ticket_count": by_parent_count,
    }


def _old_final_ranking(
    cache_path: Path,
    branches: Mapping[str, Any],
) -> list[str]:
    if not cache_path.is_file():
        return []
    candidates = []
    for response in _read(cache_path).values():
        ranked = (
            response.get("ranked_candidate_ids")
            if isinstance(response, Mapping) else None
        )
        if not ranked or not all(str(value) in branches for value in ranked):
            continue
        parents = {
            str(branches[str(value)].get("parent") or "") for value in ranked
        }
        if len(parents) == len(ranked):
            candidates.append([str(value) for value in ranked])
    return candidates[-1] if candidates else []


def _case_detail(
    args: argparse.Namespace,
    old_index: Mapping[tuple[str, str, int], Mapping[str, Any]],
    arm: str,
    case_id: str,
    replicate: int,
) -> dict[str, Any]:
    trace = _read(
        args.generation / "generation/traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )
    branches = trace["tree"]["branches"]
    labels = {
        str(branch_id): str(branch.get("label") or "")
        for branch_id, branch in branches.items()
    }
    downstream = _read(
        args.downstream / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )["record"]["baseline"]
    old_row = old_index[(arm, case_id, replicate)]
    cache_path = (
        args.old_cache / arm / f"r{replicate:02d}" / f"{case_id}.json"
    )
    old_ranking = _old_final_ranking(cache_path, branches)
    acceptable = [
        str(value) for value in old_row.get("live_acceptable_l2") or ()
    ]
    return {
        "arm": arm,
        "case_id": case_id,
        "replicate": replicate,
        "leaf_burden": old_row["leaf_burden"],
        "coverage": old_row["gold_l2_coverage"],
        "local_champion": old_row["local_champion"],
        "legacy_top2": old_row["actual_top2"],
        "acceptable": [
            {
                "id": value,
                "label": labels.get(value, ""),
                "parent_id": str((branches.get(value) or {}).get("parent") or ""),
            }
            for value in acceptable
        ],
        "legacy_final_ranking": [
            {"id": value, "label": labels.get(value, "")}
            for value in old_ranking
        ],
        "unified_champions": [
            {"id": value, "label": labels.get(value, "")}
            for value in downstream.get("champion") or ()
        ],
        "unified_final_ranking": [
            {"id": value, "label": labels.get(value, "")}
            for value in (downstream.get("output") or {}).get("ranking") or ()
        ],
    }


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    old_rows = _read(args.old_records)["records"]
    old_by_arm = {
        arm: [dict(row) for row in old_rows if row["arm"] == arm]
        for arm in ARMS
    }
    unified_by_arm = _load_unified(args)
    evidence = _evidence_alignment(args)
    old_index = {
        (str(row["arm"]), str(row["case_id"]), int(row["replicate"])): row
        for row in old_rows
    }
    old_baseline = _index(old_by_arm["A-raw"])
    unified_baseline = _index(unified_by_arm["A-raw"])
    old_baseline_top2 = _mean(old_by_arm["A-raw"], "actual_top2")
    unified_baseline_top2 = _mean(
        unified_by_arm["A-raw"], "actual_top2"
    )
    gold_index = matrix.load_gold_index(args.gold_fixture)

    arm_summary = []
    case_cells = []
    for arm in ARMS:
        old_cells = _index(old_by_arm[arm])
        unified_cells = _index(unified_by_arm[arm])
        old_top1 = _mean(old_by_arm[arm], "actual_top1")
        unified_top1 = _mean(unified_by_arm[arm], "actual_top1")
        old_top2 = _mean(old_by_arm[arm], "actual_top2")
        unified_top2 = _mean(unified_by_arm[arm], "actual_top2")
        old_mrr = _mean(old_by_arm[arm], "actual_rr")
        unified_mrr = _mean(unified_by_arm[arm], "mrr_at_2")
        old_relative = old_top2 - old_baseline_top2
        unified_relative = unified_top2 - unified_baseline_top2
        old_endpoint_gains = 0
        old_endpoint_losses = 0
        interaction_distribution: Counter[str] = Counter()
        evidence_flip_distribution: dict[str, Counter[str]] = {
            category: Counter()
            for category in ("same_order", "same_set_reordered", "different_set")
        }
        for key in sorted(old_cells):
            old_value = bool(old_cells[key]["actual_top2"])
            unified_value = bool(unified_cells[key]["actual_top2"])
            baseline_old = bool(old_baseline[key]["actual_top2"])
            baseline_unified = bool(unified_baseline[key]["actual_top2"])
            variant_shift = int(old_value) - int(unified_value)
            baseline_shift = int(baseline_old) - int(baseline_unified)
            interaction = variant_shift - baseline_shift
            if old_value and not unified_value:
                old_endpoint_gains += 1
                flip = "legacy_gain"
            elif unified_value and not old_value:
                old_endpoint_losses += 1
                flip = "legacy_loss"
            else:
                flip = "stable"
            category = evidence[key]["category"]
            evidence_flip_distribution[category][flip] += 1
            interaction_distribution[
                f"baseline_shift={baseline_shift};"
                f"variant_shift={variant_shift};interaction={interaction}"
            ] += 1
            case_cells.append({
                "arm": arm,
                "case_id": key[0],
                "replicate": key[1],
                "evidence_alignment": category,
                "legacy_top2": old_value,
                "unified_top2": unified_value,
                "legacy_a_raw_top2": baseline_old,
                "unified_a_raw_top2": baseline_unified,
                "variant_endpoint_shift": variant_shift,
                "a_raw_endpoint_shift": baseline_shift,
                "relative_interaction": interaction,
            })
        arm_summary.append({
            "arm": arm,
            "n": len(old_by_arm[arm]),
            "legacy_top1_pct": round(100 * old_top1, 1),
            "unified_top1_pct": round(100 * unified_top1, 1),
            "absolute_top1_shift_pp": round(
                100 * (old_top1 - unified_top1), 1,
            ),
            "legacy_top2_pct": round(100 * old_top2, 1),
            "unified_top2_pct": round(100 * unified_top2, 1),
            "absolute_top2_shift_pp": round(
                100 * (old_top2 - unified_top2), 1,
            ),
            "legacy_mrr_pct": round(100 * old_mrr, 1),
            "unified_mrr_pct": round(100 * unified_mrr, 1),
            "legacy_relative_top2_pp": round(100 * old_relative, 1),
            "unified_relative_top2_pp": round(100 * unified_relative, 1),
            "relative_endpoint_interaction_pp": round(
                100 * (old_relative - unified_relative), 1,
            ),
            "legacy_endpoint_top2_gains": old_endpoint_gains,
            "legacy_endpoint_top2_losses": old_endpoint_losses,
            "funnel": _funnel(old_by_arm[arm]),
            "gold_ticket_funnel": _gold_ticket_funnel(
                args, arm, old_by_arm[arm], gold_index,
            ),
            "interaction_distribution": dict(interaction_distribution),
            "evidence_flip_distribution": {
                key: dict(value)
                for key, value in evidence_flip_distribution.items()
            },
        })

    old_vs_baseline = {}
    for arm in VARIANTS:
        current = _index(old_by_arm[arm])
        losses = []
        gains = []
        for key, baseline in old_baseline.items():
            row = current[key]
            if baseline["actual_top2"] and not row["actual_top2"]:
                losses.append({
                    "case_id": key[0],
                    "replicate": key[1],
                    "gate": _loss_gate(row),
                })
            elif row["actual_top2"] and not baseline["actual_top2"]:
                gains.append({
                    "case_id": key[0],
                    "replicate": key[1],
                    "baseline_failure_gate": _loss_gate(baseline),
                })
        old_vs_baseline[arm] = {
            "gain_count": len(gains),
            "loss_count": len(losses),
            "gain_by_baseline_gate": dict(Counter(
                row["baseline_failure_gate"] for row in gains
            )),
            "loss_by_variant_gate": dict(Counter(
                row["gate"] for row in losses
            )),
            "gains": gains,
            "losses": losses,
        }

    examples = [
        _case_detail(args, old_index, *key)
        for key in (
            ("A2", "mb55_glucagonoma", 1),
            ("A2", "mxh036", 2),
            ("A4", "mb83_foreignbody", 1),
            ("A4", "mxh075", 1),
            ("A6", "mb11_pancoast", 2),
        )
    ]
    evidence_counts = Counter(
        row["category"] for row in evidence.values()
    )
    payload = {
        "asset_kind": "l2_a_variant_endpoint_gap_analysis",
        "schema_version": 1,
        "analysis_status": "research_only",
        "question": (
            "Why do A-variant gains change under the legacy AB endpoint?"
        ),
        "endpoint_contracts": {
            "legacy_ab": (
                "true L1 consumption F2 -> ordinal per-parent annotator "
                "with leaf posterior -> one champion per parent -> rich joint "
                "arbiter with all findings, parent prior and local audit"
            ),
            "unified_replay": (
                "auto-filter ranked F2 -> direct per-parent list ranker "
                "without leaf posterior -> one champion per valid parent -> "
                "direct intergroup list ranker"
            ),
        },
        "evidence_alignment": {
            "counts": dict(evidence_counts),
            "same_order_fraction": (
                evidence_counts["same_order"] / len(evidence)
            ),
            "cells": [
                {
                    "case_id": key[0],
                    "replicate": key[1],
                    **value,
                }
                for key, value in sorted(evidence.items())
            ],
        },
        "a_raw_endpoint_lift": {
            "unified_top2_pct": round(100 * unified_baseline_top2, 1),
            "legacy_top2_pct": round(100 * old_baseline_top2, 1),
            "lift_pp": round(
                100 * (old_baseline_top2 - unified_baseline_top2), 1,
            ),
            "cell_net": int(round(
                len(old_by_arm["A-raw"])
                * (old_baseline_top2 - unified_baseline_top2)
            )),
        },
        "arms": arm_summary,
        "legacy_vs_a_raw_gate_attribution": old_vs_baseline,
        "representative_cases": examples,
    }
    _write(args.output, payload)

    with args.output_tsv.open("w", encoding="utf-8", newline="") as handle:
        rows = []
        for row in arm_summary:
            rows.append({
                key: value for key, value in row.items()
                if key not in {
                    "funnel", "gold_ticket_funnel",
                    "interaction_distribution",
                    "evidence_flip_distribution",
                }
            })
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows)
    with args.case_tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(case_cells[0]), delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(case_cells)
    return payload


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-records", type=Path, default=DEFAULT_OLD)
    parser.add_argument("--old-cache", type=Path, default=(
        ROOT / "logs/l2_a_variant_legacy_ab_v1/cache/evaluate"
    ))
    parser.add_argument("--matrix-records", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--generation", type=Path, default=DEFAULT_GENERATION)
    parser.add_argument("--downstream", type=Path, default=DEFAULT_DOWNSTREAM)
    parser.add_argument("--gold-fixture", type=Path, default=matrix.DEFAULT_GOLD)
    parser.add_argument(
        "--finding-fixture", type=Path, default=legacy.DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=legacy.DEFAULT_BASE_OUTPUT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-tsv", type=Path, default=DEFAULT_TSV)
    parser.add_argument("--case-tsv", type=Path, default=DEFAULT_CASE_TSV)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    payload = analyze(args)
    print(json.dumps({
        "output": str(args.output),
        "arms": len(payload["arms"]),
        "evidence_alignment": payload["evidence_alignment"]["counts"],
        "a_raw_endpoint_lift": payload["a_raw_endpoint_lift"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
