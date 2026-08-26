"""Deterministic and citation-bounded extraction for the guideline KG.

The extractor intentionally separates three things that ordinary triple
extraction tends to conflate:

* source structure and exact evidence spans;
* clinical assertions, including polarity and logical scope; and
* ontology mappings, which may be unresolved without invalidating a claim.

This module is dependency-free.  It implements the high-precision template
lane and the conversion of already validated LLM slots into schema records.
Network calls live in ``scripts/extract_guideline_kg_residuals.py`` so schema
validation can be tested without credentials or a provider.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .guideline_kg_schema import (
    Concept,
    DiagnosisExpression,
    DiagnosticAssertion,
    DifferentialAssertion,
    EvidenceSpan,
    ExtractionActivity,
    FeaturePattern,
    LogicExpression,
    Passage,
    record_to_dict,
)


PIPELINE_NAME = "guideline_kg_template_extractor"
PIPELINE_VERSION = "0.1.1"

_WS_RE = re.compile(r"\s+")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_DIAGNOSTIC_CUE_RE = re.compile(
    r"\b(?:diagnos(?:is|ed|tic)|differential|characteri[sz]ed|suggests?|"
    r"consistent with|pathognomonic|rules? out|unlikely|criteria|criterion|"
    r"clinical features?|symptoms?|signs?|laboratory|imaging|biopsy|"
    r"histolog(?:y|ic)|at least\s+\d+|more likely|less likely)\b",
    re.I,
)
_COMPLEX_CUE_RE = re.compile(
    r"\b(?:at least\s+\d+|\d+\s+of\s+(?:the\s+)?following|unless|except|"
    r"either|neither|distinguish(?:es|ed|ing)?|compared with|whereas|"
    r"more likely|less likely|within\s+\d+|before|after|during)\b|"
    r"(?:<=|>=|<|>|≤|≥)",
    re.I,
)
_ASSERTION_SENTENCE_CUE_RE = re.compile(
    r"\b(?:diagnos(?:is|ed|tic)|characteri[sz]ed by|suggests?|"
    r"consistent with|pathognomonic|rules? out|makes? .{0,40} unlikely|"
    r"criteria|criterion|distinguish(?:es|ed|ing)?|more likely|less likely)\b",
    re.I,
)
_BAD_TARGET_RE = re.compile(
    r"^(?:the following|diagnosis|differential diagnosis|key points?|"
    r"symptoms?(?: and signs?)?|testing|evaluation|treatment|introduction|"
    r"this type|these disorders?|the latter|it|they)$",
    re.I,
)

# These patterns are deliberately conservative.  Each match must still pass a
# disease-vocabulary check or be an explicit source entry/syndrome anchor.
_EXPLICIT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "diagnosed_by",
        re.compile(
            r"^(?P<target>[A-Z][A-Za-z0-9\u00c0-\u024f'()\- ]{2,90}?)\s+"
            r"(?:is|are)\s+diagnosed\s+(?:clinically\s+)?by\s+"
            r"(?P<feature>.+)$",
            re.I,
        ),
    ),
    (
        "characterized_by",
        re.compile(
            r"^(?P<target>[A-Z][A-Za-z0-9\u00c0-\u024f'()\- ]{2,90}?)\s+"
            r"(?:is|are)\s+characteri[sz]ed\s+by\s+(?P<feature>.+)$",
            re.I,
        ),
    ),
    (
        "diagnosis_of_based_on",
        re.compile(
            r"^Diagnosis\s+of\s+(?P<target>[A-Za-z0-9\u00c0-\u024f'()\- ]{2,90}?)\s+"
            r"(?:is|may be)\s+based\s+on\s+(?P<feature>.+)$",
            re.I,
        ),
    ),
)

_ENTRY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "diagnosis_based_on",
        re.compile(
            r"^Diagnosis\s+(?:is|may be)\s+based\s+on\s+(?P<feature>.+)$",
            re.I,
        ),
    ),
    (
        "diagnosis_requires",
        re.compile(
            r"^(?:The\s+)?diagnosis\s+(?:requires?|is established by)\s+"
            r"(?P<feature>.+)$",
            re.I,
        ),
    ),
)


def normalize_term(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = re.sub(r"[^a-z0-9\u00c0-\u024f]+", " ", text)
    return " ".join(text.split())


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def passage_metadata(passage: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten the deterministic primary provenance for extraction routing."""

    ext = dict(passage.get("extensions") or {})
    provenances = ext.get("provenances") or []
    primary = next(
        (item for item in provenances if isinstance(item, Mapping) and item.get("admitted")),
        provenances[0] if provenances and isinstance(provenances[0], Mapping) else {},
    )
    metadata = {
        key: value for key, value in ext.items()
        if key not in {"provenances", "_passage_extensions"}
    }
    if isinstance(primary, Mapping):
        metadata.update(dict(primary.get("metadata") or {}))
    for key in ("source", "source_family", "source_id"):
        if key not in metadata and isinstance(primary, Mapping) and primary.get(key) is not None:
            metadata[key] = primary[key]
    metadata.setdefault("section_path", metadata.get("section_path") or ext.get("section_path") or [])
    metadata["_passage_extensions"] = ext
    return metadata


