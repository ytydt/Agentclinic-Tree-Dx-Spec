#!/usr/bin/env python3
"""Export fail-closed, non-ranking views from the frozen guideline-KG ledger.

This exporter implements the two mechanical rules frozen by
``GUIDELINE_KG_BASE_GRAPH_QUALITY_AUDIT.md``.  It does not repair or validate
clinical meaning.  It only exposes:

* a very small template-core *candidate* view; and
* a separate WikEM differential-membership view.

Everything else is sent to a source-free quarantine ledger.  Public outputs
contain record IDs, hashes, offsets, lengths and provenance IDs, but never
``Passage.text``, ``EvidenceSpan.quote`` or ``FeaturePattern.surface``.

The default count contract is deliberately frozen to the audited base graph.
Any drift aborts before publishing output.  This prevents a later extractor
change from silently broadening the view.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("/tmp/gkg-build-all-clean-v2/graph.internal.jsonl")
DEFAULT_OUTPUT = (
    ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/safe_views"
)

RULE_ID = "guideline_kg_base_graph_quality_audit.mechanical_safe_export.v0.1"
PUBLIC_SCHEMA = "guideline_kg_safe_pointer.v0.1"
EXPECTED_TEMPLATE_CORE = 5
EXPECTED_WIKEM_MEMBERSHIP = 2521
EXPECTED_QUARANTINE = 1043

_SAFE_TEMPLATE_NAMES = {
    "characterized_by",
    "diagnosed_by",
    "diagnosis_of_based_on",
}
_SAFE_FEATURE_TYPES = {
    "symptom",
    "sign",
    "laboratory",
    "imaging",
    "pathology",
    "genetics",
    "history",
    "procedure",
}
_GENERIC_OR_PRONOMINAL_TARGETS = {
    "this disease",
    "the disease",
    "this disorder",
    "the disorder",
    "this condition",
    "the condition",
    "this syndrome",
    "the syndrome",
    "these disorders",
    "these conditions",
    "the diagnosis",
}
_PRONOMINAL_FIRST_TOKENS = {
    "it",
    "its",
    "they",
    "their",
    "this",
    "that",
    "these",
    "those",
}
_BIBLIOGRAPHY_RE = re.compile(r"PubMed|Google Scholar|DOI", re.IGNORECASE)
_NAVIGATION_SECTION_RE = re.compile(
    r"\b(?:algorithms?|index|contents)\b", re.IGNORECASE
)


class CountContractError(RuntimeError):
    """Raised before output when the frozen export population has drifted."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def norm(value: Any) -> str:
    """Apply the audit's exact terminology normalization rule."""

    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected JSON object")
            record_id = row.get("id")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError(f"{path}:{line_number}: missing record id")
            if record_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate record id {record_id}")
            seen.add(record_id)
            rows.append(row)
    return rows


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    temporary = path.with_name(path.name + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ))
            handle.write("\n")
            count += 1
    os.replace(temporary, path)
    return count


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def _ref(
    index: Mapping[str, Mapping[str, Any]],
    record_id: Any,
    expected_type: str,
) -> Mapping[str, Any] | None:
    if not isinstance(record_id, str):
        return None
    row = index.get(record_id)
    if row is None or row.get("record_type") != expected_type:
        return None
    return row


