#!/usr/bin/env python3
"""Exhaustive canonical-endpoint migration for the 79 non-E2 experiment arms.

The migration is deliberately split into immutable stages:

``freeze``
    Recover every registered case-arm Top-1 output, replay deterministic
    endpoints, attach only exact-normalized E2 root relations, and freeze
    method-blind clinical and family-specific task cards.
``run-reviewer``
    Run one independent clinical-relation reviewer over the frozen blind
    cards.  Embedded E2 sentinels are hidden from the reviewer.
``run-task``
    Run one canonical family-specific task evaluator per case.  DA maps every
    diagnosis to a source option before the gold option is joined offline;
    MCR applies one semantic diagnostic judge to every candidate.
``compile-panel``
    Validate coverage and score the embedded sentinels before freezing a
    panel ledger and a fully blinded arbitration queue.
``run-arbitrator``
    Optionally resolve every novel relation after seeing the three blinded
    reviews but no experiment, arm, endpoint, or historical proxy metadata.
    This is a sensitivity layer, never human-root truth.
``finalize``
    Expand root, optional arbitrator, or explicitly model-panel relations and
    fresh task projections back to the 24,076 intention rows, then compute
    ITA/served arm rates and preregistered paired contrasts.

No credential is written to any artifact.  Online calls use the repository's
audited ``OnlineJSONCaller`` and its immutable content-addressed cache.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "scripts"))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    file_sha256,
    normalize_label,
)
from analysis.mechanism_v2.e2_blinded_adjudication import (  # noqa: E402
    IDENTIFIABILITY,
    RELATIONS,
    _load_case_universe,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    atomic_json,
    stable_seed,
    validate_workers,
)
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
    _normalize_label,
)


EXPERIMENT_ID = "canonical-endpoint-migration-79-arm-v1"
SOURCE_COMMIT = "6ed5ccc02caec2550e0b625915a649ad5738e473"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION"
COVERAGE_MATRIX = (
    ROOT
    / "analysis/mechanism_v2/results/ENDPOINT_COVERAGE_AUDIT/endpoint_coverage_matrix.json"
)
E2_REPLAY = (
    ROOT
    / "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication"
    / "unified_800/five_endpoint_replay.jsonl"
)
E2_ROOT = E2_REPLAY.parents[1] / "root_audit"
E2_SUPPLEMENT_ROOT = E2_REPLAY.parent / "root_audit"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
CLINICAL_REVIEWERS = {
    "reviewer_a": "google/gemini-2.5-flash",
    "reviewer_b": "anthropic/claude-sonnet-4.6",
    "reviewer_c": "openai/gpt-5.6",
}
TASK_MODEL = "google/gemini-2.5-flash"
ARBITRATOR_MODEL = "openai/gpt-5.6"
RELATION_CODE = {
    "complete_equivalent": "C",
    "partial_parent_or_component": "P",
    "conflicting_subtype_or_scope": "X",
    "manifestation_or_related": "M",
    "not_equivalent": "N",
    "uncertain": "U",
}
COMPATIBLE_RELATIONS = frozenset(
    {"complete_equivalent", "partial_parent_or_component"}
)


CLINICAL_PROMPT = r"""You are an independent clinical endpoint reviewer. You
do not know which diagnostic system or experimental condition produced any
candidate. Evaluate only the supplied clinical record, benchmark reference,
and neutrally numbered candidates. Candidate order and wording polish carry no
evidential weight.

For every candidate, judge its relation to the FULL requested benchmark
reference in this case. Preserve every required subtype, etiology, anatomy,
time/state, complication, stage, and composite component:
- complete_equivalent: the same final diagnostic object with all required
  components; harmless aliases and wording variants are allowed;
- partial_parent_or_component: compatible family/parent/child/cause/
  manifestation/component but missing required specificity or a component;
- conflicting_subtype_or_scope: related but asserts an incompatible subtype,
  anatomy, cause, time/state, stage, or composite scope;
- manifestation_or_related: manifestation, complication, association, or
  differential rather than the requested final object;
- not_equivalent: a different diagnostic entity;
- uncertain: the supplied record genuinely cannot resolve the relation.

Do not upgrade a merely plausible diagnosis to complete equivalence. Missing
tests are unknown, not negative. Return strict JSON and cover every candidate
exactly once:
{
  "candidate_relations": [
    {
      "candidate_id": "C001",
      "relation": "complete_equivalent|partial_parent_or_component|conflicting_subtype_or_scope|manifestation_or_related|not_equivalent|uncertain",
      "scope_detail": "brief boundary description",
      "reason": "brief case-grounded reason",
      "confidence": "high|medium|low"
    }
  ],
  "case_quality_flags": ["optional concise flag"]
}
"""

DA_TASK_PROMPT = r"""You are the frozen DiagnosisArena answer projection
mapper. Map every predicted diagnosis to the single source answer option that
is clinically closest in meaning. Do not decide whether the prediction is a
complete diagnosis and do not use candidate order. Use NONE only when no
option is a defensible projection. Return strict JSON and cover every
candidate_id exactly once:
{
  "mappings": [
    {
      "candidate_id": "T001",
      "mapped_option": "A|B|C|D|E|F|NONE",
      "reason": "brief semantic mapping reason",
      "confidence": "high|medium|low"
    }
  ]
}
"""

MCR_TASK_PROMPT = r"""Apply the frozen MedCaseReasoning Prompt-7 diagnostic
accuracy criterion independently to every prediction: is the predicted
diagnosis correct relative to the true diagnosis? This is the benchmark task
judge, not the clinical-completeness relation taxonomy. Return strict JSON and
cover every candidate_id exactly once:
{
  "judgments": [
    {
      "candidate_id": "T001",
      "correct": true,
      "reason": "brief semantic judge reason",
      "confidence": "high|medium|low"
    }
  ]
}
"""

ARBITRATION_PROMPT = r"""You are the blinded final clinical adjudicator. The
case and candidate labels are method-blind. Three independent reviewers have
already assessed each candidate; their judgments may be wrong. Re-evaluate
the candidate against the FULL reference using the clinical record, then use
the reviews only as fallible advice. Apply exactly the six supplied relation
definitions:
- complete_equivalent: same final diagnostic object with all required subtype,
  etiology, anatomy, time/state, complication, stage and composite components;
- partial_parent_or_component: compatible family/parent/child/cause/
  manifestation/component but missing required specificity or a component;
- conflicting_subtype_or_scope: related but incompatible subtype, anatomy,
  cause, time/state, stage, or composite scope;
- manifestation_or_related: manifestation, complication, association, or
  differential rather than the requested final object;
- not_equivalent: different diagnostic entity;
- uncertain: the record genuinely cannot resolve the relation.
Do not infer anything from reviewer order or candidate wording.
Return strict JSON and cover every candidate exactly once:
{
  "final_relations": [
    {
      "candidate_id": "C001",
      "relation": "complete_equivalent|partial_parent_or_component|conflicting_subtype_or_scope|manifestation_or_related|not_equivalent|uncertain",
      "reason": "brief case-grounded final reason",
      "confidence": "high|medium|low"
    }
  ],
  "case_quality_flags": ["optional concise flag"]
}
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _prediction_key(value: str) -> str:
    return normalize_label(str(value or ""))


