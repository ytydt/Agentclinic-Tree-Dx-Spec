"""Claim-centric schema primitives for a diagnostic-guideline knowledge graph.

This module deliberately keeps the *assertion ledger* independent from any
particular graph database.  Flat ``disease -> finding`` triples lose negation,
temporality, thresholds, Boolean criteria, and source scope; the records below
retain those details and can later be projected to RDF or a property graph.

The implementation has no dependency beyond the Python standard library.  A
LinkML representation of the same public contract lives at
``schemas/guideline_diagnostic_kg.linkml.yaml``.  Runtime validation is kept in
Python so extraction and audit jobs do not need LinkML installed.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import ChainMap
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1

RECORD_TYPES = {
    "Concept",
    "DiagnosisExpression",
    "FeaturePattern",
    "LogicExpression",
    "DiagnosticAssertion",
    "DifferentialAssertion",
    "SourceWork",
    "DocumentVersion",
    "Section",
    "Passage",
    "EvidenceSpan",
    "ExtractionActivity",
    "ConceptMapping",
}

CONCEPT_KINDS = {
    "disease",
    "syndrome",
    "phenotype",
    "test",
    "anatomy",
    "substance",
    "organism",
    "population",
    "unit",
    "specimen",
    "procedure",
    "gene",
    "other",
}
FEATURE_TYPES = {
    "symptom",
    "sign",
    "laboratory",
    "imaging",
    "pathology",
    "genetics",
    "procedure",
    "history",
    "demographic",
    "exposure",
    "medication",
    "course",
    "other",
}
POLARITIES = {"present", "absent", "uncertain"}
TEMPORAL_RELATIONS = {
    "before",
    "after",
    "during",
    "overlaps",
    "at_onset",
    "recurrent",
    "persistent",
    "resolved",
    "not_stated",
}
LOGIC_OPERATORS = {"and", "or", "not", "k_of_n", "sequence"}
COMPOSITION_OPERATORS = {"and", "or", "sequence"}
DIAGNOSTIC_ROLES = {
    "defining",
    "necessary",
    "sufficient",
    "supporting",
    "typical",
    "compatible",
    "argues_against",
    "excluding",
    "risk_factor",
}
DIRECTIONS = {"supports", "argues_against", "neutral"}
NECESSITIES = {"necessary", "sufficient", "optional", "not_stated"}
FAVORS = {"a", "b", "neither", "context_dependent"}
ASSERTION_STATUSES = {"asserted", "derived", "conflict", "rejected"}
REVIEW_STATUSES = {"unreviewed", "accepted", "rejected", "adjudicated"}
MAPPING_PREDICATES = {
    "exact_match",
    "broad_match",
    "narrow_match",
    "related_match",
}
EXTRACTOR_TYPES = {"deterministic", "template", "llm", "hybrid", "human"}

_ID_RE = re.compile(r"^gkg_[a-z][a-z0-9_]*_[a-f0-9]{20}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_PREFIX_BY_TYPE = {
    "Concept": "concept",
    "DiagnosisExpression": "diagnosis",
    "FeaturePattern": "feature",
    "LogicExpression": "logic",
    "DiagnosticAssertion": "assertion",
    "DifferentialAssertion": "differential",
    "SourceWork": "work",
    "DocumentVersion": "version",
    "Section": "section",
    "Passage": "passage",
    "EvidenceSpan": "span",
    "ExtractionActivity": "activity",
    "ConceptMapping": "mapping",
}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _term(value: Any) -> str:
    """Normalize an identity-bearing terminology string, not source prose."""

    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.casefold().split())


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _jsonable(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    """Return a deterministic ledger ID for caller-defined identity parts.

    Extractors may use this helper for staging records before a full dataclass
    exists.  Production records should normally use :func:`stable_id_for`,
    which chooses the correct immutable identity fields for each record type.
    """

    normalized_prefix = _term(prefix).replace(" ", "_")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized_prefix):
        raise ValueError("prefix must contain lowercase letters, digits, or underscores")
    digest = _canonical_hash({"parts": _jsonable(parts)})[:20]
    return f"gkg_{normalized_prefix}_{digest}"


def _identity_payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return immutable identity fields for one record.

    Extraction/review confidences are intentionally excluded: re-reviewing the
    same source-grounded assertion updates its metadata rather than creating a
    second clinical fact.  Evidence spans remain part of assertion identity so
    conflicting sources are never silently collapsed.
    """

    kind = record.get("record_type")
    if kind == "Concept":
        system, code = record.get("system"), record.get("code")
        if system and code:
            return {
                "system": _term(system),
                "code": _term(code),
            }
        return {
            "concept_kind": _term(record.get("concept_kind")),
            "label": _term(record.get("label")),
        }
    if kind == "DiagnosisExpression":
        components = list(record.get("component_diagnosis_ids") or [])
        if record.get("composition_operator") in {"and", "or"}:
            components.sort()
        return {
            "base_concept_id": record.get("base_concept_id"),
            "qualifiers": record.get("qualifiers") or {},
            "component_diagnosis_ids": components,
            "composition_operator": record.get("composition_operator"),
        }
    if kind == "FeaturePattern":
        return {
            key: record.get(key)
            for key in (
                "feature_type",
                "concept_id",
                "surface",
                "polarity",
                "measurement",
                "temporality",
                "site_concept_ids",
                "specimen_concept_id",
                "qualifiers",
            )
        }
    if kind == "LogicExpression":
        operands = list(record.get("operand_ids") or [])
        if record.get("operator") in {"and", "or", "k_of_n"}:
            operands.sort()
        return {
            "operator": record.get("operator"),
            "operand_ids": operands,
            "k": record.get("k"),
            "temporal_window": record.get("temporal_window"),
        }
    if kind in {"DiagnosticAssertion", "DifferentialAssertion"}:
        excluded = {
            "id",
            "schema_version",
            "assertion_confidence",
            "extraction_confidence",
            "extraction_activity_id",
            "review_status",
            "extensions",
        }
        return {
            key: value for key, value in record.items()
            if key not in excluded
        }
    if kind == "SourceWork":
        return {
            "title": _term(record.get("title")),
            "publisher": _term(record.get("publisher")),
            "canonical_url": str(record.get("canonical_url") or "").strip(),
        }
    if kind == "DocumentVersion":
        return {
            key: record.get(key)
            for key in (
                "source_work_id", "version_label", "published_date",
                "content_sha256",
            )
        }
    if kind == "Section":
        return {
            "document_version_id": record.get("document_version_id"),
            "section_path": record.get("section_path") or [],
            "ordinal": record.get("ordinal"),
        }
    if kind == "Passage":
        return {
            "section_id": record.get("section_id"),
            "ordinal": record.get("ordinal"),
            "text_sha256": hashlib.sha256(
                str(record.get("text") or "").encode("utf-8")
            ).hexdigest(),
        }
    if kind == "EvidenceSpan":
        return {
            key: record.get(key)
            for key in ("passage_id", "start_char", "end_char", "quote")
        }
    if kind == "ExtractionActivity":
        return {
            key: record.get(key)
            for key in (
                "pipeline_name", "pipeline_version", "extractor_type",
                "model", "prompt_sha256", "input_sha256", "schema_version",
            )
        }
    if kind == "ConceptMapping":
        return {
            "subject_concept_id": record.get("subject_concept_id"),
            "predicate": record.get("predicate"),
            "object_concept_id": record.get("object_concept_id"),
        }
    raise ValueError(f"unsupported record_type: {kind!r}")


