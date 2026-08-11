#!/usr/bin/env python3
"""Deep offline analysis and audit queues for completed E5 arms."""
from __future__ import annotations

import argparse
import csv
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
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import FrozenExactSynonymBridge, normalize_label  # noqa: E402
from analysis.mechanism_v2.e5_candidate_interference import (  # noqa: E402
    ADD_COMPONENT,
    ADD_PARENT,
    ADD_SIBLING,
    ADD_SYNONYM,
    ADD_UNRELATED,
    ARMS,
    BASE,
    BRIDGE_PATH,
    DEFAULT_OUT,
    REMOVE,
    WIDTH6,
    WIDTH8,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


PRIMARY_RIGHT_ARMS = tuple(arm for arm in ARMS if arm != BASE)
TYPED_ARMS = (ADD_PARENT, ADD_SIBLING, ADD_UNRELATED, ADD_SYNONYM, ADD_COMPONENT)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, index)
        for index in range(min(left_only, right_only) + 1)
    )
    return min(1.0, 2.0 * tail / (2**discordant))


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1.0 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    half = z * math.sqrt(
        proportion * (1 - proportion) / total + z * z / (4 * total * total)
    ) / denominator
    return [round(center - half, 6), round(center + half, 6)]


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def bootstrap_mean(
    values: Sequence[float], seed_key: str, repetitions: int = 10_000
) -> list[float]:
    if not values:
        return []
    rng = random.Random(stable_seed("E5-bootstrap-v1", seed_key))
    n = len(values)
    estimates = [
        sum(values[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(repetitions)
    ]
    return [
        round(percentile(estimates, 0.025), 6),
        round(percentile(estimates, 0.975), 6),
    ]


def candidate_ids(row: Mapping[str, Any]) -> list[str]:
    return [str(candidate["candidate_id"]) for candidate in row.get("candidates") or []]


def label_by_id(row: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(candidate["candidate_id"]): str(candidate.get("label") or "")
        for candidate in row.get("candidates") or []
    }


def index_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Mapping[str, Any]]]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    return indexed


