from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from agentclinic_tree_dx.knowledge.guideline_kg_schema import (
    Concept,
    ConceptMapping,
    DiagnosisExpression,
    DiagnosticAssertion,
    DocumentVersion,
    EvidenceSpan,
    ExtractionActivity,
    FeaturePattern,
    GraphValidationIndex,
    GuidelineKGValidationError,
    LogicExpression,
    Passage,
    Section,
    SourceWork,
    assert_valid_graph,
    read_jsonl,
    record_to_dict,
    stable_id,
    stable_id_for,
    validate_graph,
    validate_record,
    write_jsonl,
)


def _graph_fixture():
    source_text = (
        "Absence of fever before antibiotics argues against bacterial "
        "pneumonia; focal consolidation supports it."
    )
    quote = "Absence of fever before antibiotics argues against bacterial pneumonia"

    work = SourceWork(
        title="Test diagnostic guideline",
        publisher="Fixture Society",
        canonical_url="https://example.test/guideline",
        source_family="cpg",
        license="test fixture",
    )
    version = DocumentVersion(
        source_work_id=work.id,
        version_label="2026",
        published_date="2026-01-01",
        content_sha256=sha256(source_text.encode()).hexdigest(),
        source_uri="https://example.test/guideline/2026",
    )
    section = Section(
        document_version_id=version.id,
        heading="Differential diagnosis",
        section_path=("Pneumonia", "Differential diagnosis"),
        ordinal=2,
        section_type="differential",
    )
    passage = Passage(section_id=section.id, ordinal=0, text=source_text, page_start=8)
    span = EvidenceSpan(
        passage_id=passage.id,
        start_char=0,
        end_char=len(quote),
        quote=quote,
    )
    activity = ExtractionActivity(
        pipeline_name="guideline-kg-test",
        pipeline_version="1",
        extractor_type="hybrid",
        input_sha256=sha256(source_text.encode()).hexdigest(),
        model="fixture-model",
        prompt_sha256="f" * 64,
        parameters={"temperature": 0},
    )
    disease = Concept(
        label="bacterial pneumonia",
        concept_kind="disease",
        system="MONDO",
        code="0005249",
    )
    diagnosis = DiagnosisExpression(
        canonical_label="bacterial pneumonia",
        base_concept_id=disease.id,
        qualifiers={"etiology": "bacterial"},
    )
    absent_fever = FeaturePattern(
        canonical_label="absence of fever before antibiotics",
        feature_type="sign",
        polarity="absent",
        surface="Absence of fever",
        temporality={"relation": "before", "anchor": "antibiotics"},
    )
    consolidation = FeaturePattern(
        canonical_label="focal consolidation",
        feature_type="imaging",
        polarity="present",
        surface="focal consolidation",
        temporality={"relation": "not_stated"},
    )
    criterion = LogicExpression(
        operator="k_of_n",
        operand_ids=(absent_fever.id, consolidation.id),
        k=1,
        label="one of two pneumonia discriminators",
    )
    assertion = DiagnosticAssertion(
        diagnosis_id=diagnosis.id,
        criterion_id=criterion.id,
        diagnostic_role="argues_against",
        direction="argues_against",
        necessity="optional",
        evidence_span_ids=(span.id,),
        assertion_confidence=0.72,
        extraction_confidence=0.94,
        extraction_activity_id=activity.id,
        review_status="accepted",
        qualifiers={"scope": "pre-treatment"},
    )
    return [
        work,
        version,
        section,
        passage,
        span,
        activity,
        disease,
        diagnosis,
        absent_fever,
        consolidation,
        criterion,
        assertion,
    ]


def test_negation_temporality_and_k_of_n_are_first_class_and_valid():
    graph = _graph_fixture()
    assert validate_graph(graph) == []
    feature = next(
        record for record in graph
        if isinstance(record, FeaturePattern) and record.polarity == "absent"
    )
    assert feature.temporality == {"relation": "before", "anchor": "antibiotics"}
    logic = next(record for record in graph if isinstance(record, LogicExpression))
    assert logic.operator == "k_of_n"
    assert logic.k == 1


