from __future__ import annotations

import hashlib

from agentclinic_tree_dx.knowledge.guideline_kg_extraction import (
    RecordAccumulator,
    convert_validated_llm_slots,
    diagnostic_passage_reasons,
    evidence_sentence_inventory,
    extract_template_assertions,
    extract_wikem_differential_memberships,
    llm_candidate_inventory,
    residual_priority,
    template_activity,
)
from agentclinic_tree_dx.knowledge.guideline_kg_schema import (
    Concept,
    DocumentVersion,
    FeaturePattern,
    Passage,
    Section,
    SourceWork,
    assert_valid_graph,
    record_to_dict,
)


def _passage(text: str, **extensions):
    work = SourceWork(
        title="Test manual", publisher="Test", canonical_url="urn:test:work",
        source_family="test", license="test-only",
    )
    version = DocumentVersion(
        source_work_id=work.id, version_label="v1",
        content_sha256=hashlib.sha256(b"test").hexdigest(),
    )
    section = Section(
        document_version_id=version.id, heading="Diagnosis",
        section_path=("Disease", "Diagnosis"), ordinal=0,
        section_type="diagnostic",
    )
    passage = Passage(
        section_id=section.id, ordinal=0, text=text,
        extensions={"section_path": ["Disease", "Diagnosis"], **extensions},
    )
    return [
        record_to_dict(work), record_to_dict(version), record_to_dict(section),
        record_to_dict(passage),
    ], record_to_dict(passage)