def _surface(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _legacy_label_match(
    left: str, right: str, resolver: DiseaseNameResolver
) -> bool:
    """Byte-compatible logic of the historical L2 ``_label_match`` chain."""
    a = _normalize_label(left)
    b = _normalize_label(right)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    try:
        return resolver.canonicalize_entity(left) == resolver.canonicalize_entity(right)
    except Exception:
        return False


def _json_rows(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    if not rows:
        raise FileNotFoundError(f"required nonempty source missing: {path}")
    return rows


def _target_arm_records() -> list[dict[str, Any]]:
    document = json.loads(COVERAGE_MATRIX.read_text(encoding="utf-8"))
    records = [
        dict(row)
        for row in document["arm_records"]
        if str(row["experiment_id"]) not in {"E2", "E7a"}
    ]
    if len(records) != 79:
        raise AssertionError(f"expected 79 migration arms, found {len(records)}")
    if any(bool(row.get("full_root_census")) for row in records):
        raise AssertionError("target registry unexpectedly contains a full E2 census arm")
    return records


def _append_row(
    rows: list[dict[str, Any]],
    *,
    experiment: str,
    arm: str,
    source: Path,
    source_row: Mapping[str, Any],
    prediction: Any,
    success: Any,
    case_key: Any | None = None,
    family: Any | None = None,
    gold: Any | None = None,
) -> None:
    prediction_text = _surface(prediction)
    rows.append(
        {
            "experiment_id": experiment,
            "arm_id": arm,
            "case_key": str(case_key or source_row.get("case_key") or ""),
            "benchmark_family": str(family or source_row.get("family") or ""),
            "reference_diagnosis": _surface(gold or source_row.get("gold")),
            "prediction_pre_projection": prediction_text,
            "served": bool(_bool(success) and prediction_text),
            "source_path": str(source.relative_to(ROOT)),
        }
    )


def load_target_rows() -> list[dict[str, Any]]:
    """Recover the exact Top-1 intention ledger for all registered 79 arms."""
    results = ROOT / "analysis/mechanism_v2/results"
    rows: list[dict[str, Any]] = []

    ordinary = {
        "E1": ("E1_input_factorial", "champion_label"),
        "E4": ("E4_fixed_pool_crossover", "champion_label"),
        "E5": ("E5_candidate_interference", "champion_label"),
        "E6": ("E6_representation_fidelity", "champion_label"),
        "E8": ("E8_temporal_veto", "champion_label"),
        "E9": ("E9_view_independence", "champion_label"),
        "E10": ("E10_mac_factorial", "top2_labels"),
        "E11": ("E11_b07_factorial", "top2_labels"),
        "E12": ("E12_e7_factorial", "champion_label"),
        "RCR3": ("RCR3_relation_preserving", "champion_label"),
    }
    for experiment, (directory, field) in ordinary.items():
        for path in sorted((results / directory / "arms").glob("*/case_results.jsonl")):
            arm = path.parent.name
            for row in _json_rows(path):
                prediction: Any = row.get(field)
                if field == "top2_labels":
                    labels = list(row.get(field) or [])
                    prediction = labels[0] if labels else ""
                _append_row(
                    rows,
                    experiment=experiment,
                    arm=arm,
                    source=path,
                    source_row=row,
                    prediction=prediction,
                    success=row.get("success", True),
                )

    e6x_sources = (
        (
            "flat_facts_padded",
            results / "E6_representation_fidelity/arms/flat_facts/case_results.jsonl",
        ),
        (
            "flat_facts_unpadded",
            results / "E6x_unpadded_flat/arm/case_results.jsonl",
        ),
    )
    for arm, path in e6x_sources:
        for row in _json_rows(path):
            _append_row(
                rows,
                experiment="E6x",
                arm=arm,
                source=path,
                source_row=row,
                prediction=row.get("champion_label"),
                success=row.get("success", True),
            )

    for experiment, directory in (
        ("E7b", "E7b_registry_selector"),
        ("E7c", "E7c_directional_registry"),
    ):
        path = results / directory / "case_summary.csv"
        for row in _read_csv(path):
            _append_row(
                rows,
                experiment=experiment,
                arm=str(row["arm"]),
                source=path,
                source_row=row,
                prediction=row.get("champion_label"),
                success=row.get("success"),
            )

    path = results / "E14x_runtime_gate/case_ledger.jsonl"
    for row in _json_rows(path):
        for arm, field in (
            ("mosaic_lite_v1", "lite_champion"),
            ("mosaic_adaptive4v2_v1", "adaptive_champion"),
        ):
            _append_row(
                rows,
                experiment="E14x",
                arm=arm,
                source=path,
                source_row=row,
                prediction=row.get(field),
                success=bool(row.get(field)),
            )
    return rows


def load_e2_registry() -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, dict[str, Any]]]:
    """Load E2 final root relations and identities with conflict checks."""
    relations: dict[tuple[str, str], dict[str, Any]] = {}
    identities: dict[str, dict[str, Any]] = {}
    # The replay contains only the nine arm champions.  The authoritative root
    # registry is larger (3,103 unique case-candidate relations) and is what a
    # cross-experiment exact-normalized reuse must consult.
    old_rows = _json_rows(E2_ROOT / "resolved_relations.jsonl")
    if len(old_rows) != 1673:
        raise AssertionError(f"E2 v1 relation registry drift: {len(old_rows)}")
    for row in old_rows:
        key = (str(row["case_key"]), _prediction_key(str(row["candidate_label"])))
        candidate = {
            "relation": str(row["relation"]),
            "source": "e2_v1_blinded_root_census_sample",
            "provenance": str(row["source"]),
            "status": "root_adjudicated",
            "safe_exact": str(row["source"]) == "frozen_exact_identity",
            "surface": _surface(row["candidate_label"]),
        }
        if candidate["relation"] not in RELATIONS:
            raise AssertionError(f"invalid E2 v1 relation for {key}")
        if key in relations:
            raise AssertionError(f"duplicate normalized E2 v1 relation: {key}")
        relations[key] = candidate

    index_rows = _json_rows(E2_SUPPLEMENT_ROOT / "index.jsonl")
    final_rows = _json_rows(E2_SUPPLEMENT_ROOT / "final_decisions.jsonl")
    if len(index_rows) != 1430 or len(final_rows) != 400:
        raise AssertionError(
            f"E2 supplement drift: index={len(index_rows)} final={len(final_rows)}"
        )
    index = {str(row["blind_candidate_id"]): row for row in index_rows}
    if len(index) != len(index_rows):
        raise AssertionError("duplicate E2 supplement blind_candidate_id")
    final_relations: dict[str, dict[str, Any]] = {}
    case_confidence: dict[str, str] = {}
    for case in final_rows:
        blind_case_id = str(case["blind_case_id"])
        case_confidence[blind_case_id] = str(case["confidence_bucket"])
        for relation in list(case.get("relations") or []):
            blind_id = str(relation["blind_candidate_id"])
            if blind_id in final_relations:
                raise AssertionError(f"duplicate E2 supplement decision: {blind_id}")
            final_relations[blind_id] = dict(relation)
    safe_n = 0
    for blind_id, row in index.items():
        safe = bool(row["safe_exact"])
        if safe:
            safe_n += 1
            relation = "complete_equivalent"
            provenance = "frozen_exact_identity"
        else:
            decision = final_relations.get(blind_id)
            if decision is None:
                raise AssertionError(f"missing E2 supplement relation: {blind_id}")
            relation = {
                "C": "complete_equivalent",
                "P": "partial_parent_or_component",
                "X": "conflicting_subtype_or_scope",
                "M": "manifestation_or_related",
                "N": "not_equivalent",
                "U": "uncertain",
            }[str(decision["final_code"])]
            provenance = (
                "root_manual_blinded_supplement_override"
                if bool(decision.get("root_overridden"))
                else "root_manual_blinded_supplement"
            )
        key = (str(row["case_key"]), _prediction_key(str(row["candidate_label"])))
        candidate = {
            "relation": relation,
            "source": "e2_v2_blinded_root_census_supplement",
            "provenance": provenance,
            "status": "root_adjudicated",
            "safe_exact": safe,
            "surface": _surface(row["candidate_label"]),
            "case_review_confidence": case_confidence[str(row["blind_case_id"])],
        }
        prior = relations.get(key)
        if prior is not None:
            raise AssertionError(f"duplicate old/new normalized E2 relation: {key}")
        relations[key] = candidate
    if safe_n != 59 or len(final_relations) != 1371:
        raise AssertionError(
            f"E2 supplement coverage drift: safe={safe_n} manual={len(final_relations)}"
        )

    # Identity metadata are already expanded to all 800 cases in the final
    # replay.  Read it only for identity/gold/family, never to shrink the
    # authoritative relation registry back to champion outputs.
    for row in _json_rows(E2_REPLAY):
        case_key = str(row["case_key"])
        identity = {
            "reference_identifiability": str(row["reference_identifiability"]),
            "reference_diagnosis": _surface(row["reference_diagnosis"]),
            "benchmark_family": str(row["benchmark_family"]),
        }
        if identity["reference_identifiability"] not in IDENTIFIABILITY:
            raise AssertionError(f"invalid E2 identity for {case_key}")
        prior_identity = identities.get(case_key)
        if prior_identity and prior_identity != identity:
            raise AssertionError(f"conflicting E2 identity metadata for {case_key}")
        identities[case_key] = identity
    if len(relations) != 3103 or len(identities) != 800:
        raise AssertionError(
            f"E2 registry drift: relations={len(relations)} identities={len(identities)}"
        )
    expected = Counter({
        "complete_equivalent": 296,
        "partial_parent_or_component": 972,
        "conflicting_subtype_or_scope": 598,
        "manifestation_or_related": 449,
        "not_equivalent": 787,
        "uncertain": 1,
    })
    observed = Counter(row["relation"] for row in relations.values())
    if observed != expected:
        raise AssertionError(f"E2 relation distribution drift: {observed}")
    return relations, identities


def load_case_metadata() -> dict[str, dict[str, Any]]:
    universe, _hashes = _load_case_universe()
    metadata = {str(row["case_key"]): dict(row) for row in universe}
    if len(metadata) != 800:
        raise AssertionError("E2 case universe must contain 800 unique cases")
    return metadata


def _relation_id(case_key: str, normalized_prediction: str) -> str:
    return hashlib.sha256(
        f"relation-v1\0{case_key}\0{normalized_prediction}".encode("utf-8")
    ).hexdigest()[:24]


def _row_id(experiment: str, arm: str, case_key: str) -> str:
    return hashlib.sha256(
        f"intention-row-v1\0{experiment}\0{arm}\0{case_key}".encode("utf-8")
    ).hexdigest()[:24]


def _task_id(
    family: str, case_key: str, prediction: str, reference_diagnosis: str
) -> str:
    # DA projection depends on that case's source options; MCR Prompt-7 depends
    # only on the raw predicted and actual diagnosis strings.
    identity = (
        (family, case_key, prediction)
        if family == "DA"
        else (family, prediction, reference_diagnosis)
    )
    return hashlib.sha256(
        ("task-v1\0" + "\0".join(identity)).encode("utf-8")
    ).hexdigest()[:24]


def _validate_registered_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    registry = _target_arm_records()
    expected = {
        (str(row["experiment_id"]), str(row["arm_id"])): int(row["intended_case_n"])
        for row in registry
    }
    observed = Counter((str(row["experiment_id"]), str(row["arm_id"])) for row in rows)
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        raise AssertionError(f"79-arm registry mismatch; missing={missing} extra={extra}")
    wrong = {key: (observed[key], expected[key]) for key in expected if observed[key] != expected[key]}
    if wrong:
        raise AssertionError(f"intention row count mismatch: {wrong}")
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (str(row["experiment_id"]), str(row["arm_id"]), str(row["case_key"]))
        if key in seen:
            raise AssertionError(f"duplicate intention row: {key}")
        seen.add(key)
    if len(rows) != 24076:
        raise AssertionError(f"expected 24,076 intention rows, found {len(rows)}")