def _assertion_context(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> tuple[
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
    list[tuple[
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
    ]],
]:
    diagnosis = _ref(index, assertion.get("diagnosis_id"), "DiagnosisExpression")
    criterion_id = assertion.get("criterion_id")
    criterion = index.get(criterion_id) if isinstance(criterion_id, str) else None
    spans: list[tuple[
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
        Mapping[str, Any] | None,
    ]] = []
    evidence_ids = assertion.get("evidence_span_ids")
    if not isinstance(evidence_ids, list) or not evidence_ids:
        spans.append((None, None, None, None, None))
        return diagnosis, criterion, spans
    for span_id in evidence_ids:
        span = _ref(index, span_id, "EvidenceSpan")
        passage = (
            _ref(index, span.get("passage_id"), "Passage") if span else None
        )
        section = (
            _ref(index, passage.get("section_id"), "Section")
            if passage else None
        )
        document = (
            _ref(index, section.get("document_version_id"), "DocumentVersion")
            if section else None
        )
        work = (
            _ref(index, document.get("source_work_id"), "SourceWork")
            if document else None
        )
        spans.append((span, passage, section, document, work))
    return diagnosis, criterion, spans


def _exact_quote(
    span: Mapping[str, Any] | None,
    passage: Mapping[str, Any] | None,
) -> bool:
    if span is None or passage is None:
        return False
    start, end = span.get("start_char"), span.get("end_char")
    quote, text = span.get("quote"), passage.get("text")
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or not isinstance(quote, str)
        or not isinstance(text, str)
        or start < 0
        or end <= start
        or end > len(text)
    ):
        return False
    return text[start:end] == quote


def _generic_or_pronominal_target(target: str) -> bool:
    tokens = target.split()
    return (
        target in _GENERIC_OR_PRONOMINAL_TARGETS
        or not tokens
        or tokens[0] in _PRONOMINAL_FIRST_TOKENS
    )


def _common_reference_reasons(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
    diagnosis: Mapping[str, Any] | None,
) -> list[str]:
    """Fail closed on direct or identity-bearing references not in a lane rule."""

    reasons: list[str] = []
    if _ref(
        index, assertion.get("extraction_activity_id"), "ExtractionActivity"
    ) is None:
        reasons.append("reference.extraction_activity_missing_or_wrong_type")
    population_ids = assertion.get("population_context_ids", [])
    if not isinstance(population_ids, list):
        reasons.append("reference.population_context_ids_not_list")
    elif any(_ref(index, item, "Concept") is None for item in population_ids):
        reasons.append("reference.population_context_missing_or_wrong_type")
    if diagnosis is not None:
        base_id = diagnosis.get("base_concept_id")
        components = diagnosis.get("component_diagnosis_ids") or []
        if base_id is not None and _ref(index, base_id, "Concept") is None:
            reasons.append("reference.base_concept_missing_or_wrong_type")
        if not isinstance(components, list):
            reasons.append("reference.component_diagnosis_ids_not_list")
        elif any(
            _ref(index, item, "DiagnosisExpression") is None for item in components
        ):
            reasons.append("reference.component_diagnosis_missing_or_wrong_type")
    return reasons


def _template_prefixes(target: str) -> tuple[str, ...]:
    return (
        f"{target} is characterized by",
        f"{target} are characterized by",
        f"{target} is characterised by",
        f"{target} are characterised by",
        f"{target} is diagnosed by",
        f"{target} are diagnosed by",
        f"diagnosis of {target} is based on",
    )