def stable_id_for(record: Mapping[str, Any] | Any) -> str:
    """Compute a deterministic ID from the record's immutable identity."""

    payload = record_to_dict(record)
    kind = payload.get("record_type")
    if kind not in RECORD_TYPES:
        raise ValueError(f"unsupported record_type: {kind!r}")
    digest = _canonical_hash(_identity_payload(payload))[:20]
    return f"gkg_{_PREFIX_BY_TYPE[kind]}_{digest}"


class _KGRecord:
    """Dataclass mixin that assigns a deterministic ID after construction."""

    id: str

    def __post_init__(self) -> None:
        if not self.id:
            object.__setattr__(self, "id", stable_id_for(self))

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)


@dataclass(frozen=True)
class Concept(_KGRecord):
    label: str
    concept_kind: str
    system: str = "LOCAL"
    code: str | None = None
    synonyms: tuple[str, ...] = ()
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="Concept", init=False)


@dataclass(frozen=True)
class DiagnosisExpression(_KGRecord):
    canonical_label: str
    base_concept_id: str | None = None
    qualifiers: Mapping[str, Any] = field(default_factory=dict)
    component_diagnosis_ids: tuple[str, ...] = ()
    composition_operator: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="DiagnosisExpression", init=False)


@dataclass(frozen=True)
class FeaturePattern(_KGRecord):
    canonical_label: str
    feature_type: str
    polarity: str = "present"
    concept_id: str | None = None
    surface: str | None = None
    measurement: Mapping[str, Any] = field(default_factory=dict)
    temporality: Mapping[str, Any] = field(default_factory=dict)
    site_concept_ids: tuple[str, ...] = ()
    specimen_concept_id: str | None = None
    qualifiers: Mapping[str, Any] = field(default_factory=dict)
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="FeaturePattern", init=False)


@dataclass(frozen=True)
class LogicExpression(_KGRecord):
    operator: str
    operand_ids: tuple[str, ...]
    k: int | None = None
    temporal_window: Mapping[str, Any] = field(default_factory=dict)
    label: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="LogicExpression", init=False)


@dataclass(frozen=True)
class DiagnosticAssertion(_KGRecord):
    diagnosis_id: str
    criterion_id: str
    diagnostic_role: str
    direction: str
    necessity: str
    evidence_span_ids: tuple[str, ...]
    assertion_confidence: float
    extraction_confidence: float
    extraction_activity_id: str
    status: str = "asserted"
    review_status: str = "unreviewed"
    population_context_ids: tuple[str, ...] = ()
    qualifiers: Mapping[str, Any] = field(default_factory=dict)
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="DiagnosticAssertion", init=False)


