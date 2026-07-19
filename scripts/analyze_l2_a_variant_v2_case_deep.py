#!/usr/bin/env python3
"""Deep case-level V2 analysis aligned with AB / matrix v1 metric inventory.

Produces:
  - arm_performance_canonical.{json,tsv}  (Top1/Top2/MRR/cov/local/oracle/quality)
  - case_means_3run.{json,tsv}            (per-case 3-run averages)
  - arm_case_transitions_vs_a_raw_v2.json
  - error_mode_cells.json                 (cells for lineage join)
  - quality_by_arm.json                   (parent-valid / clean / dup-excess)
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECORDS = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation" / "records.json"
)
DEFAULT_JUDGE = (
    ROOT / "logs" / "l2_a_variant_matrix_v2" / "judge" / "final_audit_human_sim.json"
)
DEFAULT_GEN = ROOT / "logs" / "l2_a_variant_matrix_v2" / "generation" / "traces"
DEFAULT_OUT = (
    ROOT / "logs" / "l2_a_variant_legacy_ab_v2" / "evaluation" / "case_deep"
)
BASELINE = "A-raw-v2"
ARM_ORDER = (
    "C-prod-v2",
    "A-raw-v2",
    "A4-v2-ref",
    "A4+A14-v2-ref",
    "A18-parent-safe",
    "A19-budget-safe",
    "A20-generation-v2",
    "A21-generation-v2+F4",
    "A22-adaptive-local-rescue",
)
BOOL_METRICS = (
    "actual_top1",
    "actual_top2",
    "active_gold_l2_coverage",
    "inventory_gold_l2_coverage",
    "local_champion",
    "oracle_top1",
    "oracle_top2",
    "strict_top2",
    "technical_fallback",
    "reserve_gold_present",
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_tsv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _mean(rows: Sequence[Mapping[str, Any]], key: str) -> Optional[float]:
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            values.append(1.0 if value else 0.0)
        else:
            values.append(float(value))
    if not values:
        return None
    return statistics.fmean(values)


def _field_value(fields: Mapping[str, Any], name: str) -> Any:
    raw = fields.get(name)
    if not isinstance(raw, Mapping):
        return None
    return raw.get("value")


def quality_from_audit(
    audit: Mapping[str, Any],
) -> dict[tuple[str, int, str], dict[str, float]]:
    buckets: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in audit.get("decisions") or ():
        fields = row.get("fields") or {}
        specific = _field_value(fields, "is_specific_disease")
        parent_valid = _field_value(fields, "is_parent_valid")
        cluster = _field_value(fields, "semantic_cluster_id")
        case_id = str(row.get("case_id") or "")
        for occ in row.get("occurrences") or ():
            if not isinstance(occ, Mapping):
                continue
            key = (
                str(occ.get("arm") or ""),
                int(occ.get("replicate") or 0),
                str(occ.get("case_id") or case_id),
            )
            buckets[key].append({
                "is_specific_disease": specific,
                "is_parent_valid": parent_valid,
                "semantic_cluster_id": cluster,
            })
    output: dict[tuple[str, int, str], dict[str, float]] = {}
    for key, leaves in buckets.items():
        usable = [
            leaf for leaf in leaves
            if leaf["is_specific_disease"] is not None
            and leaf["is_parent_valid"] is not None
        ]
        n = len(usable) or 1
        invalid = sum(1 for leaf in usable if leaf["is_parent_valid"] is False)
        clusters: Counter[str] = Counter()
        for leaf in usable:
            cid = str(leaf.get("semantic_cluster_id") or "").strip()
            if cid:
                clusters[cid] += 1
        excess = sum(max(0, size - 1) for size in clusters.values())
        clean = sum(
            1
            for leaf in usable
            if leaf["is_specific_disease"] is True
            and leaf["is_parent_valid"] is True
            and clusters.get(str(leaf.get("semantic_cluster_id") or "").strip(), 0)
            == 1
        )
        output[key] = {
            "leaf_parent_invalid_rate": invalid / n,
            "parent_valid_rate": 1.0 - (invalid / n),
            "semantic_duplicate_excess_rate": excess / n,
            "leaf_clean_rate": clean / n,
            "n_leaves": float(len(usable)),
        }
    return output


def enrich_records(
    records: Sequence[Mapping[str, Any]],
    quality: Mapping[tuple[str, int, str], Mapping[str, float]],
    *,
    quality_by_branch: Mapping[tuple[str, int, str, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for row in records:
        source_arm = str(row.get("source_tree_arm") or row["arm"])
        key = (source_arm, int(row["replicate"]), str(row["case_id"]))
        q = quality.get(key) or {}
        # Active-only parent validity: only leaves in active_ids.
        active_ids = {
            str(value) for value in (row.get("active_ids") or ()) if value
        }
        active_leaves = []
        for branch_id in active_ids:
            leaf = quality_by_branch.get(
                (source_arm, int(row["replicate"]), str(row["case_id"]), branch_id)
            )
            if leaf is not None:
                active_leaves.append(leaf)
        if active_leaves:
            n_act = len(active_leaves)
            invalid_act = sum(
                1 for leaf in active_leaves if leaf.get("is_parent_valid") is False
            )
            active_parent_valid_rate = 1.0 - (invalid_act / n_act)
            active_parent_invalid_rate = invalid_act / n_act
        else:
            active_parent_valid_rate = None
            active_parent_invalid_rate = None
            n_act = 0
        item = dict(row)
        item.update({
            "quality_source_arm": source_arm,
            "leaf_parent_invalid_rate": q.get("leaf_parent_invalid_rate"),
            "parent_valid_rate": q.get("parent_valid_rate"),
            "semantic_duplicate_excess_rate": q.get(
                "semantic_duplicate_excess_rate"
            ),
            "leaf_clean_rate": q.get("leaf_clean_rate"),
            "n_quality_leaves": q.get("n_leaves"),
            "active_parent_valid_rate": active_parent_valid_rate,
            "active_parent_invalid_rate": active_parent_invalid_rate,
            "n_active_quality_leaves": float(n_act),
            "mrr_at_2_capped": (
                float(row.get("mrr_at_2") or 0.0)
                if row.get("actual_top2") else 0.0
            ),
        })
        enriched.append(item)
    return enriched


def quality_branch_index(
    audit: Mapping[str, Any],
) -> dict[tuple[str, int, str, str], dict[str, Any]]:
    index: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for row in audit.get("decisions") or ():
        fields = row.get("fields") or {}
        leaf = {
            "is_specific_disease": _field_value(fields, "is_specific_disease"),
            "is_parent_valid": _field_value(fields, "is_parent_valid"),
            "semantic_cluster_id": _field_value(fields, "semantic_cluster_id"),
            "leaf_label": row.get("leaf_label"),
            "parent_label": row.get("parent_label"),
        }
        case_id = str(row.get("case_id") or "")
        for occ in row.get("occurrences") or ():
            if not isinstance(occ, Mapping):
                continue
            key = (
                str(occ.get("arm") or ""),
                int(occ.get("replicate") or 0),
                str(occ.get("case_id") or case_id),
                str(occ.get("branch_id") or ""),
            )
            index[key] = leaf
    return index


def case_means(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        groups[(str(row["arm"]), str(row["case_id"]))].append(row)
    rows = []
    for (arm, case_id), items in sorted(groups.items()):
        entry: dict[str, Any] = {
            "arm": arm,
            "case_id": case_id,
            "n_replicates": len(items),
        }
        for metric in BOOL_METRICS:
            entry[f"{metric}_mean"] = _mean(items, metric)
        entry["mrr_at_2_mean"] = _mean(items, "mrr_at_2")
        entry["mrr_at_2_capped_mean"] = _mean(items, "mrr_at_2_capped")
        entry["parent_valid_rate_mean"] = _mean(items, "parent_valid_rate")
        entry["active_parent_valid_rate_mean"] = _mean(
            items, "active_parent_valid_rate",
        )
        entry["leaf_parent_invalid_rate_mean"] = _mean(
            items, "leaf_parent_invalid_rate",
        )
        entry["active_parent_invalid_rate_mean"] = _mean(
            items, "active_parent_invalid_rate",
        )
        entry["leaf_clean_rate_mean"] = _mean(items, "leaf_clean_rate")
        entry["semantic_duplicate_excess_rate_mean"] = _mean(
            items, "semantic_duplicate_excess_rate",
        )
        gates = Counter(str(item.get("loss_gate") or "unknown") for item in items)
        entry["loss_gate_mode"] = gates.most_common(1)[0][0]
        entry["loss_gate_counts"] = dict(gates)
        rows.append(entry)
    return rows


def arm_performance(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    by_arm: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        by_arm[str(row["arm"])].append(row)
    rows = []
    for arm in ARM_ORDER:
        items = by_arm.get(arm) or []
        gates = Counter(str(item.get("loss_gate") or "unknown") for item in items)
        local = [item for item in items if item.get("local_champion")]
        covered = [
            item for item in items if item.get("active_gold_l2_coverage")
        ]
        rows.append({
            "arm": arm,
            "n": len(items),
            "top1_pct": 100.0 * (_mean(items, "actual_top1") or 0.0),
            "top2_pct": 100.0 * (_mean(items, "actual_top2") or 0.0),
            "mrr_pct": 100.0 * (_mean(items, "mrr_at_2") or 0.0),
            "mrr_capped_pct": 100.0 * (_mean(items, "mrr_at_2_capped") or 0.0),
            "active_cov_pct": 100.0 * (
                _mean(items, "active_gold_l2_coverage") or 0.0
            ),
            "inventory_cov_pct": 100.0 * (
                _mean(items, "inventory_gold_l2_coverage") or 0.0
            ),
            "local_champion_pct": 100.0 * (
                _mean(items, "local_champion") or 0.0
            ),
            "oracle_top1_pct": 100.0 * (_mean(items, "oracle_top1") or 0.0),
            "oracle_top2_pct": 100.0 * (_mean(items, "oracle_top2") or 0.0),
            "strict_top2_pct": 100.0 * (_mean(items, "strict_top2") or 0.0),
            "technical_fallback_pct": 100.0 * (
                _mean(items, "technical_fallback") or 0.0
            ),
            "parent_valid_pct": 100.0 * (
                _mean(items, "parent_valid_rate") or 0.0
            ),
            "parent_invalid_pct": 100.0 * (
                _mean(items, "leaf_parent_invalid_rate") or 0.0
            ),
            "active_parent_valid_pct": 100.0 * (
                _mean(items, "active_parent_valid_rate") or 0.0
            ),
            "active_parent_invalid_pct": 100.0 * (
                _mean(items, "active_parent_invalid_rate") or 0.0
            ),
            "leaf_clean_pct": 100.0 * (_mean(items, "leaf_clean_rate") or 0.0),
            "dup_excess_pct": 100.0 * (
                _mean(items, "semantic_duplicate_excess_rate") or 0.0
            ),
            "top2_given_local_champion": (
                sum(1 for item in local if item.get("actual_top2")) / len(local)
                if local else None
            ),
            "local_given_coverage": (
                len(local) / len(covered) if covered else None
            ),
            "loss_gate_counts": dict(gates),
        })
    return rows


def transitions(
    records: Sequence[Mapping[str, Any]],
    *,
    baseline: str = BASELINE,
    metrics: Sequence[str] = (
        "actual_top1", "actual_top2", "active_gold_l2_coverage", "local_champion",
    ),
) -> dict[str, Any]:
    by = {
        (str(row["arm"]), str(row["case_id"]), int(row["replicate"])): row
        for row in records
    }
    arms = sorted({arm for arm, _, _ in by})
    out: dict[str, Any] = {
        "comparator": baseline,
        "aggregation": "cell_level_boolean_flip_then_counts",
        "note": (
            "gain/loss counted per (case,replicate) cell; "
            "also report case_majority when ≥2/3 replicates flip"
        ),
        "transitions": {},
    }
    for arm in arms:
        if arm == baseline:
            continue
        arm_block: dict[str, Any] = {}
        for metric in metrics:
            gains = []
            losses = []
            case_gain = Counter()
            case_loss = Counter()
            for case_id in sorted({c for a, c, _ in by if a == arm}):
                for rep in (1, 2, 3):
                    base = by.get((baseline, case_id, rep))
                    target = by.get((arm, case_id, rep))
                    if not base or not target:
                        continue
                    bv = bool(base.get(metric))
                    tv = bool(target.get(metric))
                    cell = {"case_id": case_id, "replicate": rep}
                    if (not bv) and tv:
                        gains.append(cell)
                        case_gain[case_id] += 1
                    if bv and (not tv):
                        losses.append(cell)
                        case_loss[case_id] += 1
            arm_block[metric] = {
                "gain_count": len(gains),
                "loss_count": len(losses),
                "net": len(gains) - len(losses),
                "gains": gains,
                "losses": losses,
                "case_majority_gains": sorted(
                    cid for cid, n in case_gain.items() if n >= 2
                ),
                "case_majority_losses": sorted(
                    cid for cid, n in case_loss.items() if n >= 2
                ),
            }
        out["transitions"][arm] = arm_block
    return out


def lineage_rejection_summary(
    gen_dir: Path,
    arm: str,
    case_id: str,
    replicate: int,
) -> dict[str, Any]:
    path = gen_dir / arm / f"r{replicate:02d}__{case_id}.json"
    if not path.is_file():
        return {"available": False, "path": str(path)}
    doc = _read(path)
    reasons: Counter[str] = Counter()
    for stage in doc.get("transform_lineage") or ():
        for reason, count in (stage.get("rejections_by_reason") or {}).items():
            reasons[str(reason)] += int(count)
        if not stage.get("rejections_by_reason"):
            for rej in stage.get("rejections") or ():
                reasons[str(rej.get("reason") or "unknown")] += 1
    return {
        "available": True,
        "path": str(path),
        "rejections_by_reason": dict(reasons),
        "stages": [
            {
                "stage": stage.get("stage"),
                "hard_delete": stage.get("hard_delete"),
                "rejections_by_reason": stage.get("rejections_by_reason"),
                "n_active": len(stage.get("active_ids") or ()),
                "n_reserve": len(stage.get("reserve_ids") or ()),
                "n_pruned": len(stage.get("pruned_ids") or ()),
            }
            for stage in doc.get("transform_lineage") or ()
        ],
    }


def error_mode_cells(
    records: Sequence[Mapping[str, Any]],
    *,
    gen_dir: Path,
    arms: Sequence[str],
    baseline: str = BASELINE,
) -> dict[str, Any]:
    by = {
        (str(row["arm"]), str(row["case_id"]), int(row["replicate"])): row
        for row in records
    }
    payload: dict[str, Any] = {"baseline": baseline, "arms": {}}
    for arm in arms:
        cells = []
        for row in records:
            if row["arm"] != arm:
                continue
            case_id = str(row["case_id"])
            rep = int(row["replicate"])
            base = by.get((baseline, case_id, rep)) or {}
            source_tree = str(row.get("source_tree_arm") or arm)
            lineage = lineage_rejection_summary(
                gen_dir, source_tree, case_id, rep,
            )
            cells.append({
                "case_id": case_id,
                "replicate": rep,
                "loss_gate": row.get("loss_gate"),
                "actual_top1": row.get("actual_top1"),
                "actual_top2": row.get("actual_top2"),
                "baseline_top1": base.get("actual_top1"),
                "baseline_top2": base.get("actual_top2"),
                "top1_delta_vs_baseline": (
                    int(bool(row.get("actual_top1")))
                    - int(bool(base.get("actual_top1")))
                ),
                "top2_delta_vs_baseline": (
                    int(bool(row.get("actual_top2")))
                    - int(bool(base.get("actual_top2")))
                ),
                "active_gold_l2_coverage": row.get("active_gold_l2_coverage"),
                "inventory_gold_l2_coverage": row.get(
                    "inventory_gold_l2_coverage"
                ),
                "reserve_gold_present": row.get("reserve_gold_present"),
                "local_champion": row.get("local_champion"),
                "local_champion_ids": row.get("local_champion_ids"),
                "acceptable_l2": row.get("acceptable_l2"),
                "active_ids": row.get("active_ids"),
                "reserve_ids": row.get("reserve_ids"),
                "rank": row.get("rank"),
                "oracle_top2": row.get("oracle_top2"),
                "rescue_trace": row.get("rescue_trace"),
                "local_outputs_summary": row.get("local_outputs_summary"),
                "parent_valid_rate": row.get("parent_valid_rate"),
                "source_tree_arm": source_tree,
                "lineage": lineage,
            })
        # Aggregate failure modes for this arm
        fail_top2 = [
            cell for cell in cells if not cell.get("actual_top2")
        ]
        mode_counts = Counter(str(cell.get("loss_gate")) for cell in fail_top2)
        regress_top2 = [
            cell for cell in cells if cell.get("top2_delta_vs_baseline") < 0
        ]
        regress_top1 = [
            cell for cell in cells if cell.get("top1_delta_vs_baseline") < 0
        ]
        reason_totals: Counter[str] = Counter()
        for cell in cells:
            for reason, count in (
                (cell.get("lineage") or {}).get("rejections_by_reason") or {}
            ).items():
                reason_totals[str(reason)] += int(count)
        payload["arms"][arm] = {
            "n": len(cells),
            "top2_fail_by_gate": dict(mode_counts),
            "top2_regressions_vs_baseline": len(regress_top2),
            "top1_regressions_vs_baseline": len(regress_top1),
            "lineage_rejection_totals": dict(reason_totals),
            "cells": cells,
            "regression_top2_cells": [
                {
                    "case_id": cell["case_id"],
                    "replicate": cell["replicate"],
                    "loss_gate": cell["loss_gate"],
                    "reserve_gold_present": cell["reserve_gold_present"],
                    "local_champion": cell["local_champion"],
                }
                for cell in regress_top2
            ],
            "regression_top1_cells": [
                {
                    "case_id": cell["case_id"],
                    "replicate": cell["replicate"],
                    "loss_gate": cell["loss_gate"],
                    "rank": cell["rank"],
                }
                for cell in regress_top1
            ],
        }
    return payload


def paired_case_delta(
    case_rows: Sequence[Mapping[str, Any]],
    *,
    baseline: str,
    metric: str,
) -> dict[str, Any]:
    by = {(row["arm"], row["case_id"]): row for row in case_rows}
    deltas = []
    for arm, case_id in sorted({(a, c) for a, c in by if a != baseline}):
        base = by.get((baseline, case_id))
        target = by.get((arm, case_id))
        if not base or not target:
            continue
        bv = base.get(metric)
        tv = target.get(metric)
        if bv is None or tv is None:
            continue
        deltas.append({
            "arm": arm,
            "case_id": case_id,
            "baseline": float(bv),
            "target": float(tv),
            "delta": float(tv) - float(bv),
        })
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in deltas:
        by_arm[row["arm"]].append(row)
    summary = {}
    for arm, items in by_arm.items():
        vals = [item["delta"] for item in items]
        summary[arm] = {
            "n_cases": len(vals),
            "mean_delta": statistics.fmean(vals) if vals else None,
            "n_positive": sum(1 for value in vals if value > 0),
            "n_negative": sum(1 for value in vals if value < 0),
            "n_zero": sum(1 for value in vals if value == 0),
            "worst_cases": sorted(items, key=lambda r: r["delta"])[:5],
            "best_cases": sorted(items, key=lambda r: r["delta"], reverse=True)[:5],
        }
    return {"metric": metric, "baseline": baseline, "by_arm": summary}


def run(args: argparse.Namespace) -> dict[str, Any]:
    payload = _read(args.records)
    records_raw = payload.get("records") or payload
    audit = _read(args.judge)
    quality = quality_from_audit(audit)
    branch_q = quality_branch_index(audit)
    records = enrich_records(records_raw, quality, quality_by_branch=branch_q)
    means = case_means(records)
    arms = arm_performance(records)
    trans = transitions(records)
    experimental = [
        "A18-parent-safe",
        "A19-budget-safe",
        "A20-generation-v2",
        "A21-generation-v2+F4",
        "A22-adaptive-local-rescue",
    ]
    errors = error_mode_cells(
        records, gen_dir=args.generation_traces, arms=experimental,
    )
    case_delta_top1 = paired_case_delta(
        means, baseline=BASELINE, metric="actual_top1_mean",
    )
    case_delta_top2 = paired_case_delta(
        means, baseline=BASELINE, metric="actual_top2_mean",
    )
    quality_arm = []
    for row in arms:
        quality_arm.append({
            "arm": row["arm"],
            "parent_valid_pct": row["parent_valid_pct"],
            "parent_invalid_pct": row["parent_invalid_pct"],
            "active_parent_valid_pct": row["active_parent_valid_pct"],
            "active_parent_invalid_pct": row["active_parent_invalid_pct"],
            "leaf_clean_pct": row["leaf_clean_pct"],
            "dup_excess_pct": row["dup_excess_pct"],
        })

    out = args.output_dir
    _write(out / "arm_performance_canonical.json", {
        "schema_version": 1,
        "protocol_version": 2,
        "endpoint": "resilient_legacy_actual_top2",
        "aggregation": "pooled_51_cells_equals_mean_of_case_3run_means",
        "baseline": BASELINE,
        "rows": arms,
    })
    _write_tsv(out / "arm_performance_canonical.tsv", arms)
    _write(out / "case_means_3run.json", {
        "schema_version": 1,
        "aggregation": "mean_within_case_across_3_replicates",
        "rows": means,
    })
    _write_tsv(out / "case_means_3run.tsv", [
        {k: v for k, v in row.items() if k != "loss_gate_counts"}
        for row in means
    ])
    _write(out / "arm_case_transitions_vs_a_raw_v2.json", trans)
    _write(out / "error_mode_cells.json", errors)
    _write(out / "quality_by_arm.json", {"rows": quality_arm})
    _write(out / "case_delta_vs_a_raw_v2.json", {
        "actual_top1_mean": case_delta_top1,
        "actual_top2_mean": case_delta_top2,
    })
    _write(out / "enriched_records.json", {"records": records})

    return {
        "output_dir": str(out),
        "n_records": len(records),
        "n_case_means": len(means),
        "arms": len(arms),
        "quality_keys": len(quality),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS)
    parser.add_argument("--judge", type=Path, default=DEFAULT_JUDGE)
    parser.add_argument("--generation-traces", type=Path, default=DEFAULT_GEN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps({"status": "OK", **summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