def test_invalid_k_of_n_and_unanchored_temporality_are_rejected():
    feature = FeaturePattern(
        canonical_label="late fever",
        feature_type="sign",
        surface="late fever",
        temporality={"relation": "after"},
    )
    assert any("requires anchor" in error for error in validate_record(feature))

    logic = LogicExpression(operator="k_of_n", operand_ids=("gkg_feature_deadbeefdeadbeefdead",), k=2)
    assert any("1 <= k <= n" in error for error in validate_record(logic))


def test_exact_evidence_span_is_checked_against_passage_text():
    graph = _graph_fixture()
    assert_valid_graph(graph)

    broken = [record_to_dict(record) for record in graph]
    span = next(record for record in broken if record["record_type"] == "EvidenceSpan")
    span["quote"] = span["quote"].replace("fever", "cough")
    span["id"] = stable_id_for(span)
    assertion = next(
        record for record in broken if record["record_type"] == "DiagnosticAssertion"
    )
    assertion["evidence_span_ids"] = [span["id"]]
    assertion["id"] = stable_id_for(assertion)
    errors = validate_graph(broken)
    assert any("quote must exactly equal" in error for error in errors)


def test_assertion_and_extraction_confidence_are_not_conflated():
    assertion = next(
        record for record in _graph_fixture()
        if isinstance(record, DiagnosticAssertion)
    )
    assert assertion.assertion_confidence != assertion.extraction_confidence
    assert validate_record(assertion) == []

    ambiguous = record_to_dict(assertion)
    ambiguous["confidence"] = 0.9
    assert any("ambiguous" in error for error in validate_record(ambiguous))


def test_mapping_confidence_has_a_separate_mapping_contract():
    local = Concept(label="walking pneumonia", concept_kind="disease")
    mondo = Concept(
        label="Mycoplasma pneumonia",
        concept_kind="disease",
        system="MONDO",
        code="0001056",
    )
    mapping = ConceptMapping(
        subject_concept_id=local.id,
        predicate="related_match",
        object_concept_id=mondo.id,
        mapping_confidence=0.61,
        mapping_method="hybrid lexical review",
    )
    assert validate_graph([local, mondo, mapping]) == []
    payload = record_to_dict(mapping)
    payload["mapping_confidence"] = 1.2
    assert any("mapping_confidence" in error for error in validate_record(payload))


def test_illegal_assertion_domain_is_rejected():
    graph = _graph_fixture()
    payloads = [record_to_dict(record) for record in graph]
    disease = next(record for record in payloads if record["record_type"] == "Concept")
    assertion = next(
        record for record in payloads if record["record_type"] == "DiagnosticAssertion"
    )
    assertion["diagnosis_id"] = disease["id"]
    assertion["id"] = stable_id_for(assertion)
    errors = validate_graph(payloads)
    assert any("diagnosis_id: illegal range Concept" in error for error in errors)


def test_stable_ids_and_jsonl_round_trip(tmp_path):
    first = Concept(
        label="Pneumonia",
        concept_kind="disease",
        system="MONDO",
        code="0005249",
    )
    renamed = Concept(
        label="Pneumonia (disorder)",
        concept_kind="disease",
        system="MONDO",
        code="0005249",
    )
    assert first.id == renamed.id
    assert stable_id("staging", {"b": 2, "a": 1}) == stable_id(
        "staging", {"a": 1, "b": 2}
    )

    destination = tmp_path / "guideline-kg.jsonl"
    graph = _graph_fixture()
    assert write_jsonl(graph, destination) == len(graph)
    loaded = read_jsonl(destination)
    assert loaded == [record_to_dict(record) for record in graph]


def test_invalid_graph_raises_a_multi_error_exception():
    graph = [record_to_dict(record) for record in _graph_fixture()]
    assertion = next(
        record for record in graph if record["record_type"] == "DiagnosticAssertion"
    )
    assertion["assertion_confidence"] = -1
    with pytest.raises(GuidelineKGValidationError) as exc:
        assert_valid_graph(graph)
    assert any("assertion_confidence" in error for error in exc.value.errors)