@dataclass(frozen=True)
class DifferentialAssertion(_KGRecord):
    diagnosis_a_id: str
    diagnosis_b_id: str
    discriminator_id: str
    favors: str
    evidence_span_ids: tuple[str, ...]
    assertion_confidence: float
    extraction_confidence: float
    extraction_activity_id: str
    status: str = "asserted"
    review_status: str = "unreviewed"
    qualifiers: Mapping[str, Any] = field(default_factory=dict)
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="DifferentialAssertion", init=False)


@dataclass(frozen=True)
class SourceWork(_KGRecord):
    title: str
    publisher: str
    canonical_url: str
    source_family: str
    license: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="SourceWork", init=False)


@dataclass(frozen=True)
class DocumentVersion(_KGRecord):
    source_work_id: str
    version_label: str
    content_sha256: str
    published_date: str | None = None
    source_uri: str | None = None
    retrieved_at: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="DocumentVersion", init=False)


@dataclass(frozen=True)
class Section(_KGRecord):
    document_version_id: str
    heading: str
    section_path: tuple[str, ...]
    ordinal: int
    section_type: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="Section", init=False)


@dataclass(frozen=True)
class Passage(_KGRecord):
    section_id: str
    ordinal: int
    text: str
    page_start: int | None = None
    page_end: int | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="Passage", init=False)


@dataclass(frozen=True)
class EvidenceSpan(_KGRecord):
    passage_id: str
    start_char: int
    end_char: int
    quote: str
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="EvidenceSpan", init=False)


@dataclass(frozen=True)
class ExtractionActivity(_KGRecord):
    pipeline_name: str
    pipeline_version: str
    extractor_type: str
    input_sha256: str
    model: str | None = None
    prompt_sha256: str | None = None
    parameters: Mapping[str, Any] = field(default_factory=dict)
    started_at: str | None = None
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="ExtractionActivity", init=False)


@dataclass(frozen=True)
class ConceptMapping(_KGRecord):
    subject_concept_id: str
    predicate: str
    object_concept_id: str
    mapping_confidence: float
    mapping_method: str
    reviewer: str | None = None
    evidence_span_ids: tuple[str, ...] = ()
    id: str = ""
    schema_version: int = SCHEMA_VERSION
    extensions: Mapping[str, Any] = field(default_factory=dict)
    record_type: str = field(default="ConceptMapping", init=False)


KG_RECORD_CLASSES = {
    cls.__dataclass_fields__["record_type"].default: cls
    for cls in (
        Concept,
        DiagnosisExpression,
        FeaturePattern,
        LogicExpression,
        DiagnosticAssertion,
        DifferentialAssertion,
        SourceWork,
        DocumentVersion,
        Section,
        Passage,
        EvidenceSpan,
        ExtractionActivity,
        ConceptMapping,
    )
}