def load_disease_aliases(path: str | Path | None) -> dict[str, str]:
    """Load the repository disease bridge without requiring its resolver.

    The flat bridge is large but is only loaded for actual extraction, not at
    import time.  Values are labels, never trusted ontology identifiers.
    """

    if path is None:
        return {}
    source = Path(path)
    if not source.exists():
        return {}
    with source.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError(f"disease alias file must contain an object: {source}")
    aliases: dict[str, str] = {}
    for key, value in payload.items():
        alias = normalize_term(str(key))
        canonical = " ".join(str(value or key).split())
        if alias and canonical:
            aliases[alias] = canonical
    return aliases


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Return exact sentence-like spans without normalizing source text."""

    if not text:
        return []
    boundaries = [0]
    boundaries.extend(match.end() for match in _SENTENCE_BOUNDARY_RE.finditer(text))
    boundaries.append(len(text))
    spans: list[tuple[int, int, str]] = []
    for start, end in zip(boundaries, boundaries[1:]):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            spans.append((start, end, text[start:end]))
    return spans


def diagnostic_passage_reasons(passage: Mapping[str, Any]) -> list[str]:
    ext = passage.get("extensions") or {}
    metadata = passage_metadata(passage)
    upstream_reasons = [
        str(value) for value in ext.get("admission_reasons", []) if value
    ]
    # Context reconstruction deliberately admits non-diagnostic neighbors (or
    # whole seed-bearing documents).  Their presence is provenance, not a
    # diagnostic signal; otherwise every treatment/reference chunk becomes an
    # LLM residual merely because it was retained to restore structure.
    reasons = [
        value for value in upstream_reasons
        if value not in {"context_closure", "document_context"}
    ]
    if ext.get("admitted") is True and not upstream_reasons:
        reasons.append("upstream_admitted")
    text = str(passage.get("text") or "")
    raw_section_path = metadata.get("section_path") or ext.get("section_path") or []
    if isinstance(raw_section_path, str):
        section_path = raw_section_path
    else:
        section_path = " > ".join(str(v) for v in raw_section_path if v)
    chunk_type = str(metadata.get("chunk_type") or ext.get("chunk_type") or "").casefold()
    if chunk_type in {"evaluation", "differential", "diagnostic", "red_flag"}:
        reasons.append(f"chunk_type:{chunk_type}")
    if re.search(
        r"diagnos|clinical features?|symptoms? and signs?|differential|"
        r"evaluation|testing|pathology|imaging|criteria|red flag",
        section_path,
        re.I,
    ):
        reasons.append("diagnostic_section")
    if _DIAGNOSTIC_CUE_RE.search(text):
        reasons.append("diagnostic_cue")
    return list(OrderedDict.fromkeys(reasons))


def residual_priority(passage: Mapping[str, Any], template_count: int = 0) -> int:
    """Priority score for LLM residual extraction, independent of gold labels."""

    text = str(passage.get("text") or "")
    score = 0
    if diagnostic_passage_reasons(passage):
        score += 2
    if _COMPLEX_CUE_RE.search(text):
        score += 3
    if re.search(r"\b(?:not diagnostic|insufficient|nonspecific|may mimic)\b", text, re.I):
        score += 2
    if template_count == 0:
        score += 1
    if len(text) > 1200:
        score += 1
    return score


def _clean_target(value: str) -> str:
    value = _WS_RE.sub(" ", (value or "").strip(" :;,."))
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.I)
    return value


def _canonical_target(
    value: str,
    *,
    aliases: Mapping[str, str],
    allowed_entry_targets: Sequence[str] = (),
) -> str | None:
    candidate = _clean_target(value)
    norm = normalize_term(candidate)
    if not norm or _BAD_TARGET_RE.fullmatch(candidate):
        return None
    canonical = aliases.get(norm)
    if canonical:
        return canonical
    allowed = {normalize_term(item): _clean_target(item) for item in allowed_entry_targets}
    return allowed.get(norm)


def _feature_type(surface: str) -> str:
    value = surface.casefold()
    if re.search(r"\b(?:ct|mri|x-?ray|ultrasound|radiograph|imaging|scan)\b", value):
        return "imaging"
    if re.search(r"\b(?:biopsy|histolog|patholog|microscop|cytolog)\w*\b", value):
        return "pathology"
    if re.search(r"\b(?:mutation|gene|genetic|karyotyp|chromosom|pcr)\w*\b", value):
        return "genetics"
    if re.search(
        r"\b(?:serum|plasma|urine|cbc|level|count|titre|titer|positive|"
        r"negative|enzyme|antibody|culture|laboratory|test)\b|[<>≤≥]",
        value,
    ):
        return "laboratory"
    if re.search(r"\b(?:history|exposure|travel|contact|drug use)\b", value):
        return "history"
    if re.search(r"\b(?:pain|fever|rash|weakness|vomit|diarrhea|cough|dyspnea)\w*\b", value):
        return "symptom"
    return "other"


def _polarity(surface: str) -> str:
    if re.search(r"\b(?:absence of|absent|without|no evidence of|negative for)\b", surface, re.I):
        return "absent"
    if re.search(r"\b(?:possible|possibly|may|might|uncertain)\b", surface, re.I):
        return "uncertain"
    return "present"


def _diagnostic_contract(template_name: str) -> tuple[str, str, str, float]:
    if template_name == "characterized_by":
        return "typical", "supports", "not_stated", 0.92
    if template_name == "diagnosis_requires":
        return "necessary", "supports", "necessary", 0.94
    if template_name in {"diagnosed_by", "diagnosis_of_based_on", "diagnosis_based_on"}:
        return "supporting", "supports", "not_stated", 0.94
    return "compatible", "supports", "not_stated", 0.80


@dataclass
class RecordAccumulator:
    """Deduplicate schema records while preserving insertion order."""

    records: OrderedDict[str, dict[str, Any]]

    def __init__(
        self,
        records: Iterable[Mapping[str, Any]] = (),
        *,
        merge_identity_metadata: bool = True,
    ) -> None:
        self.records = OrderedDict()
        self.merge_identity_metadata = merge_identity_metadata
        self._delta_trackers: list[dict[str, Any]] = []
        for record in records:
            self.add(record)

    def begin_delta(self) -> dict[str, Any]:
        """Start tracking IDs newly inserted by one atomic extraction call."""

        tracker: dict[str, Any] = {"ids": [], "seen": set()}
        self._delta_trackers.append(tracker)
        return tracker

    def delta_ids(self, tracker: Mapping[str, Any]) -> list[str]:
        """Return tracked IDs that still exist, preserving insertion order."""

        if not any(item is tracker for item in self._delta_trackers):
            raise ValueError("inactive accumulator delta tracker")
        return [
            str(record_id) for record_id in tracker["ids"]
            if record_id in self.records
        ]

    def commit_delta(self, tracker: Mapping[str, Any]) -> list[str]:
        """Stop tracking and return the committed, still-present IDs."""

        ids = self.delta_ids(tracker)
        self._delta_trackers = [
            item for item in self._delta_trackers if item is not tracker
        ]
        return ids

    def rollback_delta(self, tracker: Mapping[str, Any]) -> None:
        """Remove every record inserted since ``begin_delta`` in O(delta)."""

        if not any(item is tracker for item in self._delta_trackers):
            raise ValueError("inactive accumulator delta tracker")
        for record_id in reversed(tracker["ids"]):
            self.records.pop(record_id, None)
        self._delta_trackers = [
            item for item in self._delta_trackers if item is not tracker
        ]

    def add(self, record: Mapping[str, Any] | Any) -> dict[str, Any]:
        payload = record_to_dict(record)
        current = self.records.get(payload["id"])
        if current is not None and current != payload:
            kind = payload.get("record_type")
            if kind == current.get("record_type") == "Concept" and (
                normalize_term(str(payload.get("label") or ""))
                == normalize_term(str(current.get("label") or ""))
                and payload.get("concept_kind") == current.get("concept_kind")
                and payload.get("system") == current.get("system")
                and payload.get("code") == current.get("code")
            ):
                if not self.merge_identity_metadata:
                    return current
                # Stable identity is intentionally case/spacing insensitive.
                # Preserve alternate source spellings as synonyms instead of
                # treating them as an ID collision.
                labels = {
                    str(current.get("label") or ""),
                    str(payload.get("label") or ""),
                    *[str(v) for v in current.get("synonyms", [])],
                    *[str(v) for v in payload.get("synonyms", [])],
                }
                preferred = str(current.get("label") or payload.get("label"))
                merged = dict(current)
                merged["synonyms"] = sorted(
                    (label for label in labels if label and label != preferred),
                    key=lambda value: (normalize_term(value), value),
                )
                self.records[payload["id"]] = merged
                return merged
            if kind == current.get("record_type") == "DiagnosisExpression" and (
                payload.get("base_concept_id") == current.get("base_concept_id")
                and payload.get("qualifiers") == current.get("qualifiers")
                and payload.get("component_diagnosis_ids")
                == current.get("component_diagnosis_ids")
                and payload.get("composition_operator")
                == current.get("composition_operator")
            ):
                if not self.merge_identity_metadata:
                    return current
                merged = dict(current)
                labels = sorted({
                    str(current.get("canonical_label") or ""),
                    str(payload.get("canonical_label") or ""),
                    *[str(v) for v in (current.get("extensions") or {}).get("alternate_labels", [])],
                })
                extensions = dict(current.get("extensions") or {})
                extensions["alternate_labels"] = [
                    label for label in labels
                    if label and label != current.get("canonical_label")
                ]
                merged["extensions"] = extensions
                self.records[payload["id"]] = merged
                return merged
            raise ValueError(f"stable-ID collision for {payload['id']}")
        if current is None:
            for tracker in self._delta_trackers:
                if payload["id"] not in tracker["seen"]:
                    tracker["seen"].add(payload["id"])
                    tracker["ids"].append(payload["id"])
        self.records[payload["id"]] = payload
        return payload

    def values(self) -> list[dict[str, Any]]:
        return list(self.records.values())


def _add_assertion(
    accumulator: RecordAccumulator,
    *,
    passage: Mapping[str, Any],
    quote_start: int,
    quote_end: int,
    target_label: str,
    feature_surface: str,
    feature_type: str,
    polarity: str,
    diagnostic_role: str,
    direction: str,
    necessity: str,
    assertion_confidence: float,
    extraction_confidence: float,
    activity_id: str,
    qualifiers: Mapping[str, Any],
    logic_components: Sequence[Mapping[str, Any]] = (),
    logic_operator: str | None = None,
    logic_k: int | None = None,
    target_qualifiers: Mapping[str, Any] | None = None,
) -> str:
    target_concept = accumulator.add(Concept(target_label, "disease"))
    diagnosis = accumulator.add(DiagnosisExpression(
        canonical_label=target_label,
        base_concept_id=target_concept["id"],
        qualifiers=dict(target_qualifiers or {}),
    ))
    surface = _WS_RE.sub(" ", feature_surface.strip(" ;,."))
    criterion_id: str
    if logic_components:
        operands: list[str] = []
        for component in logic_components:
            component_surface = _WS_RE.sub(
                " ", str(component["feature_surface"]).strip(" ;,.")
            )
            feature = accumulator.add(FeaturePattern(
                canonical_label=component_surface,
                feature_type=str(component["feature_type"]),
                polarity=str(component["polarity"]),
                surface=component_surface,
                temporality={"relation": "not_stated"},
                qualifiers={"normalization_status": "unresolved_surface"},
            ))
            operands.append(str(feature["id"]))
        logic = accumulator.add(LogicExpression(
            operator=str(logic_operator),
            operand_ids=tuple(operands),
            k=logic_k,
            label=surface,
        ))
        criterion_id = str(logic["id"])
    else:
        feature = accumulator.add(FeaturePattern(
            canonical_label=surface,
            feature_type=feature_type,
            polarity=polarity,
            surface=surface,
            temporality={"relation": "not_stated"},
            qualifiers={"normalization_status": "unresolved_surface"},
        ))
        criterion_id = str(feature["id"])
    quote = str(passage["text"])[quote_start:quote_end]
    span = accumulator.add(EvidenceSpan(
        passage_id=str(passage["id"]),
        start_char=quote_start,
        end_char=quote_end,
        quote=quote,
        extensions={"quote_sha256": sha256_text(quote)},
    ))
    assertion = accumulator.add(DiagnosticAssertion(
        diagnosis_id=diagnosis["id"],
        criterion_id=criterion_id,
        diagnostic_role=diagnostic_role,
        direction=direction,
        necessity=necessity,
        evidence_span_ids=(span["id"],),
        assertion_confidence=assertion_confidence,
        extraction_confidence=extraction_confidence,
        extraction_activity_id=activity_id,
        qualifiers=dict(qualifiers),
    ))
    return str(assertion["id"])


def _add_differential_assertion(
    accumulator: RecordAccumulator,
    *,
    passage: Mapping[str, Any],
    quote_start: int,
    quote_end: int,
    diagnosis_a_label: str,
    diagnosis_b_label: str,
    feature_surface: str,
    feature_type: str,
    polarity: str,
    favors: str,
    assertion_confidence: float,
    extraction_confidence: float,
    activity_id: str,
    qualifiers: Mapping[str, Any],
) -> str:
    diagnosis_ids: list[str] = []
    for label in (diagnosis_a_label, diagnosis_b_label):
        concept = accumulator.add(Concept(label, "disease"))
        expression = accumulator.add(DiagnosisExpression(
            canonical_label=label, base_concept_id=concept["id"],
        ))
        diagnosis_ids.append(str(expression["id"]))
    surface = _WS_RE.sub(" ", feature_surface.strip(" ;,."))
    feature = accumulator.add(FeaturePattern(
        canonical_label=surface,
        feature_type=feature_type,
        polarity=polarity,
        surface=surface,
        temporality={"relation": "not_stated"},
        qualifiers={"normalization_status": "unresolved_surface"},
    ))
    quote = str(passage["text"])[quote_start:quote_end]
    span = accumulator.add(EvidenceSpan(
        passage_id=str(passage["id"]), start_char=quote_start,
        end_char=quote_end, quote=quote,
        extensions={"quote_sha256": sha256_text(quote)},
    ))
    assertion = accumulator.add(DifferentialAssertion(
        diagnosis_a_id=diagnosis_ids[0], diagnosis_b_id=diagnosis_ids[1],
        discriminator_id=feature["id"], favors=favors,
        evidence_span_ids=(span["id"],),
        assertion_confidence=assertion_confidence,
        extraction_confidence=extraction_confidence,
        extraction_activity_id=activity_id,
        qualifiers=dict(qualifiers),
    ))
    return str(assertion["id"])


def extract_template_assertions(
    passage: Mapping[str, Any],
    *,
    aliases: Mapping[str, str],
    activity_id: str,
    accumulator: RecordAccumulator,
) -> list[str]:
    """Extract conservative, exact-span assertions from one passage."""

    text = str(passage.get("text") or "")
    ext = passage_metadata(passage)
    entry_targets = [
        str(value) for value in (
            ext.get("entry_title"), ext.get("syndrome_anchor"), ext.get("title_root")
        ) if value
    ]
    accepted_ids: list[str] = []
    for start, end, sentence in sentence_spans(text):
        normalized_sentence = _WS_RE.sub(" ", sentence).strip()
        terminal = normalized_sentence.rstrip(". ")
        found: tuple[str, re.Match[str], str] | None = None
        for template_name, pattern in _EXPLICIT_PATTERNS:
            match = pattern.match(terminal)
            if match:
                target = _canonical_target(
                    match.group("target"), aliases=aliases,
                    allowed_entry_targets=entry_targets,
                )
                if target:
                    found = (template_name, match, target)
                    break
        if found is None:
            for template_name, pattern in _ENTRY_PATTERNS:
                match = pattern.match(terminal)
                if not match:
                    continue
                target = next((
                    canonical for raw in entry_targets
                    if (canonical := _canonical_target(
                        raw, aliases=aliases, allowed_entry_targets=entry_targets,
                    ))
                ), None)
                if target:
                    found = (template_name, match, target)
                    break
        if found is None:
            continue
        template_name, match, target = found
        feature = match.group("feature").strip(" .")
        if len(feature) < 4 or len(feature) > 800:
            continue
        role, direction, necessity, confidence = _diagnostic_contract(template_name)
        accepted_ids.append(_add_assertion(
            accumulator,
            passage=passage,
            quote_start=start,
            quote_end=end,
            target_label=target,
            feature_surface=feature,
            feature_type=_feature_type(feature),
            polarity=_polarity(feature),
            diagnostic_role=role,
            direction=direction,
            necessity=necessity,
            assertion_confidence=confidence,
            extraction_confidence=0.96,
            activity_id=activity_id,
            qualifiers={
                "extraction_lane": "template",
                "template_name": template_name,
                "logic_status": (
                    "requires_residual_review"
                    if _COMPLEX_CUE_RE.search(feature) else "atomic_surface"
                ),
            },
        ))
    return accepted_ids


def extract_wikem_differential_memberships(
    passage: Mapping[str, Any],
    *,
    aliases: Mapping[str, str],
    activity_id: str,
    accumulator: RecordAccumulator,
) -> list[str]:
    """Compile WikEM link lists as candidate-membership, never as criteria."""

    ext = passage_metadata(passage)
    if str(ext.get("source") or "").casefold() != "wikem":
        return []
    if str(ext.get("chunk_type") or "").casefold() != "differential":
        return []
    anchor = _clean_target(str(ext.get("syndrome_anchor") or ext.get("title_root") or ""))
    links = [str(value) for value in ext.get("wiki_links", []) if value]
    if not anchor or not links:
        return []
    text = str(passage.get("text") or "")
    if not text:
        return []
    span_start, span_end = 0, len(text)
    accepted: list[str] = []
    for link in links:
        target = _canonical_target(link, aliases=aliases, allowed_entry_targets=(link,))
        if not target or normalize_term(target) == normalize_term(anchor):
            continue
        accepted.append(_add_assertion(
            accumulator,
            passage=passage,
            quote_start=span_start,
            quote_end=span_end,
            target_label=target,
            feature_surface=f"presentation: {anchor}",
            feature_type="other",
            polarity="present",
            diagnostic_role="compatible",
            direction="supports",
            necessity="not_stated",
            assertion_confidence=0.55,
            extraction_confidence=0.99,
            activity_id=activity_id,
            qualifiers={
                "extraction_lane": "structural_wikem",
                "relation": "listed_differential_for",
                "syndrome_anchor": anchor,
                "enumeration_only": True,
                "ranking_eligible": False,
            },
        ))
    return accepted


def llm_candidate_inventory(
    passage: Mapping[str, Any],
    aliases: Mapping[str, str],
    *,
    max_candidates: int = 40,
) -> list[dict[str, str]]:
    """Return a closed diagnosis candidate inventory for one residual call."""

    text = str(passage.get("text") or "")
    ext = passage_metadata(passage)
    labels: OrderedDict[str, str] = OrderedDict()
    for value in (
        ext.get("entry_title"), ext.get("syndrome_anchor"), ext.get("title_root")
    ):
        if value:
            norm = normalize_term(str(value))
            canonical = aliases.get(norm, _clean_target(str(value)))
            if canonical and not _BAD_TARGET_RE.fullmatch(canonical):
                labels.setdefault(normalize_term(canonical), canonical)
    for value in ext.get("wiki_links", []) or []:
        norm = normalize_term(str(value))
        canonical = aliases.get(norm, _clean_target(str(value)))
        if canonical:
            labels.setdefault(normalize_term(canonical), canonical)

    # Exact phrase discovery is performed by bounded text n-grams instead of
    # scanning the entire 700k-entry alias table for every passage.  One-token
    # matches are excluded to avoid the prior parent/component merge defect.
    words = normalize_term(text).split()
    for acronym in re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9-]{1,9}(?![A-Za-z0-9])", text):
        canonical = aliases.get(normalize_term(acronym))
        if canonical:
            labels.setdefault(normalize_term(canonical), canonical)
    seen_ngrams: set[str] = set()
    for width in range(8, 1, -1):
        for start in range(max(0, len(words) - width + 1)):
            alias = " ".join(words[start:start + width])
            if alias in seen_ngrams:
                continue
            seen_ngrams.add(alias)
            canonical = aliases.get(alias)
            if canonical:
                labels.setdefault(normalize_term(canonical), canonical)
                if len(labels) >= max_candidates:
                    return [
                        {"candidate_id": f"dx{index:03d}", "label": label}
                        for index, label in enumerate(labels.values(), start=1)
                    ][:max_candidates]
    return [
        {"candidate_id": f"dx{index:03d}", "label": label}
        for index, label in enumerate(labels.values(), start=1)
    ][:max_candidates]


def evidence_sentence_inventory(
    passage: Mapping[str, Any], *, max_sentences: int | None = 80,
) -> list[dict[str, Any]]:
    spans = sentence_spans(str(passage.get("text") or ""))
    if max_sentences is not None and len(spans) > max_sentences:
        raise ValueError(
            f"passage has {len(spans)} sentence spans; refusing silent "
            f"truncation at {max_sentences}"
        )
    return [
        {
            "mention_id": f"s{index:03d}",
            "start_char": start,
            "end_char": end,
            "text": sentence,
        }
        for index, (start, end, sentence) in enumerate(spans, start=1)
    ]


def convert_validated_llm_slots(
    passage: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]],
    *,
    candidate_inventory: Sequence[Mapping[str, str]],
    evidence_inventory: Sequence[Mapping[str, Any]],
    activity_id: str,
    accumulator: RecordAccumulator,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Validate LLM slots against closed inventories and compile KG records."""

    candidates = {str(item["candidate_id"]): str(item["label"]) for item in candidate_inventory}
    evidence = {str(item["mention_id"]): item for item in evidence_inventory}
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    allowed_roles = {
        "defining", "necessary", "sufficient", "supporting", "typical",
        "compatible", "argues_against", "excluding", "risk_factor",
    }
    allowed_directions = {"supports", "argues_against", "neutral"}
    allowed_necessities = {"necessary", "sufficient", "optional", "not_stated"}
    allowed_polarities = {"present", "absent", "uncertain"}
    allowed_feature_types = {
        "symptom", "sign", "laboratory", "imaging", "pathology", "genetics",
        "procedure", "history", "demographic", "exposure", "medication",
        "course", "other",
    }
    for position, slot in enumerate(slots):
        errors: list[str] = []
        candidate_id = str(slot.get("target_candidate_id") or "")
        mention_id = str(slot.get("evidence_mention_id") or "")
        target = candidates.get(candidate_id)
        mention = evidence.get(mention_id)
        feature_surface = str(slot.get("feature_surface") or "").strip()
        target_qualifiers: dict[str, Any] = {}
        if not target and candidate_id == "UNRESOLVED":
            unresolved = str(slot.get("target_surface") or "").strip()
            if mention and unresolved and unresolved in str(mention["text"]) and re.search(
                rf"(?:Diagnosis\s+of\s+{re.escape(unresolved)}|"
                rf"{re.escape(unresolved)}\s+(?:is|are)\s+(?:diagnosed|characteri[sz]ed)|"
                rf"diagnostic\s+(?:of|for)\s+{re.escape(unresolved)})",
                str(mention["text"]), re.I,
            ):
                target = unresolved
                target_qualifiers = {
                    "ontology_mapping_status": "unresolved_exact_source_mention"
                }
            else:
                errors.append("unsafe_unresolved_target")
        elif not target:
            errors.append("target_candidate_id_not_in_inventory")
        if not mention:
            errors.append("evidence_mention_id_not_in_inventory")
        offset_repaired = False
        try:
            feature_start = int(slot.get("feature_start_char"))
            feature_end = int(slot.get("feature_end_char"))
        except (TypeError, ValueError):
            feature_start = feature_end = -1
        if mention:
            valid_offsets = (
                int(mention["start_char"]) <= feature_start < feature_end
                <= int(mention["end_char"])
                and str(passage.get("text") or "")[feature_start:feature_end]
                == feature_surface
            )
            if not valid_offsets:
                evidence_text = str(mention["text"])
                positions = [
                    match.start() for match in re.finditer(
                        re.escape(feature_surface), evidence_text,
                    )
                ] if feature_surface else []
                if len(positions) == 1:
                    feature_start = int(mention["start_char"]) + positions[0]
                    feature_end = feature_start + len(feature_surface)
                    offset_repaired = True
                else:
                    errors.append("feature_offset_not_uniquely_repairable")
        role = str(slot.get("diagnostic_role") or "")
        direction = str(slot.get("direction") or "")
        necessity = str(slot.get("necessity") or "")
        polarity = str(slot.get("polarity") or "")
        feature_type = str(slot.get("feature_type") or "")
        if role not in allowed_roles:
            errors.append("invalid_diagnostic_role")
        if direction not in allowed_directions:
            errors.append("invalid_direction")
        if necessity not in allowed_necessities:
            errors.append("invalid_necessity")
        if polarity not in allowed_polarities:
            errors.append("invalid_polarity")
        if feature_type not in allowed_feature_types:
            errors.append("invalid_feature_type")
        if role in {"argues_against", "excluding"} and direction != "argues_against":
            errors.append("role_direction_conflict")
        if role in {
            "defining", "necessary", "sufficient", "supporting", "typical",
            "compatible", "risk_factor",
        } and direction != "supports":
            errors.append("role_direction_conflict")
        try:
            confidence = float(slot.get("confidence"))
            if not 0 <= confidence <= 1:
                raise ValueError
        except (TypeError, ValueError):
            confidence = 0.0
            errors.append("invalid_confidence")
        logic_operator = str(slot.get("logic_operator") or "atomic")
        component_slots = slot.get("feature_components") or []
        logic_components: list[dict[str, Any]] = []
        logic_k: int | None = None
        if logic_operator == "atomic":
            # Some schema-constrained models populate a required array with a
            # redundant copy of the atomic feature.  It has no semantic effect
            # and is ignored; the top-level exact span remains authoritative.
            component_slots = []
        elif logic_operator in {"and", "or", "sequence", "k_of_n"}:
            if not isinstance(component_slots, list) or len(component_slots) < 2:
                errors.append("logic_requires_two_or_more_components")
            else:
                seen_component_offsets: set[tuple[int, int]] = set()
                for component_index, component in enumerate(component_slots):
                    if not isinstance(component, Mapping):
                        errors.append(f"component_{component_index}_not_object")
                        continue
                    component_surface = str(component.get("feature_surface") or "").strip()
                    component_type = str(component.get("feature_type") or "")
                    component_polarity = str(component.get("polarity") or "")
                    try:
                        component_start = int(component.get("feature_start_char"))
                        component_end = int(component.get("feature_end_char"))
                    except (TypeError, ValueError):
                        errors.append(f"component_{component_index}_offsets_required")
                        continue
                    if (component_start, component_end) in seen_component_offsets:
                        errors.append("duplicate_logic_component")
                    seen_component_offsets.add((component_start, component_end))
                    if not mention or not (
                        int(mention["start_char"]) <= component_start < component_end
                        <= int(mention["end_char"])
                    ) or str(passage.get("text") or "")[component_start:component_end] != component_surface:
                        evidence_text = str(mention["text"]) if mention else ""
                        positions = [
                            match.start() for match in re.finditer(
                                re.escape(component_surface), evidence_text,
                            )
                        ] if component_surface else []
                        if len(positions) == 1 and mention:
                            component_start = int(mention["start_char"]) + positions[0]
                            component_end = component_start + len(component_surface)
                            offset_repaired = True
                        else:
                            errors.append(
                                f"component_{component_index}_offset_not_uniquely_repairable"
                            )
                    if component_type not in allowed_feature_types:
                        errors.append(f"component_{component_index}_feature_type")
                    if component_polarity not in allowed_polarities:
                        errors.append(f"component_{component_index}_polarity")
                    logic_components.append({
                        "feature_surface": component_surface,
                        "feature_type": component_type,
                        "polarity": component_polarity,
                    })
            if logic_operator == "k_of_n":
                try:
                    logic_k = int(slot.get("k"))
                    if not 1 <= logic_k <= len(logic_components):
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append("invalid_k_of_n")
        else:
            errors.append("invalid_logic_operator")

        assertion_type = str(slot.get("assertion_type") or "diagnostic")
        if assertion_type not in {"diagnostic", "differential"}:
            errors.append("invalid_assertion_type")
        diagnosis_a = diagnosis_b = None
        favors = str(slot.get("favors") or "")
        if assertion_type == "differential":
            diagnosis_a = candidates.get(str(slot.get("diagnosis_a_candidate_id") or ""))
            diagnosis_b = candidates.get(str(slot.get("diagnosis_b_candidate_id") or ""))
            if not diagnosis_a or not diagnosis_b or diagnosis_a == diagnosis_b:
                errors.append("invalid_differential_pair")
            if favors not in {"a", "b", "neither", "context_dependent"}:
                errors.append("invalid_favors")
            if logic_operator != "atomic":
                errors.append("differential_logic_not_yet_supported")

        evidence_text = str(mention.get("text") or "") if mention else ""
        section_text = str(passage_metadata(passage).get("section_path") or "")
        if assertion_type == "diagnostic" and not (
            _ASSERTION_SENTENCE_CUE_RE.search(evidence_text)
            or re.search(
                r"clinical features?|symptoms?(?: and signs?)?|diagnos|criteria",
                section_text,
                re.I,
            )
        ):
            errors.append("no_explicit_diagnostic_context")
        if normalize_term(feature_surface) in {
            normalize_term(label) for label in candidates.values()
        }:
            errors.append("feature_is_diagnosis_surface")
        if re.fullmatch(
            r"(?:the\s+)?diagnosis\s+is\s+clinical\.?",
            feature_surface,
            re.I,
        ):
            errors.append("generic_non_actionable_criterion")

        if errors:
            rejected.append({"slot_index": position, "errors": errors})
            continue
        assert target is not None and mention is not None
        if assertion_type == "differential":
            assert diagnosis_a is not None and diagnosis_b is not None
            accepted.append(_add_differential_assertion(
                accumulator,
                passage=passage,
                quote_start=int(mention["start_char"]),
                quote_end=int(mention["end_char"]),
                diagnosis_a_label=diagnosis_a,
                diagnosis_b_label=diagnosis_b,
                feature_surface=feature_surface,
                feature_type=feature_type,
                polarity=polarity,
                favors=favors,
                assertion_confidence=confidence,
                extraction_confidence=0.90,
                activity_id=activity_id,
                qualifiers={
                    "extraction_lane": "llm_residual",
                    "scope_note": str(slot.get("scope_note") or ""),
                    "citation_bounded": True,
                    "offset_repaired_by_unique_exact_match": offset_repaired,
                },
            ))
        else:
            accepted.append(_add_assertion(
                accumulator,
                passage=passage,
                quote_start=int(mention["start_char"]),
                quote_end=int(mention["end_char"]),
                target_label=target,
                feature_surface=feature_surface,
                feature_type=feature_type,
                polarity=polarity,
                diagnostic_role=role,
                direction=direction,
                necessity=necessity,
                assertion_confidence=confidence,
                extraction_confidence=0.90,
                activity_id=activity_id,
                target_qualifiers=target_qualifiers,
                logic_components=logic_components,
                logic_operator=None if logic_operator == "atomic" else logic_operator,
                logic_k=logic_k,
                qualifiers={
                    "extraction_lane": "llm_residual",
                    "logic_operator": logic_operator,
                    "scope_note": str(slot.get("scope_note") or ""),
                    "citation_bounded": True,
                    "offset_repaired_by_unique_exact_match": offset_repaired,
                },
            ))
    return accepted, rejected


def template_activity(input_sha256: str) -> ExtractionActivity:
    return ExtractionActivity(
        pipeline_name=PIPELINE_NAME,
        pipeline_version=PIPELINE_VERSION,
        extractor_type="template",
        input_sha256=input_sha256,
        parameters={
            "disease_target_policy": "closed_alias_or_source_entry",
            "wikem_enumeration_ranking_eligible": False,
        },
    )


__all__ = [
    "PIPELINE_NAME",
    "PIPELINE_VERSION",
    "RecordAccumulator",
    "convert_validated_llm_slots",
    "diagnostic_passage_reasons",
    "evidence_sentence_inventory",
    "extract_template_assertions",
    "extract_wikem_differential_memberships",
    "llm_candidate_inventory",
    "load_disease_aliases",
    "normalize_term",
    "passage_metadata",
    "residual_priority",
    "sentence_spans",
    "sha256_text",
    "template_activity",
]
