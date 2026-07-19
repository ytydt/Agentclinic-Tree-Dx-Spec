"""Versioned schema and semantic validation for CCEG clinical claims.

The Contrastive Clinical Evidence Graph (CCEG) is deliberately claim-centric:
every directional relation is bound to a candidate pair, a typed/value-aware
finding, and an exact source quote.  This module is the contract that must be
frozen before corpus extraction begins.

JSON Schema handles shape validation in external tools.  ``validate_claim``
adds clinical/source-policy invariants that are awkward to express in JSON
Schema and does not require a third-party validation package.
"""
from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

SCHEMA_VERSION_V1 = 1
SCHEMA_VERSION_V2 = 2
# Backward-compatible alias used by existing v1 extractors and auditors.
SCHEMA_VERSION = SCHEMA_VERSION_V1
LATEST_SCHEMA_VERSION = SCHEMA_VERSION_V2
SUPPORTED_SCHEMA_VERSIONS = {SCHEMA_VERSION, LATEST_SCHEMA_VERSION}

CLAIM_TYPES = {
    "direction",
    "common",
    "membership",
    "phenotype_assertion",
    "test_recommendation",
}
RELATIONS_BY_CLAIM_TYPE = {
    "direction": {
        "supports_a", "supports_b", "argues_against_a", "argues_against_b",
    },
    "common": {"common"},
    "membership": {"member_of"},
    "phenotype_assertion": {"typical_for", "atypical_for"},
    "test_recommendation": {"recommends_test"},
}
PAIR_SCOPED_TYPES = {"direction", "common", "test_recommendation"}
SOURCE_CLASSES = {
    "cpg_prose",
    "cpg_enumeration",
    "case_report_list",
    "case_report_prose",
    "oracle",
}
ALLOWED_CLAIM_TYPES_BY_SOURCE = {
    "cpg_prose": {
        "direction", "common", "membership", "phenotype_assertion",
        "test_recommendation",
    },
    "cpg_enumeration": {"membership"},
    "case_report_list": {"membership"},
    "case_report_prose": {"membership", "phenotype_assertion"},
    "oracle": CLAIM_TYPES,
}
VALUE_STATES = {
    "elevated", "suppressed", "present", "absent", "normal", "unknown",
}
STRENGTHS = {"explicit", "qualified", "anecdotal"}
CLAIM_STATUSES = {"raw", "pending_review", "grounded", "rejected"}
ENTAILMENT_STATUSES = {"unvalidated", "grounded", "rejected", "conflict"}
REVIEW_STATUSES = {"unreviewed", "accepted", "rejected"}
ALLOWED_CONSUMERS = {"audit", "p3_soft", "p4_soft", "p5_soft", "p5_veto"}

V2_CLAIM_TYPES = CLAIM_TYPES | {"candidate_effect", "derived_contrast"}
V2_RELATIONS_BY_CLAIM_TYPE = {
    **RELATIONS_BY_CLAIM_TYPE,
    "candidate_effect": {
        "supports_candidate",
        "argues_against_candidate",
        "associated_with",
    },
    "derived_contrast": {
        "supports_a", "supports_b", "argues_against_a", "argues_against_b",
    },
}
V2_PAIR_SCOPED_TYPES = PAIR_SCOPED_TYPES | {"derived_contrast"}
V2_SOURCE_CLASSES = SOURCE_CLASSES | {"composed"}
V2_ALLOWED_CLAIM_TYPES_BY_SOURCE = {
    **ALLOWED_CLAIM_TYPES_BY_SOURCE,
    "cpg_prose": ALLOWED_CLAIM_TYPES_BY_SOURCE["cpg_prose"]
    | {"candidate_effect"},
    "oracle": V2_CLAIM_TYPES - {"derived_contrast"},
    "composed": {"derived_contrast"},
}
V2_CLAIM_STATUSES = CLAIM_STATUSES | {"research_validated"}
REVIEW_MODES = {"human", "synthetic_dual_llm"}
RESEARCH_CONSUMERS = {
    "research_p3_soft", "research_p4_soft", "research_p5_soft",
}
V2_ALLOWED_CONSUMERS = ALLOWED_CONSUMERS | RESEARCH_CONSUMERS
DERIVED_COMPOSITION_PIPELINE = "deterministic_composition"