def record_to_dict(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    """Convert a dataclass or mapping to a JSON-compatible dictionary."""

    value = _jsonable(record)
    if not isinstance(value, dict):
        raise TypeError("KG record must be a dataclass or mapping")
    return value


class GuidelineKGValidationError(ValueError):
    """Raised when one or more ledger records violate the contract."""

    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_probability(value: Any, path: str, errors: list[str]) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        errors.append(f"{path}: expected a finite number in [0, 1]")


def _check_string_list(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, list) or any(not _nonempty(item) for item in value):
        errors.append(f"{path}: expected a list of non-empty strings")


def _check_temporality(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append(f"{path}: expected object")
        return
    relation = value.get("relation", "not_stated")
    if relation not in TEMPORAL_RELATIONS:
        errors.append(f"{path}.relation: unsupported temporal relation")
    if relation in {"before", "after", "during", "overlaps"} and not (
        _nonempty(value.get("anchor")) or _nonempty(value.get("anchor_id"))
    ):
        errors.append(
            f"{path}: relation={relation!r} requires anchor or anchor_id")
    for key in ("onset_min", "onset_max", "duration_min", "duration_max"):
        if key in value and value[key] is not None and (
            isinstance(value[key], bool)
            or not isinstance(value[key], (int, float))
            or float(value[key]) < 0
        ):
            errors.append(f"{path}.{key}: expected a non-negative number")


def _check_measurement(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, Mapping):
        errors.append(f"{path}: expected object")
        return
    if not value:
        return
    comparator = value.get("comparator")
    if comparator not in {"lt", "le", "eq", "ge", "gt", "between", "present"}:
        errors.append(f"{path}.comparator: unsupported comparator")
    if comparator == "between":
        low, high = value.get("low"), value.get("high")
        if not all(
            isinstance(item, (int, float)) and not isinstance(item, bool)
            for item in (low, high)
        ) or (isinstance(low, (int, float)) and isinstance(high, (int, float))
              and low > high):
            errors.append(f"{path}: between requires numeric low <= high")
    elif comparator != "present" and not (
        isinstance(value.get("value"), (int, float))
        and not isinstance(value.get("value"), bool)
    ):
        errors.append(f"{path}.value: comparator requires numeric value")
    if comparator != "present" and not _nonempty(value.get("unit_concept_id")):
        errors.append(f"{path}.unit_concept_id: numeric measurement requires unit")


def validate_record(record: Mapping[str, Any] | Any) -> list[str]:
    """Validate a record's local shape and semantics.

    Cross-record domain/range and exact-span checks are performed by
    :func:`validate_graph`.
    """

    try:
        payload = record_to_dict(record)
    except (TypeError, ValueError) as exc:
        return [str(exc)]
    errors: list[str] = []
    kind = payload.get("record_type")
    if kind not in RECORD_TYPES:
        return ["record_type: unsupported or missing"]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION}")
    record_id = payload.get("id")
    if not _nonempty(record_id) or not _ID_RE.fullmatch(str(record_id)):
        errors.append("id: expected stable gkg_<type>_<20 hex> identifier")
    else:
        try:
            expected_id = stable_id_for(payload)
        except (TypeError, ValueError) as exc:
            errors.append(f"id: could not compute stable ID ({exc})")
        else:
            if record_id != expected_id:
                errors.append(f"id: non-canonical; expected {expected_id}")
    if "confidence" in payload:
        errors.append(
            "confidence: ambiguous; use assertion_confidence, "
            "extraction_confidence, or mapping_confidence")
    if not isinstance(payload.get("extensions", {}), Mapping):
        errors.append("extensions: expected object")

    if kind == "Concept":
        if not _nonempty(payload.get("label")):
            errors.append("label: required non-empty string")
        if payload.get("concept_kind") not in CONCEPT_KINDS:
            errors.append("concept_kind: unsupported value")
        system, code = payload.get("system"), payload.get("code")
        if not _nonempty(system):
            errors.append("system: required non-empty string")
        if system != "LOCAL" and not _nonempty(code):
            errors.append("code: required for non-LOCAL concepts")
        if "synonyms" in payload:
            _check_string_list(payload["synonyms"], "synonyms", errors)

    elif kind == "DiagnosisExpression":
        if not _nonempty(payload.get("canonical_label")):
            errors.append("canonical_label: required non-empty string")
        base = payload.get("base_concept_id")
        components = payload.get("component_diagnosis_ids")
        if not isinstance(components, list):
            errors.append("component_diagnosis_ids: expected list")
            components = []
        if bool(base) == bool(components):
            errors.append(
                "diagnosis expression requires exactly one of base_concept_id "
                "or component_diagnosis_ids")
        if components:
            if len(components) < 2:
                errors.append("composite diagnosis requires at least 2 components")
            if payload.get("composition_operator") not in COMPOSITION_OPERATORS:
                errors.append("composition_operator: required for composite diagnosis")
        elif payload.get("composition_operator") is not None:
            errors.append("composition_operator: only valid for composite diagnosis")
        if not isinstance(payload.get("qualifiers"), Mapping):
            errors.append("qualifiers: expected object")

    elif kind == "FeaturePattern":
        if not _nonempty(payload.get("canonical_label")):
            errors.append("canonical_label: required non-empty string")
        if payload.get("feature_type") not in FEATURE_TYPES:
            errors.append("feature_type: unsupported value")
        if payload.get("polarity") not in POLARITIES:
            errors.append("polarity: expected present, absent, or uncertain")
        if not payload.get("concept_id") and not _nonempty(payload.get("surface")):
            errors.append("feature requires concept_id or source surface")
        _check_measurement(payload.get("measurement", {}), "measurement", errors)
        _check_temporality(payload.get("temporality", {}), "temporality", errors)
        _check_string_list(
            payload.get("site_concept_ids", []), "site_concept_ids", errors)
        if not isinstance(payload.get("qualifiers"), Mapping):
            errors.append("qualifiers: expected object")

    elif kind == "LogicExpression":
        operator = payload.get("operator")
        operands = payload.get("operand_ids")
        if operator not in LOGIC_OPERATORS:
            errors.append("operator: unsupported logic operator")
        if not isinstance(operands, list) or any(
            not _nonempty(item) for item in operands
        ):
            errors.append("operand_ids: expected non-empty string list")
            operands = []
        if len(set(operands)) != len(operands):
            errors.append("operand_ids: duplicate operands are not allowed")
        if operator == "not" and len(operands) != 1:
            errors.append("operator=not requires exactly 1 operand")
        if operator in {"and", "or", "sequence"} and len(operands) < 2:
            errors.append(f"operator={operator} requires at least 2 operands")
        if operator == "k_of_n":
            k = payload.get("k")
            if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= len(operands):
                errors.append("operator=k_of_n requires integer 1 <= k <= n")
        elif payload.get("k") is not None:
            errors.append("k: only valid for operator=k_of_n")
        window = payload.get("temporal_window", {})
        if not isinstance(window, Mapping):
            errors.append("temporal_window: expected object")

    elif kind in {"DiagnosticAssertion", "DifferentialAssertion"}:
        for key in (
            "assertion_confidence", "extraction_confidence",
        ):
            _check_probability(payload.get(key), key, errors)
        if payload.get("status") not in ASSERTION_STATUSES:
            errors.append("status: unsupported assertion status")
        if payload.get("review_status") not in REVIEW_STATUSES:
            errors.append("review_status: unsupported review status")
        spans = payload.get("evidence_span_ids")
        if not isinstance(spans, list) or not spans or any(
            not _nonempty(item) for item in spans
        ):
            errors.append("evidence_span_ids: at least one evidence span is required")
        if not _nonempty(payload.get("extraction_activity_id")):
            errors.append("extraction_activity_id: required")
        if kind == "DiagnosticAssertion":
            if payload.get("diagnostic_role") not in DIAGNOSTIC_ROLES:
                errors.append("diagnostic_role: unsupported value")
            if payload.get("direction") not in DIRECTIONS:
                errors.append("direction: unsupported value")
            if payload.get("necessity") not in NECESSITIES:
                errors.append("necessity: unsupported value")
            role = payload.get("diagnostic_role")
            direction = payload.get("direction")
            if role in {"argues_against", "excluding"} and direction != "argues_against":
                errors.append(
                    "direction must be argues_against for opposing/excluding role")
            if role in {
                "defining", "necessary", "sufficient", "supporting", "typical",
                "compatible", "risk_factor",
            } and direction != "supports":
                errors.append("supportive diagnostic role requires supports direction")
        elif payload.get("favors") not in FAVORS:
            errors.append("favors: expected a, b, neither, or context_dependent")

    elif kind == "SourceWork":
        for key in ("title", "publisher", "canonical_url", "source_family"):
            if not _nonempty(payload.get(key)):
                errors.append(f"{key}: required non-empty string")

    elif kind == "DocumentVersion":
        for key in ("source_work_id", "version_label"):
            if not _nonempty(payload.get(key)):
                errors.append(f"{key}: required non-empty string")
        if not _SHA256_RE.fullmatch(str(payload.get("content_sha256") or "")):
            errors.append("content_sha256: expected 64 lowercase hex characters")

    elif kind == "Section":
        if not _nonempty(payload.get("document_version_id")):
            errors.append("document_version_id: required")
        if not _nonempty(payload.get("heading")):
            errors.append("heading: required")
        _check_string_list(payload.get("section_path"), "section_path", errors)
        if isinstance(payload.get("ordinal"), bool) or not isinstance(
            payload.get("ordinal"), int
        ) or payload["ordinal"] < 0:
            errors.append("ordinal: expected non-negative integer")

    elif kind == "Passage":
        if not _nonempty(payload.get("section_id")):
            errors.append("section_id: required")
        if not _nonempty(payload.get("text")):
            errors.append("text: required non-empty string")
        if isinstance(payload.get("ordinal"), bool) or not isinstance(
            payload.get("ordinal"), int
        ) or payload["ordinal"] < 0:
            errors.append("ordinal: expected non-negative integer")
        page_start, page_end = payload.get("page_start"), payload.get("page_end")
        if page_start is not None and (
            isinstance(page_start, bool) or not isinstance(page_start, int)
            or page_start < 0
        ):
            errors.append("page_start: expected non-negative integer")
        if page_end is not None and (
            isinstance(page_end, bool) or not isinstance(page_end, int)
            or page_end < 0
        ):
            errors.append("page_end: expected non-negative integer")
        if page_start is not None and page_end is not None and page_end < page_start:
            errors.append("page_end: cannot precede page_start")

    elif kind == "EvidenceSpan":
        if not _nonempty(payload.get("passage_id")):
            errors.append("passage_id: required")
        start, end = payload.get("start_char"), payload.get("end_char")
        if (
            isinstance(start, bool) or not isinstance(start, int)
            or isinstance(end, bool) or not isinstance(end, int)
            or start < 0 or end <= start
        ):
            errors.append("span: expected integers 0 <= start_char < end_char")
        if not _nonempty(payload.get("quote")):
            errors.append("quote: required non-empty exact source text")

    elif kind == "ExtractionActivity":
        for key in ("pipeline_name", "pipeline_version"):
            if not _nonempty(payload.get(key)):
                errors.append(f"{key}: required non-empty string")
        if payload.get("extractor_type") not in EXTRACTOR_TYPES:
            errors.append("extractor_type: unsupported value")
        if not _SHA256_RE.fullmatch(str(payload.get("input_sha256") or "")):
            errors.append("input_sha256: expected 64 lowercase hex characters")
        prompt_hash = payload.get("prompt_sha256")
        if prompt_hash is not None and not _SHA256_RE.fullmatch(str(prompt_hash)):
            errors.append("prompt_sha256: expected 64 lowercase hex characters")
        if payload.get("extractor_type") in {"llm", "hybrid"}:
            if not _nonempty(payload.get("model")):
                errors.append("model: required for llm/hybrid extraction")
            if prompt_hash is None:
                errors.append("prompt_sha256: required for llm/hybrid extraction")

    elif kind == "ConceptMapping":
        if payload.get("predicate") not in MAPPING_PREDICATES:
            errors.append("predicate: unsupported mapping predicate")
        for key in ("subject_concept_id", "object_concept_id", "mapping_method"):
            if not _nonempty(payload.get(key)):
                errors.append(f"{key}: required non-empty string")
        if payload.get("subject_concept_id") == payload.get("object_concept_id"):
            errors.append("concept mapping cannot map a concept to itself")
        _check_probability(payload.get("mapping_confidence"), "mapping_confidence", errors)
        _check_string_list(
            payload.get("evidence_span_ids", []), "evidence_span_ids", errors)

    return errors


def _lookup_ref(
    index: Mapping[str, Mapping[str, Any]], reference: Any,
) -> Mapping[str, Any] | None:
    """Return a referenced record without letting malformed keys raise."""

    if not isinstance(reference, str):
        return None
    return index.get(reference)


def _expect_ref(
    payload: Mapping[str, Any],
    field_name: str,
    index: Mapping[str, Mapping[str, Any]],
    allowed_types: set[str],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    reference = payload.get(field_name)
    target = _lookup_ref(index, reference)
    if target is None:
        errors.append(f"{prefix}.{field_name}: missing reference {reference!r}")
    elif target.get("record_type") not in allowed_types:
        errors.append(
            f"{prefix}.{field_name}: illegal range {target.get('record_type')}; "
            f"expected {'/'.join(sorted(allowed_types))}")


def _expect_ref_list(
    payload: Mapping[str, Any],
    field_name: str,
    index: Mapping[str, Mapping[str, Any]],
    allowed_types: set[str],
    errors: list[str],
    *,
    prefix: str,
) -> None:
    references = payload.get(field_name) or []
    if not isinstance(references, list):
        return
    for position, reference in enumerate(references):
        target = _lookup_ref(index, reference)
        path = f"{prefix}.{field_name}[{position}]"
        if target is None:
            errors.append(f"{path}: missing reference {reference!r}")
        elif target.get("record_type") not in allowed_types:
            errors.append(
                f"{path}: illegal range {target.get('record_type')}; "
                f"expected {'/'.join(sorted(allowed_types))}")


def _validate_cross_record(
    payload: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> None:
    """Validate one record's references against a complete lookup index.

    Keeping this logic shared between full-graph and incremental validation is
    important: a fast path is unsafe if its domain/range contract can drift
    from :func:`validate_graph`.
    """

    kind = payload.get("record_type")
    prefix = str(payload.get("id") or kind)
    if kind == "DiagnosisExpression":
        if payload.get("base_concept_id"):
            _expect_ref(
                payload, "base_concept_id", index, {"Concept"}, errors,
                prefix=prefix,
            )
            target = _lookup_ref(index, payload.get("base_concept_id"))
            if target and target.get("concept_kind") not in {"disease", "syndrome"}:
                errors.append(
                    f"{prefix}.base_concept_id: concept must be disease/syndrome")
        _expect_ref_list(
            payload, "component_diagnosis_ids", index,
            {"DiagnosisExpression"}, errors, prefix=prefix,
        )

    elif kind == "FeaturePattern":
        if payload.get("concept_id"):
            _expect_ref(
                payload, "concept_id", index, {"Concept"}, errors,
                prefix=prefix,
            )
        _expect_ref_list(
            payload, "site_concept_ids", index, {"Concept"}, errors,
            prefix=prefix,
        )
        for site_id in payload.get("site_concept_ids") or []:
            target = _lookup_ref(index, site_id)
            if target and target.get("concept_kind") != "anatomy":
                errors.append(f"{prefix}.site_concept_ids: site must be anatomy")
        if payload.get("specimen_concept_id"):
            _expect_ref(
                payload, "specimen_concept_id", index, {"Concept"}, errors,
                prefix=prefix,
            )
            target = _lookup_ref(index, payload.get("specimen_concept_id"))
            if target and target.get("concept_kind") != "specimen":
                errors.append(
                    f"{prefix}.specimen_concept_id: concept must be specimen")
        measurement = payload.get("measurement") or {}
        unit_id = (
            measurement.get("unit_concept_id")
            if isinstance(measurement, Mapping) else None
        )
        if unit_id:
            target = _lookup_ref(index, unit_id)
            if target is None:
                errors.append(f"{prefix}.measurement.unit_concept_id: missing reference")
            elif target.get("record_type") != "Concept" or target.get(
                "concept_kind") != "unit":
                errors.append(
                    f"{prefix}.measurement.unit_concept_id: concept must be unit")

    elif kind == "LogicExpression":
        _expect_ref_list(
            payload, "operand_ids", index,
            {"FeaturePattern", "LogicExpression"}, errors, prefix=prefix,
        )

    elif kind == "DiagnosticAssertion":
        _expect_ref(
            payload, "diagnosis_id", index, {"DiagnosisExpression"}, errors,
            prefix=prefix,
        )
        _expect_ref(
            payload, "criterion_id", index,
            {"FeaturePattern", "LogicExpression"}, errors, prefix=prefix,
        )
        _expect_ref(
            payload, "extraction_activity_id", index,
            {"ExtractionActivity"}, errors, prefix=prefix,
        )
        _expect_ref_list(
            payload, "evidence_span_ids", index, {"EvidenceSpan"}, errors,
            prefix=prefix,
        )
        _expect_ref_list(
            payload, "population_context_ids", index, {"Concept"}, errors,
            prefix=prefix,
        )
        for context_id in payload.get("population_context_ids") or []:
            target = _lookup_ref(index, context_id)
            if target and target.get("concept_kind") != "population":
                errors.append(
                    f"{prefix}.population_context_ids: concept must be population")

    elif kind == "DifferentialAssertion":
        for key in ("diagnosis_a_id", "diagnosis_b_id"):
            _expect_ref(
                payload, key, index, {"DiagnosisExpression"}, errors,
                prefix=prefix,
            )
        if payload.get("diagnosis_a_id") == payload.get("diagnosis_b_id"):
            errors.append(f"{prefix}: differential diagnoses must be distinct")
        _expect_ref(
            payload, "discriminator_id", index,
            {"FeaturePattern", "LogicExpression"}, errors, prefix=prefix,
        )
        _expect_ref(
            payload, "extraction_activity_id", index,
            {"ExtractionActivity"}, errors, prefix=prefix,
        )
        _expect_ref_list(
            payload, "evidence_span_ids", index, {"EvidenceSpan"}, errors,
            prefix=prefix,
        )

    elif kind == "DocumentVersion":
        _expect_ref(
            payload, "source_work_id", index, {"SourceWork"}, errors,
            prefix=prefix,
        )
    elif kind == "Section":
        _expect_ref(
            payload, "document_version_id", index, {"DocumentVersion"}, errors,
            prefix=prefix,
        )
    elif kind == "Passage":
        _expect_ref(
            payload, "section_id", index, {"Section"}, errors,
            prefix=prefix,
        )
    elif kind == "EvidenceSpan":
        _expect_ref(
            payload, "passage_id", index, {"Passage"}, errors,
            prefix=prefix,
        )
        passage = _lookup_ref(index, payload.get("passage_id"))
        if passage and passage.get("record_type") == "Passage":
            text = passage.get("text", "")
            start, end = payload.get("start_char"), payload.get("end_char")
            if isinstance(text, str) and isinstance(start, int) and isinstance(end, int):
                if end > len(text):
                    errors.append(
                        f"{prefix}: evidence span extends beyond passage text")
                elif text[start:end] != payload.get("quote"):
                    errors.append(
                        f"{prefix}: quote must exactly equal passage[start_char:end_char]")
    elif kind == "ConceptMapping":
        for key in ("subject_concept_id", "object_concept_id"):
            _expect_ref(
                payload, key, index, {"Concept"}, errors, prefix=prefix,
            )
        _expect_ref_list(
            payload, "evidence_span_ids", index, {"EvidenceSpan"}, errors,
            prefix=prefix,
        )


def _validate_logic_cycles(
    roots: Iterable[str],
    index: Mapping[str, Mapping[str, Any]],
    errors: list[str],
) -> None:
    """Reject cycles reachable from ``roots`` in a combined graph index."""

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"{node}: cyclic LogicExpression reference")
            return
        if node in visited:
            return
        target = _lookup_ref(index, node)
        if not target or target.get("record_type") != "LogicExpression":
            return
        visiting.add(node)
        for child in target.get("operand_ids") or []:
            child_target = _lookup_ref(index, child)
            if child_target and child_target.get("record_type") == "LogicExpression":
                visit(str(child))
        visiting.remove(node)
        visited.add(node)

    for root in roots:
        visit(str(root))


def validate_graph(records: Iterable[Mapping[str, Any] | Any]) -> list[str]:
    """Validate record shapes, references, domain/range, and exact evidence."""

    payloads = [record_to_dict(record) for record in records]
    errors: list[str] = []
    index: dict[str, dict[str, Any]] = {}
    for position, payload in enumerate(payloads):
        record_id = payload.get("id")
        prefix = str(record_id or f"record[{position}]")
        errors.extend(f"{prefix}: {error}" for error in validate_record(payload))
        if _nonempty(record_id):
            if record_id in index:
                errors.append(f"{prefix}: duplicate record ID")
            else:
                index[record_id] = payload

    for payload in payloads:
        _validate_cross_record(payload, index, errors)

    # Logic cycles make the criterion non-evaluable and are rejected.
    _validate_logic_cycles(
        (
            str(payload["id"])
            for payload in payloads
            if payload.get("record_type") == "LogicExpression" and payload.get("id")
        ),
        index,
        errors,
    )
    return errors


class GraphValidationIndex:
    """Incrementally validate additions to an already-valid immutable graph.

    Full validation is deliberately the default at construction.  Callers that
    have *immediately* validated the exact same mapping objects may use
    :meth:`from_validated_records` to avoid a redundant full pass.  Existing
    IDs are immutable: an identical record is an allowed no-op, while a
    different payload under an existing stable ID rejects the entire delta.

    The index stores references to existing mapping records rather than deep
    copies.  Callers must therefore not mutate those mappings.  Records
    accepted by :meth:`apply_delta` are copied before they enter the index.
    """

    def __init__(
        self,
        records: Iterable[Mapping[str, Any] | Any],
        *,
        _already_validated: bool = False,
    ) -> None:
        payloads: list[Mapping[str, Any]] = []
        for record in records:
            # Reuse plain mappings so a 100k-record source ledger is not copied
            # merely to build its lookup index.  Dataclasses still need their
            # canonical JSON-compatible representation.
            payloads.append(
                record if isinstance(record, Mapping) else record_to_dict(record)
            )
        if not _already_validated:
            assert_valid_graph(payloads)
        self._records: dict[str, Mapping[str, Any]] = {
            str(payload["id"]): payload for payload in payloads
        }

    @classmethod
    def from_validated_records(
        cls, records: Iterable[Mapping[str, Any] | Any],
    ) -> "GraphValidationIndex":
        """Build an index after a full validator accepted these exact records."""

        return cls(records, _already_validated=True)

    @property
    def record_count(self) -> int:
        return len(self._records)

    def _prepare_delta(
        self, records: Iterable[Mapping[str, Any] | Any],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
        payloads: list[dict[str, Any]] = []
        delta_index: dict[str, dict[str, Any]] = {}
        errors: list[str] = []
        for position, record in enumerate(records):
            try:
                payload = record_to_dict(record)
            except (TypeError, ValueError) as exc:
                errors.append(f"delta[{position}]: {exc}")
                continue
            payloads.append(payload)
            record_id = payload.get("id")
            prefix = str(record_id or f"delta[{position}]")
            errors.extend(f"{prefix}: {error}" for error in validate_record(payload))
            if not _nonempty(record_id):
                continue
            record_id = str(record_id)
            if record_id in delta_index:
                errors.append(f"{prefix}: duplicate record ID in delta")
                continue
            delta_index[record_id] = payload
            current = self._records.get(record_id)
            if current is not None and current != payload:
                errors.append(
                    f"{prefix}: immutable existing record differs from delta")
        return payloads, delta_index, errors

    def validate_delta(
        self, records: Iterable[Mapping[str, Any] | Any],
    ) -> list[str]:
        """Validate a small delta without rescanning unrelated graph records."""

        payloads, delta_index, errors = self._prepare_delta(records)
        combined: Mapping[str, Mapping[str, Any]] = ChainMap(
            delta_index, self._records
        )
        for payload in payloads:
            _validate_cross_record(payload, combined, errors)
        _validate_logic_cycles(
            (
                str(payload["id"])
                for payload in payloads
                if payload.get("record_type") == "LogicExpression"
                and payload.get("id")
            ),
            combined,
            errors,
        )
        return errors

    def apply_delta(
        self, records: Iterable[Mapping[str, Any] | Any],
    ) -> int:
        """Atomically validate and add a delta; return the number of new IDs."""

        payloads = [record_to_dict(record) for record in records]
        errors = self.validate_delta(payloads)
        if errors:
            raise GuidelineKGValidationError(errors)
        additions = {
            str(payload["id"]): payload
            for payload in payloads
            if str(payload["id"]) not in self._records
        }
        self._records.update(additions)
        return len(additions)


def assert_valid_graph(records: Iterable[Mapping[str, Any] | Any]) -> None:
    errors = validate_graph(records)
    if errors:
        raise GuidelineKGValidationError(errors)


def write_jsonl(
    records: Iterable[Mapping[str, Any] | Any],
    path: str | Path,
    *,
    validate: bool = True,
) -> int:
    """Write deterministic UTF-8 JSONL and return the record count."""

    payloads = [record_to_dict(record) for record in records]
    if validate:
        assert_valid_graph(payloads)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for payload in payloads:
            handle.write(json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ))
            handle.write("\n")
    return len(payloads)


def read_jsonl(
    path: str | Path,
    *,
    validate: bool = True,
) -> list[dict[str, Any]]:
    """Read JSONL records, optionally enforcing the complete graph contract."""

    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise GuidelineKGValidationError([
                    f"line {line_number}: invalid JSON ({exc.msg})"
                ]) from exc
            if not isinstance(payload, dict):
                raise GuidelineKGValidationError([
                    f"line {line_number}: record must be a JSON object"
                ])
            records.append(payload)
    if validate:
        assert_valid_graph(records)
    return records


__all__ = [
    "SCHEMA_VERSION",
    "Concept",
    "DiagnosisExpression",
    "FeaturePattern",
    "LogicExpression",
    "DiagnosticAssertion",
    "DifferentialAssertion",
    "SourceWork",
    "DocumentVersion",
    "Section",
    "Passage",
    "EvidenceSpan",
    "ExtractionActivity",
    "ConceptMapping",
    "GuidelineKGValidationError",
    "stable_id",
    "stable_id_for",
    "record_to_dict",
    "validate_record",
    "validate_graph",
    "GraphValidationIndex",
    "assert_valid_graph",
    "write_jsonl",
    "read_jsonl",
]
