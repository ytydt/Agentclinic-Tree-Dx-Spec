#!/usr/bin/env python3
"""Offline paired analysis for E11 B07 retrieval x refine factorial."""
from __future__ import annotations

import argparse
import hashlib
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

from analysis.mechanism_v2.common import FrozenExactSynonymBridge, normalize_label  # noqa: E402
from analysis.mechanism_v2.e11_b07_factorial import (  # noqa: E402
    ARMS,
    BRIDGE_PATH,
    DEFAULT_OUT,
    RETRIEVALS,
    load_jobs,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


PRIMARY_CONTRASTS: tuple[tuple[str, str, str], ...] = (
    ("off_refine_off", "relevant_refine_off", "relevant_vs_off_without_refine"),
    ("random_refine_off", "relevant_refine_off", "relevant_vs_random_without_refine"),
    ("hard_negative_refine_off", "relevant_refine_off", "relevant_vs_hard_negative_without_refine"),
    ("off_refine_off", "off_refine_on", "refine_effect_with_retrieval_off"),
    ("relevant_refine_off", "relevant_refine_on", "refine_effect_with_relevant_retrieval"),
    ("random_refine_off", "random_refine_on", "refine_effect_with_random_context"),
    ("hard_negative_refine_off", "hard_negative_refine_on", "refine_effect_with_hard_negative_context"),
)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(left_only, right_only) + 1)
    )
    return min(1.0, 2.0 * tail / (2**discordant))


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    return float(ordered[lower] * (upper - position) + ordered[upper] * (position - lower))


def bootstrap_ci(
    values: Sequence[float], seed_key: str, repetitions: int = 10_000
) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(stable_seed("E11-bootstrap-v1", seed_key))
    n = len(values)
    estimates = [
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(repetitions)
    ]
    return [round(percentile(estimates, 0.025), 6), round(percentile(estimates, 0.975), 6)]


def load_arms(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    arms: dict[str, dict[str, dict[str, Any]]] = {}
    expected: set[str] | None = None
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        if len(rows) != 400:
            raise AssertionError(f"{arm} incomplete: {len(rows)}/400")
        by_key = {str(row["case_key"]): row for row in rows}
        if len(by_key) != 400:
            raise AssertionError(f"{arm} duplicate case keys")
        if expected is None:
            expected = set(by_key)
        elif set(by_key) != expected:
            raise AssertionError(f"{arm} case-set mismatch")
        arms[arm] = by_key
    return arms


def paired_contrast(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    endpoint: str,
    label: str,
    *,
    family: str | None = None,
    historical_gate: bool | None = None,
    repetitions: int = 10_000,
) -> dict[str, Any]:
    keys = sorted(set(arms[left]) & set(arms[right]))
    filtered: list[str] = []
    for key in keys:
        row = arms[left][key]
        if family is not None and str(row["family"]) != family:
            continue
        if historical_gate is not None and bool(row["historical_need_retrieval"]) != historical_gate:
            continue
        filtered.append(key)
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    ordered_flips = unordered_flips = 0
    jaccards: list[float] = []
    gain_keys: list[str] = []
    loss_keys: list[str] = []
    for key in filtered:
        before, after = arms[left][key], arms[right][key]
        before_value, after_value = bool(before[endpoint]), bool(after[endpoint])
        counts[(before_value, after_value)] += 1
        deltas.append(float(after_value) - float(before_value))
        if not before_value and after_value:
            gain_keys.append(key)
        elif before_value and not after_value:
            loss_keys.append(key)
        before_keys = list(before.get("top2_keys") or [])
        after_keys = list(after.get("top2_keys") or [])
        ordered_flips += before_keys != after_keys
        unordered_flips += set(before_keys) != set(after_keys)
        union = set(before_keys) | set(after_keys)
        jaccards.append(len(set(before_keys) & set(after_keys)) / len(union) if union else 1.0)
    left_only = counts[(True, False)]
    right_only = counts[(False, True)]
    n = len(filtered)
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "stratum": {
            "family": family or "all",
            "historical_need_retrieval": historical_gate if historical_gate is not None else "all",
        },
        "n": n,
        "both": counts[(True, True)],
        "left_only": left_only,
        "right_only": right_only,
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / n, 6) if n else None,
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas,
            f"{label}/{endpoint}/{family}/{historical_gate}",
            repetitions,
        ),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "ordered_top2_flip_n": ordered_flips,
        "unordered_top2_set_flip_n": unordered_flips,
        "mean_top2_jaccard": round(sum(jaccards) / len(jaccards), 6) if jaccards else None,
        "gain_case_keys": gain_keys,
        "loss_case_keys": loss_keys,
    }