def _valid_delta_for_fixture(graph):
    payloads = [record_to_dict(record) for record in graph]
    passage = next(record for record in payloads if record["record_type"] == "Passage")
    diagnosis = next(
        record for record in payloads
        if record["record_type"] == "DiagnosisExpression"
    )
    activity = next(
        record for record in payloads if record["record_type"] == "ExtractionActivity"
    )
    quote = "focal consolidation"
    start = passage["text"].index(quote)
    feature = FeaturePattern(
        canonical_label=quote,
        feature_type="imaging",
        polarity="present",
        surface=quote,
        temporality={"relation": "not_stated"},
        qualifiers={"extraction_lane": "incremental-test"},
    )
    span = EvidenceSpan(
        passage_id=passage["id"], start_char=start,
        end_char=start + len(quote), quote=quote,
    )
    assertion = DiagnosticAssertion(
        diagnosis_id=diagnosis["id"],
        criterion_id=feature.id,
        diagnostic_role="supporting",
        direction="supports",
        necessity="optional",
        evidence_span_ids=(span.id,),
        assertion_confidence=0.7,
        extraction_confidence=0.9,
        extraction_activity_id=activity["id"],
    )
    return [feature, span, assertion]


def test_incremental_validation_matches_full_graph_for_valid_delta():
    base = _graph_fixture()
    delta = _valid_delta_for_fixture(base)
    incremental = GraphValidationIndex(base)

    assert incremental.validate_delta(delta) == []
    assert validate_graph([*base, *delta]) == []
    assert incremental.apply_delta(delta) == 3
    assert incremental.record_count == len(base) + 3
    # Replaying byte-equivalent content is an idempotent no-op.
    assert incremental.apply_delta(delta) == 0


def test_incremental_validation_rejects_mutation_and_is_atomic():
    base = [record_to_dict(record) for record in _graph_fixture()]
    incremental = GraphValidationIndex(base)
    original_count = incremental.record_count
    concept = deepcopy(next(
        record for record in base if record["record_type"] == "Concept"
    ))
    # Synonyms are mutable metadata excluded from stable identity, so this is
    # the subtle collision an immutable base index must still reject.
    concept["synonyms"] = ["mutated after validation"]
    assert concept["id"] == stable_id_for(concept)

    errors = incremental.validate_delta([concept])
    assert any("immutable existing record differs" in error for error in errors)
    with pytest.raises(GuidelineKGValidationError):
        incremental.apply_delta([concept])
    assert incremental.record_count == original_count


def test_incremental_validation_checks_cross_refs_and_exact_quote():
    base = _graph_fixture()
    delta = [record_to_dict(record) for record in _valid_delta_for_fixture(base)]
    incremental = GraphValidationIndex(base)

    span = next(record for record in delta if record["record_type"] == "EvidenceSpan")
    span["quote"] = "not source text"
    span["id"] = stable_id_for(span)
    assertion = next(
        record for record in delta if record["record_type"] == "DiagnosticAssertion"
    )
    assertion["evidence_span_ids"] = [span["id"]]
    assertion["id"] = stable_id_for(assertion)
    errors = incremental.validate_delta(delta)
    assert any("quote must exactly equal" in error for error in errors)

    broken = deepcopy(delta)
    assertion = next(
        record for record in broken if record["record_type"] == "DiagnosticAssertion"
    )
    assertion["criterion_id"] = next(
        record_to_dict(record)["id"] for record in base
        if isinstance(record, Concept)
    )
    assertion["id"] = stable_id_for(assertion)
    errors = incremental.validate_delta(broken)
    assert any("criterion_id: illegal range Concept" in error for error in errors)


def test_incremental_validation_detects_delta_logic_cycle():
    base = _graph_fixture()
    feature = next(
        record_to_dict(record)["id"] for record in base
        if isinstance(record, FeaturePattern)
    )
    left = record_to_dict(LogicExpression(operator="not", operand_ids=(feature,)))
    right = record_to_dict(LogicExpression(operator="not", operand_ids=(left["id"],)))
    # Deliberately adversarial payloads cannot retain canonical content hashes
    # after forming a cycle, but cycle detection must still run alongside the
    # expected non-canonical-ID errors.
    left["operand_ids"] = [right["id"]]
    incremental_errors = GraphValidationIndex(base).validate_delta([left, right])
    full_errors = validate_graph([*base, left, right])
    assert any("cyclic LogicExpression" in error for error in incremental_errors)
    assert any("cyclic LogicExpression" in error for error in full_errors)
