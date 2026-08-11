#!/usr/bin/env python3
"""Frozen post-run analysis for E7c directional registry treatments.

The online runner intentionally writes only design-near summaries.  This file
adds failure-as-incorrect intention-to-analyse (ITA), complete-relation-case
sensitivity, relation-type heterogeneity and cache-aware telemetry allocation.
It never calls a model and never changes an online cache record.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, normalize_label  # noqa: E402
from analysis.mechanism_v2.e7c_directional_registry import (  # noqa: E402
    ARM_BOUNDED,
    ARM_DIRECTIONAL,
    ARM_EXACT,
    ARM_GENERIC,
    ARMS,
    build_relation_graph,
    make_selector_payload,
)
from analysis.mechanism_v2.online_runner import read_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E7c_directional_registry"
PRIMARY_COMPARISONS = (
    (ARM_DIRECTIONAL, ARM_EXACT),
    (ARM_BOUNDED, ARM_DIRECTIONAL),
    (ARM_BOUNDED, ARM_EXACT),
    (ARM_GENERIC, ARM_EXACT),
)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    total = int(left_only) + int(right_only)
    if total == 0:
        return 1.0
    lower = min(int(left_only), int(right_only))
    numerator = sum(math.comb(total, index) for index in range(lower + 1))
    return min(1.0, 2.0 * numerator / (2**total))


def bootstrap_delta_ci(
    paired: Sequence[tuple[bool, bool]], *, seed: int, draws: int = 5000
) -> list[float | None]:
    """Percentile CI for mean(left-right), resampling cases."""
    if not paired:
        return [None, None]
    values = [int(left) - int(right) for left, right in paired]
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(
        statistics.fmean(values[rng.randrange(n)] for _ in range(n))
        for _ in range(draws)
    )
    return [
        round(samples[int(0.025 * draws)], 6),
        round(samples[min(draws - 1, int(0.975 * draws))], 6),
    ]


def index_conditions(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Mapping[str, Any]]]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        case_key = str(row.get("case_key") or "")
        arm = str(row.get("arm") or "")
        if not case_key or arm not in ARMS:
            raise ValueError(f"invalid E7c condition identity: {case_key!r}/{arm!r}")
        if arm in by_case[case_key]:
            raise ValueError(f"duplicate E7c condition: {case_key}/{arm}")
        by_case[case_key][arm] = row
    incomplete = {key: sorted(set(ARMS) - set(value)) for key, value in by_case.items() if set(value) != set(ARMS)}
    if incomplete:
        raise ValueError(f"incomplete E7c condition blocks: {incomplete}")
    return dict(by_case)


def outcome(row: Mapping[str, Any], *, ita: bool) -> bool:
    if ita and not bool(row.get("success")):
        return False
    return bool(row.get("gold_top1"))


def paired_comparison(
    by_case: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    *,
    ita: bool,
    complete_relation_only: bool = False,
    family: str = "",
) -> dict[str, Any]:
    pairs: list[tuple[bool, bool]] = []
    flips = 0
    excluded_failure = 0
    excluded_relation = 0
    for case_key, arms in sorted(by_case.items()):
        left_row, right_row = arms[left], arms[right]
        if family and str(left_row.get("family")) != family:
            continue
        if complete_relation_only and not all(
            bool(row.get("relation_typing_success")) for row in arms.values()
        ):
            excluded_relation += 1
            continue
        if not ita and (not bool(left_row.get("success")) or not bool(right_row.get("success"))):
            excluded_failure += 1
            continue
        pairs.append((outcome(left_row, ita=ita), outcome(right_row, ita=ita)))
        if normalize_label(str(left_row.get("champion_label") or "")) != normalize_label(
            str(right_row.get("champion_label") or "")
        ):
            flips += 1
    left_only = sum(left_value and not right_value for left_value, right_value in pairs)
    right_only = sum(right_value and not left_value for left_value, right_value in pairs)
    both = sum(left_value and right_value for left_value, right_value in pairs)
    neither = len(pairs) - left_only - right_only - both
    left_rate = sum(value[0] for value in pairs) / len(pairs) if pairs else None
    right_rate = sum(value[1] for value in pairs) / len(pairs) if pairs else None
    return {
        "left": left,
        "right": right,
        "analysis": "ITA_failure_as_incorrect" if ita else "served_pair_complete_case",
        "complete_relation_only": complete_relation_only,
        "family": family or "ALL",
        "n": len(pairs),
        "excluded_selector_failure": excluded_failure,
        "excluded_incomplete_relation_typing": excluded_relation,
        "left_rate": round(left_rate, 6) if left_rate is not None else None,
        "right_rate": round(right_rate, 6) if right_rate is not None else None,
        "delta_left_minus_right": round(left_rate - right_rate, 6)
        if left_rate is not None and right_rate is not None
        else None,
        "delta_ci95_case_bootstrap": bootstrap_delta_ci(
            pairs,
            seed=stable_seed(
                "E7c", left, right, ita, complete_relation_only, family or "ALL"
            ),
        ),
        "left_only": left_only,
        "right_only": right_only,
        "both": both,
        "neither": neither,
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "champion_label_flips": flips,
        "champion_label_flip_rate": round(flips / len(pairs), 6) if pairs else None,
    }


def arm_rates(
    by_case: Mapping[str, Mapping[str, Mapping[str, Any]]], family: str = ""
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in ARMS:
        rows = [
            arms[arm]
            for arms in by_case.values()
            if not family or str(arms[arm].get("family")) == family
        ]
        served = [row for row in rows if bool(row.get("success"))]
        ita_n = sum(outcome(row, ita=True) for row in rows)
        served_n = sum(outcome(row, ita=False) for row in served)
        result[arm] = {
            "n_intention": len(rows),
            "n_served": len(served),
            "n_failed": len(rows) - len(served),
            "ita_gold_top1_n": ita_n,
            "ita_gold_top1_rate": round(ita_n / len(rows), 6) if rows else None,
            "served_gold_top1_n": served_n,
            "served_gold_top1_rate": round(served_n / len(served), 6) if served else None,
            "cache_hit_n": sum(bool(row.get("cache_hit")) for row in rows),
        }
    return result


def relation_types_by_case(
    relation_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, bool]]:
    relation_types: dict[str, set[str]] = defaultdict(set)
    complete: dict[str, bool] = defaultdict(lambda: True)
    for row in relation_rows:
        key = str(row.get("case_key") or "")
        complete[key] = complete[key] and bool(row.get("success"))
        if not bool(row.get("success")):
            continue
        for item in row.get("response", {}).get("relations") or []:
            if isinstance(item, Mapping) and item.get("relation"):
                relation_types[key].add(str(item["relation"]))
    return dict(relation_types), dict(complete)


def relation_heterogeneity(
    by_case: Mapping[str, Mapping[str, Mapping[str, Any]]],
    types_by_case: Mapping[str, set[str]],
) -> dict[str, Any]:
    all_types = sorted({kind for values in types_by_case.values() for kind in values})
    result: dict[str, Any] = {}
    for kind in all_types:
        keys = [key for key in by_case if kind in types_by_case.get(key, set())]
        transitions: dict[str, Any] = {}
        for left, right in PRIMARY_COMPARISONS[:2]:
            paired = [
                (
                    outcome(by_case[key][left], ita=True),
                    outcome(by_case[key][right], ita=True),
                )
                for key in keys
            ]
            gains = sum(left_value and not right_value for left_value, right_value in paired)
            harms = sum(right_value and not left_value for left_value, right_value in paired)
            transitions[f"{left}_vs_{right}"] = {
                "n": len(paired),
                "gains": gains,
                "harms": harms,
                "net": gains - harms,
                "exact_mcnemar_p": exact_mcnemar(gains, harms),
            }
        result[kind] = {"n_cases": len(keys), "comparisons": transitions}
    return result


def _relation_signature(
    relation: str, source: str, target: str
) -> tuple[str, ...]:
    """Map synonymous parent/subtype directions to one semantic signature."""
    if relation == "parent_of":
        return ("specificity", target, source)
    if relation in {
        "subtype_of",
        "anatomic_refinement_of",
        "temporal_refinement_of",
        "etiologic_refinement_of",
    }:
        return ("specificity", source, target)
    if relation in {
        "same_as",
        "cooccurs_with",
        "contrast_mimic",
        "unrelated",
        "unresolved",
    }:
        return (relation,)
    return (relation, source, target)


def relation_repeat_consistency(
    relation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Audit treatment stability when E7a supplied a pair more than once.

    Repeated source pairs are an accidental but useful internal replication.
    Parent/subtype inverse wording is normalised before comparison, so a group
    is marked inconsistent only when the typed semantic relation or direction
    differs, rather than because the labels were presented in reverse order.
    """
    groups: dict[tuple[str, tuple[str, str]], list[dict[str, Any]]] = defaultdict(list)
    for chunk in relation_rows:
        if not bool(chunk.get("success")):
            continue
        pairs = {
            str(pair.get("pair_id") or ""): pair
            for pair in chunk.get("pairs") or []
            if isinstance(pair, Mapping)
        }
        for item in chunk.get("response", {}).get("relations") or []:
            if not isinstance(item, Mapping):
                continue
            pair = pairs.get(str(item.get("pair_id") or ""))
            if pair is None:
                continue
            labels = {
                "left": normalize_label(str(pair.get("left_label") or "")),
                "right": normalize_label(str(pair.get("right_label") or "")),
            }
            source = labels.get(str(item.get("source_endpoint") or ""), "")
            target = labels.get(str(item.get("target_endpoint") or ""), "")
            relation = str(item.get("relation") or "")
            key = (
                str(chunk.get("case_key") or ""),
                tuple(sorted((labels["left"], labels["right"]))),
            )
            groups[key].append(
                {
                    "pair_id": item.get("pair_id"),
                    "relation": relation,
                    "source": source,
                    "target": target,
                    "signature": _relation_signature(relation, source, target),
                }
            )
    repeated = {key: values for key, values in groups.items() if len(values) > 1}
    inconsistent = {
        key: values
        for key, values in repeated.items()
        if len({tuple(item["signature"]) for item in values}) > 1
    }
    examples = []
    for (case_key, labels), values in sorted(inconsistent.items())[:100]:
        examples.append(
            {
                "case_key": case_key,
                "labels": list(labels),
                "observations": [
                    {
                        key: value
                        for key, value in item.items()
                        if key != "signature"
                    }
                    for item in values
                ],
            }
        )
    return {
        "n_edges_in_successful_chunks": sum(len(values) for values in groups.values()),
        "n_unique_case_label_pairs": len(groups),
        "n_repeated_pair_groups": len(repeated),
        "n_inconsistent_repeated_pair_groups": len(inconsistent),
        "n_cases_with_inconsistency": len({key[0] for key in inconsistent}),
        "repeated_pair_consistency_rate": round(
            (len(repeated) - len(inconsistent)) / len(repeated), 6
        )
        if repeated
        else None,
        "interpretation": (
            "Internal repeat-consistency diagnostic after normalising inverse "
            "parent/subtype wording; it is not clinical ground truth."
        ),
        "inconsistent_examples": examples,
    }