def holm_adjust(records: Sequence[Mapping[str, Any]], field_name: str) -> list[dict[str, Any]]:
    output = [dict(record) for record in records]
    order = sorted(range(len(output)), key=lambda index: (float(output[index]["exact_mcnemar_p"]), index))
    prior = 0.0
    total = len(output)
    for rank, index in enumerate(order):
        value = min(1.0, (total - rank) * float(output[index]["exact_mcnemar_p"]))
        value = max(prior, value)
        output[index][field_name] = value
        prior = value
    return output


def _telemetry_by_payload(out: Path, arm: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(out / "arms" / arm / "telemetry.jsonl"):
        payload = str(row.get("payload_sha256") or "")
        if payload:
            records[payload] = row
    return records


def arm_statistics(
    out: Path, arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        rows = list(arms[arm].values())
        telemetry_rows = read_jsonl(out / "arms" / arm / "telemetry.jsonl")
        telemetry_by_payload = _telemetry_by_payload(out, arm)
        providers = Counter(
            provider for row in telemetry_rows for provider in (row.get("providers") or [])
        )
        provider_endpoint: dict[str, Any] = {}
        for provider in sorted(providers):
            joined = [
                row for row in rows
                if provider in (telemetry_by_payload.get(str(row.get("payload_sha256") or ""), {}).get("providers") or [])
            ]
            provider_endpoint[provider] = {
                "n_unique_payload_case_rows": len(joined),
                "strict_top1_n": sum(bool(row["gold_top1"]) for row in joined),
                "strict_top2_n": sum(bool(row["gold_top2"]) for row in joined),
            }
        output[arm] = {
            "n": len(rows),
            "success_n": sum(bool(row["success"]) for row in rows),
            "strict_top1_n": sum(bool(row["gold_top1"]) for row in rows),
            "strict_top1_rate": round(sum(bool(row["gold_top1"]) for row in rows) / len(rows), 6),
            "strict_top2_n": sum(bool(row["gold_top2"]) for row in rows),
            "strict_top2_rate": round(sum(bool(row["gold_top2"]) for row in rows) / len(rows), 6),
            "cache_hit_case_rows": sum(bool(row.get("cache_hit")) for row in rows),
            "unique_semantic_calls": sum(int(row.get("semantic_calls") or 0) for row in telemetry_rows),
            "physical_attempts": sum(int(row.get("physical_attempts") or 0) for row in telemetry_rows),
            "failed_semantic_calls": sum(not bool(row.get("success")) for row in telemetry_rows),
            "input_tokens": sum(int(row.get("input_tokens") or 0) for row in telemetry_rows),
            "output_tokens": sum(int(row.get("output_tokens") or 0) for row in telemetry_rows),
            "provider_response_counts": dict(sorted(providers.items())),
            "provider_endpoint_descriptive_only": provider_endpoint,
            "by_family": {
                family: {
                    "n": sum(str(row["family"]) == family for row in rows),
                    "strict_top1_n": sum(str(row["family"]) == family and bool(row["gold_top1"]) for row in rows),
                    "strict_top2_n": sum(str(row["family"]) == family and bool(row["gold_top2"]) for row in rows),
                }
                for family in ("DA", "MCR")
            },
            "by_historical_gate": {
                str(gate).lower(): {
                    "n": sum(bool(row["historical_need_retrieval"]) == gate for row in rows),
                    "strict_top1_n": sum(bool(row["historical_need_retrieval"]) == gate and bool(row["gold_top1"]) for row in rows),
                    "strict_top2_n": sum(bool(row["historical_need_retrieval"]) == gate and bool(row["gold_top2"]) for row in rows),
                }
                for gate in (False, True)
            },
        }
    return output


def refine_mechanisms(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for retrieval in RETRIEVALS:
        off_arm, on_arm = f"{retrieval}_refine_off", f"{retrieval}_refine_on"
        counts: Counter[str] = Counter()
        introduced_labels: Counter[str] = Counter()
        removed_labels: Counter[str] = Counter()
        for key in sorted(arms[off_arm]):
            before, after = arms[off_arm][key], arms[on_arm][key]
            left = list(before.get("top2_keys") or [])
            right = list(after.get("top2_keys") or [])
            left_set, right_set = set(left), set(right)
            if left == right:
                change = "unchanged"
            elif left_set == right_set:
                change = "reorder_only"
            elif len(left_set & right_set) == 1:
                change = "one_replacement"
            else:
                change = "full_replacement"
            counts[change] += 1
            counts["introduced_candidate_cases"] += bool(right_set - left_set)
            counts["deleted_candidate_cases"] += bool(left_set - right_set)
            counts["top1_changed"] += bool(left and right and left[0] != right[0])
            counts["strict_top1_gain"] += not bool(before["gold_top1"]) and bool(after["gold_top1"])
            counts["strict_top1_loss"] += bool(before["gold_top1"]) and not bool(after["gold_top1"])
            counts["strict_top2_gain"] += not bool(before["gold_top2"]) and bool(after["gold_top2"])
            counts["strict_top2_loss"] += bool(before["gold_top2"]) and not bool(after["gold_top2"])
            before_labels = {key_: label for key_, label in zip(left, before.get("top2_labels") or [])}
            after_labels = {key_: label for key_, label in zip(right, after.get("top2_labels") or [])}
            introduced_labels.update(str(after_labels[item]) for item in right_set - left_set if item in after_labels)
            removed_labels.update(str(before_labels[item]) for item in left_set - right_set if item in before_labels)
        output[retrieval] = {
            "counts": dict(sorted(counts.items())),
            "most_common_introduced_labels": introduced_labels.most_common(20),
            "most_common_removed_labels": removed_labels.most_common(20),
        }
    return output


def factorial_interactions(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]], repetitions: int
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for endpoint in ("gold_top1", "gold_top2"):
        for retrieval in RETRIEVALS[1:]:
            values: list[float] = []
            for key in sorted(arms["off_refine_off"]):
                off_effect = float(arms["off_refine_on"][key][endpoint]) - float(arms["off_refine_off"][key][endpoint])
                treatment_effect = float(arms[f"{retrieval}_refine_on"][key][endpoint]) - float(arms[f"{retrieval}_refine_off"][key][endpoint])
                values.append(treatment_effect - off_effect)
            output.append(
                {
                    "endpoint": endpoint,
                    "retrieval": retrieval,
                    "estimand": "refine effect under retrieval minus refine effect with retrieval off",
                    "n": len(values),
                    "difference_in_differences": round(sum(values) / len(values), 6),
                    "paired_bootstrap_ci95": bootstrap_ci(values, f"interaction/{endpoint}/{retrieval}", repetitions),
                }
            )
    return output


def historical_refine_comparison() -> dict[str, Any]:
    jobs, _ = load_jobs()
    counts: Counter[str] = Counter()
    for job in jobs:
        draft = [normalize_label(value) for value in job.get("historical_draft") or []]
        final = [normalize_label(value) for value in job.get("historical_final") or []]
        if draft == final:
            counts["ordered_equal"] += 1
        elif set(draft) == set(final):
            counts["reorder_only"] += 1
        elif len(set(draft) & set(final)) == 1:
            counts["one_replacement"] += 1
        else:
            counts["full_replacement_or_missing"] += 1
    return {
        "n": len(jobs),
        "counts": dict(sorted(counts.items())),
        "ordered_equal_rate": round(counts["ordered_equal"] / len(jobs), 6),
        "interpretation_boundary": "historical and E11 prompts/routing are not a paired causal comparison",
    }


def build_case_matrix(
    out: Path, arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(arms[ARMS[0]]):
        base = arms[ARMS[0]][key]
        rows.append(
            {
                "case_key": key,
                "family": base["family"],
                "historical_need_retrieval": bool(base["historical_need_retrieval"]),
                "reference_diagnosis": base["gold"],
                "arms": {
                    arm: {
                        "top2_labels": arms[arm][key]["top2_labels"],
                        "top2_keys": arms[arm][key]["top2_keys"],
                        "strict_top1": bool(arms[arm][key]["gold_top1"]),
                        "strict_top2": bool(arms[arm][key]["gold_top2"]),
                    }
                    for arm in ARMS
                },
                "any_strict_top1_discordance": len({bool(arms[arm][key]["gold_top1"]) for arm in ARMS}) > 1,
                "any_strict_top2_discordance": len({bool(arms[arm][key]["gold_top2"]) for arm in ARMS}) > 1,
                "any_refine_change": any(
                    bool(arms[f"{retrieval}_refine_on"][key].get("changed_from_draft"))
                    for retrieval in RETRIEVALS
                ),
            }
        )
    write_jsonl(out / "case_matrix.jsonl", rows)
    return rows


def analyze(out: Path, repetitions: int = 10_000) -> dict[str, Any]:
    arms = load_arms(out)
    primary_top1 = [
        paired_contrast(arms, left, right, "gold_top1", label, repetitions=repetitions)
        for left, right, label in PRIMARY_CONTRASTS
    ]
    primary_top1 = holm_adjust(primary_top1, "holm_adjusted_p_across_7_primary")
    secondary_top2 = [
        paired_contrast(arms, left, right, "gold_top2", label, repetitions=repetitions)
        for left, right, label in PRIMARY_CONTRASTS
    ]
    stratified: list[dict[str, Any]] = []
    for endpoint in ("gold_top1", "gold_top2"):
        for left, right, label in PRIMARY_CONTRASTS:
            for family in ("DA", "MCR"):
                stratified.append(
                    paired_contrast(
                        arms, left, right, endpoint, label,
                        family=family, repetitions=repetitions,
                    )
                )
            for gate in (False, True):
                stratified.append(
                    paired_contrast(
                        arms, left, right, endpoint, label,
                        historical_gate=gate, repetitions=repetitions,
                    )
                )
    matrix = build_case_matrix(out, arms)
    summary = {
        "experiment_id": "E11",
        "n_cases": len(matrix),
        "strict_endpoint_warning": "frozen exact/safe-synonym bridge is conservative; clinical results require root adjudication",
        "arm_statistics": arm_statistics(out, arms),
        "primary_top1_contrasts": primary_top1,
        "secondary_top2_contrasts": secondary_top2,
        "stratified_contrasts": stratified,
        "refine_mechanisms": refine_mechanisms(arms),
        "factorial_interactions": factorial_interactions(arms, repetitions),
        "historical_refine_comparison": historical_refine_comparison(),
        "case_level_discordance": {
            "any_strict_top1_discordance_n": sum(bool(row["any_strict_top1_discordance"]) for row in matrix),
            "any_strict_top2_discordance_n": sum(bool(row["any_strict_top2_discordance"]) for row in matrix),
            "any_refine_change_n": sum(bool(row["any_refine_change"]) for row in matrix),
        },
        "provider_caution": "actual provider is post-routing provenance, uneven across arms, and not an estimand; no provider-normalized reruns were performed",
    }
    atomic_json(out / "preaudit_analysis.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = analyze(args.out.resolve(), args.bootstrap_repetitions)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
