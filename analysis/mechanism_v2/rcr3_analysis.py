#!/usr/bin/env python3
"""Offline paired and trajectory analysis for the completed RCR-3 matrix.

Strict exact/frozen-safe-synonym endpoints are analysed before any clinical
screen.  The script also freezes all 300 case documents for a heterogeneous
clinical-equivalence screen and a deterministic root-owned mechanism queue.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    FrozenExactSynonymBridge,
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.rcr3_end_to_end import (  # noqa: E402
    ARMS,
    BRIDGE_PATH,
    COMPACT4,
    DEFAULT_OUT,
    LITE3,
    RCR3,
    load_jobs,
)
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


CONTRASTS: tuple[tuple[str, str, str], ...] = (
    (LITE3, RCR3, "rcr3_vs_lite3_same_3call_budget"),
    (LITE3, COMPACT4, "third_generator_marginal_utility"),
    (RCR3, COMPACT4, "compact4_vs_rcr3"),
)
ENDPOINTS = (
    "strict_top1",
    "strict_top2",
    "raw_registry_exposure_hit",
    "frontier_exposure_hit",
    "success",
)


def exact_mcnemar(left_only: int, right_only: int) -> float:
    n = left_only + right_only
    if n == 0:
        return 1.0
    lower = min(left_only, right_only)
    tail = sum(math.comb(n, index) for index in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**n))


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    return float(ordered[lo] * (hi - position) + ordered[hi] * (position - lo))


def bootstrap_ci(
    deltas: Sequence[float], seed_key: str, repetitions: int
) -> list[float] | None:
    if not deltas:
        return None
    rng = random.Random(stable_seed("RCR3-bootstrap-v1", seed_key))
    n = len(deltas)
    estimates = [
        sum(deltas[rng.randrange(n)] for _ in range(n)) / n
        for _ in range(repetitions)
    ]
    return [
        round(_percentile(estimates, 0.025), 6),
        round(_percentile(estimates, 0.975), 6),
    ]


def holm_adjust(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    order = sorted(
        range(len(output)),
        key=lambda index: (
            float(output[index]["exact_mcnemar_p"]),
            str(output[index]["label"]),
        ),
    )
    previous = 0.0
    for rank, index in enumerate(order):
        adjusted = min(
            1.0,
            (len(output) - rank) * float(output[index]["exact_mcnemar_p"]),
        )
        adjusted = max(previous, adjusted)
        output[index]["holm_adjusted_p_across_3"] = adjusted
        previous = adjusted
    return output


def load_arms(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    expected: set[str] | None = None
    for arm in ARMS:
        rows = read_jsonl(out / "arms" / arm / "case_results.jsonl")
        by_key = {str(row["case_key"]): row for row in rows}
        if len(rows) != 300 or len(by_key) != 300:
            raise AssertionError(f"{arm}: expected 300 unique result rows")
        if expected is None:
            expected = set(by_key)
        elif set(by_key) != expected:
            raise AssertionError(f"{arm}: case set mismatch")
        output[arm] = by_key
    return output


def load_stages(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    output: dict[str, dict[str, dict[str, Any]]] = {}
    for arm in ARMS:
        rows = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((out / "arms" / arm / "case_stages").glob("*.json"))
        ]
        by_key = {str(row["case_key"]): row for row in rows}
        if len(rows) != 300 or len(by_key) != 300:
            raise AssertionError(f"{arm}: expected 300 unique stage documents")
        output[arm] = by_key
    return output


def paired_contrast(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    left: str,
    right: str,
    label: str,
    endpoint: str,
    repetitions: int,
    *,
    common_success: bool,
    family: str | None = None,
) -> dict[str, Any]:
    keys = sorted(set(arms[left]) & set(arms[right]))
    if family:
        keys = [key for key in keys if str(arms[left][key]["family"]) == family]
    if common_success:
        keys = [
            key
            for key in keys
            if bool(arms[left][key]["success"]) and bool(arms[right][key]["success"])
        ]
    counts: Counter[tuple[bool, bool]] = Counter()
    deltas: list[float] = []
    gains: list[str] = []
    losses: list[str] = []
    flips: list[str] = []
    for key in keys:
        before = bool(arms[left][key][endpoint])
        after = bool(arms[right][key][endpoint])
        counts[(before, after)] += 1
        deltas.append(float(after) - float(before))
        if not before and after:
            gains.append(key)
        elif before and not after:
            losses.append(key)
        if normalize_label(str(arms[left][key].get("champion_label") or "")) != normalize_label(
            str(arms[right][key].get("champion_label") or "")
        ):
            flips.append(key)
    left_only = counts[(True, False)]
    right_only = counts[(False, True)]
    n = len(keys)
    return {
        "label": label,
        "left": left,
        "right": right,
        "endpoint": endpoint,
        "analysis_set": "common_success" if common_success else "intention_to_analyse",
        "family": family or "all",
        "n": n,
        "both": counts[(True, True)],
        "left_only": left_only,
        "right_only": right_only,
        "neither": counts[(False, False)],
        "delta_right_minus_left": round(sum(deltas) / n, 6) if n else None,
        "paired_bootstrap_delta_ci95": bootstrap_ci(
            deltas, f"{label}/{endpoint}/{common_success}/{family}", repetitions
        ),
        "exact_mcnemar_p": exact_mcnemar(left_only, right_only),
        "gain_case_keys": gains,
        "loss_case_keys": losses,
        "champion_flip_n": len(flips),
        "champion_flip_case_keys": flips,
    }


def _telemetry_rows(out: Path, arm: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((out / "arms" / arm / "telemetry").glob("*.jsonl")):
        rows.extend(read_jsonl(path))
    return rows


def arm_statistics(
    out: Path, arms: Mapping[str, Mapping[str, Mapping[str, Any]]]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for arm in ARMS:
        rows = list(arms[arm].values())
        telemetry = _telemetry_rows(out, arm)

        def grouped(selected: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
            values = list(selected)
            exposed = [row for row in values if bool(row["frontier_exposure_hit"])]
            return {
                "n": len(values),
                "served_n": sum(bool(row["success"]) for row in values),
                "strict_top1_n": sum(bool(row["strict_top1"]) for row in values),
                "strict_top2_n": sum(bool(row["strict_top2"]) for row in values),
                "raw_registry_exposure_n": sum(bool(row["raw_registry_exposure_hit"]) for row in values),
                "frontier_exposure_n": len(exposed),
                "frontier_exposure_to_top1_n": sum(bool(row["strict_top1"]) for row in exposed),
                "frontier_exposure_to_top2_n": sum(bool(row["strict_top2"]) for row in exposed),
            }

        failures = Counter(str(row.get("error") or "") for row in rows if not row["success"])
        output[arm] = {
            **grouped(rows),
            "failure_reasons": dict(sorted(failures.items())),
            "mean_registry_n": round(sum(int(row["registry_n"]) for row in rows) / len(rows), 6),
            "mean_frontier_n": round(sum(int(row["frontier_n"]) for row in rows) / len(rows), 6),
            "raw_to_frontier_reference_loss_case_keys": [
                str(row["case_key"])
                for row in rows
                if row["raw_registry_exposure_hit"] and not row["frontier_exposure_hit"]
            ],
            "by_family": {
                family: grouped(row for row in rows if str(row["family"]) == family)
                for family in ("DA", "MCR")
            },
            "runtime": {
                "semantic_call_records": len(telemetry),
                "physical_attempts": sum(int(row.get("physical_attempts") or 0) for row in telemetry),
                "input_tokens": sum(int(row.get("input_tokens") or 0) for row in telemetry),
                "output_tokens": sum(int(row.get("output_tokens") or 0) for row in telemetry),
                "latency_seconds_sum": round(sum(float(row.get("latency_seconds") or 0) for row in telemetry), 6),
                "provider_response_associations": dict(sorted(Counter(
                    str(provider)
                    for row in telemetry
                    for provider in (row.get("providers") or [])
                ).items())),
                "transports": sorted({
                    str(value)
                    for row in telemetry
                    for value in (row.get("transports") or [])
                }),
            },
        }
    return output


def _flat_grounding(stages: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    by_view: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {"call_n": 0, "success_n": 0, "invalid_span_n": 0, "grounded_evidence_n": 0}
    )
    candidate_types: Counter[tuple[str, str]] = Counter()
    for stage in stages.values():
        for generator in stage.get("generators") or []:
            view = str(generator.get("view") or "unknown")
            row = by_view[view]
            row["call_n"] += 1
            row["success_n"] += int(bool(generator.get("success")))
            audit = dict((generator.get("sanitized") or {}).get("grounding_audit") or {})
            row["invalid_span_n"] += int(audit.get("invalid_span_n") or 0)
            row["grounded_evidence_n"] += int(audit.get("grounded_evidence_n") or 0)
            for candidate in (generator.get("sanitized") or {}).get("candidates") or []:
                candidate_types[(view, str(candidate.get("candidate_type") or "other"))] += 1
    return {
        "by_view": dict(sorted(by_view.items())),
        "candidate_type_by_view": {
            f"{view}:{kind}": count
            for (view, kind), count in sorted(candidate_types.items())
        },
    }


def rcr_mechanism(stages: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    skeleton_success = 0
    raw_observations = grounded_observations = dropped_observations = 0
    relations: Counter[str] = Counter()
    zero_relation_keys: list[str] = []
    dropped_span_keys: list[str] = []
    assertion_cases: list[str] = []
    requested_kinds: Counter[str] = Counter()
    invalid_refs = 0
    invalid_ref_keys: list[str] = []
    generator_types: Counter[tuple[str, str]] = Counter()
    selector_completeness: Counter[str] = Counter()
    selector_fit: Counter[str] = Counter()
    selector_margin: Counter[str] = Counter()
    for key, stage in stages.items():
        skeleton_stage = dict(stage.get("skeleton") or {})
        if skeleton_stage.get("success"):
            skeleton_success += 1
            skeleton = dict(skeleton_stage.get("sanitized") or {})
            audit = dict(skeleton.get("grounding_audit") or {})
            raw_observations += int(audit.get("raw_observation_n") or 0)
            grounded_observations += int(audit.get("grounded_observation_n") or 0)
            dropped_observations += int(audit.get("dropped_observation_n") or 0)
            if int(audit.get("dropped_observation_n") or 0):
                dropped_span_keys.append(key)
            for relation in skeleton.get("relations") or []:
                relations[str(relation.get("relation") or "unknown")] += 1
            if not skeleton.get("relations"):
                zero_relation_keys.append(key)
            if skeleton.get("diagnostic_assertions"):
                assertion_cases.append(key)
            requested_kinds[str((skeleton.get("requested_object") or {}).get("kind") or "unknown")] += 1
        generator = dict(stage.get("generator") or {})
        if generator.get("success"):
            sanitized = dict(generator.get("sanitized") or {})
            invalid = int((sanitized.get("invalid_reference_audit") or {}).get("invalid_reference_n") or 0)
            invalid_refs += invalid
            if invalid:
                invalid_ref_keys.append(key)
            for view in sanitized.get("views") or []:
                for candidate in view.get("candidates") or []:
                    generator_types[(str(view.get("view")), str(candidate.get("candidate_type") or "other"))] += 1
        selector = dict(stage.get("selector") or {})
        if selector.get("success"):
            response = dict(selector.get("response") or {})
            selector_margin[str(response.get("margin") or "unknown")] += 1
            for row in response.get("candidate_assessments") or []:
                selector_completeness[str(row.get("completeness") or "unknown")] += 1
                selector_fit[str(row.get("fit") or "unknown")] += 1
    return {
        "skeleton_schema_valid_n": skeleton_success,
        "raw_observation_n": raw_observations,
        "grounded_observation_n": grounded_observations,
        "dropped_observation_n": dropped_observations,
        "grounding_rate": round(grounded_observations / raw_observations, 6) if raw_observations else None,
        "dropped_span_case_n": len(dropped_span_keys),
        "dropped_span_case_keys": dropped_span_keys,
        "grounded_relation_n": sum(relations.values()),
        "relation_types": dict(sorted(relations.items())),
        "zero_relation_case_n": len(zero_relation_keys),
        "zero_relation_case_keys": zero_relation_keys,
        "diagnostic_assertion_case_n": len(assertion_cases),
        "diagnostic_assertion_case_keys": assertion_cases,
        "requested_object_kinds": dict(sorted(requested_kinds.items())),
        "generator_invalid_reference_n": invalid_refs,
        "generator_invalid_reference_case_n": len(invalid_ref_keys),
        "generator_invalid_reference_case_keys": invalid_ref_keys,
        "generator_candidate_type_by_view": {
            f"{view}:{kind}": count
            for (view, kind), count in sorted(generator_types.items())
        },
        "selector_assessment_completeness": dict(sorted(selector_completeness.items())),
        "selector_assessment_fit": dict(sorted(selector_fit.items())),
        "selector_margin": dict(sorted(selector_margin.items())),
    }


def compact_mechanism(
    lite: Mapping[str, Mapping[str, Any]], compact: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    shared_equal = 0
    third_counts: Counter[int] = Counter()
    third_types: Counter[str] = Counter()
    registry_added_total = frontier_added_total = frontier_removed_total = 0
    common_registry_n = 0
    common_registry_added = 0
    common_frontier_added = 0
    common_frontier_removed = 0
    registry_changed_keys: list[str] = []
    for key in sorted(compact):
        left = lite[key]
        right = compact[key]
        shared_equal += int((right.get("generators") or [])[:2] == (left.get("generators") or [])[:2])
        third = (right.get("generators") or [{}])[-1]
        response = dict(third.get("response") or {})
        candidates = response.get("candidates")
        third_counts[len(candidates) if isinstance(candidates, list) else -1] += 1
        if isinstance(candidates, list):
            for candidate in candidates:
                third_types[str(candidate.get("candidate_type") or "unknown")] += 1
        lreg = {str(row.get("concept_key")) for row in (left.get("registry") or {}).get("registry") or []}
        rreg = {str(row.get("concept_key")) for row in (right.get("registry") or {}).get("registry") or []}
        if lreg != rreg:
            registry_changed_keys.append(key)
        registry_added_total += len(rreg - lreg)
        lfront = set((left.get("registry") or {}).get("frontier_candidate_ids") or [])
        rfront = set((right.get("registry") or {}).get("frontier_candidate_ids") or [])
        # Candidate IDs are neutral hashes over the full registry and may shift;
        # compare frontier concepts instead of the opaque IDs.
        lby = {str(row.get("candidate_id")): str(row.get("concept_key")) for row in (left.get("registry") or {}).get("registry") or []}
        rby = {str(row.get("candidate_id")): str(row.get("concept_key")) for row in (right.get("registry") or {}).get("registry") or []}
        lfconcept = {lby[value] for value in lfront if value in lby}
        rfconcept = {rby[value] for value in rfront if value in rby}
        frontier_added_total += len(rfconcept - lfconcept)
        frontier_removed_total += len(lfconcept - rfconcept)
        if lreg and rreg:
            common_registry_n += 1
            common_registry_added += len(rreg - lreg)
            common_frontier_added += len(rfconcept - lfconcept)
            common_frontier_removed += len(lfconcept - rfconcept)
    return {
        "shared_first_two_generator_documents_equal_n": shared_equal,
        "third_generator_candidate_count": {str(key): value for key, value in sorted(third_counts.items())},
        "third_generator_candidate_types": dict(sorted(third_types.items())),
        "registry_changed_case_n": len(registry_changed_keys),
        "registry_changed_case_keys": registry_changed_keys,
        "new_registry_concept_total": registry_added_total,
        "frontier_concept_added_total": frontier_added_total,
        "frontier_concept_removed_total": frontier_removed_total,
        "common_nonempty_registry_case_n": common_registry_n,
        "common_nonempty_registry_new_concept_total": common_registry_added,
        "common_nonempty_registry_frontier_added_total": common_frontier_added,
        "common_nonempty_registry_frontier_removed_total": common_frontier_removed,
    }


def _candidate_documents(
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    stages: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    jobs, _ = load_jobs()
    by_job = {str(row["case_key"]): row for row in jobs}
    documents: list[dict[str, Any]] = []
    for key in sorted(by_job):
        concepts: dict[str, dict[str, Any]] = {}
        arm_concept: dict[str, dict[str, str]] = {}
        for arm in ARMS:
            registry = dict(stages[arm][key].get("registry") or {})
            frontier = set(registry.get("frontier_candidate_ids") or [])
            id_to_concept: dict[str, str] = {}
            for row in registry.get("registry") or []:
                concept = str(row.get("concept_key") or normalize_label(str(row.get("label") or "")))
                if not concept:
                    continue
                id_to_concept[str(row.get("candidate_id"))] = concept
                item = concepts.setdefault(concept, {
                    "concept_key": concept,
                    "labels": [],
                    "candidate_types": [],
                    "appearances": [],
                })
                for label in row.get("surface_labels") or [row.get("label")]:
                    text = str(label or "").strip()
                    if text and text not in item["labels"]:
                        item["labels"].append(text)
                for kind in row.get("candidate_types") or []:
                    text = str(kind)
                    if text not in item["candidate_types"]:
                        item["candidate_types"].append(text)
                item["appearances"].append({
                    "arm": arm,
                    "frontier": str(row.get("candidate_id")) in frontier,
                })
            outcome = arms[arm][key]
            arm_concept[arm] = {
                "champion": id_to_concept.get(str(outcome.get("champion_id") or ""), ""),
                "runner_up": id_to_concept.get(str(outcome.get("runner_up_id") or ""), ""),
            }
        ordered = sorted(concepts)
        candidate_id_by_concept = {concept: f"J{index:03d}" for index, concept in enumerate(ordered, 1)}
        candidates = []
        for concept in ordered:
            item = concepts[concept]
            labels = sorted(item["labels"], key=lambda value: (-len(normalize_label(value)), normalize_label(value)))
            candidates.append({
                "candidate_id": candidate_id_by_concept[concept],
                "label": labels[0],
                "surface_labels": labels,
                "candidate_types": sorted(item["candidate_types"]),
                "appearances": item["appearances"],
            })
        outcome_view: dict[str, Any] = {}
        for arm in ARMS:
            row = arms[arm][key]
            outcome_view[arm] = {
                "success": bool(row["success"]),
                "error": str(row["error"]),
                "champion_candidate_id": candidate_id_by_concept.get(arm_concept[arm]["champion"], ""),
                "champion_label": str(row.get("champion_label") or ""),
                "runner_up_candidate_id": candidate_id_by_concept.get(arm_concept[arm]["runner_up"], ""),
                "runner_up_label": str(row.get("runner_up_label") or ""),
                "strict_top1": bool(row["strict_top1"]),
                "strict_top2": bool(row["strict_top2"]),
                "raw_registry_exposure_hit": bool(row["raw_registry_exposure_hit"]),
                "frontier_exposure_hit": bool(row["frontier_exposure_hit"]),
            }
        documents.append({
            "case_key": key,
            "family": by_job[key]["family"],
            "reference_diagnosis": by_job[key]["gold"],
            "vignette": by_job[key]["vignette"],
            "candidate_registry": candidates,
            "arm_outcomes": outcome_view,
        })
    return documents


def build_audit_queue(
    documents: Sequence[Mapping[str, Any]],
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
    stages: Mapping[str, Mapping[str, Mapping[str, Any]]],
    contrast_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    reasons: defaultdict[str, set[str]] = defaultdict(set)
    for row in contrast_rows:
        if row["analysis_set"] != "intention_to_analyse" or row["family"] != "all":
            continue
        if row["endpoint"] not in {"strict_top1", "strict_top2", "frontier_exposure_hit"}:
            continue
        for key in row["gain_case_keys"] + row["loss_case_keys"]:
            reasons[str(key)].add(f"{row['label']}:{row['endpoint']}_discordance")
    for key in sorted(arms[LITE3]):
        if any(arms[arm][key]["frontier_exposure_hit"] for arm in ARMS):
            reasons[key].add("strict_reference_frontier_exposure")
        for arm in ARMS:
            if not arms[arm][key]["success"]:
                reasons[key].add(f"{arm}:fail_closed")
        skeleton = dict((stages[RCR3][key].get("skeleton") or {}).get("sanitized") or {})
        audit = dict(skeleton.get("grounding_audit") or {})
        if int(audit.get("dropped_observation_n") or 0):
            reasons[key].add("rcr3:dropped_grounding_span")
        if (stages[RCR3][key].get("skeleton") or {}).get("success") and not skeleton.get("relations"):
            reasons[key].add("rcr3:zero_grounded_relations")
        labels = {
            normalize_label(str(arms[arm][key].get("champion_label") or ""))
            for arm in ARMS if arms[arm][key]["success"]
        }
        if len(labels) > 1:
            reasons[key].add("cross_arm_champion_disagreement")
    # Frozen family-balanced samples of all-negative/common-champion cases keep
    # the root review capable of discovering proxy false negatives.
    for family in ("DA", "MCR"):
        pool = [
            str(row["case_key"])
            for row in documents
            if row["family"] == family and str(row["case_key"]) not in reasons
        ]
        selected = sorted(
            pool,
            key=lambda key: (stable_seed("RCR3-root-negative-sample-v1", family, key), key),
        )[:15]
        for key in selected:
            reasons[key].add("frozen_family_balanced_negative_sample")
    by_document = {str(row["case_key"]): dict(row) for row in documents}
    queue = []
    for key in sorted(reasons):
        row = by_document[key]
        row["queue_reasons"] = sorted(reasons[key])
        row["stage_paths"] = {
            arm: (
                f"arms/{arm}/case_stages/"
                f"{arms[arm][key]['slice_id']}__{arms[arm][key]['source_id']}.json"
            )
            for arm in ARMS
        }
        queue.append(row)
    return queue


def analyze(out: Path, repetitions: int) -> dict[str, Any]:
    # Loading the bridge is an integrity check even though result booleans were
    # frozen by the online runner.
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    arms = load_arms(out)
    stages = load_stages(out)
    contrast_rows: list[dict[str, Any]] = []
    for endpoint in ENDPOINTS:
        ita = [
            paired_contrast(
                arms, left, right, label, endpoint, repetitions,
                common_success=False,
            )
            for left, right, label in CONTRASTS
        ]
        contrast_rows.extend(holm_adjust(ita))
        if endpoint != "success":
            common = [
                paired_contrast(
                    arms, left, right, label, endpoint, repetitions,
                    common_success=True,
                )
                for left, right, label in CONTRASTS
            ]
            contrast_rows.extend(holm_adjust(common))
        for family in ("DA", "MCR"):
            contrast_rows.extend(
                paired_contrast(
                    arms, left, right, label, endpoint, repetitions,
                    common_success=False, family=family,
                )
                for left, right, label in CONTRASTS
            )
    write_jsonl(out / "strict_contrasts.jsonl", contrast_rows)
    documents = _candidate_documents(arms, stages)
    write_jsonl(out / "semantic_screen_inputs.jsonl", documents)
    queue = build_audit_queue(documents, arms, stages, contrast_rows)
    write_jsonl(out / "root_audit_queue.jsonl", queue)
    mechanism = {
        "lite_flat_generation": _flat_grounding(stages[LITE3]),
        "rcr3": rcr_mechanism(stages[RCR3]),
        "compact4": compact_mechanism(stages[LITE3], stages[COMPACT4]),
    }
    summary = {
        "experiment_id": "RCR3",
        "bootstrap_repetitions": repetitions,
        "bridge_sha256": bridge.sha256,
        "contrast_family": [
            {"left": left, "right": right, "label": label}
            for left, right, label in CONTRASTS
        ],
        "arms": arm_statistics(out, arms),
        "strict_contrasts_sha256": file_sha256(out / "strict_contrasts.jsonl"),
        "strict_contrasts": contrast_rows,
        "mechanism": mechanism,
        "semantic_screen_inputs": {
            "n": len(documents),
            "candidate_relation_n": sum(len(row["candidate_registry"]) for row in documents),
            "sha256": file_sha256(out / "semantic_screen_inputs.jsonl"),
        },
        "root_audit_queue": {
            "n": len(queue),
            "reason_counts": dict(sorted(Counter(
                reason for row in queue for reason in row["queue_reasons"]
            ).items())),
            "sha256": file_sha256(out / "root_audit_queue.jsonl"),
        },
        "limitations": [
            "Strict identity is exact/frozen-safe-synonym and is not final clinical equivalence.",
            "Fail-closed intention-to-analyse is primary; common-success estimates are survivor-selected sensitivity analyses.",
            "Provider routing is descriptive, not randomized, and no provider-standardized reruns were performed.",
            "A grounded source span does not establish that a normalized fact or relation is semantically correct; root review remains required.",
        ],
    }
    atomic_json(out / "strict_analysis.json", summary)
    (out / "analysis_run.log").write_text(
        "RCR3 strict paired and trajectory analysis completed\n"
        f"bootstrap_repetitions={repetitions}\n"
        f"contrast_rows={len(contrast_rows)}\n"
        f"semantic_screen_cases={len(documents)}\n"
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
        "arms": {arm: result["arms"][arm]["strict_top1_n"] for arm in ARMS},
        "audit_queue_n": result["root_audit_queue"]["n"],
        "screen_candidate_relation_n": result["semantic_screen_inputs"]["candidate_relation_n"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