def flip_mechanism_census(
    by_case: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
) -> dict[str, Any]:
    """Describe where changed champions sit relative to the treatment graph."""
    flipped: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for arms in by_case.values():
        left_row, right_row = arms[left], arms[right]
        if normalize_label(str(left_row.get("champion_label") or "")) != normalize_label(
            str(right_row.get("champion_label") or "")
        ):
            flipped.append((left_row, right_row))
    counts = Counter()
    edge_total = 0
    for left_row, right_row in flipped:
        graph = list(left_row.get("relation_graph") or [])
        edge_total += len(graph)
        nodes = {
            str(endpoint)
            for edge in graph
            for endpoint in (edge.get("source_id"), edge.get("target_id"))
            if endpoint
        }
        left_id = str(left_row.get("champion_id") or "")
        right_id = str(right_row.get("champion_id") or "")
        left_touch = left_id in nodes
        right_touch = right_id in nodes
        connected = any(
            {str(edge.get("source_id") or ""), str(edge.get("target_id") or "")}
            == {left_id, right_id}
            for edge in graph
            if left_id and right_id
        )
        counts["graph_empty"] += not graph
        counts["left_champion_is_graph_node"] += left_touch
        counts["right_champion_is_graph_node"] += right_touch
        counts["either_champion_is_graph_node"] += left_touch or right_touch
        counts["both_champions_are_graph_nodes"] += left_touch and right_touch
        counts["champions_directly_connected"] += connected
        counts["left_correct_right_wrong"] += outcome(left_row, ita=True) and not outcome(
            right_row, ita=True
        )
        counts["right_correct_left_wrong"] += outcome(right_row, ita=True) and not outcome(
            left_row, ita=True
        )
        counts["selector_failure_in_pair"] += not bool(left_row.get("success")) or not bool(
            right_row.get("success")
        )
    return {
        "left": left,
        "right": right,
        "n_champion_flips": len(flipped),
        "mean_left_graph_edges": round(edge_total / len(flipped), 6) if flipped else None,
        **{key: int(value) for key, value in sorted(counts.items())},
    }


