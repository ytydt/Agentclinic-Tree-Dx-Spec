#!/usr/bin/env python3
"""E7: replay MOSAIC identity registration under three equivalence policies.

Arms
----
``legacy_substring``
    Exact normalized equality plus the production MOSAIC substring rule.
``exact_synonym``
    Exact normalized equality or an exact lookup in the frozen disease-name
    bridge.  No substring, fuzzy, parent/child or component folding.
``typed_relation``
    Same identity policy as ``exact_synonym``; lexical-containment pairs
    remain separate nodes and are emitted as explicit *non-equivalence*
    relation candidates.  The offline arm does not guess a clinical direction.

This is an offline causal replay over the 800 existing development trajectories.
It identifies registration-mediated exposure and score changes.  It does not
pretend that a logged selector response is a fresh response to a changed pool;
fresh blinded selector calls are a separate E7b arm.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    combined_file_sha256,
    iter_stage_cases,
    json_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    atomic_json,
    dependency_capabilities,
    stable_seed,
)


ARM_LEGACY = "legacy_substring"
ARM_EXACT = "exact_synonym"
ARM_TYPED = "typed_relation"
ARMS = (ARM_LEGACY, ARM_EXACT, ARM_TYPED)
VIEW_KEYS = ("ax_syndrome", "ax_mechanism", "ax_modality", "a1")
ENDPOINT_CONTRACT = (
    "raw nominations -> registry identity -> score/frontier exposure -> "
    "logged-selector label projection; no fresh selector inference"
)


@dataclass(frozen=True)
class Occurrence:
    occurrence_id: str
    name: str
    view: str
    ordinal: int
    support_spans: tuple[str, ...]
    contradict_spans: tuple[str, ...]
    axis_node: str
    protected_reason: str


@dataclass
class Concept:
    concept_id: str
    preferred_name: str
    occurrences: list[Occurrence] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    generator_views: list[str] = field(default_factory=list)
    axis_nodes: list[str] = field(default_factory=list)
    support_spans: list[str] = field(default_factory=list)
    contradict_spans: list[str] = field(default_factory=list)
    protected_reason: str = ""
    score_logit: float = 0.0

    def add(self, occurrence: Occurrence) -> None:
        self.occurrences.append(occurrence)
        if (
            normalize_label(occurrence.name) != normalize_label(self.preferred_name)
            and occurrence.name not in self.aliases
        ):
            self.aliases.append(occurrence.name)
        if occurrence.view not in self.generator_views:
            self.generator_views.append(occurrence.view)
        if occurrence.axis_node and occurrence.axis_node not in self.axis_nodes:
            self.axis_nodes.append(occurrence.axis_node)
        for span in occurrence.support_spans:
            if span not in self.support_spans:
                self.support_spans.append(span)
        for span in occurrence.contradict_spans:
            if span not in self.contradict_spans:
                self.contradict_spans.append(span)
        if occurrence.protected_reason and not self.protected_reason:
            self.protected_reason = occurrence.protected_reason

    def score(self) -> float:
        value = float(len(self.support_spans))
        value -= 1.25 * len(self.contradict_spans)
        value += 0.35 * max(0, len(self.generator_views) - 1)
        value += 0.15 * max(0, len(self.axis_nodes) - 1)
        if self.protected_reason:
            value += 0.25
        if not self.support_spans:
            value -= 0.5
        self.score_logit = value
        return value

    @property
    def member_names(self) -> list[str]:
        return [occurrence.name for occurrence in self.occurrences]


@dataclass
class RegistryReplay:
    arm: str
    concepts: list[Concept]
    relations: list[dict[str, str]]
    events: list[dict[str, Any]]

    def frontier(self, main_k: int = 4, protected_k: int = 2) -> list[Concept]:
        live = sorted(
            self.concepts,
            key=lambda concept: (-concept.score_logit, concept.preferred_name.lower()),
        )
        main = live[:main_k]
        main_ids = {concept.concept_id for concept in main}
        rest = [concept for concept in live if concept.concept_id not in main_ids]
        protected: list[Concept] = []
        for concept in rest:
            if concept.protected_reason or (
                concept.support_spans and len(concept.generator_views) == 1
            ):
                protected.append(concept)
            if len(protected) >= protected_k:
                break
        for concept in rest:
            if len(protected) >= protected_k:
                break
            if concept not in protected:
                protected.append(concept)
        return main + [concept for concept in protected if concept not in main]


def extract_occurrences(stages: Mapping[str, Any]) -> list[Occurrence]:
    rows: list[Occurrence] = []
    ordinal = 0
    for view in VIEW_KEYS:
        raw = stages.get(view)
        if not isinstance(raw, Mapping):
            continue
        candidates = raw.get("candidates") or []
        if not isinstance(candidates, list):
            continue
        for within_view, item in enumerate(candidates):
            if not isinstance(item, Mapping):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            rows.append(
                Occurrence(
                    occurrence_id=f"O{ordinal + 1:03d}",
                    name=name,
                    view=view,
                    ordinal=ordinal,
                    support_spans=tuple(
                        str(value).strip()
                        for value in (item.get("support_spans") or [])
                        if str(value).strip()
                    ),
                    contradict_spans=tuple(
                        str(value).strip()
                        for value in (item.get("contradict_spans") or [])
                        if str(value).strip()
                    ),
                    axis_node=str(item.get("axis_node") or "").strip(),
                    protected_reason=str(item.get("protected_reason") or "").strip(),
                )
            )
            ordinal += 1
    return rows


def legacy_equivalent(left: str, right: str) -> bool:
    left_key, right_key = normalize_label(left), normalize_label(right)
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    return (
        len(left_key) >= 6
        and len(right_key) >= 6
        and (left_key in right_key or right_key in left_key)
    )


def lexical_relation(left: str, right: str) -> tuple[str, str, str] | None:
    """Return ``(longer, contained, evidence_type)`` without clinical typing."""
    left_key, right_key = normalize_label(left), normalize_label(right)
    if not left_key or not right_key or left_key == right_key:
        return None
    if len(left_key) < 6 or len(right_key) < 6:
        return None
    if right_key in left_key:
        return left, right, "surface_containment"
    if left_key in right_key:
        return right, left, "surface_containment"
    left_tokens, right_tokens = set(left_key.split()), set(right_key.split())
    if right_tokens < left_tokens and len(right_tokens) >= 2:
        return left, right, "token_containment"
    if left_tokens < right_tokens and len(left_tokens) >= 2:
        return right, left, "token_containment"
    return None


def _find_concept(
    concepts: Sequence[Concept],
    occurrence: Occurrence,
    *,
    arm: str,
    bridge: FrozenExactSynonymBridge,
) -> Concept | None:
    for concept in concepts:
        labels = [concept.preferred_name] + list(concept.aliases)
        if arm == ARM_LEGACY:
            if any(legacy_equivalent(occurrence.name, label) for label in labels):
                return concept
        elif any(bridge.equivalent(occurrence.name, label) for label in labels):
            return concept
    return None


def build_registry(
    occurrences: Sequence[Occurrence],
    *,
    arm: str,
    bridge: FrozenExactSynonymBridge,
) -> RegistryReplay:
    if arm not in ARMS:
        raise ValueError(f"unknown registry arm: {arm}")
    concepts: list[Concept] = []
    # Production MOSAIC checks its exact preferred-name index before scanning
    # concepts with the substring matcher.  This precedence matters when A and
    # B were both created, after which a broad C matches both lexically: a later
    # exact B occurrence must return to B rather than be swallowed by A.
    preferred_surface_index: dict[str, Concept] = {}
    events: list[dict[str, Any]] = []
    for occurrence in occurrences:
        concept = preferred_surface_index.get(normalize_label(occurrence.name))
        if concept is None:
            concept = _find_concept(concepts, occurrence, arm=arm, bridge=bridge)
        if concept is None:
            concept = Concept(
                concept_id=f"C{len(concepts) + 1:03d}",
                preferred_name=occurrence.name,
            )
            concepts.append(concept)
            preferred_surface_index[normalize_label(occurrence.name)] = concept
            operation = "add"
        else:
            operation = "merge_equivalent"
        concept.add(occurrence)
        events.append(
            {
                "op": operation,
                "concept_id": concept.concept_id,
                "occurrence_id": occurrence.occurrence_id,
                "name": occurrence.name,
                "view": occurrence.view,
            }
        )
    for concept in concepts:
        concept.score()

    relations: list[dict[str, str]] = []
    if arm == ARM_TYPED:
        for left_index, left in enumerate(concepts):
            for right in concepts[left_index + 1 :]:
                relation = lexical_relation(left.preferred_name, right.preferred_name)
                if relation is None:
                    continue
                longer_name, contained_name, relation_type = relation
                longer = left if longer_name == left.preferred_name else right
                contained = right if longer is left else left
                relations.append(
                    {
                        "source": longer.concept_id,
                        "target": contained.concept_id,
                        "relation": "non_equivalent_lexical_relation",
                        "evidence": relation_type,
                        "clinical_direction": "unresolved",
                        "source_label": longer.preferred_name,
                        "target_label": contained.preferred_name,
                    }
                )
    return RegistryReplay(arm=arm, concepts=concepts, relations=relations, events=events)


def partition_signature(replay: RegistryReplay) -> dict[str, tuple[str, ...]]:
    signature: dict[str, tuple[str, ...]] = {}
    for concept in replay.concepts:
        members = tuple(sorted(occurrence.occurrence_id for occurrence in concept.occurrences))
        for occurrence_id in members:
            signature[occurrence_id] = members
    return signature


def relation_pairs(replay: RegistryReplay) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for concept in replay.concepts:
        ids = [occurrence.occurrence_id for occurrence in concept.occurrences]
        for left_index, left in enumerate(ids):
            for right in ids[left_index + 1 :]:
                pairs.add(tuple(sorted((left, right))))
    return pairs


def concept_for_label(
    replay: RegistryReplay,
    label: str,
    *,
    bridge: FrozenExactSynonymBridge,
    exact_surface_first: bool = True,
) -> Concept | None:
    target_surface = normalize_label(label)
    if exact_surface_first:
        for concept in replay.concepts:
            if any(
                normalize_label(occurrence.name) == target_surface
                for occurrence in concept.occurrences
            ):
                return concept
    for concept in replay.concepts:
        if any(bridge.equivalent(occurrence.name, label) for occurrence in concept.occurrences):
            return concept
    return None


def concept_has_gold(
    concept: Concept | None, gold: str, bridge: FrozenExactSynonymBridge
) -> bool:
    return bool(
        concept
        and any(bridge.equivalent(occurrence.name, gold) for occurrence in concept.occurrences)
    )


def concept_is_identity_contaminated(
    concept: Concept | None,
    reference: str,
    bridge: FrozenExactSynonymBridge,
) -> bool:
    return bool(
        concept
        and any(
            not bridge.equivalent(occurrence.name, reference)
            for occurrence in concept.occurrences
        )
    )


def cross_identity_evidence_transfers(
    replay: RegistryReplay, bridge: FrozenExactSynonymBridge
) -> list[dict[str, Any]]:
    transfers: list[dict[str, Any]] = []
    for concept in replay.concepts:
        if len(concept.occurrences) < 2:
            continue
        for target in concept.occurrences:
            target_support = set(target.support_spans)
            foreign: set[str] = set()
            foreign_sources: list[str] = []
            for source in concept.occurrences:
                if source.occurrence_id == target.occurrence_id:
                    continue
                if bridge.equivalent(source.name, target.name):
                    continue
                additions = set(source.support_spans) - target_support
                if additions:
                    foreign.update(additions)
                    foreign_sources.append(source.occurrence_id)
            if foreign:
                transfers.append(
                    {
                        "concept_id": concept.concept_id,
                        "target_occurrence": target.occurrence_id,
                        "target_label": target.name,
                        "source_occurrences": sorted(set(foreign_sources)),
                        "foreign_support_spans_n": len(foreign),
                        "foreign_support_spans": sorted(foreign),
                    }
                )
    return transfers


def unsafe_merge_pairs(
    replay: RegistryReplay, bridge: FrozenExactSynonymBridge
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for concept in replay.concepts:
        occurrences = concept.occurrences
        for left_index, left in enumerate(occurrences):
            for right in occurrences[left_index + 1 :]:
                if bridge.equivalent(left.name, right.name):
                    continue
                relation = lexical_relation(left.name, right.name)
                rows.append(
                    {
                        "concept_id": concept.concept_id,
                        "left_occurrence": left.occurrence_id,
                        "right_occurrence": right.occurrence_id,
                        "left_label": left.name,
                        "right_label": right.name,
                        "left_view": left.view,
                        "right_view": right.view,
                        "relation": relation[2] if relation else "untyped_non_synonym",
                    }
                )
    return rows


def _concept_payload(concept: Concept) -> dict[str, Any]:
    return {
        "concept_id": concept.concept_id,
        "preferred_name": concept.preferred_name,
        "member_names": concept.member_names,
        "generator_views": concept.generator_views,
        "axis_nodes": concept.axis_nodes,
        "support_n": len(concept.support_spans),
        "contradict_n": len(concept.contradict_spans),
        "protected": bool(concept.protected_reason),
        "score_logit": round(concept.score_logit, 6),
    }


def _legacy_validation(
    replay: RegistryReplay, logged_registry: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    logged_groups = {
        normalize_label(str(row.get("preferred_name") or "")): {
            normalize_label(str(row.get("preferred_name") or "")),
            *{
                normalize_label(str(alias))
                for alias in (row.get("aliases") or [])
                if normalize_label(str(alias))
            },
        }
        for row in logged_registry
    }
    replay_groups = {
        normalize_label(concept.preferred_name): {
            normalize_label(name) for name in concept.member_names if normalize_label(name)
        }
        for concept in replay.concepts
    }
    score_by_label = {
        normalize_label(str(row.get("preferred_name") or "")): float(
            row.get("score_logit") or 0.0
        )
        for row in logged_registry
    }
    score_deltas = []
    for concept in replay.concepts:
        key = normalize_label(concept.preferred_name)
        if key in score_by_label:
            score_deltas.append(abs(concept.score_logit - score_by_label[key]))
    return {
        "concept_count_equal": len(replay.concepts) == len(logged_registry),
        "partition_equal": replay_groups == logged_groups,
        "max_abs_score_delta": max(score_deltas, default=None),
        "scores_equal": bool(score_deltas) and max(score_deltas) < 1e-9,
    }


def analyze_case(
    *,
    slice_id: str,
    family: str,
    case: Mapping[str, Any],
    stage: Mapping[str, Any],
    bridge: FrozenExactSynonymBridge,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    stages = stage.get("stages") or {}
    occurrences = extract_occurrences(stages)
    if not occurrences:
        raise ValueError(f"no candidate occurrences for {slice_id}/{case.get('id')}")
    replays = {
        arm: build_registry(occurrences, arm=arm, bridge=bridge) for arm in ARMS
    }
    reversed_replays = {
        arm: build_registry(list(reversed(occurrences)), arm=arm, bridge=bridge)
        for arm in ARMS
    }
    legacy, exact, typed = (replays[arm] for arm in ARMS)
    gold = str(case.get("gold") or case.get("gold_option_text") or "").strip()
    champion = str(stage.get("champion") or "").strip()
    unsafe = unsafe_merge_pairs(legacy, bridge)
    transfers = cross_identity_evidence_transfers(legacy, bridge)

    arm_values: dict[str, dict[str, Any]] = {}
    for arm, replay in replays.items():
        frontier = replay.frontier()
        top = frontier[0] if frontier else None
        gold_concepts = [
            concept for concept in replay.concepts if concept_has_gold(concept, gold, bridge)
        ]
        champion_concept = concept_for_label(replay, champion, bridge=bridge)
        reversed_replay = reversed_replays[arm]
        reversed_frontier = reversed_replay.frontier()
        forward_pairs = relation_pairs(replay)
        reverse_pairs = relation_pairs(reversed_replay)
        arm_values[arm] = {
            "n_concepts": len(replay.concepts),
            "n_relations": len(replay.relations),
            "frontier_n": len(frontier),
            "frontier": [_concept_payload(concept) for concept in frontier],
            "score_top1": top.preferred_name if top else "",
            "score_top1_gold": concept_has_gold(top, gold, bridge),
            "gold_raw_hit": any(
                bridge.equivalent(occurrence.name, gold) for occurrence in occurrences
            ),
            "gold_registry_hit": bool(gold_concepts),
            "gold_exposure_hit": any(
                concept_has_gold(concept, gold, bridge) for concept in frontier
            ),
            "gold_identity_contaminated": any(
                concept_is_identity_contaminated(concept, gold, bridge)
                for concept in gold_concepts
            ),
            "logged_champion_mapped": champion_concept is not None,
            "logged_champion_identity_contaminated": concept_is_identity_contaminated(
                champion_concept, champion, bridge
            ),
            "order_partition_changed": forward_pairs != reverse_pairs,
            "order_preferred_labels_changed": sorted(
                concept.preferred_name for concept in replay.concepts
            )
            != sorted(concept.preferred_name for concept in reversed_replay.concepts),
            "order_score_top1_changed": bool(frontier and reversed_frontier)
            and not bridge.equivalent(
                frontier[0].preferred_name, reversed_frontier[0].preferred_name
            ),
        }

    logged_registry = stages.get("registry") or []
    validation = _legacy_validation(legacy, logged_registry)
    row = {
        "slice_id": slice_id,
        "family": family,
        "source_id": str(case.get("id") or stage.get("source_id") or ""),
        "case_id": str(stage.get("case_id") or ""),
        "gold": gold,
        "logged_champion": champion,
        "n_occurrences": len(occurrences),
        "legacy_unsafe_merge_pairs": len(unsafe),
        "legacy_unsafe_merge_concepts": len({item["concept_id"] for item in unsafe}),
        "legacy_evidence_transfer_targets": len(transfers),
        "legacy_foreign_support_spans": sum(
            int(item["foreign_support_spans_n"]) for item in transfers
        ),
        "exact_minus_legacy_concepts": len(exact.concepts) - len(legacy.concepts),
        "typed_relation_edges": len(typed.relations),
        "legacy_validation": validation,
        "arms": arm_values,
    }
    unsafe_rows = [
        {
            "slice_id": slice_id,
            "family": family,
            "source_id": row["source_id"],
            "case_id": row["case_id"],
            "gold": gold,
            "logged_champion": champion,
            **item,
        }
        for item in unsafe
    ]
    return row, unsafe_rows


def _mean(rows: Sequence[Mapping[str, Any]], getter) -> float:
    return statistics.fmean(float(getter(row)) for row in rows) if rows else float("nan")


def _rate(rows: Sequence[Mapping[str, Any]], getter) -> float:
    return _mean(rows, lambda row: bool(getter(row)))


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float]:
    if total <= 0:
        return [float("nan"), float("nan")]
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return [max(0.0, centre - radius), min(1.0, centre + radius)]


def _bootstrap_mean_delta(
    values: Sequence[float], *, seed: int, draws: int = 5000
) -> list[float]:
    if not values:
        return [float("nan"), float("nan")]
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(
        statistics.fmean(values[rng.randrange(n)] for _ in range(n))
        for _ in range(draws)
    )
    return [samples[int(0.025 * draws)], samples[min(draws - 1, int(0.975 * draws))]]


def summarize_group(rows: Sequence[Mapping[str, Any]], group_id: str) -> dict[str, Any]:
    n = len(rows)
    affected = sum(bool(row["legacy_unsafe_merge_pairs"]) for row in rows)
    concept_deltas = [float(row["exact_minus_legacy_concepts"]) for row in rows]
    summary: dict[str, Any] = {
        "group": group_id,
        "n_cases": n,
        "n_with_legacy_unsafe_merge": affected,
        "legacy_unsafe_merge_case_rate": affected / n if n else float("nan"),
        "legacy_unsafe_merge_case_rate_ci95_wilson": _wilson(affected, n),
        "legacy_unsafe_merge_pairs": sum(
            int(row["legacy_unsafe_merge_pairs"]) for row in rows
        ),
        "legacy_unsafe_merge_concepts": sum(
            int(row["legacy_unsafe_merge_concepts"]) for row in rows
        ),
        "legacy_evidence_transfer_targets": sum(
            int(row["legacy_evidence_transfer_targets"]) for row in rows
        ),
        "legacy_foreign_support_spans": sum(
            int(row["legacy_foreign_support_spans"]) for row in rows
        ),
        "mean_exact_minus_legacy_concepts": statistics.fmean(concept_deltas)
        if concept_deltas
        else float("nan"),
        "mean_exact_minus_legacy_concepts_ci95_bootstrap": _bootstrap_mean_delta(
            concept_deltas, seed=stable_seed("E7", group_id, "concept_delta")
        ),
        "legacy_reconstruction": {
            "concept_count_equal_rate": _rate(
                rows, lambda row: row["legacy_validation"]["concept_count_equal"]
            ),
            "partition_equal_rate": _rate(
                rows, lambda row: row["legacy_validation"]["partition_equal"]
            ),
            "scores_equal_rate": _rate(
                rows, lambda row: row["legacy_validation"]["scores_equal"]
            ),
        },
        "arms": {},
    }
    for arm in ARMS:
        summary["arms"][arm] = {
            "mean_concepts": _mean(rows, lambda row: row["arms"][arm]["n_concepts"]),
            "mean_relations": _mean(rows, lambda row: row["arms"][arm]["n_relations"]),
            "raw_gold_recall": _rate(
                rows, lambda row: row["arms"][arm]["gold_raw_hit"]
            ),
            "registry_gold_recall": _rate(
                rows, lambda row: row["arms"][arm]["gold_registry_hit"]
            ),
            "frontier_gold_recall": _rate(
                rows, lambda row: row["arms"][arm]["gold_exposure_hit"]
            ),
            "score_top1_gold": _rate(
                rows, lambda row: row["arms"][arm]["score_top1_gold"]
            ),
            "gold_identity_contamination_rate": _rate(
                rows, lambda row: row["arms"][arm]["gold_identity_contaminated"]
            ),
            "logged_champion_identity_contamination_rate": _rate(
                rows,
                lambda row: row["arms"][arm][
                    "logged_champion_identity_contaminated"
                ],
            ),
            "order_partition_change_rate": _rate(
                rows, lambda row: row["arms"][arm]["order_partition_changed"]
            ),
            "order_preferred_label_change_rate": _rate(
                rows,
                lambda row: row["arms"][arm]["order_preferred_labels_changed"],
            ),
            "order_score_top1_change_rate": _rate(
                rows, lambda row: row["arms"][arm]["order_score_top1_changed"]
            ),
        }
    return summary


def build_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    groups["ALL"].extend(rows)
    for row in rows:
        groups[str(row["family"])].append(row)
        groups[str(row["slice_id"])].append(row)
    ordered = ["ALL", "DA", "MCR"] + [spec.slice_id for spec in DEVELOPMENT_SLICES]
    return {
        "experiment_id": "E7",
        "analysis_level": "case trajectory",
        "development_not_confirmation": True,
        "groups": [summarize_group(groups[group], group) for group in ordered],
    }


def write_case_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = [
        "slice_id",
        "family",
        "source_id",
        "case_id",
        "gold",
        "logged_champion",
        "n_occurrences",
        "legacy_unsafe_merge_pairs",
        "legacy_unsafe_merge_concepts",
        "legacy_evidence_transfer_targets",
        "legacy_foreign_support_spans",
        "exact_minus_legacy_concepts",
        "typed_relation_edges",
        "legacy_gold_contaminated",
        "exact_gold_contaminated",
        "legacy_order_partition_changed",
        "exact_order_partition_changed",
        "legacy_score_top1",
        "exact_score_top1",
        "score_top1_flipped",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            legacy = row["arms"][ARM_LEGACY]
            exact = row["arms"][ARM_EXACT]
            writer.writerow(
                {
                    **{field: row.get(field, "") for field in fields},
                    "legacy_gold_contaminated": legacy["gold_identity_contaminated"],
                    "exact_gold_contaminated": exact["gold_identity_contaminated"],
                    "legacy_order_partition_changed": legacy["order_partition_changed"],
                    "exact_order_partition_changed": exact["order_partition_changed"],
                    "legacy_score_top1": legacy["score_top1"],
                    "exact_score_top1": exact["score_top1"],
                    "score_top1_flipped": not normalize_label(legacy["score_top1"])
                    == normalize_label(exact["score_top1"]),
                }
            )


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    unsafe_rows: Sequence[Mapping[str, Any]],
) -> None:
    groups = {row["group"]: row for row in summary["groups"]}
    overall = groups["ALL"]
    critical = sorted(
        rows,
        key=lambda row: (
            bool(row["arms"][ARM_LEGACY]["gold_identity_contaminated"]),
            int(row["legacy_unsafe_merge_pairs"]),
            int(row["legacy_foreign_support_spans"]),
        ),
        reverse=True,
    )[:20]
    lines = [
        "# E7 registry identity replay",
        "",
        "## Result in one sentence",
        "",
        (
            f"Across {overall['n_cases']} existing development trajectories, the legacy "
            f"substring registry made at least one non-synonym fold in "
            f"{overall['n_with_legacy_unsafe_merge']} cases "
            f"({_pct(overall['legacy_unsafe_merge_case_rate'])}); replacing it with "
            f"exact frozen-synonym identity restored a mean of "
            f"{overall['mean_exact_minus_legacy_concepts']:.3f} separately addressable "
            "concepts per case."
        ),
        "",
        "These are mechanism/development estimates, not a new confirmation result. "
        "The offline replay isolates identity and exposure mechanics; it does not count "
        "the old selector's answer as if the selector had seen the changed pool.",
        "",
        "## Primary endpoints",
        "",
        "| Group | n | Cases with unsafe fold | Unsafe pairs | Evidence-transfer targets | Mean nodes restored | Legacy gold identity contamination | Exact-synonym contamination |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for group_name in ("ALL", "DA", "MCR"):
        group = groups[group_name]
        lines.append(
            "| {group} | {n} | {affected} ({rate}) | {pairs} | {transfers} | {delta:.3f} | {legacy} | {exact} |".format(
                group=group_name,
                n=group["n_cases"],
                affected=group["n_with_legacy_unsafe_merge"],
                rate=_pct(group["legacy_unsafe_merge_case_rate"]),
                pairs=group["legacy_unsafe_merge_pairs"],
                transfers=group["legacy_evidence_transfer_targets"],
                delta=group["mean_exact_minus_legacy_concepts"],
                legacy=_pct(
                    group["arms"][ARM_LEGACY]["gold_identity_contamination_rate"]
                ),
                exact=_pct(
                    group["arms"][ARM_EXACT]["gold_identity_contamination_rate"]
                ),
            )
        )
    lines += [
        "",
        "The identity-contamination endpoint asks whether the node containing an "
        "exact/frozen-synonym gold or selected label also contains a label that is not "
        "a confirmed synonym. It is therefore stricter than simple post-registry recall: "
        "a swallowed gold string can remain textually present while losing its own node.",
        "",
        "## Reconstruction check",
        "",
        (
            "The replay reproduced the logged production concept count in "
            f"{_pct(overall['legacy_reconstruction']['concept_count_equal_rate'])} of cases, "
            "the logged preferred-name/alias partition in "
            f"{_pct(overall['legacy_reconstruction']['partition_equal_rate'])}, and logged "
            f"scores in {_pct(overall['legacy_reconstruction']['scores_equal_rate'])}."
        ),
        "",
        "Any non-100% reconstruction is retained at case level and is a scope warning, "
        "not silently discarded.",
        "",
        "## Highest-leverage trajectories for manual audit",
        "",
        "| Slice / case | Gold | Logged champion | Unsafe pairs | Foreign support spans | Legacy top score | Exact top score |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for row in critical:
        lines.append(
            "| {slice_id}/{source_id} | {gold} | {champion} | {pairs} | {spans} | {legacy} | {exact} |".format(
                slice_id=row["slice_id"],
                source_id=row["source_id"],
                gold=str(row["gold"]).replace("|", "/"),
                champion=str(row["logged_champion"]).replace("|", "/"),
                pairs=row["legacy_unsafe_merge_pairs"],
                spans=row["legacy_foreign_support_spans"],
                legacy=str(row["arms"][ARM_LEGACY]["score_top1"]).replace("|", "/"),
                exact=str(row["arms"][ARM_EXACT]["score_top1"]).replace("|", "/"),
            )
        )
    lines += [
        "",
        "## Mechanism interpretation and falsifier",
        "",
        "The production rule is not merely cosmetic deduplication. When a broad label "
        "is encountered first, a later specific label can be converted into an alias; "
        "support spans, generator agreement and axis bonuses are then pooled into the "
        "broad node. Reversing insertion order tests the complementary failure: the same "
        "evidence may be attached to a different preferred surface, and non-transitive "
        "substring chains can change the partition itself. The typed arm keeps those "
        "nodes distinct and records `non_equivalent_lexical_relation` edges. Their "
        "clinical direction is deliberately unresolved: for example, pseudoseptic "
        "arthritis is not a subtype of septic arthritis merely because one string "
        "contains the other.",
        "",
        "This mechanism would be weakened if (a) unsafe folds were rare with tight "
        "case-level intervals, (b) they caused no evidence or exposure change, and (c) "
        "fresh blinded selector calls were invariant. E7a tests (a) and the registry "
        "portion of (b). E7b is the preregistered fresh-selector test for (c).",
        "",
        "## Deliberate limits",
        "",
        "- The disease bridge is used only by exact normalized key lookup; its fuzzy and substring resolver tiers are disabled.",
        "- Lexical relation edges assert non-identity and surface containment only; they are not a clinical ontology gold standard.",
        "- Logged selector outputs are mapped for identity contamination only; no clinical win/loss is credited without a fresh selector call.",
        f"- Full unsafe-pair ledger contains {len(unsafe_rows)} rows; case-level JSONL retains all arm payloads.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "analysis/mechanism_v2/results/E7_registry_replay",
    )
    parser.add_argument(
        "--bridge",
        type=Path,
        default=ROOT / "data/knowledge_raw/disease_name_bridge.json",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(args.bridge)
    started = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    unsafe_rows: list[dict[str, Any]] = []
    input_paths: list[Path] = [args.bridge]
    log_lines = [
        f"started_at_utc={started.isoformat()}",
        f"bridge={args.bridge}",
        f"bridge_sha256={bridge.sha256}",
        f"bridge_exact_aliases={bridge.n_aliases}",
        f"bridge_ambiguous_aliases_excluded={len(bridge.collisions)}",
    ]

    by_slice = Counter()
    for spec, case, stage, stage_path in iter_stage_cases():
        row, case_unsafe = analyze_case(
            slice_id=spec.slice_id,
            family=spec.family,
            case=case,
            stage=stage,
            bridge=bridge,
        )
        rows.append(row)
        unsafe_rows.extend(case_unsafe)
        input_paths.append(stage_path)
        by_slice[spec.slice_id] += 1
    if len(rows) != 800:
        raise AssertionError(f"expected frozen 800-case development set; got {len(rows)}")

    summary = build_summary(rows)
    input_hash = combined_file_sha256(input_paths)
    summary.update(
        {
            "source_commit": source_commit(),
            "input_hash": input_hash,
            "bridge_sha256": bridge.sha256,
            "bridge_exact_aliases": bridge.n_aliases,
            "bridge_ambiguous_aliases_excluded": len(bridge.collisions),
            "slice_counts": dict(sorted(by_slice.items())),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )

    with (out / "case_results.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (out / "unsafe_merge_pairs.jsonl").open("w", encoding="utf-8") as stream:
        for row in unsafe_rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    write_case_csv(out / "case_summary.csv", rows)
    atomic_json(out / "summary.json", summary)
    write_report(out / "REPORT.md", summary, rows, unsafe_rows)

    manifest = RunManifest(
        experiment_id="E7",
        arm_id="legacy_substring__exact_synonym__typed_relation",
        dataset="DA400+MCR400 development trajectories",
        model="offline deterministic replay",
        workers=1,
        rag=False,
        source_commit=summary["source_commit"],
        prompt_hashes={},
        input_hash=input_hash,
        selection_freeze="all 800 existing MOSAIC Forest trajectories; no outcome-based selection",
        endpoint_contract=ENDPOINT_CONTRACT,
        excluded_variance_controls=[
            "repeated multi-run execution",
            "expanded confirmation set",
            "provider/retry standardization arm",
        ],
        capabilities=dependency_capabilities(),
        created_at_utc=started.isoformat(),
    )
    manifest.write(out / "manifest.json")
    finished = datetime.now(timezone.utc)
    log_lines += [
        f"finished_at_utc={finished.isoformat()}",
        f"duration_seconds={(finished - started).total_seconds():.3f}",
        f"n_cases={len(rows)}",
        f"n_unsafe_merge_pairs={len(unsafe_rows)}",
        f"input_hash={input_hash}",
        f"summary_hash={json_sha256(summary)}",
        "llm_calls=0",
        "status=complete_e7a_offline_registry_replay",
    ]
    (out / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print(json.dumps(summary["groups"][:3], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