_CLAIM_ID_RE = re.compile(r"^cceg_[a-f0-9]{12,64}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class CandidateRef:
    name: str
    id: str | None = None
    id_provenance: str | None = None
    l1_parent: str | None = None


@dataclass(frozen=True)
class ConceptRef:
    system: str
    code: str
    display: str
    provenance: str
    confidence: float = 1.0


@dataclass(frozen=True)
class TemporalContext:
    onset: str | None = None
    duration: str | None = None
    relation: str | None = None
    anchor: str | None = None


@dataclass(frozen=True)
class FindingState:
    surface: str
    event_type: str
    value_state: str
    concepts: tuple[ConceptRef, ...] = ()
    polarity: int = 1
    value: str | float | None = None
    unit: str | None = None
    specimen: str | None = None
    temporal: TemporalContext = field(default_factory=TemporalContext)
    context: Mapping[str, Any] = field(default_factory=dict)
    abstained: bool = False


@dataclass(frozen=True)
class Comparator:
    required: bool
    has_support_excerpt: bool
    has_contrast_excerpt: bool
    contrast_candidates: tuple[str, ...] = ()


@dataclass(frozen=True)
class Provenance:
    source_id: str
    chunk_id: str
    article_id: str
    section: str
    chunk_type: str
    quote: str
    quote_span: tuple[int, int]
    url: str
    evidence_grade: str | None = None


@dataclass(frozen=True)
class ExtractionMeta:
    pipeline: str
    model: str
    prompt_sha256: str
    confidence: float
    entailment_status: str
    normalization_abstained: bool = False
    normalization_reason: str | None = None


@dataclass(frozen=True)
class ClaimAudit:
    enumeration_only: bool
    pair_binding_ok: bool
    negation_scope_ok: bool
    value_scope_ok: bool


@dataclass(frozen=True)
class Review:
    status: str = "unreviewed"
    reviewer_ids: tuple[str, ...] = ()
    adjudication: str | None = None
    mode: str = "human"
    reviewer_runs: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class Derivation:
    derived: bool
    premise_claim_ids: tuple[str, ...]
    composition_rule: str


@dataclass(frozen=True)
class Split:
    document_family: str
    document_split: str
    family_held_out: bool
    pilot_scope: bool


@dataclass(frozen=True)
class CCEGClaim:
    claim_id: str
    claim_type: str
    candidate_a: CandidateRef
    finding: FindingState
    relation: str
    strength: str
    source_class: str
    provenance: Provenance | None
    extraction: ExtractionMeta
    audit: ClaimAudit
    review: Review
    split: Split
    comparator: Comparator
    candidate_b: CandidateRef | None = None
    recommended_test: Mapping[str, Any] | None = None
    provenance_bundle: tuple[Provenance, ...] = ()
    derivation: Derivation | None = None
    allowed_consumers: tuple[str, ...] = ("audit",)
    claim_status: str = "raw"
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CCEGValidationError(ValueError):
    """Raised when a CCEG claim violates the frozen contract."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_mapping(
    payload: Mapping[str, Any], key: str, errors: list[str],
) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        errors.append(f"{key}: required object")
        return {}
    return value


def _validate_provenance(
    provenance: Mapping[str, Any],
    errors: list[str],
    *,
    prefix: str = "provenance",
) -> None:
    for key in (
        "source_id", "chunk_id", "article_id", "section", "chunk_type",
        "quote", "url",
    ):
        if not _is_nonempty_string(provenance.get(key)):
            errors.append(f"{prefix}.{key}: required non-empty string")
    span = provenance.get("quote_span")
    if not (
        isinstance(span, list) and len(span) == 2
        and all(isinstance(value, int) for value in span)
        and span[0] >= 0 and span[1] > span[0]
    ):
        errors.append(
            f"{prefix}.quote_span: expected [start, end], 0<=start<end")
    elif isinstance(provenance.get("quote"), str) and (
        span[1] - span[0] != len(provenance["quote"])
    ):
        errors.append(f"{prefix}.quote_span: length must equal quote length")


def _validate_v2_lane_policy(
    payload: Mapping[str, Any],
    errors: list[str],
    *,
    claim_type: Any,
    relation: Any,
    source_class: Any,
    consumers: list[Any],
    status: Any,
    review_mode: Any,
) -> None:
    consumer_set = set(consumers)
    research_consumers = consumer_set & RESEARCH_CONSUMERS
    clinical_consumers = consumer_set & (ALLOWED_CONSUMERS - {"audit"})

    if review_mode == "synthetic_dual_llm":
        if status != "research_validated":
            errors.append(
                "synthetic_dual_llm review requires "
                "claim_status=research_validated")
        if clinical_consumers:
            errors.append(
                "synthetic_dual_llm review cannot grant clinical consumers")
    elif status == "research_validated":
        errors.append(
            "claim_status=research_validated requires "
            "review.mode=synthetic_dual_llm")

    if research_consumers and (
        status != "research_validated"
        or review_mode != "synthetic_dual_llm"
    ):
        errors.append(
            "research consumers require synthetic_dual_llm "
            "research_validated claims")

    derivation = payload.get("derivation")
    if claim_type == "candidate_effect":
        if source_class not in {"cpg_prose", "oracle"}:
            errors.append(
                "source_policy: candidate_effect requires cpg_prose or oracle")
        if derivation is not None:
            errors.append(
                "derivation: candidate_effect must be directly sourced")
        forbidden = consumer_set & {
            "p5_soft", "p5_veto", "research_p5_soft",
        }
        if forbidden:
            errors.append(
                "candidate_effect cannot enter a P5 consumer before "
                "composition")
        if relation == "associated_with" and consumer_set != {"audit"}:
            errors.append(
                "associated_with candidate_effect is audit-only")

    if claim_type == "derived_contrast":
        if source_class != "composed":
            errors.append(
                "source_policy: derived_contrast requires source_class=composed")
        if not isinstance(derivation, Mapping):
            errors.append("derivation: required object for derived_contrast")
            derivation = {}
        if derivation.get("derived") is not True:
            errors.append("derivation.derived: must be true")
        premise_ids = derivation.get("premise_claim_ids")
        if not isinstance(premise_ids, list) or len(premise_ids) < 2:
            errors.append(
                "derivation.premise_claim_ids: requires at least two claims")
            premise_ids = []
        else:
            invalid_ids = [
                claim_id for claim_id in premise_ids
                if not isinstance(claim_id, str)
                or not _CLAIM_ID_RE.fullmatch(claim_id)
            ]
            if invalid_ids:
                errors.append(
                    "derivation.premise_claim_ids: every id must match "
                    "cceg_<12-64 lowercase hex>")
            if len(set(premise_ids)) != len(premise_ids):
                errors.append(
                    "derivation.premise_claim_ids: claims must be unique")
        if not _is_nonempty_string(derivation.get("composition_rule")):
            errors.append(
                "derivation.composition_rule: required non-empty string")
        extraction = payload.get("extraction")
        if (
            not isinstance(extraction, Mapping)
            or extraction.get("pipeline") != DERIVED_COMPOSITION_PIPELINE
        ):
            errors.append(
                "derived_contrast must be emitted by "
                f"extraction.pipeline={DERIVED_COMPOSITION_PIPELINE}")
        bundle = payload.get("provenance_bundle")
        if isinstance(bundle, list) and premise_ids and (
            len(bundle) != len(premise_ids)
        ):
            errors.append(
                "provenance_bundle: must contain one provenance per premise")
        if review_mode == "synthetic_dual_llm":
            forbidden = consumer_set - {"audit", "research_p5_soft"}
            if forbidden:
                errors.append(
                    "synthetic derived_contrast is composed-only P5 research "
                    "evidence")
        else:
            forbidden = consumer_set - {"audit", "p5_soft"}
            if forbidden:
                errors.append(
                    "derived_contrast is composed-only P5 evidence")
    elif source_class == "composed":
        errors.append(
            "source_policy: composed source may only emit derived_contrast")
    elif derivation is not None:
        errors.append("derivation: only derived_contrast may set derivation")


def validate_claim(payload: Mapping[str, Any]) -> list[str]:
    """Return all structural and source-policy violations for one claim."""
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return ["claim: required object"]

    schema_version = payload.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return [
            "schema_version: expected one of "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        ]
    is_v2 = schema_version == LATEST_SCHEMA_VERSION
    claim_types = V2_CLAIM_TYPES if is_v2 else CLAIM_TYPES
    relations_by_type = (
        V2_RELATIONS_BY_CLAIM_TYPE if is_v2 else RELATIONS_BY_CLAIM_TYPE
    )
    pair_scoped_types = V2_PAIR_SCOPED_TYPES if is_v2 else PAIR_SCOPED_TYPES
    source_classes = V2_SOURCE_CLASSES if is_v2 else SOURCE_CLASSES
    allowed_types_by_source = (
        V2_ALLOWED_CLAIM_TYPES_BY_SOURCE
        if is_v2 else ALLOWED_CLAIM_TYPES_BY_SOURCE
    )
    claim_statuses = V2_CLAIM_STATUSES if is_v2 else CLAIM_STATUSES
    allowed_consumers = V2_ALLOWED_CONSUMERS if is_v2 else ALLOWED_CONSUMERS

    claim_id = payload.get("claim_id")
    if not isinstance(claim_id, str) or not _CLAIM_ID_RE.fullmatch(claim_id):
        errors.append("claim_id: expected cceg_<12-64 lowercase hex>")

    claim_type = payload.get("claim_type")
    relation = payload.get("relation")
    source_class = payload.get("source_class")
    if claim_type not in claim_types:
        errors.append(f"claim_type: invalid {claim_type!r}")
    elif relation not in relations_by_type[claim_type]:
        errors.append(
            f"relation: {relation!r} is invalid for claim_type {claim_type!r}")
    if source_class not in source_classes:
        errors.append(f"source_class: invalid {source_class!r}")
    elif claim_type in claim_types and claim_type not in (
        allowed_types_by_source[source_class]
    ):
        errors.append(
            f"source_policy: {source_class} cannot emit {claim_type}")

    candidate_a = _require_mapping(payload, "candidate_a", errors)
    candidate_b = payload.get("candidate_b")
    if not _is_nonempty_string(candidate_a.get("name")):
        errors.append("candidate_a.name: required non-empty string")
    if candidate_a.get("id") and not candidate_a.get("id_provenance"):
        errors.append("candidate_a.id_provenance: required when id is set")
    if claim_type in pair_scoped_types:
        if not isinstance(candidate_b, Mapping):
            errors.append(f"candidate_b: required for {claim_type}")
        elif not _is_nonempty_string(candidate_b.get("name")):
            errors.append("candidate_b.name: required non-empty string")
    elif is_v2 and claim_type == "candidate_effect" and candidate_b is not None:
        errors.append("candidate_b: must be null for candidate_effect")
    if isinstance(candidate_b, Mapping) and candidate_b.get("id") and not (
        candidate_b.get("id_provenance")
    ):
        errors.append("candidate_b.id_provenance: required when id is set")

    finding = _require_mapping(payload, "finding", errors)
    if not _is_nonempty_string(finding.get("surface")):
        errors.append("finding.surface: required non-empty string")
    if not _is_nonempty_string(finding.get("event_type")):
        errors.append("finding.event_type: required non-empty string")
    if finding.get("value_state") not in VALUE_STATES:
        errors.append(f"finding.value_state: invalid {finding.get('value_state')!r}")
    if finding.get("polarity") not in {-1, 0, 1}:
        errors.append("finding.polarity: expected -1, 0, or 1")
    concepts = finding.get("concepts")
    abstained = finding.get("abstained")
    if not isinstance(concepts, list):
        errors.append("finding.concepts: required array")
        concepts = []
    if not isinstance(abstained, bool):
        errors.append("finding.abstained: required boolean")
    elif concepts and abstained:
        errors.append("finding: mapped concepts and abstained cannot both be set")
    elif not concepts and not abstained:
        errors.append("finding: empty concepts require abstained=true")
    for index, concept in enumerate(concepts):
        if not isinstance(concept, Mapping):
            errors.append(f"finding.concepts[{index}]: required object")
            continue
        for key in ("system", "code", "display", "provenance"):
            if not _is_nonempty_string(concept.get(key)):
                errors.append(
                    f"finding.concepts[{index}].{key}: required non-empty string")
        confidence = concept.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(
                f"finding.concepts[{index}].confidence: expected 0..1")

    if payload.get("strength") not in STRENGTHS:
        errors.append(f"strength: invalid {payload.get('strength')!r}")
    if source_class in {"case_report_list", "case_report_prose"} and (
        payload.get("strength") != "anecdotal"
    ):
        errors.append("source_policy: case-report claims must be anecdotal")

    consumers = payload.get("allowed_consumers")
    if not isinstance(consumers, list) or not consumers:
        errors.append("allowed_consumers: required non-empty array")
        consumers = []
    invalid_consumers = set(consumers) - allowed_consumers
    if invalid_consumers:
        errors.append(
            f"allowed_consumers: invalid {sorted(invalid_consumers)}")

    comparator = _require_mapping(payload, "comparator", errors)
    if claim_type in pair_scoped_types:
        if comparator.get("required") is not True:
            errors.append(f"comparator.required: must be true for {claim_type}")
        if comparator.get("has_support_excerpt") is not True:
            errors.append("comparator.has_support_excerpt: required")
        if comparator.get("has_contrast_excerpt") is not True:
            errors.append("comparator.has_contrast_excerpt: required")
        contrasts = comparator.get("contrast_candidates")
        if not isinstance(contrasts, list) or not contrasts:
            errors.append("comparator.contrast_candidates: required non-empty array")
    elif is_v2 and claim_type == "candidate_effect":
        if comparator.get("required") is not False:
            errors.append("comparator.required: must be false for candidate_effect")
        if comparator.get("has_contrast_excerpt") is not False:
            errors.append(
                "comparator.has_contrast_excerpt: must be false for "
                "candidate_effect")
        if comparator.get("contrast_candidates") not in ([], ()):
            errors.append(
                "comparator.contrast_candidates: must be empty for "
                "candidate_effect")

    if is_v2 and claim_type == "derived_contrast":
        if payload.get("provenance") is not None:
            errors.append(
                "provenance: derived_contrast must not fabricate a single "
                "source provenance")
        provenance_bundle = payload.get("provenance_bundle")
        if not isinstance(provenance_bundle, list) or len(provenance_bundle) < 2:
            errors.append(
                "provenance_bundle: derived_contrast requires at least two "
                "premise provenances")
            provenance_bundle = []
        chunk_ids: set[str] = set()
        for index, item in enumerate(provenance_bundle):
            if not isinstance(item, Mapping):
                errors.append(
                    f"provenance_bundle[{index}]: required object")
                continue
            _validate_provenance(
                item, errors, prefix=f"provenance_bundle[{index}]")
            chunk_id = item.get("chunk_id")
            if isinstance(chunk_id, str):
                chunk_ids.add(chunk_id)
        if len(provenance_bundle) >= 2 and len(chunk_ids) < 2:
            errors.append(
                "provenance_bundle: premise provenances must cover at least "
                "two chunks")
    else:
        provenance = _require_mapping(payload, "provenance", errors)
        _validate_provenance(provenance, errors)
        if is_v2 and payload.get("provenance_bundle") not in (None, []):
            errors.append(
                "provenance_bundle: only derived_contrast may use a bundle")

    extraction = _require_mapping(payload, "extraction", errors)
    for key in ("pipeline", "model"):
        if not _is_nonempty_string(extraction.get(key)):
            errors.append(f"extraction.{key}: required non-empty string")
    prompt_hash = extraction.get("prompt_sha256")
    if not isinstance(prompt_hash, str) or not _SHA256_RE.fullmatch(prompt_hash):
        errors.append("extraction.prompt_sha256: expected lowercase SHA-256")
    confidence = extraction.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append("extraction.confidence: expected 0..1")
    if extraction.get("entailment_status") not in ENTAILMENT_STATUSES:
        errors.append(
            "extraction.entailment_status: invalid "
            f"{extraction.get('entailment_status')!r}")
    if bool(extraction.get("normalization_abstained")) != bool(abstained):
        errors.append(
            "extraction.normalization_abstained must match finding.abstained")

    audit = _require_mapping(payload, "audit", errors)
    for key in (
        "enumeration_only", "pair_binding_ok", "negation_scope_ok",
        "value_scope_ok",
    ):
        if not isinstance(audit.get(key), bool):
            errors.append(f"audit.{key}: required boolean")
    if claim_type in pair_scoped_types and audit.get("enumeration_only"):
        errors.append(f"audit.enumeration_only: cannot emit {claim_type}")

    review = _require_mapping(payload, "review", errors)
    if review.get("status") not in REVIEW_STATUSES:
        errors.append(f"review.status: invalid {review.get('status')!r}")
    reviewers = review.get("reviewer_ids")
    if not isinstance(reviewers, list):
        errors.append("review.reviewer_ids: required array")
        reviewers = []
    review_mode = review.get("mode") if is_v2 else "human"
    reviewer_runs: list[Any] = []
    if is_v2:
        if review_mode not in REVIEW_MODES:
            errors.append(f"review.mode: invalid {review_mode!r}")
        reviewer_runs_value = review.get("reviewer_runs")
        if not isinstance(reviewer_runs_value, list):
            errors.append("review.reviewer_runs: required array")
        else:
            reviewer_runs = reviewer_runs_value
        for index, run in enumerate(reviewer_runs):
            if not isinstance(run, Mapping):
                errors.append(f"review.reviewer_runs[{index}]: required object")
                continue
            for key in ("reviewer_id", "model", "prompt"):
                if not _is_nonempty_string(run.get(key)):
                    errors.append(
                        f"review.reviewer_runs[{index}].{key}: "
                        "required non-empty string")
            run_hash = run.get("prompt_sha256")
            if not isinstance(run_hash, str) or not _SHA256_RE.fullmatch(run_hash):
                errors.append(
                    f"review.reviewer_runs[{index}].prompt_sha256: "
                    "expected lowercase SHA-256")
            seed = run.get("seed")
            if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
                errors.append(
                    f"review.reviewer_runs[{index}].seed: "
                    "expected non-negative integer")
        if review_mode == "synthetic_dual_llm":
            run_ids = {
                run.get("reviewer_id") for run in reviewer_runs
                if isinstance(run, Mapping)
                and _is_nonempty_string(run.get("reviewer_id"))
            }
            if len(run_ids) < 2:
                errors.append(
                    "synthetic_dual_llm review requires two independent "
                    "reviewer runs")
            run_fingerprints = {
                (
                    run.get("model"),
                    run.get("prompt_sha256"),
                    run.get("seed"),
                )
                for run in reviewer_runs if isinstance(run, Mapping)
            }
            if len(run_fingerprints) < 2:
                errors.append(
                    "synthetic_dual_llm reviewer runs must use independent "
                    "model/prompt/seed configurations")
            if len(set(reviewers)) < 2:
                errors.append(
                    "synthetic_dual_llm review requires two reviewer_ids")

    split = _require_mapping(payload, "split", errors)
    if not _is_nonempty_string(split.get("document_family")):
        errors.append("split.document_family: required non-empty string")
    if split.get("document_split") not in {"build", "audit", "held_out"}:
        errors.append("split.document_split: expected build|audit|held_out")
    for key in ("family_held_out", "pilot_scope"):
        if not isinstance(split.get(key), bool):
            errors.append(f"split.{key}: required boolean")

    status = payload.get("claim_status")
    if status not in claim_statuses:
        errors.append(f"claim_status: invalid {status!r}")
    if is_v2:
        _validate_v2_lane_policy(
            payload,
            errors,
            claim_type=claim_type,
            relation=relation,
            source_class=source_class,
            consumers=consumers,
            status=status,
            review_mode=review_mode,
        )
    if status == "grounded":
        if extraction.get("entailment_status") != "grounded":
            errors.append("grounded claim requires grounded entailment")
        if review.get("status") != "accepted":
            errors.append("grounded claim requires accepted review")
        required_reviewers = 2 if claim_type in pair_scoped_types else 1
        if len(set(reviewers)) < required_reviewers:
            errors.append(
                f"grounded {claim_type} requires {required_reviewers} reviewer(s)")
        for key in ("pair_binding_ok", "negation_scope_ok", "value_scope_ok"):
            if audit.get(key) is not True:
                errors.append(f"grounded claim requires audit.{key}=true")
        if claim_type in pair_scoped_types and audit.get("enumeration_only"):
            errors.append(
                f"grounded {claim_type} claim cannot be enumeration_only")
    elif is_v2 and status == "research_validated":
        if extraction.get("entailment_status") != "grounded":
            errors.append(
                "research_validated claim requires grounded entailment")
        if review.get("status") != "accepted":
            errors.append(
                "research_validated claim requires accepted review")
        for key in ("pair_binding_ok", "negation_scope_ok", "value_scope_ok"):
            if audit.get(key) is not True:
                errors.append(
                    f"research_validated claim requires audit.{key}=true")
    return errors


def assert_valid_claim(payload: Mapping[str, Any]) -> None:
    """Raise :class:`CCEGValidationError` if a claim is invalid."""
    errors = validate_claim(payload)
    if errors:
        raise CCEGValidationError(errors)


def _claim_json_schema_v1() -> dict[str, Any]:
    """Return the machine-readable JSON Schema for CCEG claim version 1."""
    nonempty_string = {"type": "string", "minLength": 1}
    nullable_string = {"type": ["string", "null"]}
    candidate = {
        "type": ["object", "null"],
        "properties": {
            "name": nonempty_string,
            "id": nullable_string,
            "id_provenance": nullable_string,
            "l1_parent": nullable_string,
        },
        "required": ["name", "id", "id_provenance", "l1_parent"],
        "additionalProperties": False,
    }


    concept = {
        "type": "object",
        "properties": {
            "system": nonempty_string,
            "code": nonempty_string,
            "display": nonempty_string,
            "provenance": nonempty_string,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "system", "code", "display", "provenance", "confidence",
        ],
        "additionalProperties": False,
    }


    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://agentclinic.local/schemas/cceg-claim-v1.schema.json",
        "title": "CCEG Reified Clinical Claim v1",
        "description": (
            "Pair-scoped, value-aware, provenance-bearing clinical evidence "
            "claim. Cross-field source permissions are additionally enforced "
            "by cceg_schema.validate_claim."
        ),
        "type": "object",
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "claim_id": {
                "type": "string", "pattern": r"^cceg_[a-f0-9]{12,64}$",
            },
            "claim_type": {"enum": sorted(CLAIM_TYPES)},
            "candidate_a": {**candidate, "type": "object"},
            "candidate_b": candidate,
            "finding": {
                "type": "object",
                "properties": {
                    "surface": nonempty_string,
                    "event_type": nonempty_string,
                    "concepts": {"type": "array", "items": concept},
                    "polarity": {"enum": [-1, 0, 1]},
                    "value_state": {"enum": sorted(VALUE_STATES)},
                    "value": {"type": ["string", "number", "null"]},
                    "unit": nullable_string,
                    "specimen": nullable_string,
                    "temporal": {
                        "type": "object",
                        "properties": {
                            "onset": nullable_string,
                            "duration": nullable_string,
                            "relation": nullable_string,
                            "anchor": nullable_string,
                        },
                        "required": ["onset", "duration", "relation", "anchor"],
                        "additionalProperties": False,
                    },
                    "context": {"type": "object"},
                    "abstained": {"type": "boolean"},
                },
                "required": [
                    "surface", "event_type", "concepts", "polarity",
                    "value_state", "value", "unit", "specimen", "temporal",
                    "context", "abstained",
                ],
                "additionalProperties": False,
            },
            "relation": {
                "enum": sorted(set().union(*RELATIONS_BY_CLAIM_TYPE.values())),
            },
            "recommended_test": {"type": ["object", "null"]},
            "strength": {"enum": sorted(STRENGTHS)},
            "source_class": {"enum": sorted(SOURCE_CLASSES)},
            "allowed_consumers": {
                "type": "array", "minItems": 1, "uniqueItems": True,
                "items": {"enum": sorted(ALLOWED_CONSUMERS)},
            },
            "comparator": {
                "type": "object",
                "properties": {
                    "required": {"type": "boolean"},
                    "has_support_excerpt": {"type": "boolean"},
                    "has_contrast_excerpt": {"type": "boolean"},
                    "contrast_candidates": {
                        "type": "array", "items": nonempty_string,
                        "uniqueItems": True,
                    },
                },
                "required": [
                    "required", "has_support_excerpt", "has_contrast_excerpt",
                    "contrast_candidates",
                ],
                "additionalProperties": False,
            },
            "provenance": {
                "type": "object",
                "properties": {
                    "source_id": nonempty_string,
                    "chunk_id": nonempty_string,
                    "article_id": nonempty_string,
                    "section": nonempty_string,
                    "chunk_type": nonempty_string,
                    "quote": nonempty_string,
                    "quote_span": {
                        "type": "array", "minItems": 2, "maxItems": 2,
                        "items": {"type": "integer", "minimum": 0},
                    },
                    "url": nonempty_string,
                    "evidence_grade": nullable_string,
                },
                "required": [
                    "source_id", "chunk_id", "article_id", "section",
                    "chunk_type", "quote", "quote_span", "url",
                    "evidence_grade",
                ],
                "additionalProperties": False,
            },
            "extraction": {
                "type": "object",
                "properties": {
                    "pipeline": nonempty_string,
                    "model": nonempty_string,
                    "prompt_sha256": {
                        "type": "string", "pattern": r"^[a-f0-9]{64}$",
                    },
                    "confidence": {
                        "type": "number", "minimum": 0, "maximum": 1,
                    },
                    "entailment_status": {
                        "enum": sorted(ENTAILMENT_STATUSES),
                    },
                    "normalization_abstained": {"type": "boolean"},
                    "normalization_reason": nullable_string,
                },
                "required": [
                    "pipeline", "model", "prompt_sha256", "confidence",
                    "entailment_status", "normalization_abstained",
                    "normalization_reason",
                ],
                "additionalProperties": False,
            },
            "audit": {
                "type": "object",
                "properties": {
                    "enumeration_only": {"type": "boolean"},
                    "pair_binding_ok": {"type": "boolean"},
                    "negation_scope_ok": {"type": "boolean"},
                    "value_scope_ok": {"type": "boolean"},
                },
                "required": [
                    "enumeration_only", "pair_binding_ok",
                    "negation_scope_ok", "value_scope_ok",
                ],
                "additionalProperties": False,
            },
            "review": {
                "type": "object",
                "properties": {
                    "status": {"enum": sorted(REVIEW_STATUSES)},
                    "reviewer_ids": {
                        "type": "array", "items": nonempty_string,
                        "uniqueItems": True,
                    },
                    "adjudication": nullable_string,
                },
                "required": ["status", "reviewer_ids", "adjudication"],
                "additionalProperties": False,
            },
            "split": {
                "type": "object",
                "properties": {
                    "document_family": nonempty_string,
                    "document_split": {
                        "enum": ["build", "audit", "held_out"],
                    },
                    "family_held_out": {"type": "boolean"},
                    "pilot_scope": {"type": "boolean"},
                },
                "required": [
                    "document_family", "document_split",
                    "family_held_out", "pilot_scope",
                ],
                "additionalProperties": False,
            },
            "claim_status": {"enum": sorted(CLAIM_STATUSES)},
        },
        "required": [
            "schema_version", "claim_id", "claim_type", "candidate_a",
            "candidate_b", "finding", "relation", "recommended_test",
            "strength", "source_class", "allowed_consumers", "comparator",
            "provenance", "extraction", "audit", "review", "split",
            "claim_status",
        ],
        "additionalProperties": False,
    }


def _claim_json_schema_v2() -> dict[str, Any]:
    schema = deepcopy(_claim_json_schema_v1())
    schema["$id"] = (
        "https://agentclinic.local/schemas/cceg-claim-v2.schema.json")
    schema["title"] = "CCEG Reified Clinical Claim v2"
    schema["description"] = (
        "Versioned CCEG claim supporting directly sourced unary candidate "
        "effects and deterministic, multi-provenance derived contrasts. "
        "Cross-field source, review-lane, and consumer permissions are "
        "enforced by cceg_schema.validate_claim."
    )
    properties = schema["properties"]
    properties["schema_version"] = {"const": LATEST_SCHEMA_VERSION}
    properties["claim_type"] = {"enum": sorted(V2_CLAIM_TYPES)}
    properties["relation"] = {
        "enum": sorted(set().union(*V2_RELATIONS_BY_CLAIM_TYPE.values())),
    }
    properties["source_class"] = {"enum": sorted(V2_SOURCE_CLASSES)}
    properties["allowed_consumers"]["items"] = {
        "enum": sorted(V2_ALLOWED_CONSUMERS),
    }
    properties["claim_status"] = {"enum": sorted(V2_CLAIM_STATUSES)}

    review = properties["review"]
    review["properties"]["mode"] = {"enum": sorted(REVIEW_MODES)}
    review["properties"]["reviewer_runs"] = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "reviewer_id": {"type": "string", "minLength": 1},
                "model": {"type": "string", "minLength": 1},
                "prompt": {"type": "string", "minLength": 1},
                "prompt_sha256": {
                    "type": "string", "pattern": r"^[a-f0-9]{64}$",
                },
                "seed": {"type": "integer", "minimum": 0},
            },
            "required": [
                "reviewer_id", "model", "prompt", "prompt_sha256", "seed",
            ],
            "additionalProperties": False,
        },
    }
    review["required"].extend(["mode", "reviewer_runs"])

    provenance = deepcopy(properties["provenance"])
    properties["provenance"] = {
        "anyOf": [provenance, {"type": "null"}],
    }
    properties["provenance_bundle"] = {
        "type": "array",
        "items": provenance,
    }
    properties["derivation"] = {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "derived": {"const": True},
                    "premise_claim_ids": {
                        "type": "array",
                        "minItems": 2,
                        "uniqueItems": True,
                        "items": {
                            "type": "string",
                            "pattern": r"^cceg_[a-f0-9]{12,64}$",
                        },
                    },
                    "composition_rule": {
                        "type": "string", "minLength": 1,
                    },
                },
                "required": [
                    "derived", "premise_claim_ids", "composition_rule",
                ],
                "additionalProperties": False,
            },
            {"type": "null"},
        ],
    }
    schema["required"].extend(["provenance_bundle", "derivation"])
    return schema


def claim_json_schema(schema_version: int = SCHEMA_VERSION) -> dict[str, Any]:
    """Return the canonical JSON Schema for CCEG version 1 or 2.

    The no-argument behavior intentionally remains v1-compatible.
    """
    if schema_version == SCHEMA_VERSION:
        return _claim_json_schema_v1()
    if schema_version == LATEST_SCHEMA_VERSION:
        return _claim_json_schema_v2()
    raise ValueError(
        f"unsupported CCEG schema version: {schema_version!r}; "
        f"expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}")