def lexical_direction_diagnostics(
    relation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Check direction against the proper-containment structure E7a detected.

    This is deliberately not called clinical ground truth.  For parent/subtype
    and explicit refinement predicates, however, a source endpoint that points
    from the lexically shorter parent to ``subtype_of`` the longer child (or the
    reverse for ``parent_of``) is internally inconsistent with the predicate's
    declared semantics.  The diagnostic is therefore a treatment-fidelity
    lower bound and supplies concrete records for manual clinical review.
    """
    longer_source_relations = {
        "subtype_of",
        "anatomic_refinement_of",
        "temporal_refinement_of",
        "etiologic_refinement_of",
    }
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    mismatches: list[dict[str, Any]] = []
    for chunk in relation_rows:
        if not bool(chunk.get("success")):
            continue
        pairs = {
            str(pair.get("pair_id") or ""): pair
            for pair in chunk.get("pairs") or []
            if isinstance(pair, Mapping)
        }
        for item in chunk.get("response", {}).get("relations") or []:
            if not isinstance(item, Mapping):
                continue
            relation = str(item.get("relation") or "")
            if relation not in longer_source_relations | {"parent_of"}:
                continue
            pair = pairs.get(str(item.get("pair_id") or ""))
            if pair is None:
                continue
            labels = {
                "left": str(pair.get("left_label") or ""),
                "right": str(pair.get("right_label") or ""),
            }
            normalized = {endpoint: normalize_label(label) for endpoint, label in labels.items()}
            left, right = normalized["left"], normalized["right"]
            if left and left != right and left in right:
                shorter, longer = "left", "right"
            elif right and left != right and right in left:
                shorter, longer = "right", "left"
            else:
                counts[relation]["not_proper_containment"] += 1
                continue
            expected = shorter if relation == "parent_of" else longer
            observed = str(item.get("source_endpoint") or "")
            agreement = observed == expected
            counts[relation]["agree" if agreement else "disagree"] += 1
            if not agreement:
                mismatches.append(
                    {
                        "case_key": chunk.get("case_key"),
                        "pair_id": item.get("pair_id"),
                        "left_label": labels["left"],
                        "right_label": labels["right"],
                        "relation": relation,
                        "observed_source_endpoint": observed,
                        "expected_source_endpoint_from_containment": expected,
                    }
                )
    by_relation: dict[str, Any] = {}
    agree_total = disagree_total = 0
    for relation, counter in sorted(counts.items()):
        agree = int(counter["agree"])
        disagree = int(counter["disagree"])
        agree_total += agree
        disagree_total += disagree
        by_relation[relation] = {
            "agree": agree,
            "disagree": disagree,
            "not_proper_containment": int(counter["not_proper_containment"]),
            "agreement_rate": round(agree / (agree + disagree), 6)
            if agree + disagree
            else None,
        }
    return {
        "interpretation": (
            "Internal predicate-direction sanity check on E7a proper-containment "
            "pairs; not a substitute for manual clinical relation adjudication."
        ),
        "n_assessable": agree_total + disagree_total,
        "agree": agree_total,
        "disagree": disagree_total,
        "agreement_rate": round(agree_total / (agree_total + disagree_total), 6)
        if agree_total + disagree_total
        else None,
        "by_relation": by_relation,
        "mismatch_examples": mismatches[:100],
    }


def _telemetry_sums(rows: Iterable[Mapping[str, Any]], weight: float = 1.0) -> dict[str, float]:
    totals = {
        "semantic_calls": 0.0,
        "physical_attempts": 0.0,
        "input_tokens": 0.0,
        "output_tokens": 0.0,
        "latency_seconds": 0.0,
        "failed_records": 0.0,
    }
    for row in rows:
        totals["semantic_calls"] += float(row.get("semantic_calls") or 0) * weight
        totals["physical_attempts"] += float(row.get("physical_attempts") or 0) * weight
        totals["input_tokens"] += float(row.get("input_tokens") or 0) * weight
        totals["output_tokens"] += float(row.get("output_tokens") or 0) * weight
        totals["latency_seconds"] += float(row.get("latency_seconds") or 0) * weight
        totals["failed_records"] += (not bool(row.get("success"))) * weight
    return totals


def _selector_wire_payloads(
    condition_rows: Sequence[Mapping[str, Any]],
    relation_rows: Sequence[Mapping[str, Any]],
) -> dict[str, set[str]]:
    """Rebuild transport hashes and return the selector arms using each hash.

    ``OnlineJSONCaller`` stores a canonical JSON hash in the condition record,
    while ``RobustLLMClient`` logs the hash of ``json.dumps`` as transmitted.
    They describe the same payload but are intentionally different hashes.
    Rebuilding the latter prevents every selector call from being mislabelled
    as an unassociated relation-typing call in the offline cost ledger.
    """
    by_case = index_conditions(condition_rows)
    chunks_by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in relation_rows:
        chunks_by_case[str(row.get("case_key") or "")].append(row)

    arms_by_payload: dict[str, set[str]] = defaultdict(set)
    for case_key, arms in by_case.items():
        chunks = sorted(
            chunks_by_case.get(case_key, []),
            key=lambda row: int(row.get("chunk_index") or 0),
        )
        pairs = [pair for chunk in chunks for pair in (chunk.get("pairs") or [])]
        relation_response = {
            "relations": [
                item
                for chunk in chunks
                if bool(chunk.get("success"))
                for item in (chunk.get("response", {}).get("relations") or [])
            ]
        }
        source = arms[ARM_EXACT]
        for arm in ARMS:
            graph = build_relation_graph(source, pairs, relation_response, arm)
            payload = make_selector_payload(source, graph)
            wire_json = json.dumps(payload, default=str, ensure_ascii=False)
            wire_hash = hashlib.sha256(wire_json.encode("utf-8")).hexdigest()
            arms_by_payload[wire_hash].add(arm)
    return dict(arms_by_payload)


def telemetry_allocation(
    condition_rows: Sequence[Mapping[str, Any]],
    relation_rows: Sequence[Mapping[str, Any]],
    telemetry_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Report actual totals and split shared payload charges across associated arms.

    Several arms can have byte-identical payloads when relation typing yields no
    usable edge.  OnlineJSONCaller single-flights those requests.  Naively
    assigning the one charged call to every arm double-counts cost; this routine
    both reports overlapping associations and a fractional actual allocation.
    """
    arms_by_payload = _selector_wire_payloads(condition_rows, relation_rows)
    telemetry_by_payload: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in telemetry_rows:
        telemetry_by_payload[str(row.get("payload_sha256") or "")].append(row)

    actual = _telemetry_sums(telemetry_rows)
    associated: dict[str, Any] = {}
    allocated: dict[str, dict[str, float]] = {
        arm: {key: 0.0 for key in actual} for arm in ARMS
    }
    for arm in ARMS:
        payloads = {payload for payload, arms in arms_by_payload.items() if arm in arms}
        rows = [row for payload in payloads for row in telemetry_by_payload.get(payload, [])]
        associated[arm] = _telemetry_sums(rows)
    for payload, rows in telemetry_by_payload.items():
        arms = sorted(arms_by_payload.get(payload, set()))
        if not arms:
            continue  # relation-typing calls are not selector-arm costs
        share = 1.0 / len(arms)
        charge = _telemetry_sums(rows, weight=share)
        for arm in arms:
            for key, value in charge.items():
                allocated[arm][key] += value
    return {
        "actual_all_modules": actual,
        "selector_arm_association_non_additive": associated,
        "selector_arm_fractional_actual_allocation": allocated,
        "unassociated_relation_stage": _telemetry_sums(
            row
            for row in telemetry_rows
            if str(row.get("payload_sha256") or "") not in arms_by_payload
        ),
        "note": (
            "Association columns overlap for identical arm payloads; fractional "
            "allocation splits the one actual charged record equally across them."
        ),
    }


def discordance_rows(
    by_case: Mapping[str, Mapping[str, Mapping[str, Any]]],
    types_by_case: Mapping[str, set[str]],
    relation_complete: Mapping[str, bool],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_key, arms in sorted(by_case.items()):
        champions = {
            normalize_label(str(arms[arm].get("champion_label") or "")) for arm in ARMS
        }
        correct = {outcome(arms[arm], ita=True) for arm in ARMS}
        if len(champions) == 1 and len(correct) == 1:
            continue
        first = arms[ARM_EXACT]
        row: dict[str, Any] = {
            "case_key": case_key,
            "family": first.get("family"),
            "gold": first.get("gold"),
            "relation_typing_complete": relation_complete.get(case_key, False),
            "relation_types": "|".join(sorted(types_by_case.get(case_key, set()))),
        }
        for arm in ARMS:
            row[f"{arm}_success"] = bool(arms[arm].get("success"))
            row[f"{arm}_champion"] = arms[arm].get("champion_label")
            row[f"{arm}_correct_ita"] = outcome(arms[arm], ita=True)
            row[f"{arm}_requested_object"] = arms[arm].get("requested_object")
        row["directional_effect"] = (
            "gain"
            if outcome(arms[ARM_DIRECTIONAL], ita=True)
            and not outcome(arms[ARM_EXACT], ita=True)
            else "harm"
            if outcome(arms[ARM_EXACT], ita=True)
            and not outcome(arms[ARM_DIRECTIONAL], ita=True)
            else "label_flip_only"
            if normalize_label(str(arms[ARM_DIRECTIONAL].get("champion_label") or ""))
            != normalize_label(str(arms[ARM_EXACT].get("champion_label") or ""))
            else "none"
        )
        row["bounded_effect"] = (
            "gain"
            if outcome(arms[ARM_BOUNDED], ita=True)
            and not outcome(arms[ARM_DIRECTIONAL], ita=True)
            else "harm"
            if outcome(arms[ARM_DIRECTIONAL], ita=True)
            and not outcome(arms[ARM_BOUNDED], ita=True)
            else "label_flip_only"
            if normalize_label(str(arms[ARM_BOUNDED].get("champion_label") or ""))
            != normalize_label(str(arms[ARM_DIRECTIONAL].get("champion_label") or ""))
            else "none"
        )
        rows.append(row)
    priority = {"gain": 0, "harm": 1, "label_flip_only": 2, "none": 3}
    return sorted(
        rows,
        key=lambda row: (
            min(priority[str(row["directional_effect"])], priority[str(row["bounded_effect"])]),
            str(row["case_key"]),
        ),
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyse(out: Path) -> dict[str, Any]:
    condition_rows = read_jsonl(out / "case_conditions.jsonl")
    relation_rows = read_jsonl(out / "relation_classifications.jsonl")
    telemetry_rows = read_jsonl(out / "telemetry.jsonl")
    by_case = index_conditions(condition_rows)
    types_by_case, relation_complete = relation_types_by_case(relation_rows)

    comparisons: list[dict[str, Any]] = []
    for family in ("", "DA", "MCR"):
        for left, right in PRIMARY_COMPARISONS:
            comparisons.append(
                paired_comparison(by_case, left, right, ita=True, family=family)
            )
            comparisons.append(
                paired_comparison(by_case, left, right, ita=False, family=family)
            )
            comparisons.append(
                paired_comparison(
                    by_case,
                    left,
                    right,
                    ita=True,
                    complete_relation_only=True,
                    family=family,
                )
            )

    discordances = discordance_rows(by_case, types_by_case, relation_complete)
    write_csv(out / "discordance_cases.csv", discordances)
    result = {
        "experiment_id": "E7c",
        "n_cases": len(by_case),
        "n_conditions": len(condition_rows),
        "n_relation_chunks": len(relation_rows),
        "n_relation_complete_cases": sum(relation_complete.values()),
        "n_discordant_cases": len(discordances),
        "arms": {
            "ALL": arm_rates(by_case),
            "DA": arm_rates(by_case, "DA"),
            "MCR": arm_rates(by_case, "MCR"),
        },
        "paired_comparisons": comparisons,
        "relation_type_heterogeneity": relation_heterogeneity(by_case, types_by_case),
        "relation_repeat_consistency": relation_repeat_consistency(relation_rows),
        "flip_mechanism_census": [
            flip_mechanism_census(by_case, left, right)
            for left, right in PRIMARY_COMPARISONS
        ],
        "lexical_direction_diagnostics": lexical_direction_diagnostics(relation_rows),
        "telemetry_allocation": telemetry_allocation(
            condition_rows, relation_rows, telemetry_rows
        ),
        "analysis_contract": {
            "primary": "ITA with terminal selector failures scored incorrect",
            "sensitivity_1": "served-pair complete case",
            "sensitivity_2": "ITA restricted to complete relation typing",
            "development_not_confirmation": True,
            "no_model_calls": True,
        },
    }
    atomic_json(out / "analysis_summary.json", result)
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analyse(args.out.resolve())
    print(json.dumps(result["arms"]["ALL"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