def _sentinel_keys(
    case_key: str,
    e2_relations: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[tuple[str, str]]:
    candidates = [
        key
        for key, value in e2_relations.items()
        if key[0] == case_key and not bool(value.get("safe_exact"))
    ]
    relation_rank = {
        "complete_equivalent": 0,
        "partial_parent_or_component": 1,
        "conflicting_subtype_or_scope": 2,
        "manifestation_or_related": 3,
        "not_equivalent": 4,
        "uncertain": 5,
    }
    ordered = sorted(
        candidates,
        key=lambda key: (
            stable_seed("endpoint-migration-sentinel-v1", case_key, key[1]),
            key[1],
        ),
    )
    selected: list[tuple[str, str]] = []
    used_groups: set[str] = set()
    for key in ordered:
        relation = str(e2_relations[key]["relation"])
        group = "compatible" if relation in COMPATIBLE_RELATIONS else "incompatible"
        if group not in used_groups:
            selected.append(key)
            used_groups.add(group)
        if len(selected) == 2:
            break
    for key in sorted(
        ordered,
        key=lambda item: (
            relation_rank[str(e2_relations[item]["relation"])],
            stable_seed("endpoint-migration-sentinel-fill-v1", case_key, item[1]),
        ),
    ):
        if key not in selected:
            selected.append(key)
        if len(selected) == 2:
            break
    return selected


def freeze(out: Path) -> dict[str, Any]:
    out = Path(out)
    design = out / "design"
    design.mkdir(parents=True, exist_ok=True)
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    resolver = DiseaseNameResolver()
    e2_relations, identities = load_e2_registry()
    case_metadata = load_case_metadata()
    rows = load_target_rows()
    _validate_registered_rows(rows)

    relation_surfaces: dict[tuple[str, str], str] = {}
    for row in rows:
        case_key = str(row["case_key"])
        metadata = case_metadata.get(case_key)
        identity = identities.get(case_key)
        if metadata is None or identity is None:
            raise AssertionError(f"target case absent from E2 universe: {case_key}")
        if not row["reference_diagnosis"]:
            row["reference_diagnosis"] = str(metadata["gold"])
        if _prediction_key(row["reference_diagnosis"]) != _prediction_key(metadata["gold"]):
            raise AssertionError(f"reference diagnosis drift for {case_key}")
        if str(row["benchmark_family"]) != str(metadata["family"]):
            raise AssertionError(f"benchmark family drift for {case_key}")
        row["reference_identifiability"] = identity["reference_identifiability"]
        row["row_id"] = _row_id(
            str(row["experiment_id"]), str(row["arm_id"]), case_key
        )
        if row["served"]:
            normalized = _prediction_key(row["prediction_pre_projection"])
            if not normalized:
                raise AssertionError(f"served row has empty normalized prediction: {row['row_id']}")
            relation_key = (case_key, normalized)
            prior_surface = relation_surfaces.get(relation_key)
            surface = str(row["prediction_pre_projection"])
            if prior_surface is None or (len(surface), surface) < (len(prior_surface), prior_surface):
                relation_surfaces[relation_key] = surface
            row["relation_id"] = _relation_id(*relation_key)
            row["task_id"] = _task_id(
                str(row["benchmark_family"]),
                case_key,
                surface,
                str(row["reference_diagnosis"]),
            )
            row["safe_exact"] = bool(
                bridge.equivalent(surface, str(row["reference_diagnosis"]))
            )
            row["legacy_chain"] = bool(
                _legacy_label_match(
                    surface, str(row["reference_diagnosis"]), resolver
                )
            )
            existing = e2_relations.get(relation_key)
            if existing is not None:
                row["clinical_relation"] = str(existing["relation"])
                row["clinical_audit_source"] = "e2_exact_normalized_reuse"
                row["clinical_audit_parent_source"] = str(existing["source"])
            elif row["safe_exact"]:
                row["clinical_relation"] = "complete_equivalent"
                row["clinical_audit_source"] = "deterministic_frozen_safe_exact"
                row["clinical_audit_parent_source"] = ""
            else:
                row["clinical_relation"] = None
                row["clinical_audit_source"] = "pending_blinded_panel"
                row["clinical_audit_parent_source"] = ""
        else:
            row.update(
                {
                    "relation_id": None,
                    "task_id": None,
                    "safe_exact": False,
                    "legacy_chain": False,
                    "clinical_relation": None,
                    "clinical_audit_source": "unserved_not_applicable",
                    "clinical_audit_parent_source": "",
                }
            )

    served = [row for row in rows if row["served"]]
    unique_relations = {
        (str(row["case_key"]), _prediction_key(row["prediction_pre_projection"]))
        for row in served
    }
    pending = {
        key
        for key in unique_relations
        if key not in e2_relations
        and not bridge.equivalent(relation_surfaces[key], identities[key[0]]["reference_diagnosis"])
    }
    if len(served) != 23035 or len(unique_relations) != 5344 or len(pending) != 3400:
        raise AssertionError(
            "migration census drift: "
            f"served={len(served)} unique={len(unique_relations)} pending={len(pending)}"
        )

    pending_by_case: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key in pending:
        pending_by_case[key[0]].append(key)
    if len(pending_by_case) != 628:
        raise AssertionError(f"expected 628 pending cases, found {len(pending_by_case)}")

    clinical_cards: list[dict[str, Any]] = []
    relation_index: list[dict[str, Any]] = []
    sentinel_truth: list[dict[str, Any]] = []
    for case_number, case_key in enumerate(sorted(pending_by_case), 1):
        blind_case_id = f"MIGC{case_number:04d}"
        novel_keys = sorted(pending_by_case[case_key])
        sentinel_keys = _sentinel_keys(case_key, e2_relations)
        combined = [(key, "novel") for key in novel_keys] + [
            (key, "sentinel") for key in sentinel_keys
        ]
        combined.sort(
            key=lambda item: (
                stable_seed("endpoint-migration-card-order-v1", case_key, item[0][1]),
                item[0][1],
            )
        )
        registry: list[dict[str, str]] = []
        for candidate_number, (key, kind) in enumerate(combined, 1):
            candidate_id = f"C{candidate_number:03d}"
            blind_candidate_id = f"{blind_case_id}-{candidate_id}"
            surface = (
                relation_surfaces[key]
                if kind == "novel"
                else str(e2_relations[key]["surface"])
            )
            registry.append({"candidate_id": candidate_id, "label": surface})
            relation_index.append(
                {
                    "blind_case_id": blind_case_id,
                    "candidate_id": candidate_id,
                    "blind_candidate_id": blind_candidate_id,
                    "case_key": case_key,
                    "relation_id": _relation_id(*key),
                    "normalized_prediction": key[1],
                    "candidate_label": surface,
                    "candidate_kind": kind,
                }
            )
            if kind == "sentinel":
                sentinel_truth.append(
                    {
                        "blind_candidate_id": blind_candidate_id,
                        "relation": str(e2_relations[key]["relation"]),
                        "parent_source": str(e2_relations[key]["source"]),
                    }
                )
        metadata = case_metadata[case_key]
        clinical_cards.append(
            {
                "blind_case_id": blind_case_id,
                "clinical_record": str(metadata["vignette"]),
                "reference_diagnosis": str(metadata["gold"]),
                "candidate_registry": registry,
            }
        )

    task_cards: list[dict[str, Any]] = []
    task_index: list[dict[str, Any]] = []
    task_by_case: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in served:
        task_id = str(row["task_id"])
        task_by_case[str(row["case_key"])].setdefault(
            task_id,
            {
                "task_id": task_id,
                "prediction": str(row["prediction_pre_projection"]),
                "relation_id": str(row["relation_id"]),
            },
        )
    for case_number, case_key in enumerate(sorted(task_by_case), 1):
        blind_task_id = f"MIGT{case_number:04d}"
        metadata = case_metadata[case_key]
        task_rows = sorted(
            task_by_case[case_key].values(),
            key=lambda row: (
                stable_seed(
                    "endpoint-migration-task-order-v1", case_key, row["task_id"]
                ),
                row["task_id"],
            ),
        )
        registry: list[dict[str, str]] = []
        for candidate_number, task_row in enumerate(task_rows, 1):
            candidate_id = f"T{candidate_number:03d}"
            registry.append(
                {"candidate_id": candidate_id, "label": task_row["prediction"]}
            )
            task_index.append(
                {
                    "blind_task_id": blind_task_id,
                    "candidate_id": candidate_id,
                    "task_id": task_row["task_id"],
                    "case_key": case_key,
                    "relation_id": task_row["relation_id"],
                    "benchmark_family": str(metadata["family"]),
                    "gold_option": str(metadata["gold_option"]),
                }
            )
        task_card: dict[str, Any] = {
            "blind_task_id": blind_task_id,
            "benchmark_family": str(metadata["family"]),
            "candidate_registry": registry,
        }
        if metadata["family"] == "DA":
            task_card["source_options"] = dict(metadata["source_options"])
            task_card["clinical_record"] = str(metadata["vignette"])
        else:
            task_card["reference_diagnosis"] = str(metadata["gold"])
        task_cards.append(task_card)

    rows.sort(key=lambda row: (row["experiment_id"], row["arm_id"], row["case_key"]))
    write_jsonl(design / "intention_ledger.jsonl", rows)
    write_jsonl(design / "blinded_clinical_cards.jsonl", clinical_cards)
    write_jsonl(design / "relation_index.jsonl", relation_index)
    write_jsonl(design / "sentinel_truth.jsonl", sentinel_truth)
    write_jsonl(design / "blinded_task_cards.jsonl", task_cards)
    write_jsonl(design / "task_index.jsonl", task_index)
    atomic_json(design / "arm_registry.json", {"arms": _target_arm_records()})

    summary = {
        "schema_version": "canonical-endpoint-migration-freeze-v1",
        "experiment_id": EXPERIMENT_ID,
        "source_commit": SOURCE_COMMIT,
        "created_at_utc": utcnow(),
        "n_arms": 79,
        "n_intention_rows": len(rows),
        "n_served_rows": len(served),
        "n_unserved_rows": len(rows) - len(served),
        "n_unique_case_prediction_relations": len(unique_relations),
        "n_e2_reused_relations": len(unique_relations & set(e2_relations)),
        "n_pending_relations": len(pending),
        "n_pending_cases": len(pending_by_case),
        "n_embedded_sentinels": len(sentinel_truth),
        "n_task_cases": len(task_cards),
        "n_task_payloads": len({row["task_id"] for row in task_index}),
        "n_task_case_payload_links": len(task_index),
        "clinical_payload_withheld": [
            "case_key",
            "experiment_id",
            "arm_id",
            "safe_exact",
            "legacy_chain",
            "task",
            "historical_proxy",
            "candidate_kind",
            "sentinel_truth",
        ],
        "task_payload_withheld": [
            "case_key",
            "experiment_id",
            "arm_id",
            "clinical_relation",
            "safe_exact",
            "legacy_chain",
            "historical_task",
            "gold_option (DA only; joined offline)",
        ],
        "source_hashes": {
            str(E2_REPLAY.relative_to(ROOT)): file_sha256(E2_REPLAY),
            str(COVERAGE_MATRIX.relative_to(ROOT)): file_sha256(COVERAGE_MATRIX),
            str(BRIDGE_PATH.relative_to(ROOT)): file_sha256(BRIDGE_PATH),
        },
    }
    summary["artifact_hashes"] = {
        path.name: file_sha256(path)
        for path in sorted(design.iterdir())
        if path.is_file() and path.name != "freeze_summary.json"
    }
    atomic_json(design / "freeze_summary.json", summary)
    return summary


def _clinical_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "blind_case_id": str(card["blind_case_id"]),
        "clinical_record": str(card["clinical_record"]),
        "reference_diagnosis": str(card["reference_diagnosis"]),
        "candidate_registry": [
            {
                "candidate_id": str(row["candidate_id"]),
                "label": str(row["label"]),
            }
            for row in card["candidate_registry"]
        ],
    }


def _validate_relation_response(
    response: Mapping[str, Any], allowed: set[str], field: str = "candidate_relations"
) -> str | None:
    rows = response.get(field)
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        return f"{field} must be a list of objects"
    identifiers = [str(row.get("candidate_id") or "") for row in rows]
    if len(identifiers) != len(allowed) or set(identifiers) != allowed:
        return f"{field} must cover every candidate exactly once"
    for row in rows:
        if str(row.get("relation") or "") not in RELATIONS:
            return "invalid clinical relation"
        if str(row.get("confidence") or "") not in {"high", "medium", "low"}:
            return "invalid relation confidence"
        if not str(row.get("reason") or "").strip():
            return "relation reason is required"
    flags = response.get("case_quality_flags")
    if flags is not None and not isinstance(flags, list):
        return "case_quality_flags must be a list"
    return None


