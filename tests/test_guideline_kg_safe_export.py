"""Tests for the audited, fail-closed guideline-KG safe export."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_guideline_kg_safe_views import (  # noqa: E402
    CountContractError,
    classify_assertions,
    export_safe_views,
    norm,
    template_rejection_reasons,
    wikem_rejection_reasons,
)


def _record(record_id: str, record_type: str, **values: object) -> dict:
    return {
        "id": record_id,
        "record_type": record_type,
        **values,
    }


def _graph() -> list[dict]:
    work = _record(
        "work", "SourceWork", source_family="test", title="Test guideline"
    )
    document = _record(
        "document", "DocumentVersion", source_work_id="work"
    )
    section_template = _record(
        "section_template",
        "Section",
        document_version_id="document",
        section_path=["Alpha disease", "Diagnosis"],
    )
    section_wikem = _record(
        "section_wikem",
        "Section",
        document_version_id="document",
        section_path=["Example syndrome", "Differential diagnosis"],
    )
    template_text = "Context. Alpha disease is diagnosed by a characteristic test."
    template_quote = "Alpha disease is diagnosed by a characteristic test."
    template_start = template_text.index(template_quote)
    passage_template = _record(
        "passage_template",
        "Passage",
        section_id="section_template",
        text=template_text,
        extensions={
            "provenances": [{
                "document_version_id": "document",
                "raw_chunk_ordinal": 2,
                "raw_id": "raw-template",
                "source": "Merck-Manual-19e",
                "source_family": "merck",
                "source_id": "source-template",
                "source_ordinal": 2,
                "source_work_id": "work",
                "metadata": {},
            }],
        },
    )
    span_template = _record(
        "span_template",
        "EvidenceSpan",
        passage_id="passage_template",
        start_char=template_start,
        end_char=template_start + len(template_quote),
        quote=template_quote,
    )
    passage_wikem = _record(
        "passage_wikem",
        "Passage",
        section_id="section_wikem",
        text="Disease A\nDisease B",
        extensions={
            "provenances": [{
                "document_version_id": "document",
                "raw_chunk_ordinal": 1,
                "raw_id": "raw-wikem",
                "source": "WikEM",
                "source_family": "wikem",
                "source_id": "source-wikem",
                "source_ordinal": 1,
                "source_work_id": "work",
                "metadata": {"wiki_links": ["Disease A", "Disease B"]},
            }],
        },
    )
    span_wikem = _record(
        "span_wikem",
        "EvidenceSpan",
        passage_id="passage_wikem",
        start_char=0,
        end_char=len(passage_wikem["text"]),
        quote=passage_wikem["text"],
    )
    concept_alpha = _record("concept_alpha", "Concept")
    diagnosis_alpha = _record(
        "diagnosis_alpha",
        "DiagnosisExpression",
        canonical_label="Alpha disease",
        base_concept_id="concept_alpha",
    )
    concept_wikem = _record("concept_wikem", "Concept")
    diagnosis_wikem = _record(
        "diagnosis_wikem",
        "DiagnosisExpression",
        canonical_label="Disease A",
        base_concept_id="concept_wikem",
    )
    feature_template = _record(
        "feature_template", "FeaturePattern", feature_type="laboratory"
    )
    feature_wikem = _record(
        "feature_wikem", "FeaturePattern", feature_type="other"
    )
    activity = _record("activity", "ExtractionActivity")
    assertion_template = _record(
        "assertion_template",
        "DiagnosticAssertion",
        assertion_confidence=0.9,
        criterion_id="feature_template",
        diagnosis_id="diagnosis_alpha",
        diagnostic_role="supporting",
        direction="supports",
        evidence_span_ids=["span_template"],
        extraction_activity_id="activity",
        extraction_confidence=0.9,
        necessity="not_stated",
        qualifiers={
            "extraction_lane": "template",
            "logic_status": "atomic_surface",
            "template_name": "diagnosed_by",
        },
        review_status="unreviewed",
    )
    assertion_wikem = _record(
        "assertion_wikem",
        "DiagnosticAssertion",
        assertion_confidence=0.5,
        criterion_id="feature_wikem",
        diagnosis_id="diagnosis_wikem",
        diagnostic_role="compatible",
        direction="supports",
        evidence_span_ids=["span_wikem"],
        extraction_activity_id="activity",
        extraction_confidence=0.99,
        necessity="not_stated",
        qualifiers={
            "enumeration_only": True,
            "extraction_lane": "structural_wikem",
            "ranking_eligible": False,
            "relation": "listed_differential_for",
        },
        review_status="unreviewed",
    )
    assertion_quarantine = copy.deepcopy(assertion_template)
    assertion_quarantine["id"] = "assertion_quarantine"
    assertion_quarantine["qualifiers"]["template_name"] = "diagnosis_requires"
    return [
        work,
        document,
        section_template,
        section_wikem,
        passage_template,
        passage_wikem,
        span_template,
        span_wikem,
        concept_alpha,
        concept_wikem,
        diagnosis_alpha,
        diagnosis_wikem,
        feature_template,
        feature_wikem,
        activity,
        assertion_template,
        assertion_wikem,
        assertion_quarantine,
    ]


def _index(rows: list[dict]) -> dict[str, dict]:
    return {row["id"]: row for row in rows}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_audit_normalization_is_exact() -> None:
    assert norm("  Diagnosis-of: Alpha/Beta  ") == "diagnosis of alpha beta"


def test_rules_retain_only_exact_template_and_membership_contracts() -> None:
    rows = _graph()
    index = _index(rows)
    assert template_rejection_reasons(index["assertion_template"], index) == []
    assert wikem_rejection_reasons(index["assertion_wikem"], index) == []

    bad_quote = copy.deepcopy(rows)
    bad_index = _index(bad_quote)
    bad_index["span_template"]["quote"] = "wrong"
    assert "evidence.quote_not_exact" in template_rejection_reasons(
        bad_index["assertion_template"], bad_index
    )

    navigation = copy.deepcopy(rows)
    navigation_index = _index(navigation)
    navigation_index["section_wikem"]["section_path"] = [
        "Example syndrome", "Algorithms"
    ]
    assert "membership.navigation_section" in wikem_rejection_reasons(
        navigation_index["assertion_wikem"], navigation_index
    )

    missing_activity = [row for row in copy.deepcopy(rows) if row["id"] != "activity"]
    missing_index = _index(missing_activity)
    assert "reference.extraction_activity_missing_or_wrong_type" in (
        template_rejection_reasons(
            missing_index["assertion_template"], missing_index
        )
    )


def test_export_is_separate_nonranking_source_free_and_exhaustive(
    tmp_path: Path,
) -> None:
    source = tmp_path / "graph.internal.jsonl"
    _write_jsonl(source, _graph())
    output = tmp_path / "safe"
    manifest = export_safe_views(
        input_path=source,
        output_dir=output,
        expected_template_core=1,
        expected_wikem_membership=1,
        expected_quarantine=1,
    )
    assert manifest["statistics"]["assertions_input"] == 3
    assert manifest["statistics"]["dispositions"] == {
        "quarantine": 1,
        "template_core_candidate": 1,
        "wikem_differential_membership": 1,
    }
    template = (output / "template_core.public.jsonl").read_text()
    membership = (output / "wikem_membership.public.jsonl").read_text()
    quarantine = (output / "quarantine.public.jsonl").read_text()
    for payload in (template, membership, quarantine):
        assert "characteristic test" not in payload
        assert "Disease A\\nDisease B" not in payload
        assert '"quote":' not in payload
        assert '"text":' not in payload
    template_row = json.loads(template)
    membership_row = json.loads(membership)
    assert template_row["release_view"] == "template_core_candidate"
    assert membership_row["release_view"] == "wikem_differential_membership"
    assert membership_row["synthetic_feature_is_diagnostic"] is False
    for row in (template_row, membership_row):
        assert row["review_status"] == "unreviewed"
        assert row["ranking_eligible"] is False


def test_count_contract_aborts_before_writing(tmp_path: Path) -> None:
    source = tmp_path / "graph.internal.jsonl"
    _write_jsonl(source, _graph())
    output = tmp_path / "safe"
    with pytest.raises(CountContractError, match="count contract drifted"):
        export_safe_views(
            input_path=source,
            output_dir=output,
            expected_template_core=5,
            expected_wikem_membership=2521,
            expected_quarantine=1043,
        )
    assert not output.exists()


def test_classification_has_exactly_one_disposition_per_assertion() -> None:
    template, membership, quarantine, reasons = classify_assertions(_graph())
    assert len(template) == len(membership) == len(quarantine) == 1
    assert reasons["template.template_name_not_allowed"] == 1


def test_unknown_assertion_type_cannot_bypass_quarantine() -> None:
    rows = _graph()
    rows.append(_record(
        "differential",
        "DifferentialAssertion",
        evidence_span_ids=["span_template"],
        qualifiers={},
        review_status="unreviewed",
    ))
    template, membership, quarantine, reasons = classify_assertions(rows)
    assert len(template) == 1
    assert len(membership) == 1
    assert len(quarantine) == 2
    assert reasons["assertion.unsupported_record_type"] == 1