def test_template_lane_produces_exact_span_valid_graph():
    base, passage = _passage(
        "Hyperhidrosis is diagnosed by history and examination.",
        entry_title="Hyperhidrosis", chunk_type="evaluation",
    )
    activity = template_activity(hashlib.sha256(b"input").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    ids = extract_template_assertions(
        passage,
        aliases={"hyperhidrosis": "Hyperhidrosis"},
        activity_id=activity.id,
        accumulator=accumulator,
    )
    assert len(ids) == 1
    assertions = [r for r in accumulator.values() if r["record_type"] == "DiagnosticAssertion"]
    spans = [r for r in accumulator.values() if r["record_type"] == "EvidenceSpan"]
    assert assertions[0]["diagnostic_role"] == "supporting"
    assert spans[0]["quote"] == passage["text"]
    assert_valid_graph(accumulator.values())


def test_bad_entry_heading_is_not_promoted_to_disease():
    base, passage = _passage(
        "Diagnosis is based on typical ocular findings.",
        entry_title="The following findings", chunk_type="evaluation",
    )
    activity = template_activity(hashlib.sha256(b"input").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    assert extract_template_assertions(
        passage, aliases={}, activity_id=activity.id, accumulator=accumulator,
    ) == []


def test_wikem_membership_is_explicitly_not_ranking_evidence():
    base, passage = _passage(
        "MI, dissection, mesenteric ischemia",
        source="WikEM", chunk_type="differential",
        syndrome_anchor="Abdominal pain", wiki_links=["Myocardial infarction"],
    )
    activity = template_activity(hashlib.sha256(b"input").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    ids = extract_wikem_differential_memberships(
        passage, aliases={"myocardial infarction": "Myocardial infarction"},
        activity_id=activity.id, accumulator=accumulator,
    )
    assert len(ids) == 1
    assertion = next(
        r for r in accumulator.values() if r["record_type"] == "DiagnosticAssertion"
    )
    assert assertion["qualifiers"]["enumeration_only"] is True
    assert assertion["qualifiers"]["ranking_eligible"] is False
    assert_valid_graph(accumulator.values())


def test_llm_slot_is_closed_inventory_and_exact_substring_bounded():
    base, passage = _passage(
        "Pellagra is characterized by skin, CNS, and GI symptoms.",
        entry_title="Pellagra", chunk_type="evaluation",
    )
    candidates = llm_candidate_inventory(
        passage, {"pellagra": "Pellagra", "gi symptoms": "GI symptoms"},
    )
    evidence = evidence_sentence_inventory(passage)
    activity = template_activity(hashlib.sha256(b"input").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    feature_surface = "skin, CNS, and GI symptoms"
    feature_start = passage["text"].index(feature_surface)
    accepted, rejected = convert_validated_llm_slots(
        passage,
        [{
            "target_candidate_id": candidates[0]["candidate_id"],
            "evidence_mention_id": evidence[0]["mention_id"],
            "feature_surface": feature_surface,
            "feature_start_char": feature_start,
            "feature_end_char": feature_start + len(feature_surface),
            "feature_type": "symptom",
            "polarity": "present",
            "diagnostic_role": "typical",
            "direction": "supports",
            "necessity": "not_stated",
            "logic_operator": "atomic",
            "confidence": 0.91,
        }],
        candidate_inventory=candidates,
        evidence_inventory=evidence,
        activity_id=activity.id,
        accumulator=accumulator,
    )
    assert len(accepted) == 1
    assert rejected == []
    assert_valid_graph(accumulator.values())

    accepted, rejected = convert_validated_llm_slots(
        passage,
        [{
            "target_candidate_id": "dx999",
            "evidence_mention_id": evidence[0]["mention_id"],
            "feature_surface": "invented feature",
            "feature_start_char": 0,
            "feature_end_char": len("invented feature"),
            "feature_type": "other", "polarity": "present",
            "diagnostic_role": "supporting", "direction": "supports",
            "necessity": "not_stated", "confidence": 0.9,
        }],
        candidate_inventory=candidates, evidence_inventory=evidence,
        activity_id=activity.id, accumulator=accumulator,
    )
    assert accepted == []
    assert {error for row in rejected for error in row["errors"]} >= {
        "target_candidate_id_not_in_inventory",
        "feature_offset_not_uniquely_repairable",
    }


def test_residual_priority_targets_complex_uncovered_passages():
    _, passage = _passage(
        "Diagnosis requires at least 2 of the following findings.",
        chunk_type="evaluation",
    )
    assert diagnostic_passage_reasons(passage)
    assert residual_priority(passage, template_count=0) >= 6


def test_context_admission_alone_is_not_a_diagnostic_signal():
    _, treatment = _passage(
        "Offer oral therapy once daily.",
        section_path=["Disease", "Treatment"],
        chunk_type="recommendation",
        admitted=True,
        admission_reasons=["context_closure"],
    )
    assert diagnostic_passage_reasons(treatment) == []

    _, diagnostic_context = _passage(
        "Biopsy confirms the diagnosis.",
        section_path=["Disease", "Treatment"],
        chunk_type="recommendation",
        admitted=True,
        admission_reasons=["document_context"],
    )
    assert diagnostic_passage_reasons(diagnostic_context) == ["diagnostic_cue"]


def test_llm_logic_materializes_real_logic_expression():
    base, passage = _passage(
        "Pellagra is characterized by rash and diarrhea.",
        entry_title="Pellagra", chunk_type="evaluation",
    )
    candidates = llm_candidate_inventory(passage, {"pellagra": "Pellagra"})
    evidence = evidence_sentence_inventory(passage)
    activity = template_activity(hashlib.sha256(b"logic").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    whole = "rash and diarrhea"
    whole_start = passage["text"].index(whole)
    components = []
    for surface in ("rash", "diarrhea"):
        start = passage["text"].index(surface)
        components.append({
            "feature_surface": surface,
            "feature_start_char": start,
            "feature_end_char": start + len(surface),
            "feature_type": "symptom",
            "polarity": "present",
        })
    accepted, rejected = convert_validated_llm_slots(
        passage,
        [{
            "assertion_type": "diagnostic",
            "target_candidate_id": candidates[0]["candidate_id"],
            "evidence_mention_id": evidence[0]["mention_id"],
            "feature_surface": whole,
            "feature_start_char": whole_start,
            "feature_end_char": whole_start + len(whole),
            "feature_type": "symptom", "polarity": "present",
            "diagnostic_role": "typical", "direction": "supports",
            "necessity": "not_stated", "logic_operator": "and",
            "feature_components": components, "confidence": 0.9,
        }],
        candidate_inventory=candidates, evidence_inventory=evidence,
        activity_id=activity.id, accumulator=accumulator,
    )
    assert len(accepted) == 1 and rejected == []
    assertions = [r for r in accumulator.values() if r["record_type"] == "DiagnosticAssertion"]
    logics = [r for r in accumulator.values() if r["record_type"] == "LogicExpression"]
    assert len(logics) == 1
    assert assertions[0]["criterion_id"] == logics[0]["id"]
    assert logics[0]["operator"] == "and"
    assert_valid_graph(accumulator.values())


def test_llm_differential_materializes_differential_assertion():
    text = "A normal MMA level differentiates folate deficiency from vitamin B12 deficiency."
    base, passage = _passage(text, chunk_type="evaluation")
    aliases = {
        "folate deficiency": "Folate deficiency",
        "vitamin b12 deficiency": "Vitamin B12 deficiency",
    }
    candidates = llm_candidate_inventory(passage, aliases)
    by_label = {item["label"]: item["candidate_id"] for item in candidates}
    evidence = evidence_sentence_inventory(passage)
    feature = "A normal MMA level"
    start = text.index(feature)
    activity = template_activity(hashlib.sha256(b"diff").hexdigest())
    accumulator = RecordAccumulator([*base, record_to_dict(activity)])
    accepted, rejected = convert_validated_llm_slots(
        passage,
        [{
            "assertion_type": "differential",
            "target_candidate_id": by_label["Folate deficiency"],
            "diagnosis_a_candidate_id": by_label["Folate deficiency"],
            "diagnosis_b_candidate_id": by_label["Vitamin B12 deficiency"],
            "favors": "a",
            "evidence_mention_id": evidence[0]["mention_id"],
            "feature_surface": feature,
            "feature_start_char": start,
            "feature_end_char": start + len(feature),
            "feature_type": "laboratory", "polarity": "present",
            "diagnostic_role": "supporting", "direction": "supports",
            "necessity": "not_stated", "logic_operator": "atomic",
            "confidence": 0.88,
        }],
        candidate_inventory=candidates, evidence_inventory=evidence,
        activity_id=activity.id, accumulator=accumulator,
    )
    assert len(accepted) == 1 and rejected == []
    assert any(r["record_type"] == "DifferentialAssertion" for r in accumulator.values())
    assert_valid_graph(accumulator.values())


def test_evidence_inventory_refuses_silent_sentence_truncation():
    _, passage = _passage(" ".join(f"Sentence {i}." for i in range(81)))
    try:
        evidence_sentence_inventory(passage, max_sentences=80)
    except ValueError as exc:
        assert "refusing silent truncation" in str(exc)
    else:
        raise AssertionError("expected explicit overflow failure")


def test_acronym_candidate_survives_closed_inventory():
    _, passage = _passage("MI may present with epigastric pain.")
    candidates = llm_candidate_inventory(
        passage, {"mi": "Myocardial infarction"},
    )
    assert any(row["label"] == "Myocardial infarction" for row in candidates)


def test_immutable_accumulator_delta_rolls_back_only_new_records():
    existing = Concept(label="Pneumonia", concept_kind="disease")
    accumulator = RecordAccumulator(
        [record_to_dict(existing)], merge_identity_metadata=False,
    )
    original = record_to_dict(existing)
    tracker = accumulator.begin_delta()

    # Same stable identity with alternate display metadata must not rewrite the
    # already-validated record in immutable extraction mode.
    returned = accumulator.add(Concept(
        label=" pneumonia ", concept_kind="disease", synonyms=("PNA",),
    ))
    assert returned == original
    feature = accumulator.add(FeaturePattern(
        canonical_label="new fever", feature_type="sign",
        surface="new fever", temporality={"relation": "not_stated"},
    ))
    assert accumulator.delta_ids(tracker) == [feature["id"]]

    accumulator.rollback_delta(tracker)
    assert accumulator.values() == [original]