def paired_contrast(
    rows: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
    seed_key: str,
    allowed_cases: set[str] | None = None,
) -> dict[str, Any]:
    counts: Counter[tuple[bool, bool]] = Counter()
    strict_deltas: list[float] = []
    rank_deltas: list[float] = []
    probability_deltas: list[float] = []
    champion_flips = 0
    new_champions = 0
    removed_left_champions = 0
    direct_harms = context_harms = removal_rescues = context_gains = 0
    new_champion_relations: Counter[str] = Counter()
    indexed = index_rows(rows)
    for case_key, arms in indexed.items():
        if allowed_cases is not None and case_key not in allowed_cases:
            continue
        if left not in arms or right not in arms:
            continue
        before, after = arms[left], arms[right]
        if not before.get("success") or not after.get("success"):
            continue
        before_hit = bool(before.get("strict_top1"))
        after_hit = bool(after.get("strict_top1"))
        counts[(before_hit, after_hit)] += 1
        strict_deltas.append(float(after_hit) - float(before_hit))
        if before.get("gold_rank") is not None and after.get("gold_rank") is not None:
            rank_deltas.append(float(after["gold_rank"]) - float(before["gold_rank"]))
        probability_deltas.append(
            float(after.get("top1_probability") or 0)
            - float(before.get("top1_probability") or 0)
        )
        before_ids = set(candidate_ids(before))
        after_ids = set(candidate_ids(after))
        new_ids = after_ids - before_ids
        removed_ids = before_ids - after_ids
        after_champion = str(after.get("champion_id") or "")
        before_champion = str(before.get("champion_id") or "")
        champion_flip = normalize_label(str(before.get("champion_label") or "")) != normalize_label(
            str(after.get("champion_label") or "")
        )
        champion_flips += int(champion_flip)
        if after_champion in new_ids:
            new_champions += 1
            new_champion_relations[str(after.get("champion_relation") or "unknown")] += 1
        if before_champion in removed_ids:
            removed_left_champions += 1
        if before_hit and not after_hit:
            if after_champion in new_ids:
                direct_harms += 1
            else:
                context_harms += 1
        elif not before_hit and after_hit:
            if before_champion in removed_ids:
                removal_rescues += 1
            else:
                context_gains += 1
    left_only = counts[(True, False)]
    right_only = counts[(False, True)]
    n = len(strict_deltas)
    return {
        "left": left,
        "right": right,
        "n_comparable": n,
        "left_only_harms": left_only,
        "right_only_gains": right_only,
        "both": counts[(True, True)],
        "neither": counts[(False, False)],
        "strict_delta_right_minus_left": round(sum(strict_deltas) / n, 6) if n else None,
        "strict_delta_bootstrap_95ci": bootstrap_mean(strict_deltas, seed_key + "/strict"),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "champion_flip_n": champion_flips,
        "champion_flip_rate": round(champion_flips / n, 6) if n else None,
        "new_candidate_champion_n": new_champions,
        "new_candidate_champion_relations": dict(sorted(new_champion_relations.items())),
        "removed_left_champion_n": removed_left_champions,
        "direct_new_candidate_harm_n": direct_harms,
        "shared_candidate_context_harm_n": context_harms,
        "removed_candidate_rescue_n": removal_rescues,
        "shared_candidate_context_gain_n": context_gains,
        "mean_gold_rank_delta": round(sum(rank_deltas) / len(rank_deltas), 6) if rank_deltas else None,
        "gold_rank_delta_bootstrap_95ci": bootstrap_mean(rank_deltas, seed_key + "/rank"),
        "mean_self_reported_top1_probability_delta": round(
            sum(probability_deltas) / len(probability_deltas), 6
        ) if probability_deltas else None,
        "probability_delta_bootstrap_95ci": bootstrap_mean(
            probability_deltas, seed_key + "/probability"
        ),
    }


def holm_adjust(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        (dict(record) for record in records),
        key=lambda record: (float(record["exact_mcnemar_p"]), str(record["right"])),
    )
    previous = 0.0
    total = len(ordered)
    for index, record in enumerate(ordered):
        adjusted = min(1.0, (total - index) * float(record["exact_mcnemar_p"]))
        previous = max(previous, adjusted)
        record["holm_adjusted_p_across_8_primary"] = previous
    return sorted(ordered, key=lambda record: PRIMARY_RIGHT_ARMS.index(str(record["right"])))


