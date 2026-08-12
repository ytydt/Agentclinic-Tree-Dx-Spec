#!/usr/bin/env python3
"""Paired strict-endpoint and trajectory analysis for E12.

The script is offline-only.  It freezes the preregistered 39-comparison
family, an incremental call-depth family, common-support sensitivity analyses,
runtime burden, and a deterministic root-audit queue.  Clinical equivalence is
handled separately by ``e12_semantic_screen.py`` and root adjudication.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.e12_e7_factorial import (  # noqa: E402
    ARMS,
    BRIDGE_PATH,
    DEFAULT_OUT,
    MAIN_ARMS,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


REPRESENTATIONS = ("raw", "s1", "graph")
WIDTHS = (5, 10)
COMPARATORS = ("first", "pointwise", "pairwise")


def exact_mcnemar(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(left_only, right_only) + 1))
    return min(1.0, 2.0 * tail / (2**n))


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (hi - position) + ordered[hi] * (position - lo))


def bootstrap_ci(
    deltas: Sequence[float], seed_key: str, repetitions: int = 10_000
) -> list[float] | None:
    if not deltas:
        return None
    rng = random.Random(stable_seed("E12-bootstrap-v1", seed_key))
    n = len(deltas)
    estimates = [
        sum(deltas[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(repetitions)
    ]
    return [round(_percentile(estimates, 0.025), 6), round(_percentile(estimates, 0.975), 6)]


def holm_adjust(records: Sequence[Mapping[str, Any]], field: str) -> list[dict[str, Any]]:
    output = [dict(row) for row in records]
    order = sorted(
        range(len(output)),
        key=lambda i: (float(output[i]["exact_mcnemar_p"]), str(output[i]["label"])),
    )
    previous = 0.0
    total = len(output)
    for rank, index in enumerate(order):
        adjusted = min(1.0, (total - rank) * float(output[index]["exact_mcnemar_p"]))
        adjusted = max(previous, adjusted)
        output[index][field] = adjusted
        previous = adjusted
    return output


def primary_contrasts() -> list[tuple[str, str, str]]:
    records: list[tuple[str, str, str]] = []
    for width in WIDTHS:
        for comparator in COMPARATORS:
            records.append((
                f"s1_k{width}_{comparator}",
                f"raw_k{width}_{comparator}",
                f"raw_vs_s1_k{width}_{comparator}",
            ))
            records.append((
                f"s1_k{width}_{comparator}",
                f"graph_k{width}_{comparator}",
                f"graph_vs_s1_k{width}_{comparator}",
            ))
    for representation in REPRESENTATIONS:
        for comparator in COMPARATORS:
            records.append((
                f"{representation}_k5_{comparator}",
                f"{representation}_k10_{comparator}",
                f"k10_vs_k5_{representation}_{comparator}",
            ))
    for representation in REPRESENTATIONS:
        for width in WIDTHS:
            for comparator in ("pointwise", "pairwise"):
                records.append((
                    f"{representation}_k{width}_first",
                    f"{representation}_k{width}_{comparator}",
                    f"{comparator}_vs_first_{representation}_k{width}",
                ))
            records.append((
                f"{representation}_k{width}_pointwise",
                f"{representation}_k{width}_pairwise",
                f"pairwise_vs_pointwise_{representation}_k{width}",
            ))
    if len(records) != 39 or len({row[2] for row in records}) != 39:
        raise AssertionError("E12 preregistered contrast family must contain 39 unique rows")
    return records


INCREMENTAL_CONTRASTS: tuple[tuple[str, str, str], ...] = (
    ("raw_depth1_k10_pairwise", "raw_depth2_k10_pairwise", "depth2_vs_depth1"),
    ("raw_depth2_k10_pairwise", "raw_k10_pairwise", "depth3_vs_depth2"),
)


def load_arms(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    expected: set[str] | None = None
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        by_key = {str(row["case_key"]): row for row in rows}
        if len(rows) != 300 or len(by_key) != 300:
            raise AssertionError(f"{arm}: expected 300 unique rows")
        if expected is None:
            expected = set(by_key)
        elif set(by_key) != expected:
            raise AssertionError(f"{arm}: case set mismatch")
        output[arm] = by_key
    return output


def strict_value(row: Mapping[str, Any], endpoint: str, bridge: FrozenExactSynonymBridge) -> bool:
    if endpoint == "top1":
        return bool(row["gold_top1"])
    if endpoint == "top2":
        return bool(row["gold_top1"]) or (
            bool(row["success"])
            and bridge.equivalent(str(row.get("runner_up_label") or ""), str(row["gold"]))
        )
    raise ValueError(endpoint)


def paired_contrast(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    label: str,
    endpoint: str,
    bridge: FrozenExactSynonymBridge,
    repetitions: int,
    *,
    common_support: bool,
) -> dict[str, Any]:
    keys = sorted(set(arms[left]) & set(arms[right]))
    if common_support:
        keys = [
            key for key in keys
            if bool(arms[left][key]["success"]) and bool(arms[right][key]["success"])
        ]
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    gains: list[str] = []
    losses: list[str] = []
    champion_flips: list[str] = []
    for key in keys:
        before = strict_value(arms[left][key], endpoint, bridge)
        after = strict_value(arms[right][key], endpoint, bridge)
        counts[(before, after)] += 1
        deltas.append(float(after) - float(before))
        if not before and after:
            gains.append(key)
        elif before and not after:
            losses.append(key)
        if normalize_label(str(arms[left][key].get("champion_label") or "")) != normalize_label(
            str(arms[right][key].get("champion_label") or "")
        ):
            champion_flips.append(key)
    left_only, right_only = counts[(True, False)], counts[(False, True)]
    n = len(keys)
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "analysis_set": "common_success" if common_support else "intention_to_analyse",
        "n": n,
        "both": counts[(True, True)],
        "left_only": left_only,
        "right_only": right_only,
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / n, 6) if n else None,
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas, f"{label}/{endpoint}/{common_support}", repetitions
        ),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "gain_case_keys": gains,
        "loss_case_keys": losses,
        "champion_flip_n": len(champion_flips),
        "champion_flip_case_keys": champion_flips,
    }


def arm_statistics(
    out: Path,
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    bridge: FrozenExactSynonymBridge,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        rows = list(arms[arm].values())
        telemetry = read_jsonl(out / "arms" / arm / "telemetry.jsonl")
        error_counts = Counter(str(row.get("error") or "") for row in rows if not row["success"])
        output[arm] = {
            "n": len(rows),
            "success_n": sum(bool(row["success"]) for row in rows),
            "failure_n": sum(not bool(row["success"]) for row in rows),
            "failure_reasons": dict(sorted(error_counts.items())),
            "strict_top1_n": sum(strict_value(row, "top1", bridge) for row in rows),
            "strict_top2_n": sum(strict_value(row, "top2", bridge) for row in rows),
            "strict_exposure_n": sum(bool(row["gold_exposure_hit"]) for row in rows),
            "champion_unique_n": len({normalize_label(str(row.get("champion_label") or "")) for row in rows if row["success"]}),
            "semantic_calls": sum(int(row.get("semantic_calls") or 0) for row in telemetry),
            "physical_attempts": sum(int(row.get("physical_attempts") or 0) for row in telemetry),
            "input_tokens": sum(int(row.get("input_tokens") or 0) for row in telemetry),
            "output_tokens": sum(int(row.get("output_tokens") or 0) for row in telemetry),
            "providers": sorted({str(provider) for row in telemetry for provider in (row.get("providers") or [])}),
            "by_family": {
                family: {
                    "n": sum(str(row["family"]) == family for row in rows),
                    "success_n": sum(str(row["family"]) == family and bool(row["success"]) for row in rows),
                    "strict_top1_n": sum(str(row["family"]) == family and strict_value(row, "top1", bridge) for row in rows),
                    "strict_top2_n": sum(str(row["family"]) == family and strict_value(row, "top2", bridge) for row in rows),
                }
                for family in ("DA", "MCR")
            },
        }
    return output


def pool_and_incremental_statistics(
    out: Path,
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    fixed = read_jsonl(out / "fixed_inputs.jsonl")
    transitions: dict[str, Any] = {}
    for left_key, right_key, label in (
        ("depth1_k10", "depth2_k10", "depth2_vs_depth1"),
        ("depth2_k10", "depth3_k10", "depth3_vs_depth2"),
        ("depth3_k5", "depth3_k10", "k10_vs_k5"),
    ):
        added_counts: list[int] = []
        displaced_counts: list[int] = []
        changed_pool: list[str] = []
        strict_exposure_gains: list[str] = []
        strict_exposure_losses: list[str] = []
        for row in fixed:
            left = row["pools"][left_key]
            right = row["pools"][right_key]
            lset = set(left["candidate_ids_by_priority"])
            rset = set(right["candidate_ids_by_priority"])
            added_counts.append(len(rset - lset))
            displaced_counts.append(len(lset - rset))
            if lset != rset:
                changed_pool.append(str(row["case_key"]))
            gold = bool(
                arms[
                    "raw_depth1_k10_pairwise" if left_key == "depth1_k10"
                    else "raw_depth2_k10_pairwise" if left_key == "depth2_k10"
                    else "raw_k5_first"
                ][str(row["case_key"])]["gold_exposure_hit"]
            )
            right_gold = bool(
                arms[
                    "raw_depth2_k10_pairwise" if right_key == "depth2_k10"
                    else "raw_k10_pairwise" if right_key == "depth3_k10"
                    else "raw_k10_first"
                ][str(row["case_key"])]["gold_exposure_hit"]
            )
            if not gold and right_gold:
                strict_exposure_gains.append(str(row["case_key"]))
            elif gold and not right_gold:
                strict_exposure_losses.append(str(row["case_key"]))
        transitions[label] = {
            "changed_pool_case_n": len(changed_pool),
            "changed_pool_case_keys": changed_pool,
            "new_candidate_total": sum(added_counts),
            "displaced_candidate_total": sum(displaced_counts),
            "mean_new_candidates": round(sum(added_counts) / len(added_counts), 6),
            "mean_displaced_candidates": round(sum(displaced_counts) / len(displaced_counts), 6),
            "strict_exposure_gain_case_keys": strict_exposure_gains,
            "strict_exposure_loss_case_keys": strict_exposure_losses,
        }
    return {
        "transitions": transitions,
        "historical_s3_unmatched_case_n": sum(bool(row["s3_unmatched_labels"]) for row in fixed),
        "historical_s3_unmatched_label_n": sum(len(row["s3_unmatched_labels"]) for row in fixed),
        "historical_s3_unmatched": [
            {"case_key": row["case_key"], "labels": row["s3_unmatched_labels"]}
            for row in fixed if row["s3_unmatched_labels"]
        ],
    }


def build_audit_queue(
    out: Path,
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    strict: Mapping[str, Any],
) -> list[dict[str, Any]]:
    fixed = {str(row["case_key"]): row for row in read_jsonl(out / "fixed_inputs.jsonl")}
    reasons: defaultdict[str, set[str]] = defaultdict(set)
    for endpoint in ("top1", "top2"):
        for record in strict["primary"][endpoint]["intention_to_analyse"]:
            for key in record["gain_case_keys"] + record["loss_case_keys"]:
                reasons[key].add(f"strict_{endpoint}_discordance")
        for record in strict["incremental"][endpoint]["intention_to_analyse"]:
            for key in record["gain_case_keys"] + record["loss_case_keys"]:
                reasons[key].add(f"incremental_strict_{endpoint}_discordance")
    for key in fixed:
        if any(bool(arms[arm][key]["gold_exposure_hit"]) for arm in ARMS):
            reasons[key].add("strict_reference_exposure")
        if fixed[key]["s3_unmatched_labels"]:
            reasons[key].add("historical_s3_created_candidate_absent_from_s2")
        for arm in ARMS:
            row = arms[arm][key]
            if not row["success"] and row["error"] != "frozen E6 typed graph unavailable; fail closed":
                reasons[key].add("online_schema_or_transport_failure")
    # Mechanism sample: champion flips that do not already enter by endpoint.
    sample_axes = (
        ("raw_k10_pairwise", "s1_k10_pairwise", "raw_vs_s1"),
        ("s1_k10_pairwise", "graph_k10_pairwise", "graph_vs_s1"),
        ("raw_k5_pairwise", "raw_k10_pairwise", "width"),
        ("raw_k10_pointwise", "raw_k10_pairwise", "comparator"),
        ("raw_depth1_k10_pairwise", "raw_depth2_k10_pairwise", "call2"),
        ("raw_depth2_k10_pairwise", "raw_k10_pairwise", "call3"),
    )
    for left, right, axis in sample_axes:
        for family in ("DA", "MCR"):
            pool = [
                key for key in sorted(fixed)
                if fixed[key]["family"] == family
                and arms[left][key]["success"] and arms[right][key]["success"]
                and normalize_label(str(arms[left][key]["champion_label"]))
                != normalize_label(str(arms[right][key]["champion_label"]))
                and key not in reasons
            ]
            selected = sorted(
                pool,
                key=lambda key: (stable_seed("E12-mechanism-audit-v1", axis, family, key), key),
            )[:5]
            for key in selected:
                reasons[key].add(f"frozen_nonendpoint_champion_flip_sample:{axis}")
    queue: list[dict[str, Any]] = []
    for key in sorted(reasons):
        job = fixed[key]
        arm_view = {
            arm: {
                "success": arms[arm][key]["success"],
                "error": arms[arm][key]["error"],
                "champion_id": arms[arm][key]["champion_id"],
                "champion_label": arms[arm][key]["champion_label"],
                "runner_up_label": arms[arm][key]["runner_up_label"],
                "gold_top1": arms[arm][key]["gold_top1"],
                "gold_exposure_hit": arms[arm][key]["gold_exposure_hit"],
            }
            for arm in ARMS
        }
        queue.append({
            "case_key": key,
            "family": job["family"],
            "gold": arms["raw_k5_first"][key]["gold"],
            "vignette": job["representations"]["raw"]["content"],
            "representations": job["representations"],
            "pools": job["pools"],
            "s2_calls": job["s2_calls"],
            "historical_s3_labels": job["historical_s3_labels"],
            "s3_unmatched_labels": job["s3_unmatched_labels"],
            "arm_outcomes": arm_view,
            "queue_reasons": sorted(reasons[key]),
        })
    return queue


def analyze(out: Path, repetitions: int) -> dict[str, Any]:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    arms = load_arms(out)
    primary: dict[str, Any] = {}
    incremental: dict[str, Any] = {}
    for endpoint in ("top1", "top2"):
        primary[endpoint] = {}
        for common in (False, True):
            rows = [
                paired_contrast(arms, left, right, label, endpoint, bridge, repetitions, common_support=common)
                for left, right, label in primary_contrasts()
            ]
            key = "common_success" if common else "intention_to_analyse"
            primary[endpoint][key] = holm_adjust(rows, "holm_adjusted_p_across_39")
        incremental[endpoint] = {}
        for common in (False, True):
            rows = [
                paired_contrast(arms, left, right, label, endpoint, bridge, repetitions, common_support=common)
                for left, right, label in INCREMENTAL_CONTRASTS
            ]
            key = "common_success" if common else "intention_to_analyse"
            incremental[endpoint][key] = holm_adjust(rows, "holm_adjusted_p_across_2")
    strict = {"primary": primary, "incremental": incremental}
    queue = build_audit_queue(out, arms, strict)
    write_jsonl(out / "root_audit_queue.jsonl", queue)
    summary = {
        "experiment_id": "E12",
        "bootstrap_repetitions": repetitions,
        "strict": strict,
        "arms": arm_statistics(out, arms, bridge),
        "pool_and_incremental": pool_and_incremental_statistics(out, arms),
        "root_audit_queue": {
            "n": len(queue),
            "reason_counts": dict(sorted(Counter(reason for row in queue for reason in row["queue_reasons"]).items())),
            "sha256": file_sha256(out / "root_audit_queue.jsonl"),
        },
        "limitations": [
            "Strict matching is exact/frozen-safe-synonym and is not the final clinical-equivalence endpoint.",
            "Graph online cells have 42 preregistered fail-closed E6 construction failures; common-success is a sensitivity analysis.",
            "Historical S2 lacks a shared evidence ledger, so incremental evidence novelty is unidentified.",
            "Provider associations are descriptive and not causal because routing was not randomized.",
        ],
    }
    atomic_json(out / "strict_analysis.json", summary)
    (out / "analysis_run.log").write_text(
        "E12 strict paired analysis completed\n"
        f"bootstrap_repetitions={repetitions}\n"
        f"primary_contrasts={len(primary_contrasts())}\n"
        f"root_audit_queue_n={len(queue)}\n",
        encoding="utf-8",
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyze(args.out.resolve(), args.bootstrap_repetitions)
    print(json.dumps({
        "primary_contrasts": len(result["strict"]["primary"]["top1"]["intention_to_analyse"]),
        "audit_queue": result["root_audit_queue"]["n"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