def template_rejection_reasons(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return every fail-closed reason under audit rule A."""

    reasons: list[str] = []
    qualifiers = assertion.get("qualifiers")
    qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
    if qualifiers.get("extraction_lane") != "template":
        reasons.append("template.extraction_lane_mismatch")
    if qualifiers.get("template_name") not in _SAFE_TEMPLATE_NAMES:
        reasons.append("template.template_name_not_allowed")
    if qualifiers.get("logic_status") != "atomic_surface":
        reasons.append("template.logic_status_not_atomic_surface")
    if qualifiers.get("ranking_eligible") is True:
        reasons.append("safety.input_ranking_eligible_true")
    if assertion.get("review_status") != "unreviewed":
        reasons.append("safety.review_status_not_unreviewed")

    diagnosis, criterion, span_contexts = _assertion_context(assertion, index)
    if diagnosis is None:
        reasons.append("reference.diagnosis_missing_or_wrong_type")
        target = ""
    else:
        target = norm(diagnosis.get("canonical_label"))
        token_count = len(target.split())
        if not 2 <= token_count <= 10:
            reasons.append("template.target_token_count_out_of_range")
        if _generic_or_pronominal_target(target):
            reasons.append("template.target_generic_or_pronominal")
    reasons.extend(_common_reference_reasons(assertion, index, diagnosis))

    if criterion is None or criterion.get("record_type") != "FeaturePattern":
        reasons.append("reference.criterion_missing_or_wrong_type")
    elif criterion.get("feature_type") not in _SAFE_FEATURE_TYPES:
        reasons.append("template.feature_type_not_allowed")

    for span, passage, section, document, work in span_contexts:
        if None in (span, passage, section, document, work):
            reasons.append("reference.evidence_lineage_incomplete")
            continue
        if not _exact_quote(span, passage):
            reasons.append("evidence.quote_not_exact")
            continue
        quote = norm(span.get("quote"))
        if not target or not any(
            quote.startswith(prefix) for prefix in _template_prefixes(target)
        ):
            reasons.append("template.target_prefix_mismatch")
        start = int(span["start_char"])
        preceding = str(passage["text"])[max(0, start - 500):start]
        if _BIBLIOGRAPHY_RE.search(preceding):
            reasons.append("template.bibliography_cue_preceding_span")

    if assertion.get("direction") != "supports":
        reasons.append("template.direction_not_supports")
    if assertion.get("diagnostic_role") not in {"typical", "supporting"}:
        reasons.append("template.role_not_typical_or_supporting")
    if assertion.get("necessity") != "not_stated":
        reasons.append("template.necessity_not_stated")
    return sorted(set(reasons))


def _raw_wiki_links(passage: Mapping[str, Any]) -> list[str]:
    links: list[str] = []
    extensions = passage.get("extensions")
    extensions = extensions if isinstance(extensions, Mapping) else {}
    provenances = extensions.get("provenances")
    if not isinstance(provenances, list):
        return links
    for provenance in provenances:
        if not isinstance(provenance, Mapping):
            continue
        metadata = provenance.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        values = metadata.get("wiki_links")
        if not isinstance(values, list):
            continue
        links.extend(str(value) for value in values if isinstance(value, str))
    return links


def wikem_rejection_reasons(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return every fail-closed reason under audit rule B."""

    reasons: list[str] = []
    qualifiers = assertion.get("qualifiers")
    qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
    contract = {
        "extraction_lane": "structural_wikem",
        "relation": "listed_differential_for",
        "enumeration_only": True,
        "ranking_eligible": False,
    }
    for key, expected in contract.items():
        if qualifiers.get(key) != expected:
            reasons.append(f"membership.qualifier_contract_mismatch:{key}")
    if assertion.get("review_status") != "unreviewed":
        reasons.append("safety.review_status_not_unreviewed")

    diagnosis, criterion, span_contexts = _assertion_context(assertion, index)
    if diagnosis is None:
        reasons.append("reference.diagnosis_missing_or_wrong_type")
        target = ""
    else:
        target = norm(diagnosis.get("canonical_label"))
    reasons.extend(_common_reference_reasons(assertion, index, diagnosis))
    if criterion is None or criterion.get("record_type") != "FeaturePattern":
        reasons.append("reference.criterion_missing_or_wrong_type")

    for span, passage, section, document, work in span_contexts:
        if None in (span, passage, section, document, work):
            reasons.append("reference.evidence_lineage_incomplete")
            continue
        if not _exact_quote(span, passage):
            reasons.append("evidence.quote_not_exact")
        raw_links = {norm(item) for item in _raw_wiki_links(passage)}
        if not target or target not in raw_links:
            reasons.append("membership.target_not_exact_raw_wiki_link")
        section_path = section.get("section_path")
        flattened = " ".join(section_path) if isinstance(section_path, list) else ""
        if _NAVIGATION_SECTION_RE.search(flattened):
            reasons.append("membership.navigation_section")
    return sorted(set(reasons))


def _lineage_pointer(
    span: Mapping[str, Any] | None,
    passage: Mapping[str, Any] | None,
    section: Mapping[str, Any] | None,
    document: Mapping[str, Any] | None,
    work: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build a source-free, exact-locator pointer for one evidence span."""

    quote = span.get("quote") if span else None
    text = passage.get("text") if passage else None
    passage_extensions = passage.get("extensions") if passage else None
    passage_extensions = (
        passage_extensions if isinstance(passage_extensions, Mapping) else {}
    )
    sources: list[dict[str, Any]] = []
    provenances = passage_extensions.get("provenances")
    if isinstance(provenances, list):
        for provenance in provenances:
            if not isinstance(provenance, Mapping):
                continue
            sources.append({
                "document_version_id": provenance.get("document_version_id"),
                "raw_chunk_ordinal": provenance.get("raw_chunk_ordinal"),
                "raw_id": provenance.get("raw_id"),
                "source": provenance.get("source"),
                "source_family": provenance.get("source_family"),
                "source_id": provenance.get("source_id"),
                "source_ordinal": provenance.get("source_ordinal"),
                "source_work_id": provenance.get("source_work_id"),
            })
    sources.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
    section_path = section.get("section_path") if section else None
    section_path_payload = section_path if isinstance(section_path, list) else []
    return {
        "document_version_id": document.get("id") if document else None,
        "end_char": span.get("end_char") if span else None,
        "evidence_span_id": span.get("id") if span else None,
        "passage_id": passage.get("id") if passage else None,
        "passage_text_chars": len(text) if isinstance(text, str) else None,
        "passage_text_sha256": (
            sha256_text(text) if isinstance(text, str) else None
        ),
        "quote_chars": len(quote) if isinstance(quote, str) else None,
        "quote_sha256": sha256_text(quote) if isinstance(quote, str) else None,
        "section_id": section.get("id") if section else None,
        "section_path_sha256": sha256_text(
            json.dumps(section_path_payload, ensure_ascii=False, separators=(",", ":"))
        ),
        "source_occurrences": sources,
        "source_work_id": work.get("id") if work else None,
        "start_char": span.get("start_char") if span else None,
    }


def _evidence_pointers(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    _, _, contexts = _assertion_context(assertion, index)
    return [_lineage_pointer(*context) for context in contexts]


def _safe_pointer(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
    *,
    release_view: str,
) -> dict[str, Any]:
    qualifiers = assertion.get("qualifiers")
    qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
    row = {
        "assertion_confidence": assertion.get("assertion_confidence"),
        "criterion_id": assertion.get("criterion_id"),
        "diagnosis_id": assertion.get("diagnosis_id"),
        "diagnostic_role": assertion.get("diagnostic_role"),
        "direction": assertion.get("direction"),
        "evidence_pointers": _evidence_pointers(assertion, index),
        "extraction_activity_id": assertion.get("extraction_activity_id"),
        "extraction_confidence": assertion.get("extraction_confidence"),
        "necessity": assertion.get("necessity"),
        "ranking_eligible": False,
        "record_type": "SafeAssertionPointer",
        "release_view": release_view,
        "review_status": "unreviewed",
        "schema": PUBLIC_SCHEMA,
        "source_assertion_id": assertion.get("id"),
    }
    if release_view == "template_core_candidate":
        row["logic_status"] = qualifiers.get("logic_status")
        row["template_name"] = qualifiers.get("template_name")
    else:
        row.update({
            "enumeration_only": True,
            "relation": "listed_differential_for",
            "synthetic_feature_is_diagnostic": False,
        })
    return row


def _quarantine_pointer(
    assertion: Mapping[str, Any],
    index: Mapping[str, Mapping[str, Any]],
    reasons: Sequence[str],
) -> dict[str, Any]:
    qualifiers = assertion.get("qualifiers")
    qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
    return {
        "criterion_id": assertion.get("criterion_id"),
        "diagnosis_id": assertion.get("diagnosis_id"),
        "disposition": "quarantine",
        "evidence_pointers": _evidence_pointers(assertion, index),
        "extraction_lane": qualifiers.get("extraction_lane"),
        "ranking_eligible": False,
        "reason_codes": sorted(set(reasons)),
        "record_type": "QuarantinedAssertionPointer",
        "review_status": assertion.get("review_status"),
        "schema": PUBLIC_SCHEMA,
        "source_assertion_id": assertion.get("id"),
    }


def classify_assertions(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], Counter[str]]:
    index = {
        str(row["id"]): row
        for row in records
        if isinstance(row.get("id"), str)
    }
    template: list[dict[str, Any]] = []
    membership: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()

    assertions = sorted(
        (
            row for row in records
            if row.get("record_type") in {
                "DiagnosticAssertion", "DifferentialAssertion"
            }
        ),
        key=lambda row: str(row.get("id")),
    )
    for assertion in assertions:
        if assertion.get("record_type") != "DiagnosticAssertion":
            reasons = ["assertion.unsupported_record_type"]
            quarantine.append(_quarantine_pointer(assertion, index, reasons))
            reason_counts.update(reasons)
            continue
        qualifiers = assertion.get("qualifiers")
        qualifiers = qualifiers if isinstance(qualifiers, Mapping) else {}
        lane = qualifiers.get("extraction_lane")
        if lane == "template":
            reasons = template_rejection_reasons(assertion, index)
            if not reasons:
                template.append(_safe_pointer(
                    assertion, index, release_view="template_core_candidate"
                ))
                continue
        elif lane == "structural_wikem":
            reasons = wikem_rejection_reasons(assertion, index)
            if not reasons:
                membership.append(_safe_pointer(
                    assertion, index, release_view="wikem_differential_membership"
                ))
                continue
        else:
            reasons = ["lane.unrecognized_or_missing"]
        quarantine.append(_quarantine_pointer(assertion, index, reasons))
        reason_counts.update(set(reasons))
    return template, membership, quarantine, reason_counts


def _assert_public_source_free(rows: Sequence[Mapping[str, Any]]) -> None:
    """Reject any accidental source-body field in a public projection."""

    forbidden_keys = {"text", "quote", "surface", "canonical_label"}

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in forbidden_keys:
                    raise ValueError(f"public source leak at {path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for position, child in enumerate(value):
                walk(child, f"{path}[{position}]")

    for position, row in enumerate(rows):
        walk(row, f"row[{position}]")


def export_safe_views(
    *,
    input_path: Path,
    output_dir: Path,
    expected_template_core: int = EXPECTED_TEMPLATE_CORE,
    expected_wikem_membership: int = EXPECTED_WIKEM_MEMBERSHIP,
    expected_quarantine: int = EXPECTED_QUARANTINE,
    rule_report: Path | None = None,
) -> dict[str, Any]:
    records = read_jsonl(input_path)
    template, membership, quarantine, reason_counts = classify_assertions(records)
    actual = {
        "template_core_candidate": len(template),
        "wikem_differential_membership": len(membership),
        "quarantine": len(quarantine),
    }
    expected = {
        "template_core_candidate": expected_template_core,
        "wikem_differential_membership": expected_wikem_membership,
        "quarantine": expected_quarantine,
    }
    if actual != expected:
        raise CountContractError(
            "frozen safe-export count contract drifted; refusing publication: "
            f"expected={expected}, actual={actual}"
        )
    assertion_count = sum(
        row.get("record_type") in {"DiagnosticAssertion", "DifferentialAssertion"}
        for row in records
    )
    if assertion_count != sum(actual.values()):
        raise CountContractError(
            "not every DiagnosticAssertion received exactly one disposition: "
            f"assertions={assertion_count}, dispositions={sum(actual.values())}"
        )
    for row in [*template, *membership]:
        if row.get("review_status") != "unreviewed":
            raise ValueError(f"retained record is reviewed: {row['source_assertion_id']}")
        if row.get("ranking_eligible") is not False:
            raise ValueError(f"retained record is ranking eligible: {row['source_assertion_id']}")
    _assert_public_source_free([*template, *membership, *quarantine])

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "template_core_candidate": output_dir / "template_core.public.jsonl",
        "wikem_differential_membership": output_dir / "wikem_membership.public.jsonl",
        "quarantine": output_dir / "quarantine.public.jsonl",
    }
    atomic_write_jsonl(paths["template_core_candidate"], template)
    atomic_write_jsonl(paths["wikem_differential_membership"], membership)
    atomic_write_jsonl(paths["quarantine"], quarantine)

    source_counts: Counter[str] = Counter()
    for row in [*template, *membership, *quarantine]:
        sources = {
            occurrence.get("source")
            for pointer in row.get("evidence_pointers", [])
            for occurrence in pointer.get("source_occurrences", [])
            if occurrence.get("source")
        }
        for source in sources or {"unknown"}:
            source_counts[str(source)] += 1
    stats = {
        "assertions_input": assertion_count,
        "dispositions": actual,
        "quarantine_reason_counts_nonexclusive": dict(sorted(reason_counts.items())),
        "source_counts_nonexclusive": dict(sorted(source_counts.items())),
    }
    stats_path = output_dir / "stats.json"
    atomic_write_json(stats_path, stats)

    output_descriptors = {}
    for key, path in {**paths, "stats": stats_path}.items():
        output_descriptors[key] = {
            "bytes": path.stat().st_size,
            "contains_exact_quotes_or_passage_text": False,
            "path": str(path),
            "sha256": file_sha256(path),
        }
    manifest = {
        "audit_rule": {
            "id": RULE_ID,
            "report_path": str(rule_report) if rule_report else None,
            "report_sha256": (
                file_sha256(rule_report)
                if rule_report is not None and rule_report.is_file()
                else None
            ),
        },
        "count_contract": expected,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input": {
            "bytes": input_path.stat().st_size,
            "path": str(input_path),
            "sha256": file_sha256(input_path),
        },
        "outputs": output_descriptors,
        "public_contract": {
            "authoritative_clinical_knowledge": False,
            "contains_exact_quotes_or_passage_text": False,
            "ranking_eligible": False,
            "review_status_for_retained": "unreviewed",
            "template_and_membership_views_separate": True,
        },
        "rule_version": RULE_ID,
        "schema": "guideline_kg_safe_export_manifest.v0.1",
        "statistics": stats,
    }
    atomic_write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rule-report", type=Path)
    parser.add_argument(
        "--expected-template-core", type=int, default=EXPECTED_TEMPLATE_CORE
    )
    parser.add_argument(
        "--expected-wikem-membership", type=int, default=EXPECTED_WIKEM_MEMBERSHIP
    )
    parser.add_argument(
        "--expected-quarantine", type=int, default=EXPECTED_QUARANTINE
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if any(value < 0 for value in (
        args.expected_template_core,
        args.expected_wikem_membership,
        args.expected_quarantine,
    )):
        parser.error("expected counts must be non-negative")
    expected_outputs = (
        "template_core.public.jsonl",
        "wikem_membership.public.jsonl",
        "quarantine.public.jsonl",
        "stats.json",
        "manifest.json",
    )
    existing = [
        args.output_dir / name for name in expected_outputs
        if (args.output_dir / name).exists()
    ]
    if existing and not args.force:
        parser.error(
            "refusing to overwrite existing output(s): "
            + ", ".join(str(path) for path in existing)
            + "; pass --force"
        )
    manifest = export_safe_views(
        input_path=args.input,
        output_dir=args.output_dir,
        expected_template_core=args.expected_template_core,
        expected_wikem_membership=args.expected_wikem_membership,
        expected_quarantine=args.expected_quarantine,
        rule_report=args.rule_report,
    )
    print(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