def arm_stats(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    served = [row for row in rows if row.get("success")]
    hits = sum(bool(row.get("strict_top1")) for row in served)
    intention = len(rows)
    return {
        "n_intention": intention,
        "n_served": len(served),
        "served_rate": round(len(served) / intention, 6) if intention else None,
        "failure_reasons": dict(
            sorted(Counter(str(row.get("error") or "") for row in rows if not row.get("success")).items())
        ),
        "strict_top1_n": hits,
        "strict_top1_rate_intention_failures_wrong": round(hits / intention, 6) if intention else None,
        "strict_top1_wilson95_intention": wilson(hits, intention),
        "strict_top1_rate_served": round(hits / len(served), 6) if served else None,
        "strict_top1_wilson95_served": wilson(hits, len(served)),
        "mean_gold_rank_served": round(
            sum(float(row["gold_rank"]) for row in served if row.get("gold_rank") is not None)
            / sum(row.get("gold_rank") is not None for row in served),
            6,
        ) if any(row.get("gold_rank") is not None for row in served) else None,
        "champion_relation_counts": dict(
            sorted(Counter(str(row.get("champion_relation") or "") for row in served).items())
        ),
    }


def group_analysis(
    rows: Sequence[Mapping[str, Any]], group: str, common_cases: set[str]
) -> dict[str, Any]:
    group_rows = list(rows) if group == "all" else [row for row in rows if row["family"] == group]
    group_case_keys = {str(row["case_key"]) for row in group_rows}
    common_group = common_cases & group_case_keys
    primary = [
        paired_contrast(group_rows, BASE, arm, f"{group}/{BASE}/{arm}")
        for arm in PRIMARY_RIGHT_ARMS
    ]
    if group == "all":
        primary = holm_adjust(primary)
    return {
        "arms": {
            arm: arm_stats([row for row in group_rows if row["arm"] == arm])
            for arm in ARMS
        },
        "primary_vs_base": primary,
        "width6_to_width8": paired_contrast(
            group_rows, WIDTH6, WIDTH8, f"{group}/{WIDTH6}/{WIDTH8}"
        ),
        "common_complete_case_n": len(common_group),
        "common_complete_arms": {
            arm: arm_stats([
                row for row in group_rows
                if row["arm"] == arm and str(row["case_key"]) in common_group
            ])
            for arm in ARMS
        },
        "common_complete_primary_vs_base": [
            paired_contrast(
                group_rows,
                BASE,
                arm,
                f"{group}/common/{BASE}/{arm}",
                allowed_cases=common_group,
            )
            for arm in PRIMARY_RIGHT_ARMS
        ],
    }


def order_integrity(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    indexed = index_rows(rows)
    comparisons = label_failures = relative_order_failures = 0
    gold_position_deltas: dict[str, Counter[int]] = defaultdict(Counter)
    for arms in indexed.values():
        base = arms.get(BASE)
        if not base or not base.get("success"):
            continue
        base_ids = candidate_ids(base)
        base_labels = label_by_id(base)
        base_gold = str((base.get("gold_candidate_ids") or [""])[0])
        for arm in PRIMARY_RIGHT_ARMS:
            after = arms.get(arm)
            if not after or not after.get("success"):
                continue
            comparisons += 1
            after_ids = candidate_ids(after)
            after_labels = label_by_id(after)
            shared_in_base = [candidate_id for candidate_id in base_ids if candidate_id in after_labels]
            shared_in_after = [candidate_id for candidate_id in after_ids if candidate_id in base_labels]
            label_failures += int(any(
                normalize_label(base_labels[candidate_id]) != normalize_label(after_labels[candidate_id])
                for candidate_id in set(base_labels) & set(after_labels)
            ))
            relative_order_failures += int(shared_in_base != shared_in_after)
            if base_gold in after_ids:
                gold_position_deltas[arm][after_ids.index(base_gold) - base_ids.index(base_gold)] += 1
    width_pairs = nesting_failures = width_order_failures = 0
    for arms in indexed.values():
        width6 = arms.get(WIDTH6)
        width8 = arms.get(WIDTH8)
        if not width6 or not width8 or not width6.get("success") or not width8.get("success"):
            continue
        width_pairs += 1
        ids6, ids8 = candidate_ids(width6), candidate_ids(width8)
        nesting_failures += int(not (set(ids6) < set(ids8) and len(set(ids8) - set(ids6)) == 2))
        width_order_failures += int(ids6 != [candidate_id for candidate_id in ids8 if candidate_id in set(ids6)])
    return {
        "base_to_arm_comparisons": comparisons,
        "shared_label_identity_failures": label_failures,
        "shared_relative_order_failures": relative_order_failures,
        "gold_absolute_position_delta_counts": {
            arm: {str(delta): count for delta, count in sorted(counter.items())}
            for arm, counter in sorted(gold_position_deltas.items())
        },
        "width6_width8_comparable_n": width_pairs,
        "width_nesting_failures": nesting_failures,
        "width_shared_relative_order_failures": width_order_failures,
    }


def position_selection_diagnostics(
    rows: Sequence[Mapping[str, Any]], repetitions: int = 50_000
) -> dict[str, Any]:
    """Post-hoc serial-position diagnostic under outcome-blind hash ordering."""
    output: dict[str, Any] = {"typed_single_injection": {}, "width_conditional_on_injected_champion": {}}
    for group in ("all", "DA", "MCR"):
        positions_by_arm: dict[str, list[int]] = {}
        selected_by_arm: dict[str, list[int]] = {}
        exposure_counts: Counter[int] = Counter()
        champion_counts: Counter[int] = Counter()
        for arm in TYPED_ARMS:
            positions: list[int] = []
            selected: list[int] = []
            for row in rows:
                if row["arm"] != arm or not row.get("success"):
                    continue
                if group != "all" and row["family"] != group:
                    continue
                injected = [
                    (index, candidate)
                    for index, candidate in enumerate(row["candidates"], 1)
                    if candidate.get("audit_relation")
                ]
                if len(injected) != 1:
                    raise AssertionError(f"typed arm has {len(injected)} injections: {arm}")
                position, candidate = injected[0]
                positions.append(position)
                exposure_counts[position] += 1
                if row["champion_id"] == candidate["candidate_id"]:
                    selected.append(position)
                    champion_counts[position] += 1
            positions_by_arm[arm] = positions
            selected_by_arm[arm] = selected
        n_selected = sum(len(values) for values in selected_by_arm.values())
        n_total = sum(len(values) for values in positions_by_arm.values())
        selected_sum = sum(sum(values) for values in selected_by_arm.values())
        total_sum = sum(sum(values) for values in positions_by_arm.values())
        observed = (
            selected_sum / n_selected - (total_sum - selected_sum) / (n_total - n_selected)
            if n_selected and n_total > n_selected else 0.0
        )
        rng = random.Random(stable_seed("E5-position-permutation-v1", group))
        extreme = 0
        for _ in range(repetitions):
            permuted_selected_sum = sum(
                sum(rng.sample(positions_by_arm[arm], len(selected_by_arm[arm])))
                for arm in TYPED_ARMS
            )
            statistic = (
                permuted_selected_sum / n_selected
                - (total_sum - permuted_selected_sum) / (n_total - n_selected)
            ) if n_selected and n_total > n_selected else 0.0
            extreme += int(abs(statistic) >= abs(observed) - 1e-12)
        output["typed_single_injection"][group] = {
            "n_exposures": n_total,
            "n_injected_champions": n_selected,
            "position_exposure_counts": {str(key): value for key, value in sorted(exposure_counts.items())},
            "position_champion_counts": {str(key): value for key, value in sorted(champion_counts.items())},
            "mean_position_champion": round(selected_sum / n_selected, 6) if n_selected else None,
            "mean_position_not_champion": round(
                (total_sum - selected_sum) / (n_total - n_selected), 6
            ) if n_total > n_selected else None,
            "mean_position_difference_champion_minus_other": round(observed, 6),
            "within_arm_permutation_two_sided_p": (extreme + 1) / (repetitions + 1),
            "repetitions": repetitions,
        }
    for arm in (WIDTH6, WIDTH8):
        output["width_conditional_on_injected_champion"][arm] = {}
        for group in ("all", "DA", "MCR"):
            events: list[tuple[list[int], int]] = []
            for row in rows:
                if row["arm"] != arm or not row.get("success"):
                    continue
                if group != "all" and row["family"] != group:
                    continue
                if row.get("champion_relation") != "width_distractor":
                    continue
                available = [
                    index for index, candidate in enumerate(row["candidates"], 1)
                    if candidate.get("audit_relation") == "width_distractor"
                ]
                champion_position = next(
                    index for index, candidate in enumerate(row["candidates"], 1)
                    if candidate["candidate_id"] == row["champion_id"]
                )
                events.append((available, champion_position))
            observed = sum(
                champion - sum(available) / len(available)
                for available, champion in events
            ) / len(events) if events else 0.0
            rng = random.Random(stable_seed("E5-width-position-permutation-v1", arm, group))
            extreme = 0
            for _ in range(repetitions):
                statistic = sum(
                    rng.choice(available) - sum(available) / len(available)
                    for available, _champion in events
                ) / len(events) if events else 0.0
                extreme += int(abs(statistic) >= abs(observed) - 1e-12)
            output["width_conditional_on_injected_champion"][arm][group] = {
                "n_injected_champion_events": len(events),
                "mean_champion_position_minus_available_mean": round(observed, 6),
                "within_case_random_position_two_sided_p": (extreme + 1) / (repetitions + 1),
                "repetitions": repetitions,
            }
    output["caveat"] = (
        "Post-hoc diagnostic: hash ordering is outcome blind, but position was not a randomized experimental arm; "
        "candidate semantics and position can still be associated by chance. Width tests condition on an injected champion."
    )
    return output


def construction_analysis(
    root: Path, bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    rows = read_jsonl(root / "perturbations" / "case_perturbations.jsonl")
    successful = [row for row in rows if row.get("success")]
    base_by_case = {
        str(result["case_key"]): result
        for result in read_jsonl(root / "arms" / BASE / "case_results.jsonl")
    }
    bridge_hits: list[dict[str, str]] = []
    for row in successful:
        response = row.get("response") or {}
        synonym = next(
            item for item in response.get("perturbations") or []
            if str(item.get("relation")) == "synonym"
        )
        # Gold is intentionally absent from construction result rows; recover it
        # from the base selector row, which is immutable and already frozen.
        gold = str(base_by_case[str(row["case_key"])]["gold"])
        if bridge.equivalent(str(synonym.get("label") or ""), gold):
            bridge_hits.append({
                "case_key": str(row["case_key"]),
                "gold": gold,
                "injected_synonym": str(synonym.get("label") or ""),
            })
    return {
        "n": len(rows),
        "success_n": len(successful),
        "success_by_family": dict(sorted(Counter(row["family"] for row in successful).items())),
        "failure_by_family": dict(sorted(Counter(row["family"] for row in rows if not row.get("success")).items())),
        "failure_reasons": dict(sorted(Counter(
            str(row.get("error") or "") for row in rows if not row.get("success")
        ).items())),
        "frozen_semantic_sample_n": len(read_jsonl(root / "perturbation_audit_sample.jsonl")),
        "frozen_semantic_candidate_judgments_n": 9 * len(
            read_jsonl(root / "perturbation_audit_sample.jsonl")
        ),
        "synonym_bridge_recognized_n": len(bridge_hits),
        "synonym_bridge_recognized": bridge_hits,
    }


def telemetry_analysis(root: Path) -> dict[str, Any]:
    phases = {"perturbation_construction": root / "perturbations"}
    phases.update({arm: root / "arms" / arm for arm in ARMS})
    output: dict[str, Any] = {}
    totals: Counter[str] = Counter()
    provider_union: set[str] = set()
    for phase, directory in phases.items():
        summary = json.loads((directory / "telemetry_summary.json").read_text(encoding="utf-8"))
        semantic = int(summary.get("semantic_calls") or 0)
        physical = int(summary.get("physical_attempts") or 0)
        phase_summary = dict(summary)
        phase_summary["physical_per_semantic"] = round(physical / semantic, 6) if semantic else None
        phase_summary["output_tokens_per_semantic"] = round(
            int(summary.get("output_tokens") or 0) / semantic, 3
        ) if semantic else None
        output[phase] = phase_summary
        provider_union.update(str(provider) for provider in summary.get("providers") or [])
        for key in (
            "semantic_calls", "physical_attempts", "input_tokens", "output_tokens",
            "failed_semantic_calls",
        ):
            totals[key] += int(summary.get(key) or 0)
        totals["latency_seconds_sum_milli"] += int(
            round(float(summary.get("latency_seconds_sum") or 0) * 1000)
        )
    return {
        "phases": output,
        "totals": {
            **{key: value for key, value in totals.items() if key != "latency_seconds_sum_milli"},
            "latency_seconds_sum": round(totals["latency_seconds_sum_milli"] / 1000, 3),
            "provider_union": sorted(provider_union),
        },
        "cost_note": "No provider-price field was captured; token and latency totals are auditable, monetary cost is not reconstructed.",
    }


def transition_class(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    before_hit = bool(before.get("strict_top1"))
    after_hit = bool(after.get("strict_top1"))
    before_ids, after_ids = set(candidate_ids(before)), set(candidate_ids(after))
    after_new = str(after.get("champion_id") or "") in (after_ids - before_ids)
    before_removed = str(before.get("champion_id") or "") in (before_ids - after_ids)
    if before_hit and not after_hit:
        return "direct_new_candidate_harm" if after_new else "shared_candidate_context_harm"
    if not before_hit and after_hit:
        return "removed_candidate_rescue" if before_removed else "shared_candidate_context_gain"
    if after_new:
        return "new_candidate_champion_without_strict_flip"
    if normalize_label(str(before.get("champion_label") or "")) != normalize_label(
        str(after.get("champion_label") or "")
    ):
        return "shared_candidate_champion_flip_without_strict_flip"
    return "stable_champion"


def make_audit_queue(root: Path, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed = index_rows(rows)
    queue: list[dict[str, Any]] = []
    for case_key, arms in indexed.items():
        before = arms[BASE]
        for arm in PRIMARY_RIGHT_ARMS:
            after = arms[arm]
            if not before.get("success") or not after.get("success"):
                continue
            category = transition_class(before, after)
            if category == "stable_champion":
                continue
            queue.append({
                "record_type": "selector_transition",
                "case_key": case_key,
                "family": before["family"],
                "arm": arm,
                "transition_class": category,
                "gold": before["gold"],
                "vignette": before["vignette"],
                "base_candidates": before["candidates"],
                "arm_candidates": after["candidates"],
                "before": {
                    "strict_top1": before["strict_top1"],
                    "champion_id": before["champion_id"],
                    "champion_label": before["champion_label"],
                    "gold_rank": before["gold_rank"],
                    "response": before["response"],
                },
                "after": {
                    "strict_top1": after["strict_top1"],
                    "champion_id": after["champion_id"],
                    "champion_label": after["champion_label"],
                    "champion_relation": after["champion_relation"],
                    "gold_rank": after["gold_rank"],
                    "response": after["response"],
                },
            })
    for case in read_jsonl(root / "perturbation_audit_sample.jsonl"):
        for item in case["perturbations"]:
            queue.append({
                "record_type": "frozen_construction_semantic_judgment",
                "case_key": case["case_key"],
                "family": case["family"],
                "gold": case["gold"],
                "vignette": case["vignette"],
                "base_candidates": case["base_candidates"],
                "claimed_relation": item["relation"],
                "candidate_label": item["label"],
                "builder_rationale": item["rationale"],
            })
        for index, item in enumerate(case["width_distractors"], 1):
            queue.append({
                "record_type": "frozen_construction_semantic_judgment",
                "case_key": case["case_key"],
                "family": case["family"],
                "gold": case["gold"],
                "vignette": case["vignette"],
                "base_candidates": case["base_candidates"],
                "claimed_relation": f"width_distractor_{index}",
                "candidate_label": item["label"],
                "builder_rationale": item["rationale"],
            })
    queue.sort(key=lambda row: (
        str(row["record_type"]),
        stable_seed("E5-audit-order-v1", str(row["case_key"]), str(row.get("arm") or "")),
        str(row["case_key"]),
        str(row.get("claimed_relation") or ""),
    ))
    write_jsonl(root / "audit_queue.jsonl", queue)
    return queue


def write_transition_csv(
    root: Path, rows: Sequence[Mapping[str, Any]]
) -> int:
    indexed = index_rows(rows)
    output: list[dict[str, Any]] = []
    for case_key, arms in sorted(indexed.items()):
        before = arms[BASE]
        for arm in PRIMARY_RIGHT_ARMS:
            after = arms[arm]
            if not before.get("success") or not after.get("success"):
                continue
            category = transition_class(before, after)
            if category == "stable_champion":
                continue
            output.append({
                "case_key": case_key,
                "family": before["family"],
                "arm": arm,
                "transition_class": category,
                "gold": before["gold"],
                "base_champion": before["champion_label"],
                "arm_champion": after["champion_label"],
                "arm_champion_relation": after["champion_relation"],
                "base_hit": before["strict_top1"],
                "arm_hit": after["strict_top1"],
                "base_gold_rank": before["gold_rank"],
                "arm_gold_rank": after["gold_rank"],
            })
    fields = list(output[0])
    with (root / "transition_discordances.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)
    return len(output)


def analyse(root: Path) -> dict[str, Any]:
    rows = read_jsonl(root / "case_conditions.jsonl")
    if len(rows) != 200 * len(ARMS):
        raise AssertionError(f"E5 joined table incomplete: {len(rows)}")
    indexed = index_rows(rows)
    if len(indexed) != 200 or any(set(arms) != set(ARMS) for arms in indexed.values()):
        raise AssertionError("E5 case-arm matrix is not rectangular")
    common_cases = {
        case_key for case_key, arms in indexed.items()
        if all(bool(arms[arm].get("success")) for arm in ARMS)
    }
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    groups = {
        group: group_analysis(rows, group, common_cases)
        for group in ("all", "DA", "MCR")
    }
    queue = make_audit_queue(root, rows)
    transition_n = write_transition_csv(root, rows)
    summary = {
        "experiment_id": "E5",
        "n_cases": len(indexed),
        "n_conditions": len(rows),
        "groups": groups,
        "construction": construction_analysis(root, bridge),
        "candidate_identity_and_order_integrity": order_integrity(rows),
        "serial_position_diagnostics": position_selection_diagnostics(rows),
        "telemetry": telemetry_analysis(root),
        "audit_queue": {
            "total_n": len(queue),
            "selector_transition_n": sum(row["record_type"] == "selector_transition" for row in queue),
            "frozen_construction_judgment_n": sum(
                row["record_type"] == "frozen_construction_semantic_judgment" for row in queue
            ),
            "transition_csv_n": transition_n,
        },
        "analysis_contract": [
            "The eight all-case base contrasts are preregistered primary comparisons and receive Holm correction as one family.",
            "DA/MCR, common-complete-case, and width6-to-width8 analyses are mechanism diagnostics; raw p-values are not confirmation claims.",
            "Intention rates count failed conditions as not correct; paired contrasts use only successful pairs and explicitly report n.",
            "Strict bridge scoring remains frozen. Manual semantic adjudication is reported separately and never silently overwrites it.",
            "Direct harm means the newly added candidate became champion; context harm means a shared candidate became champion after set mutation.",
            "Single calls cannot identify provider/run stochasticity case by case; repeated-run and provider standardisation controls were excluded by task scope.",
        ],
    }
    atomic_json(root / "analysis_summary.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    summary = analyse(args.root.resolve())
    print(json.dumps({
        "common_complete": summary["groups"]["all"]["common_complete_case_n"],
        "primary": [
            {
                "right": row["right"],
                "n": row["n_comparable"],
                "delta": row["strict_delta_right_minus_left"],
                "p": row["exact_mcnemar_p"],
                "holm_p": row.get("holm_adjusted_p_across_8_primary"),
            }
            for row in summary["groups"]["all"]["primary_vs_base"]
        ],
        "width6_to_width8": summary["groups"]["all"]["width6_to_width8"],
        "audit_queue": summary["audit_queue"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