def run_reviewer(
    out: Path,
    reviewer_id: str,
    model: str,
    workers: int,
    *,
    cache_only: bool = False,
) -> dict[str, Any]:
    workers = validate_workers(workers, rag=False)
    cards_path = Path(out) / "design/blinded_clinical_cards.jsonl"
    cards = read_jsonl(cards_path)
    if len(cards) != 628:
        raise AssertionError(f"expected 628 frozen clinical cards, found {len(cards)}")
    directory = Path(out) / "reviewers" / reviewer_id
    directory.mkdir(parents=True, exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = _clinical_payload(card)
        allowed = {
            str(row["candidate_id"]) for row in payload["candidate_registry"]
        }
        try:
            outcome = caller.call(
                module=f"EndpointMigrationClinical_{reviewer_id}",
                prompt=CLINICAL_PROMPT,
                payload=payload,
                validator=lambda response: _validate_relation_response(
                    response, allowed
                ),
                cache_only=cache_only,
            )
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": outcome.success,
                "error": outcome.error,
                "review": outcome.response,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "reviewer_id": reviewer_id,
                "model": model,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "review": {},
                "cache_hit": False,
                "cache_key": "",
                "prompt_sha256": hashlib.sha256(
                    CLINICAL_PROMPT.encode("utf-8")
                ).hexdigest(),
                "payload_sha256": canonical_sha256(payload),
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, card): str(card["blind_case_id"]) for card in cards}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["blind_case_id"])
    write_jsonl(directory / "reviews.jsonl", results)
    summary = {
        "schema_version": "canonical-endpoint-clinical-reviewer-v1",
        "reviewer_id": reviewer_id,
        "model": model,
        "created_at_utc": utcnow(),
        "cards_sha256": file_sha256(cards_path),
        "prompt_sha256": hashlib.sha256(CLINICAL_PROMPT.encode("utf-8")).hexdigest(),
        "n_cards": len(results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "n_cache_hit": sum(bool(row["cache_hit"]) for row in results),
    }
    atomic_json(directory / "summary.json", summary)
    return summary


class _OnlineMapperAdapter:
    """Adapter exposing ``call_module`` while retaining cache provenance."""

    def __init__(self, caller: OnlineJSONCaller, *, cache_only: bool = False) -> None:
        self.caller = caller
        self.cache_only = cache_only
        self.calls: list[dict[str, Any]] = []

    def call_module(
        self, module: str, prompt: str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        outcome = self.caller.call(
            module=f"EndpointMigrationTask_{module}",
            prompt=prompt,
            payload=dict(payload),
            cache_only=self.cache_only,
        )
        self.calls.append(
            {
                "module": module,
                "success": outcome.success,
                "error": outcome.error,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        )
        if not outcome.success:
            raise ValueError(outcome.error or f"invalid {module} response")
        return outcome.response


def _validate_mcr_task(response: Mapping[str, Any]) -> str | None:
    if str(response.get("answer") or "").strip().lower() not in {"y", "n"}:
        return "answer must be y or n"
    if not str(response.get("reason") or "").strip():
        return "reason is required"
    return None


def run_task(
    out: Path,
    model: str,
    workers: int,
    *,
    cache_only: bool = False,
) -> dict[str, Any]:
    """Run fresh canonical DA mapper and MCR Prompt-7 task projections."""
    from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: WPS433
        RelationAwareAnswerMapper,
        load_offline_resolver,
    )

    workers = validate_workers(workers, rag=False)
    out = Path(out)
    task_dir = out / "task_evaluator"
    task_dir.mkdir(parents=True, exist_ok=True)
    cards = read_jsonl(out / "design/blinded_task_cards.jsonl")
    index_rows = read_jsonl(out / "design/task_index.jsonl")
    if len(cards) != 751:
        raise AssertionError(f"expected 751 task cards, found {len(cards)}")
    card_by_id = {str(row["blind_task_id"]): row for row in cards}
    index = {
        (str(row["blind_task_id"]), str(row["candidate_id"])): row
        for row in index_rows
    }
    if len(index) != len(index_rows):
        raise AssertionError("duplicate task card candidate index")
    unique_tasks: dict[str, dict[str, Any]] = {}
    for (blind_task_id, candidate_id), row in index.items():
        card = card_by_id[blind_task_id]
        candidate = next(
            item
            for item in card["candidate_registry"]
            if str(item["candidate_id"]) == candidate_id
        )
        task_id = str(row["task_id"])
        spec = {
            "task_id": task_id,
            "benchmark_family": str(row["benchmark_family"]),
            "prediction": str(candidate["label"]),
            "blind_task_id": blind_task_id,
            "candidate_id": candidate_id,
            "card": card,
        }
        prior = unique_tasks.get(task_id)
        if prior and (
            prior["benchmark_family"] != spec["benchmark_family"]
            or prior["prediction"] != spec["prediction"]
        ):
            raise AssertionError(f"task ID collision: {task_id}")
        unique_tasks.setdefault(task_id, spec)
    if len(unique_tasks) != 5832:
        raise AssertionError(f"expected 5,832 unique task payloads, found {len(unique_tasks)}")

    caller = OnlineJSONCaller(
        out_dir=task_dir,
        model=model,
        telemetry_path=task_dir / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )
    relation_prompt = (
        ROOT / "src/agentclinic_tree_dx/prompts/answer_relation_mapper.txt"
    ).read_text(encoding="utf-8")
    strict_prompt = (
        ROOT / "src/agentclinic_tree_dx/prompts/answer_option_strict_total_order.txt"
    ).read_text(encoding="utf-8")
    tls: dict[int, tuple[Any, Any]] = {}

    def mapper_pair() -> tuple[RelationAwareAnswerMapper, RelationAwareAnswerMapper]:
        import threading

        thread_id = threading.get_ident()
        pair = tls.get(thread_id)
        if pair is None:
            resolver = load_offline_resolver(ROOT)
            deterministic = RelationAwareAnswerMapper(resolver=resolver)
            adapter = _OnlineMapperAdapter(caller, cache_only=cache_only)
            typed = RelationAwareAnswerMapper(
                resolver=resolver,
                llm=adapter,
                relation_prompt=relation_prompt,
                strict_order_prompt=strict_prompt,
                strict_total_order=True,
            )
            pair = (deterministic, typed)
            tls[thread_id] = pair
        return pair

    def one(spec: Mapping[str, Any]) -> dict[str, Any]:
        family = str(spec["benchmark_family"])
        prediction = str(spec["prediction"])
        card = spec["card"]
        try:
            if family == "MCR":
                payload = {
                    "predicted_diagnosis": prediction,
                    "actual_diagnosis": str(card["reference_diagnosis"]),
                }
                prompt = (
                    "Is our predicted diagnosis correct (y/n)?\n"
                    "Predicted diagnosis: {predicted_diagnosis}, True diagnosis: "
                    "{actual_diagnosis}\nAnswer [y/n].\n"
                    "Return strict JSON as {\"answer\":\"y|n\",\"reason\":\"brief reason\"}."
                )
                outcome = caller.call(
                    module="EndpointMigrationTask_MCRPrompt7JSONEnvelopeV1",
                    prompt=prompt,
                    payload=payload,
                    validator=_validate_mcr_task,
                    cache_only=cache_only,
                )
                if not outcome.success:
                    raise ValueError(outcome.error)
                return {
                    "task_id": spec["task_id"],
                    "benchmark_family": family,
                    "success": True,
                    "task_correct": str(outcome.response["answer"]).lower() == "y",
                    "task_projection": "mcr_prompt7_json_envelope_v1",
                    "mapped_option": None,
                    "reason": str(outcome.response["reason"]),
                    "cache_keys": [outcome.cache_key],
                    "cache_hit": outcome.cache_hit,
                    "error": "",
                }

            options = {
                str(letter).upper(): str(text)
                for letter, text in card["source_options"].items()
            }
            leaves = [
                {
                    "leaf_id": "pred_1",
                    "leaf_label": prediction,
                    "parent_id": "",
                    "parent_label": "",
                    "joint_rank": 1,
                    "posterior": 1.0,
                }
            ]
            deterministic, typed = mapper_pair()
            projection = deterministic.map(
                case_id=str(spec["task_id"]),
                vignette=str(card["clinical_record"]),
                question="What is the most likely diagnosis?",
                options=options,
                leaves=leaves,
                mode="deterministic_gold_blind",
            )
            matched = [
                str(letter).upper()
                for letter, row in projection["option_maps"].items()
                if row.get("best_rank") is not None or bool(row.get("matched"))
            ]
            method = "da_relation_mapper_deterministic_unique_v1"
            cache_keys: list[str] = []
            if len(matched) == 1:
                mapped_option = matched[0]
            else:
                if cache_only:
                    # The nested mapper calls enforce their own immutable cache
                    # identities; missing cache records raise from the adapter.
                    pass
                typed_projection = typed.map(
                    case_id=str(spec["task_id"]),
                    vignette=str(card["clinical_record"]),
                    question="What is the most likely diagnosis?",
                    options=options,
                    leaves=leaves,
                    mode="typed_llm",
                )
                projection = typed_projection
                order = list(typed_projection.get("option_order") or [])
                mapped_option = str(order[0]).upper() if order else "NONE"
                method = "da_relation_mapper_typed_strict_total_order_v1"
                adapter = typed.llm
                if isinstance(adapter, _OnlineMapperAdapter):
                    cache_keys = [str(row["cache_key"]) for row in adapter.calls]
                    adapter.calls.clear()
            return {
                "task_id": spec["task_id"],
                "benchmark_family": family,
                "success": True,
                "task_correct": None,
                "task_projection": method,
                "mapped_option": mapped_option,
                "reason": "",
                "cache_keys": cache_keys,
                "cache_hit": bool(cache_keys),
                "projection_sha256": canonical_sha256(projection),
                "error": "",
            }
        except Exception as exc:
            return {
                "task_id": spec["task_id"],
                "benchmark_family": family,
                "success": False,
                "task_correct": None,
                "task_projection": "",
                "mapped_option": None,
                "reason": "",
                "cache_keys": [],
                "cache_hit": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(one, spec): task_id
            for task_id, spec in sorted(unique_tasks.items())
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["task_id"])
    # DA gold remains outside every online payload and is joined only now.
    gold_by_task: dict[str, set[str]] = defaultdict(set)
    for row in index_rows:
        if row["benchmark_family"] == "DA":
            gold_by_task[str(row["task_id"])].add(str(row["gold_option"]).upper())
    for result in results:
        if result["benchmark_family"] == "DA" and result["success"]:
            gold = gold_by_task[result["task_id"]]
            if len(gold) != 1:
                raise AssertionError(f"DA task has ambiguous offline gold: {result['task_id']}")
            result["task_correct"] = result["mapped_option"] == next(iter(gold))
    write_jsonl(task_dir / "task_results.jsonl", results)
    summary = {
        "schema_version": "unified-task-endpoint-v1",
        "model": model,
        "created_at_utc": utcnow(),
        "n_unique_tasks": len(results),
        "n_da": sum(row["benchmark_family"] == "DA" for row in results),
        "n_mcr": sum(row["benchmark_family"] == "MCR" for row in results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "da_gold_join_stage": "offline_after_projection",
        "historical_task_cache_seeded": False,
    }
    atomic_json(task_dir / "summary.json", summary)
    return summary


def _binary_metrics(pairs: Sequence[tuple[bool, bool]]) -> dict[str, Any]:
    tp = sum(pred and truth for pred, truth in pairs)
    fp = sum(pred and not truth for pred, truth in pairs)
    fn = sum(not pred and truth for pred, truth in pairs)
    tn = sum(not pred and not truth for pred, truth in pairs)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "specificity": tn / (tn + fp) if tn + fp else None,
        "accuracy": (tp + tn) / len(pairs) if pairs else None,
    }


def compile_panel(out: Path, reviewer_ids: Sequence[str]) -> dict[str, Any]:
    out = Path(out)
    cards = read_jsonl(out / "design/blinded_clinical_cards.jsonl")
    index_rows = read_jsonl(out / "design/relation_index.jsonl")
    sentinels = {
        str(row["blind_candidate_id"]): str(row["relation"])
        for row in read_jsonl(out / "design/sentinel_truth.jsonl")
    }
    index = {
        (str(row["blind_case_id"]), str(row["candidate_id"])): row
        for row in index_rows
    }
    if len(index) != len(index_rows):
        raise AssertionError("duplicate clinical relation index")
    reviews: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    reviewer_summaries: dict[str, Any] = {}
    for reviewer_id in reviewer_ids:
        path = out / "reviewers" / reviewer_id / "reviews.jsonl"
        rows = read_jsonl(path)
        if len(rows) != 628:
            raise AssertionError(f"{reviewer_id}: expected 628 reviews, found {len(rows)}")
        if len({str(row["blind_case_id"]) for row in rows}) != 628:
            raise AssertionError(f"{reviewer_id}: duplicate blind case review")
        reviewer_summaries[reviewer_id] = json.loads(
            (out / "reviewers" / reviewer_id / "summary.json").read_text(encoding="utf-8")
        )
        for case in rows:
            blind_case_id = str(case["blind_case_id"])
            if not case["success"]:
                continue
            for relation in case["review"]["candidate_relations"]:
                candidate_id = str(relation["candidate_id"])
                key = (blind_case_id, candidate_id)
                if key not in index:
                    raise AssertionError(f"review relation absent from index: {key}")
                reviews[reviewer_id][str(index[key]["blind_candidate_id"])] = dict(relation)

    calibration: dict[str, Any] = {}
    for reviewer_id in reviewer_ids:
        observed: list[tuple[str, str]] = []
        for blind_id, truth in sorted(sentinels.items()):
            relation = reviews[reviewer_id].get(blind_id)
            if relation is not None:
                observed.append((str(relation["relation"]), truth))
        fine_correct = sum(pred == truth for pred, truth in observed)
        complete_pairs = [
            (pred == "complete_equivalent", truth == "complete_equivalent")
            for pred, truth in observed
        ]
        compatible_pairs = [
            (pred in COMPATIBLE_RELATIONS, truth in COMPATIBLE_RELATIONS)
            for pred, truth in observed
        ]
        calibration[reviewer_id] = {
            "n_sentinels": len(sentinels),
            "n_scored": len(observed),
            "n_missing": len(sentinels) - len(observed),
            "fine_label_accuracy": fine_correct / len(observed) if observed else None,
            "fine_label_confusion": dict(
                sorted(Counter(f"truth={truth}|pred={pred}" for pred, truth in observed).items())
            ),
            "clinical_complete_boundary": _binary_metrics(complete_pairs),
            "complete_or_compatible_partial_boundary": _binary_metrics(compatible_pairs),
        }

    novel_index = [row for row in index_rows if row["candidate_kind"] == "novel"]
    if len(novel_index) != 3400 or len(index_rows) != 4907:
        raise AssertionError(
            f"expected 3,400 novel + 1,507 sentinel rows, found {len(novel_index)} + "
            f"{len(index_rows) - len(novel_index)}"
        )
    panel_rows: list[dict[str, Any]] = []
    for item in index_rows:
        blind_id = str(item["blind_candidate_id"])
        reviewer_rows = {
            reviewer_id: reviews[reviewer_id].get(blind_id)
            for reviewer_id in reviewer_ids
        }
        votes = [
            str(row["relation"])
            for row in reviewer_rows.values()
            if row is not None
        ]
        counts = Counter(votes)
        ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        provisional = ordered[0][0] if ordered and ordered[0][1] >= 2 else "uncertain"
        panel_rows.append(
            {
                **dict(item),
                "reviewer_relations": reviewer_rows,
                "vote_counts": dict(sorted(counts.items())),
                "n_valid_votes": len(votes),
                "unanimous": len(votes) == len(reviewer_ids) and len(counts) == 1,
                "provisional_relation": provisional,
                "provisional_status": (
                    "three_model_unanimous_proxy"
                    if len(votes) == len(reviewer_ids) and len(counts) == 1
                    else "model_majority_proxy"
                    if ordered and ordered[0][1] >= 2
                    else "model_unresolved_proxy"
                ),
            }
        )
    panel_rows.sort(key=lambda row: row["blind_candidate_id"])
    panel_dir = out / "panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(panel_dir / "panel_decisions.jsonl", panel_rows)

    panel_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in panel_rows:
        panel_by_case[str(row["blind_case_id"])].append(row)
    card_by_id = {str(row["blind_case_id"]): row for row in cards}
    arbitration_cards: list[dict[str, Any]] = []
    for blind_case_id in sorted(panel_by_case):
        card = card_by_id[blind_case_id]
        included_ids = {str(row["candidate_id"]) for row in panel_by_case[blind_case_id]}
        candidate_registry = [
            dict(row)
            for row in card["candidate_registry"]
            if str(row["candidate_id"]) in included_ids
        ]
        evidence = []
        for panel_row in sorted(panel_by_case[blind_case_id], key=lambda row: row["candidate_id"]):
            evidence.append(
                {
                    "candidate_id": str(panel_row["candidate_id"]),
                    "independent_reviews": [
                        {
                            "relation": value["relation"],
                            "reason": value["reason"],
                            "confidence": value["confidence"],
                        }
                        for _reviewer_id, value in sorted(
                            panel_row["reviewer_relations"].items()
                        )
                        if value is not None
                    ],
                }
            )
        arbitration_cards.append(
            {
                "blind_case_id": blind_case_id,
                "clinical_record": str(card["clinical_record"]),
                "reference_diagnosis": str(card["reference_diagnosis"]),
                "candidate_registry": candidate_registry,
                "review_evidence": evidence,
            }
        )
    write_jsonl(panel_dir / "blinded_arbitration_cards.jsonl", arbitration_cards)
    summary = {
        "schema_version": "canonical-endpoint-panel-v1",
        "created_at_utc": utcnow(),
        "reviewers": list(reviewer_ids),
        "reviewer_run_summaries": reviewer_summaries,
        "embedded_sentinel_calibration": calibration,
        "n_panel_relations": len(panel_rows),
        "n_novel_relations": len(novel_index),
        "n_sentinel_relations": len(sentinels),
        "n_unanimous_novel": sum(
            bool(row["unanimous"]) and row["candidate_kind"] == "novel"
            for row in panel_rows
        ),
        "n_majority_not_unanimous": sum(
            row["provisional_status"] == "model_majority_proxy"
            and row["candidate_kind"] == "novel"
            for row in panel_rows
        ),
        "n_unresolved": sum(
            row["provisional_status"] == "model_unresolved_proxy"
            and row["candidate_kind"] == "novel"
            for row in panel_rows
        ),
        "truth_rule": "panel decisions are provisional proxies and never root truth",
        "arbitration_cards_sha256": file_sha256(
            panel_dir / "blinded_arbitration_cards.jsonl"
        ),
    }
    atomic_json(panel_dir / "summary.json", summary)
    return summary


def run_arbitrator(
    out: Path,
    model: str,
    workers: int,
    *,
    cache_only: bool = False,
) -> dict[str, Any]:
    workers = validate_workers(workers, rag=False)
    out = Path(out)
    cards_path = out / "panel/blinded_arbitration_cards.jsonl"
    cards = read_jsonl(cards_path)
    if len(cards) != 628:
        raise AssertionError(f"expected 628 arbitration cards, found {len(cards)}")
    directory = out / "arbitrator"
    directory.mkdir(parents=True, exist_ok=True)
    caller = OnlineJSONCaller(
        out_dir=directory,
        model=model,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=300,
        max_retries=3,
    )

    def one(card: Mapping[str, Any]) -> dict[str, Any]:
        payload = {
            "blind_case_id": str(card["blind_case_id"]),
            "clinical_record": str(card["clinical_record"]),
            "reference_diagnosis": str(card["reference_diagnosis"]),
            "candidate_registry": [dict(row) for row in card["candidate_registry"]],
            "independent_review_evidence": [dict(row) for row in card["review_evidence"]],
        }
        allowed = {str(row["candidate_id"]) for row in card["candidate_registry"]}
        try:
            outcome = caller.call(
                module="EndpointMigrationBlindedModelArbitratorV1",
                prompt=ARBITRATION_PROMPT,
                payload=payload,
                validator=lambda response: _validate_relation_response(
                    response, allowed, "final_relations"
                ),
                cache_only=cache_only,
            )
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "model": model,
                "success": outcome.success,
                "error": outcome.error,
                "adjudication": outcome.response,
                "cache_hit": outcome.cache_hit,
                "cache_key": outcome.cache_key,
                "prompt_sha256": outcome.prompt_sha256,
                "payload_sha256": outcome.payload_sha256,
            }
        except Exception as exc:
            return {
                "blind_case_id": str(card["blind_case_id"]),
                "model": model,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "adjudication": {},
                "cache_hit": False,
                "cache_key": "",
                "prompt_sha256": hashlib.sha256(
                    ARBITRATION_PROMPT.encode("utf-8")
                ).hexdigest(),
                "payload_sha256": canonical_sha256(payload),
            }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, card): str(card["blind_case_id"]) for card in cards}
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda row: row["blind_case_id"])
    write_jsonl(directory / "adjudications.jsonl", results)
    relation_index = {
        (str(row["blind_case_id"]), str(row["candidate_id"])): str(
            row["blind_candidate_id"]
        )
        for row in read_jsonl(out / "design/relation_index.jsonl")
    }
    sentinel_truth = {
        str(row["blind_candidate_id"]): str(row["relation"])
        for row in read_jsonl(out / "design/sentinel_truth.jsonl")
    }
    sentinel_observed: list[tuple[str, str]] = []
    for case in results:
        if not case["success"]:
            continue
        for relation in case["adjudication"]["final_relations"]:
            blind_id = relation_index[
                (str(case["blind_case_id"]), str(relation["candidate_id"]))
            ]
            if blind_id in sentinel_truth:
                sentinel_observed.append(
                    (str(relation["relation"]), sentinel_truth[blind_id])
                )
    complete_pairs = [
        (pred == "complete_equivalent", truth == "complete_equivalent")
        for pred, truth in sentinel_observed
    ]
    compatible_pairs = [
        (pred in COMPATIBLE_RELATIONS, truth in COMPATIBLE_RELATIONS)
        for pred, truth in sentinel_observed
    ]
    calibration = {
        "n_sentinels": len(sentinel_truth),
        "n_scored": len(sentinel_observed),
        "n_missing": len(sentinel_truth) - len(sentinel_observed),
        "fine_label_accuracy": (
            sum(pred == truth for pred, truth in sentinel_observed)
            / len(sentinel_observed)
            if sentinel_observed
            else None
        ),
        "fine_label_confusion": dict(
            sorted(
                Counter(
                    f"truth={truth}|pred={pred}"
                    for pred, truth in sentinel_observed
                ).items()
            )
        ),
        "clinical_complete_boundary": _binary_metrics(complete_pairs),
        "complete_or_compatible_partial_boundary": _binary_metrics(
            compatible_pairs
        ),
    }
    summary = {
        "schema_version": "canonical-endpoint-model-arbitrator-v1",
        "model": model,
        "created_at_utc": utcnow(),
        "n_cards": len(results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "n_candidate_relations": sum(
            len(row.get("adjudication", {}).get("final_relations", []))
            for row in results
            if row["success"]
        ),
        "embedded_sentinel_calibration": calibration,
        "provenance_warning": (
            "model arbitration is not root adjudication and cannot by itself "
            "satisfy the full-root-census allowlist"
        ),
    }
    atomic_json(directory / "summary.json", summary)
    return summary


def _contrast_registry() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []

    def add(experiment: str, left: str, right: str, label: str, family: str = "primary") -> None:
        records.append(
            {
                "experiment_id": experiment,
                "left_arm": left,
                "right_arm": right,
                "label": label,
                "multiplicity_family": family,
            }
        )

    for architecture in ("aphhm_hierarchical", "ab02_flat"):
        add(
            "E1",
            f"{architecture}__clean_fixed",
            f"{architecture}__options_fixed",
            f"options_vs_clean_fixed__{architecture}",
        )
        add(
            "E1",
            f"{architecture}__clean_shuffled_blocks",
            f"{architecture}__options_shuffled_blocks",
            f"options_vs_clean_shuffled__{architecture}",
        )
        add(
            "E1",
            f"{architecture}__clean_fixed",
            f"{architecture}__clean_shuffled_blocks",
            f"shuffle_vs_fixed_clean__{architecture}",
        )
        add(
            "E1",
            f"{architecture}__options_fixed",
            f"{architecture}__options_shuffled_blocks",
            f"shuffle_vs_fixed_options__{architecture}",
        )

    e4_arms = (
        "evidence_count_control",
        "e7_contrast",
        "forest_evidence_integrator",
        "collapse_obligation_ledger",
        "pairwise_tournament",
    )
    for left_index, left in enumerate(e4_arms):
        for right in e4_arms[left_index + 1 :]:
            add("E4", left, right, f"{right}_vs_{left}")

    for right in (
        "remove_non_gold3",
        "add_parent5",
        "add_sibling5",
        "add_unrelated5",
        "add_synonym5",
        "add_component5",
        "nested_width6",
        "nested_width8",
    ):
        add("E5", "base4", right, f"{right}_vs_base4")
    add("E5", "nested_width6", "nested_width8", "width8_vs_width6", "width_secondary")

    for left, right, label in (
        ("raw_vignette", "flat_facts", "flat_vs_raw"),
        ("raw_vignette", "typed_event_graph", "graph_vs_raw"),
        ("flat_facts", "typed_event_graph", "graph_vs_flat"),
    ):
        add("E6", left, right, label)
    add("E6x", "flat_facts_padded", "flat_facts_unpadded", "unpadded_vs_padded")
    add("E7b", "legacy_substring", "exact_synonym", "exact_vs_legacy")
    add("E7b", "exact_synonym", "typed_relation", "typed_vs_exact")
    add("E7c", "exact_control", "directional_relation", "directional_vs_exact")
    add("E7c", "directional_relation", "bounded_inheritance", "bounded_vs_directional")
    add(
        "E7c",
        "exact_control",
        "generic_non_equivalence",
        "generic_vs_exact",
        "exploratory",
    )
    for left, right, label in (
        ("atemporal_hard_veto", "time_scope_soft_veto", "soft_vs_hard"),
        ("time_scope_soft_veto", "time_scope_soft_legal_order", "legal_vs_soft"),
        ("time_scope_soft_veto", "time_scope_soft_invalid_time", "invalid_vs_soft"),
    ):
        add("E8", left, right, label)
    for left, right, label in (
        ("real_views", "role_rotated", "role_rotated_vs_real"),
        ("single_anchor", "duplicate_anchor", "duplicate_vs_single"),
        ("single_anchor", "real_views", "real_vs_single"),
        ("duplicate_anchor", "real_views", "real_vs_duplicate"),
    ):
        add("E9", left, right, label)
    for left, right, label in (
        ("isolated_rrf", "sequential_rrf", "history_effect_rrf"),
        ("isolated_supervisor", "sequential_supervisor", "history_effect_supervisor"),
        ("isolated_rrf", "isolated_supervisor", "supervisor_effect_isolated"),
        ("sequential_rrf", "sequential_supervisor", "supervisor_effect_sequential"),
    ):
        add("E10", left, right, label)
    for left, right, label in (
        ("off_refine_off", "relevant_refine_off", "relevant_vs_off_without_refine"),
        ("random_refine_off", "relevant_refine_off", "relevant_vs_random_without_refine"),
        (
            "hard_negative_refine_off",
            "relevant_refine_off",
            "relevant_vs_hard_negative_without_refine",
        ),
        ("off_refine_off", "off_refine_on", "refine_effect_with_retrieval_off"),
        (
            "relevant_refine_off",
            "relevant_refine_on",
            "refine_effect_with_relevant_retrieval",
        ),
        ("random_refine_off", "random_refine_on", "refine_effect_with_random_context"),
        (
            "hard_negative_refine_off",
            "hard_negative_refine_on",
            "refine_effect_with_hard_negative_context",
        ),
    ):
        add("E11", left, right, label)

    representations = ("raw", "s1", "graph")
    widths = (5, 10)
    comparators = ("first", "pointwise", "pairwise")
    for width in widths:
        for comparator in comparators:
            add(
                "E12",
                f"s1_k{width}_{comparator}",
                f"raw_k{width}_{comparator}",
                f"raw_vs_s1_k{width}_{comparator}",
                "factorial39",
            )
            add(
                "E12",
                f"s1_k{width}_{comparator}",
                f"graph_k{width}_{comparator}",
                f"graph_vs_s1_k{width}_{comparator}",
                "factorial39",
            )
    for representation in representations:
        for comparator in comparators:
            add(
                "E12",
                f"{representation}_k5_{comparator}",
                f"{representation}_k10_{comparator}",
                f"k10_vs_k5_{representation}_{comparator}",
                "factorial39",
            )
    for representation in representations:
        for width in widths:
            for comparator in ("pointwise", "pairwise"):
                add(
                    "E12",
                    f"{representation}_k{width}_first",
                    f"{representation}_k{width}_{comparator}",
                    f"{comparator}_vs_first_{representation}_k{width}",
                    "factorial39",
                )
            add(
                "E12",
                f"{representation}_k{width}_pointwise",
                f"{representation}_k{width}_pairwise",
                f"pairwise_vs_pointwise_{representation}_k{width}",
                "factorial39",
            )
    add(
        "E12",
        "raw_depth1_k10_pairwise",
        "raw_depth2_k10_pairwise",
        "depth2_vs_depth1",
        "incremental2",
    )
    add(
        "E12",
        "raw_depth2_k10_pairwise",
        "raw_k10_pairwise",
        "depth3_vs_depth2",
        "incremental2",
    )
    add(
        "E14x",
        "mosaic_lite_v1",
        "mosaic_adaptive4v2_v1",
        "adaptive_vs_lite",
    )
    for left, right, label in (
        ("lite3_safe", "rcr3_default", "rcr3_vs_lite3_same_3call_budget"),
        ("lite3_safe", "compact4_true3gen", "third_generator_marginal_utility"),
        ("rcr3_default", "compact4_true3gen", "compact4_vs_rcr3"),
    ):
        add("RCR3", left, right, label)
    if sum(row["experiment_id"] == "E12" and row["multiplicity_family"] == "factorial39" for row in records) != 39:
        raise AssertionError("E12 contrast registry must preserve the 39-comparison family")
    return records


def _exact_mcnemar(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if not discordant:
        return 1.0
    lower = min(left_only, right_only)
    tail = sum(math.comb(discordant, index) for index in range(lower + 1))
    return min(1.0, 2.0 * tail / (2**discordant))


def _paired_bootstrap_ci(
    left_only: int,
    right_only: int,
    neither_or_both: int,
    seed_key: str,
    repetitions: int,
) -> list[float]:
    import numpy as np

    n = left_only + right_only + neither_or_both
    if n <= 0:
        return [0.0, 0.0]
    rng = np.random.default_rng(stable_seed("endpoint-migration-bootstrap-v1", seed_key))
    draws = rng.multinomial(
        n,
        [left_only / n, right_only / n, neither_or_both / n],
        size=repetitions,
    )
    deltas = (draws[:, 1] - draws[:, 0]) / n
    bounds = np.quantile(deltas, [0.025, 0.975])
    return [round(float(bounds[0]), 6), round(float(bounds[1]), 6)]


def _holm(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows]
    order = sorted(
        range(len(output)),
        key=lambda index: (float(output[index]["exact_mcnemar_p"]), str(output[index]["label"])),
    )
    prior = 0.0
    for rank, index in enumerate(order):
        value = min(1.0, (len(output) - rank) * float(output[index]["exact_mcnemar_p"]))
        value = max(prior, value)
        output[index]["holm_adjusted_p"] = value
        prior = value
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )


def _load_novel_final_relations(
    out: Path, *, allow_model_only: bool
) -> tuple[dict[str, dict[str, Any]], str]:
    root_path = out / "root/final_decisions.jsonl"
    if root_path.is_file():
        rows = read_jsonl(root_path)
        source_mode = "full_root_census"
        allowed_sources = {"root_blinded_primary", "root_blinded_arbitrated"}
        if any(str(row.get("adjudication_source")) not in allowed_sources for row in rows):
            raise AssertionError("root decision ledger contains a non-root final source")
    else:
        if not allow_model_only:
            raise FileNotFoundError(
                "root/final_decisions.jsonl is required; pass --allow-model-only "
                "only for an explicitly non-root sensitivity replay"
            )
        index = {
            (str(row["blind_case_id"]), str(row["candidate_id"])): row
            for row in read_jsonl(out / "design/relation_index.jsonl")
            if row["candidate_kind"] == "novel"
        }
        rows = []
        adjudication_path = out / "arbitrator/adjudications.jsonl"
        if adjudication_path.is_file():
            adjudications = read_jsonl(adjudication_path)
            if len(adjudications) != 628 or any(
                not bool(row["success"]) for row in adjudications
            ):
                raise AssertionError("model arbitration is incomplete")
            for case in adjudications:
                for relation in case["adjudication"]["final_relations"]:
                    key = (str(case["blind_case_id"]), str(relation["candidate_id"]))
                    item = index.get(key)
                    if item is None:  # embedded calibration sentinel
                        continue
                    rows.append(
                        {
                            "relation_id": str(item["relation_id"]),
                            "relation": str(relation["relation"]),
                            "reason": str(relation["reason"]),
                            "confidence": str(relation["confidence"]),
                            "adjudication_source": "model_arbiter",
                        }
                    )
            source_mode = "full_blinded_model_panel_sensitivity_not_root"
        else:
            # A complete three-reviewer panel is itself an exhaustive model-panel
            # census.  A 2/3 majority is retained as a proxy decision and a
            # three-way split remains the canonical ``uncertain`` code.  This is
            # deliberately weaker provenance than either a fourth-model
            # arbitration or human-root adjudication.
            panel_rows = read_jsonl(out / "panel/panel_decisions.jsonl")
            novel_panel = [
                row for row in panel_rows if str(row.get("candidate_kind")) == "novel"
            ]
            if len(novel_panel) != 3400:
                raise AssertionError("three-reviewer novel panel is incomplete")
            for panel_row in novel_panel:
                key = (
                    str(panel_row["blind_case_id"]),
                    str(panel_row["candidate_id"]),
                )
                item = index.get(key)
                if item is None:
                    raise AssertionError(f"panel relation missing private index: {key}")
                rows.append(
                    {
                        "relation_id": str(item["relation_id"]),
                        "relation": str(panel_row["provisional_relation"]),
                        "reason": json.dumps(
                            panel_row["vote_counts"],
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "confidence": (
                            "unanimous"
                            if bool(panel_row["unanimous"])
                            else (
                                "majority"
                                if panel_row["provisional_status"]
                                == "model_majority_proxy"
                                else "unresolved"
                            )
                        ),
                        "adjudication_source": str(
                            panel_row["provisional_status"]
                        ),
                    }
                )
            source_mode = "full_blinded_three_model_panel_census_not_root"
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        relation_id = str(row["relation_id"])
        relation = str(row["relation"])
        if relation not in RELATIONS:
            raise AssertionError(f"invalid final relation: {relation}")
        if relation_id in result:
            raise AssertionError(f"duplicate final relation ID: {relation_id}")
        result[relation_id] = dict(row)
    if len(result) != 3400:
        raise AssertionError(f"expected 3,400 novel final relations, found {len(result)}")
    return result, source_mode


def finalize(
    out: Path,
    *,
    allow_model_only: bool = False,
    bootstrap_repetitions: int = 10_000,
) -> dict[str, Any]:
    out = Path(out)
    final_dir = out / "final"
    final_dir.mkdir(parents=True, exist_ok=True)
    rows = read_jsonl(out / "design/intention_ledger.jsonl")
    if len(rows) != 24076:
        raise AssertionError("frozen intention ledger is incomplete")
    novel, source_mode = _load_novel_final_relations(
        out, allow_model_only=allow_model_only
    )
    task_rows = read_jsonl(out / "task_evaluator/task_results.jsonl")
    task = {str(row["task_id"]): row for row in task_rows}
    if len(task) != 5832:
        raise AssertionError("canonical task replay registry must contain 5,832 payloads")
    task_success_n = sum(bool(row["success"]) for row in task.values())
    task_failure_n = len(task) - task_success_n
    task_complete = task_failure_n == 0

    final_rows: list[dict[str, Any]] = []
    for frozen in rows:
        row = dict(frozen)
        if row["served"]:
            if row["clinical_relation"] is None:
                decision = novel.get(str(row["relation_id"]))
                if decision is None:
                    raise AssertionError(f"missing novel decision for {row['row_id']}")
                row["clinical_relation"] = decision["relation"]
                row["clinical_audit_source"] = decision["adjudication_source"]
                row["clinical_decision_reason"] = decision.get("reason", "")
                row["clinical_decision_confidence"] = decision.get("confidence")
            relation = str(row["clinical_relation"])
            row["clinical_complete"] = relation == "complete_equivalent"
            row["compatible_partial"] = relation == "partial_parent_or_component"
            row["complete_or_compatible_partial"] = relation in COMPATIBLE_RELATIONS
            task_result = task[str(row["task_id"])]
            if bool(task_result["success"]):
                row["task"] = bool(task_result["task_correct"])
                row["task_contract"] = str(task_result["task_projection"])
                row["task_status"] = "evaluated_fresh_namespace"
                row["task_endpoint_evaluable"] = True
            else:
                row["task"] = None
                row["task_contract"] = "not_evaluable_external_api_credit_exhausted"
                row["task_status"] = "not_evaluable_external_api_credit_exhausted"
                row["task_endpoint_evaluable"] = False
            row["endpoint_evaluable"] = True
            row["clinical_endpoint_evaluable"] = True
        else:
            row["clinical_complete"] = False
            row["compatible_partial"] = False
            row["complete_or_compatible_partial"] = False
            row["task"] = False
            row["task_contract"] = "ita_failure_missing_prediction"
            row["task_status"] = "ita_failure_missing_prediction"
            row["task_endpoint_evaluable"] = True
            row["endpoint_evaluable"] = False
            row["clinical_endpoint_evaluable"] = False
        final_rows.append(row)
    write_jsonl(final_dir / "five_endpoint_replay.jsonl", final_rows)

    endpoints = (
        "safe_exact",
        "legacy_chain",
        "clinical_complete",
        "compatible_partial",
        "complete_or_compatible_partial",
        "task",
    )
    arm_stats: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in final_rows:
        grouped[(str(row["experiment_id"]), str(row["arm_id"]))].append(row)
    for (experiment, arm), arm_rows in sorted(grouped.items()):
        for scope in ("ALL", "DA", "MCR"):
            scoped = [
                row
                for row in arm_rows
                if scope == "ALL" or row["benchmark_family"] == scope
            ]
            served = [row for row in scoped if row["served"]]
            record: dict[str, Any] = {
                "experiment_id": experiment,
                "arm_id": arm,
                "scope": scope,
                "intention_n": len(scoped),
                "served_n": len(served),
                "unserved_n": len(scoped) - len(served),
                "served_rate": len(served) / len(scoped) if scoped else None,
                "clinical_relation_counts_served": dict(
                    sorted(Counter(row["clinical_relation"] for row in served).items())
                ),
            }
            for endpoint in endpoints:
                if endpoint == "task":
                    evaluable = [row for row in scoped if row["task_endpoint_evaluable"]]
                    served_evaluable = [
                        row for row in served if row["task_endpoint_evaluable"]
                    ]
                    hits_ita = sum(bool(row[endpoint]) for row in evaluable)
                    hits_served = sum(bool(row[endpoint]) for row in served_evaluable)
                    record["task_evaluable_n_ita"] = len(evaluable)
                    record["task_evaluable_n_served"] = len(served_evaluable)
                    record["task_coverage_ita"] = (
                        len(evaluable) / len(scoped) if scoped else None
                    )
                    record["task_coverage_served"] = (
                        len(served_evaluable) / len(served) if served else None
                    )
                    record["task_n_ita"] = hits_ita
                    record["task_rate_ita"] = (
                        hits_ita / len(scoped)
                        if scoped and len(evaluable) == len(scoped)
                        else None
                    )
                    record["task_rate_observed"] = (
                        hits_ita / len(evaluable) if evaluable else None
                    )
                    record["task_n_served"] = hits_served
                    record["task_rate_served"] = (
                        hits_served / len(served)
                        if served and len(served_evaluable) == len(served)
                        else None
                    )
                    record["task_rate_served_observed"] = (
                        hits_served / len(served_evaluable)
                        if served_evaluable
                        else None
                    )
                    continue
                hits_ita = sum(bool(row[endpoint]) for row in scoped)
                hits_served = sum(bool(row[endpoint]) for row in served)
                record[f"{endpoint}_n_ita"] = hits_ita
                record[f"{endpoint}_rate_ita"] = hits_ita / len(scoped) if scoped else None
                record[f"{endpoint}_n_served"] = hits_served
                record[f"{endpoint}_rate_served"] = (
                    hits_served / len(served) if served else None
                )
            arm_stats.append(record)
    atomic_json(final_dir / "arm_statistics.json", {"records": arm_stats})
    _write_csv(final_dir / "arm_statistics.csv", arm_stats)

    by_arm_case = {
        (str(row["experiment_id"]), str(row["arm_id"]), str(row["case_key"])): row
        for row in final_rows
    }
    contrast_rows: list[dict[str, Any]] = []
    for contrast in _contrast_registry():
        experiment = contrast["experiment_id"]
        left = contrast["left_arm"]
        right = contrast["right_arm"]
        left_rows = {
            key[2]: row
            for key, row in by_arm_case.items()
            if key[0] == experiment and key[1] == left
        }
        right_rows = {
            key[2]: row
            for key, row in by_arm_case.items()
            if key[0] == experiment and key[1] == right
        }
        if set(left_rows) != set(right_rows):
            raise AssertionError(f"paired case-set mismatch for {experiment}/{left}/{right}")
        for scope in ("ALL", "DA", "MCR"):
            case_keys = [
                key
                for key in sorted(left_rows)
                if scope == "ALL" or left_rows[key]["benchmark_family"] == scope
            ]
            for endpoint in endpoints:
                if endpoint == "task" and scope == "ALL":
                    continue
                if endpoint == "task" and any(
                    not bool(left_rows[key]["task_endpoint_evaluable"])
                    or not bool(right_rows[key]["task_endpoint_evaluable"])
                    for key in case_keys
                ):
                    # Cache completion is non-random after the external API stopped.
                    # A complete-case task contrast would therefore be misleading.
                    continue
                counts: Counter[tuple[bool, bool]] = Counter(
                    (bool(left_rows[key][endpoint]), bool(right_rows[key][endpoint]))
                    for key in case_keys
                )
                left_only = counts[(True, False)]
                right_only = counts[(False, True)]
                n = len(case_keys)
                record = {
                    **contrast,
                    "scope": scope,
                    "endpoint": endpoint,
                    "n": n,
                    "both": counts[(True, True)],
                    "left_only": left_only,
                    "right_only": right_only,
                    "neither": counts[(False, False)],
                    "left_rate_ita": sum(bool(left_rows[key][endpoint]) for key in case_keys) / n,
                    "right_rate_ita": sum(bool(right_rows[key][endpoint]) for key in case_keys) / n,
                    "delta_right_minus_left": (right_only - left_only) / n,
                    "exact_mcnemar_p": _exact_mcnemar(left_only, right_only),
                    "paired_bootstrap_delta_ci95": _paired_bootstrap_ci(
                        left_only,
                        right_only,
                        n - left_only - right_only,
                        f"{experiment}/{contrast['label']}/{scope}/{endpoint}",
                        bootstrap_repetitions,
                    ),
                    "gain_case_keys": [
                        key
                        for key in case_keys
                        if not bool(left_rows[key][endpoint]) and bool(right_rows[key][endpoint])
                    ],
                    "loss_case_keys": [
                        key
                        for key in case_keys
                        if bool(left_rows[key][endpoint]) and not bool(right_rows[key][endpoint])
                    ],
                }
                contrast_rows.append(record)
    adjusted: list[dict[str, Any]] = []
    families: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in contrast_rows:
        families[
            (
                str(row["experiment_id"]),
                str(row["multiplicity_family"]),
                str(row["scope"]),
                str(row["endpoint"]),
            )
        ].append(row)
    for rows_in_family in families.values():
        adjusted.extend(_holm(rows_in_family))
    adjusted.sort(
        key=lambda row: (
            row["experiment_id"],
            row["multiplicity_family"],
            row["scope"],
            row["endpoint"],
            row["label"],
        )
    )
    atomic_json(final_dir / "paired_contrasts.json", {"records": adjusted})
    _write_csv(final_dir / "paired_contrasts.csv", adjusted)

    summary = {
        "schema_version": "canonical-endpoint-migration-final-v1",
        "created_at_utc": utcnow(),
        "source_commit": SOURCE_COMMIT,
        "endpoint_contract": [
            "safe_exact",
            "legacy_chain",
            "clinical_complete",
            "compatible_partial",
            "complete_or_compatible_partial",
            "task",
        ],
        "clinical_census_status": source_mode,
        "full_root_census": source_mode == "full_root_census",
        "n_arms": len(grouped),
        "n_intention_rows": len(final_rows),
        "n_served_rows": sum(bool(row["served"]) for row in final_rows),
        "n_clinical_relations": len(
            {str(row["relation_id"]) for row in final_rows if row["served"]}
        ),
        "n_task_payloads": len(task),
        "n_task_payloads_successful": task_success_n,
        "n_task_payloads_not_evaluable": task_failure_n,
        "task_census_status": (
            "complete_fresh_replay"
            if task_complete
            else "partial_fresh_replay_external_api_credit_exhausted"
        ),
        "n_confirmatory_contrasts": len(_contrast_registry()),
        "multiplicity": (
            "Holm within experiment x preregistered contrast family x scope x endpoint"
        ),
        "task_interpretation": (
            "DA mapper and MCR semantic judge are reported by family; pooled ALL task "
            "is prohibited as a homogeneous estimand. If task replay is partial, "
            "observed cache-complete rows are provenance only and no task contrast is inferred."
        ),
        "failure_policy": "unserved arm-case rows retained as endpoint failures in ITA",
        "artifact_hashes": {
            path.name: file_sha256(path)
            for path in sorted(final_dir.iterdir())
            if path.is_file() and path.name != "summary.json"
        },
    }
    atomic_json(final_dir / "summary.json", summary)
    return summary


def _pct(value: Any) -> str:
    return "—" if value is None else f"{100 * float(value):.2f}%"


def _task_cell(record: Mapping[str, Any]) -> str:
    evaluable = int(record.get("task_evaluable_n_ita") or 0)
    intention = int(record.get("intention_n") or 0)
    rate = record.get("task_rate_observed")
    return f"{_pct(rate)} ({evaluable}/{intention})"


def render_report(out: Path) -> str:
    out = Path(out)
    freeze_summary = json.loads(
        (out / "design/freeze_summary.json").read_text(encoding="utf-8")
    )
    panel_summary = json.loads(
        (out / "panel/summary.json").read_text(encoding="utf-8")
    )
    task_summary = json.loads(
        (out / "task_evaluator/summary.json").read_text(encoding="utf-8")
    )
    final_summary = json.loads(
        (out / "final/summary.json").read_text(encoding="utf-8")
    )
    arm_records = json.loads(
        (out / "final/arm_statistics.json").read_text(encoding="utf-8")
    )["records"]
    contrasts = json.loads(
        (out / "final/paired_contrasts.json").read_text(encoding="utf-8")
    )["records"]
    arm_index = {
        (row["experiment_id"], row["arm_id"], row["scope"]): row
        for row in arm_records
    }
    lines = [
        "# Canonical endpoint migration: 79-arm exhaustive Top-1 replay",
        "",
        "## Decision",
        "",
        "The 79-arm metric-migration gap is closed at the exhaustive blinded "
        "three-reviewer model-panel level: every intended row has an ITA "
        "disposition and every served Top-1 has canonical clinical-complete, "
        "compatible-partial, and C∪P status. The strict "
        "human-root capability allowlist is **not** expanded: E2 remains the only "
        "human-root-owned full census, while the 79 migrated arms are a calibrated "
        "model-panel sensitivity census.",
        "",
        "The fresh task replay stopped when the authorized external API returned "
        "an insufficient-credit error. Cache-complete task rows are reported only "
        "with their evaluation coverage; historical task values were not copied, "
        "failed rows were not imputed, and no partial-cache task contrast is inferred.",
        "",
        "Historical proxy, targeted, binary-acceptable, safe-exact, and old task "
        "fields remain in their source reports as mechanism/provenance evidence; "
        "they are not renamed as canonical clinical outcomes.",
        "",
        "## Coverage and provenance",
        "",
        "| Quantity | Value |",
        "|---|---:|",
        f"| Registered target arms | {freeze_summary['n_arms']} |",
        f"| Intention rows | {freeze_summary['n_intention_rows']:,} |",
        f"| Served Top-1 rows | {freeze_summary['n_served_rows']:,} |",
        f"| Technical failures retained in ITA | {freeze_summary['n_unserved_rows']:,} |",
        f"| Unique case-prediction relations | {freeze_summary['n_unique_case_prediction_relations']:,} |",
        f"| Exact-normalized E2 root relations reused | {freeze_summary['n_e2_reused_relations']:,} |",
        f"| Newly blinded relations | {freeze_summary['n_pending_relations']:,} |",
        f"| Hidden E2 sentinels | {freeze_summary['n_embedded_sentinels']:,} |",
        f"| Registered fresh task payloads | {task_summary['n_unique_tasks']:,} |",
        f"| Fresh task payloads completed | {task_summary['n_success']:,} |",
        f"| Fresh task payloads not evaluable | {task_summary['n_failure']:,} |",
        "",
        "No credential is present in a prompt, cache identity, response artifact, "
        "manifest, or report. Clinical cards hide case key, experiment, arm, old "
        "endpoint, proxy status, safe/legacy/task status, and sentinel identity.",
        "`artifact_manifest.json` closes every migration artifact with byte count "
        "and SHA-256.",
        "",
        "## Embedded calibration",
        "",
        "| Reviewer | Model | Fine-label accuracy | Complete accuracy | Complete precision | Complete recall | C∪P accuracy | C∪P precision | C∪P recall |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for reviewer_id in panel_summary["reviewers"]:
        run = panel_summary["reviewer_run_summaries"][reviewer_id]
        calibration = panel_summary["embedded_sentinel_calibration"][reviewer_id]
        complete = calibration["clinical_complete_boundary"]
        compatible = calibration["complete_or_compatible_partial_boundary"]
        lines.append(
            "| {reviewer} | `{model}` | {fine} | {ca} | {cp} | {cr} | {ua} | {up} | {ur} |".format(
                reviewer=reviewer_id,
                model=run["model"],
                fine=_pct(calibration["fine_label_accuracy"]),
                ca=_pct(complete["accuracy"]),
                cp=_pct(complete["precision"]),
                cr=_pct(complete["recall"]),
                ua=_pct(compatible["accuracy"]),
                up=_pct(compatible["precision"]),
                ur=_pct(compatible["recall"]),
            )
        )
    lines.extend(
        [
            "",
            "The sentinels calibrate measurement error; they do not convert model "
            "decisions into human root decisions. Fine-label error is materially "
            "larger than the binary complete boundary error, so C/P/X/M/N counts "
            "must retain their model-panel provenance.",
            "",
            "## All-arm canonical endpoint table",
            "",
            "Clinical rates are ITA. Task is shown separately for DA and MCR as "
            "`observed rate (evaluable/ITA)`; incomplete task cells are descriptive "
            "only because cache completion is non-random.",
            "",
            "| Experiment | Arm | Served/ITA | Safe exact | Legacy chain | Clinical complete | Compatible partial | C∪P | DA task | MCR task |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for experiment, arm in sorted(
        {(row["experiment_id"], row["arm_id"]) for row in arm_records}
    ):
        overall = arm_index[(experiment, arm, "ALL")]
        da = arm_index[(experiment, arm, "DA")]
        mcr = arm_index[(experiment, arm, "MCR")]
        lines.append(
            "| {experiment} | `{arm}` | {served}/{ita} | {safe} | {legacy} | {complete} | {partial} | {union} | {da_task} | {mcr_task} |".format(
                experiment=experiment,
                arm=arm,
                served=overall["served_n"],
                ita=overall["intention_n"],
                safe=_pct(overall["safe_exact_rate_ita"]),
                legacy=_pct(overall["legacy_chain_rate_ita"]),
                complete=_pct(overall["clinical_complete_rate_ita"]),
                partial=_pct(overall["compatible_partial_rate_ita"]),
                union=_pct(overall["complete_or_compatible_partial_rate_ita"]),
                da_task=_task_cell(da),
                mcr_task=_task_cell(mcr),
            )
        )
    survivors = [
        row
        for row in contrasts
        if row["scope"] == "ALL"
        and row["endpoint"] in {
            "clinical_complete",
            "complete_or_compatible_partial",
        }
        and float(row["holm_adjusted_p"]) < 0.05
    ]
    lines.extend(
        [
            "",
            "## Multiplicity-controlled clinical contrasts",
            "",
            "Only ALL-scope canonical clinical contrasts with Holm-adjusted `q<.05` "
            "are listed here. Family-specific estimates and all null contrasts are "
            "preserved in `final/paired_contrasts.csv`.",
            "",
            "| Experiment | Family | Contrast | Endpoint | Δ pp | Gain/loss | McNemar p | Holm q |",
            "|---|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for row in survivors:
        lines.append(
            "| {experiment_id} | `{multiplicity_family}` | `{label}` | `{endpoint}` | {delta:.2f} | {gain}/{loss} | {p:.6g} | {q:.6g} |".format(
                delta=100 * float(row["delta_right_minus_left"]),
                gain=row["right_only"],
                loss=row["left_only"],
                p=float(row["exact_mcnemar_p"]),
                q=float(row["holm_adjusted_p"]),
                **row,
            )
        )
    if not survivors:
        lines.append("| — | — | No adjusted survivor | — | — | — | — | — |")
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This replay can update arm-level Top-1 clinical conclusions. It cannot "
            "update task conclusions until the fresh evaluator namespace is complete. "
            "It cannot by itself update candidate-registry exposure, selector capture, "
            "or trajectory-level mechanisms where non-winning candidates still use old "
            "proxy labels. Those mechanisms remain hypotheses until a separate full-pool "
            "relation migration is completed.",
            "",
            "Reproduction:",
            "",
            "```bash",
            "python -m analysis.mechanism_v2.endpoint_migration freeze",
            "python -m analysis.mechanism_v2.endpoint_migration run-reviewer --reviewer-id reviewer_a --model google/gemini-2.5-flash",
            "python -m analysis.mechanism_v2.endpoint_migration compile-panel",
            "python -m analysis.mechanism_v2.endpoint_migration run-task",
            "python -m analysis.mechanism_v2.endpoint_migration finalize --allow-model-only",
            "python -m analysis.mechanism_v2.endpoint_migration render-report",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(out: Path) -> dict[str, Any]:
    out = Path(out)
    path = out / "REPORT.md"
    path.write_text(render_report(out), encoding="utf-8")
    manifest_path = out / "artifact_manifest.json"
    files = [
        item
        for item in sorted(out.rglob("*"))
        if item.is_file() and item != manifest_path
    ]
    manifest = {
        "schema_version": "canonical-endpoint-migration-manifest-v1",
        "source_commit": SOURCE_COMMIT,
        "file_count": len(files),
        "total_bytes": sum(item.stat().st_size for item in files),
        "files": [
            {
                "path": str(item.relative_to(out)),
                "bytes": item.stat().st_size,
                "sha256": file_sha256(item),
            }
            for item in files
        ],
    }
    atomic_json(manifest_path, manifest)
    return {
        "path": str(path),
        "sha256": file_sha256(path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "manifest_file_count": len(files),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("freeze")

    reviewer = subparsers.add_parser("run-reviewer")
    reviewer.add_argument("--reviewer-id", required=True)
    reviewer.add_argument("--model", required=True)
    reviewer.add_argument("--workers", type=int, default=32)
    reviewer.add_argument("--cache-only", action="store_true")

    task = subparsers.add_parser("run-task")
    task.add_argument("--model", default=TASK_MODEL)
    task.add_argument("--workers", type=int, default=32)
    task.add_argument("--cache-only", action="store_true")

    panel = subparsers.add_parser("compile-panel")
    panel.add_argument(
        "--reviewer-ids",
        nargs="+",
        default=sorted(CLINICAL_REVIEWERS),
    )

    arbitrator = subparsers.add_parser("run-arbitrator")
    arbitrator.add_argument("--model", default=ARBITRATOR_MODEL)
    arbitrator.add_argument("--workers", type=int, default=32)
    arbitrator.add_argument("--cache-only", action="store_true")

    final = subparsers.add_parser("finalize")
    final.add_argument("--allow-model-only", action="store_true")
    final.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    subparsers.add_parser("render-report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze":
        result = freeze(args.out)
    elif args.command == "run-reviewer":
        result = run_reviewer(
            args.out,
            args.reviewer_id,
            args.model,
            args.workers,
            cache_only=args.cache_only,
        )
    elif args.command == "run-task":
        result = run_task(
            args.out,
            args.model,
            args.workers,
            cache_only=args.cache_only,
        )
    elif args.command == "compile-panel":
        result = compile_panel(args.out, args.reviewer_ids)
    elif args.command == "run-arbitrator":
        result = run_arbitrator(
            args.out,
            args.model,
            args.workers,
            cache_only=args.cache_only,
        )
    elif args.command == "finalize":
        result = finalize(
            args.out,
            allow_model_only=args.allow_model_only,
            bootstrap_repetitions=args.bootstrap_repetitions,
        )
    elif args.command == "render-report":
        result = write_report(args.out)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
