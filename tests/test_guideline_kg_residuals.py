from __future__ import annotations

import importlib.util
import hashlib
import json
import stat
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from agentclinic_tree_dx.knowledge.guideline_kg_extraction import (
    RecordAccumulator,
    evidence_sentence_inventory,
)
from agentclinic_tree_dx.knowledge.guideline_kg_schema import (
    DocumentVersion,
    EvidenceSpan,
    ExtractionActivity,
    FeaturePattern,
    GraphValidationIndex,
    GuidelineKGValidationError,
    Passage,
    Section,
    SourceWork,
    assert_valid_graph,
    record_to_dict,
)


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/extract_guideline_kg_residuals.py"
SPEC = importlib.util.spec_from_file_location("extract_guideline_kg_residuals", SCRIPT)
assert SPEC and SPEC.loader
residuals = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = residuals
SPEC.loader.exec_module(residuals)


def test_parse_json_object_accepts_fence_but_rejects_non_object():
    assert residuals.parse_json_object('```json\n{"assertions": []}\n```') == {
        "assertions": []
    }
    try:
        residuals.parse_json_object("[]")
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("non-object JSON must be rejected")


def test_response_schema_is_closed_and_requires_exact_occurrence_selectors():
    assert residuals.RESPONSE_SCHEMA["required"] == [
        "assertions", "coverage_status",
    ]
    assert residuals.RESPONSE_SCHEMA["properties"]["assertions"]["maxItems"] == 12
    item = residuals.RESPONSE_SCHEMA["properties"]["assertions"]["items"]
    assert item["additionalProperties"] is False
    assert "feature_occurrence_index" in item["required"]
    assert "feature_start_char" not in item["properties"]
    assert "feature_end_char" not in item["properties"]
    assert "feature_components" in item["required"]
    assert "direction" not in item["required"]
    assert "direction" not in item["properties"]
    assert item["properties"]["k"] == {"type": "integer", "minimum": 0}
    assert residuals.DEFAULT_MAX_OUTPUT_TOKENS == (
        residuals.OUTPUT_ENVELOPE_RESERVE_TOKENS
        + 12 * residuals.OUTPUT_TOKENS_PER_ASSERTION_FLOOR
    ) == 3200
    component = item["properties"]["feature_components"]["items"]
    assert "feature_occurrence_index" in component["required"]
    assert "feature_start_char" not in component["properties"]


def test_gemini_strict_schema_subset_has_typed_enums_and_no_nullable_union():
    supported_keywords = {
        "type", "enum", "items", "minItems", "maxItems", "minimum",
        "maximum", "properties", "required", "additionalProperties",
        "description", "title", "format", "anyOf", "oneOf", "$defs", "$ref",
    }

    def visit(schema):
        assert set(schema) <= supported_keywords
        if "enum" in schema:
            assert schema.get("type") == "string"
        assert not isinstance(schema.get("type"), list)
        for child in (schema.get("properties") or {}).values():
            visit(child)
        if isinstance(schema.get("items"), dict):
            visit(schema["items"])
        for keyword in ("anyOf", "oneOf"):
            for child in schema.get(keyword) or []:
                visit(child)

    visit(residuals.RESPONSE_SCHEMA)


def test_model_supplied_direction_is_rejected_as_an_extra_field():
    item_schema = residuals.RESPONSE_SCHEMA["properties"]["assertions"]["items"]
    fixture = {
        key: (
            [] if key == "feature_components" else 0 if key == "k"
            else 1 if key == "feature_occurrence_index"
            else 0.5 if key == "confidence" else ""
        )
        for key in item_schema["required"]
    }
    fixture["direction"] = "supports"
    errors = residuals.validate_response_envelope({
        "assertions": [fixture], "coverage_status": "complete",
    })
    assert "assertions[0]_extra:direction" in errors


def test_telemetry_usage_distinguishes_token_classes():
    usage = residuals.response_usage({
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 3},
            "prompt_tokens_details": {"cached_tokens": 11},
            "cost": 0.001,
        }
    })
    assert usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "reasoning_tokens": 3,
        "cached_tokens": 11,
        "cost": 0.001,
    }


def test_preflight_records_never_include_passage_text():
    allowed = {
        "semantic_mode", "semantic_unit_id", "status", "detail",
        "input_tokens", "source_tokens", "source_tokenizer",
        "rendered_prompt_tokens", "rendered_prompt_tokens_json_schema",
        "rendered_prompt_tokens_json_object", "rendered_prompt_tokens_worst_case",
        "max_source_tokens", "tokenizer",
        "prompt_soft_limit_exceeded",
        "candidate_count", "evidence_sentence_count", "evidence_unit_count",
        "evidence_unit_mode", "cache_key",
    }
    # This is a contract test for the explicit row constructors in main.
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"source_text_written_to_preflight": False' in source
    assert '"EVIDENCE_UNITS": prompt_evidence_inventory(evidence)' in source
    assert "preflight.append" in source
    assert '"semantic_unit_sha256"' in source
    assert '"semantic_unit_text"' not in source


def test_system_prompt_forbids_inference_and_list_promotion():
    prompt = residuals.SYSTEM_PROMPT.casefold()
    assert "never infer" in prompt
    assert "do not convert a differential list" in prompt
    assert "exact" in prompt
    assert "claim-window" in prompt


def test_json_object_fallback_enforces_same_closed_envelope():
    assert residuals.validate_response_envelope({
        "assertions": [], "coverage_status": "nothing_extractable",
    }) == []
    errors = residuals.validate_response_envelope({
        "assertions": [{"assertion_type": "diagnostic"}], "commentary": "bad",
    })
    assert "top_level_keys_must_equal_status_and_assertions_contract" in errors
    assert any("_missing:" in error for error in errors)


def test_coverage_status_is_one_flat_mutually_exclusive_enum():
    statuses = set(
        residuals.RESPONSE_SCHEMA["properties"]["coverage_status"]["enum"]
    )
    assert statuses == residuals.ALL_COVERAGE_STATUSES
    assert "needs_resplit" not in statuses
    assert "coverage_reason" not in residuals.RESPONSE_SCHEMA["properties"]
    for status in residuals.RESPLIT_COVERAGE_STATUSES | residuals.REVIEW_COVERAGE_STATUSES:
        assert residuals.validate_response_envelope({
            "assertions": [], "coverage_status": status,
        }) == []


def test_coverage_contract_caps_twelve_and_never_allows_partial_resplit():
    item_schema = residuals.RESPONSE_SCHEMA["properties"]["assertions"]["items"]
    fixture = {
        key: (
            [] if key == "feature_components" else 0 if key == "k"
            else 1 if key == "feature_occurrence_index"
            else 0.5 if key == "confidence" else ""
        )
        for key in item_schema["required"]
    }
    twelve = residuals.validate_response_envelope({
        "assertions": [fixture] * 12,
        "coverage_status": "complete",
    })
    assert "assertions_exceeds_max_items" not in twelve
    thirteen = residuals.validate_response_envelope({
        "assertions": [fixture] * 13,
        "coverage_status": "complete",
    })
    assert "assertions_exceeds_max_items" in thirteen
    partial = residuals.validate_response_envelope({
        "assertions": [fixture],
        "coverage_status": "resplit_assertion_capacity",
    })
    assert "noncomplete_coverage_must_not_return_partial_assertions" in partial
    bad_atomic = {**fixture, "logic_operator": "atomic", "k": 1}
    assert "assertions[0]_non_k_of_n_requires_k_zero" in (
        residuals.validate_response_envelope({
            "assertions": [bad_atomic], "coverage_status": "complete",
        })
    )
    bad_k_of_n = {**fixture, "logic_operator": "k_of_n", "k": 0}
    assert "assertions[0]_k_of_n_requires_positive_k" in (
        residuals.validate_response_envelope({
            "assertions": [bad_k_of_n], "coverage_status": "complete",
        })
    )


def test_json_object_fallback_rejects_model_offsets_inside_components():
    item_schema = residuals.RESPONSE_SCHEMA["properties"]["assertions"]["items"]
    fixture = {
        key: (
            [] if key == "feature_components" else 0 if key == "k"
            else 1 if key == "feature_occurrence_index"
            else 0.5 if key == "confidence" else ""
        )
        for key in item_schema["required"]
    }
    fixture["feature_components"] = [{
        "feature_surface": "rash", "feature_occurrence_index": 1,
        "feature_type": "symptom", "polarity": "present",
        "feature_start_char": 100,
    }]
    errors = residuals.validate_response_envelope({
        "assertions": [fixture], "coverage_status": "complete",
    })
    assert any("components[0]_extra:feature_start_char" in error for error in errors)


def test_preflight_counts_strict_and_fallback_schema_overhead():
    messages = [
        {"role": "system", "content": "extract"},
        {"role": "user", "content": '{"EVIDENCE_UNITS":[]}'},
    ]
    estimates, tokenizer = residuals.rendered_prompt_token_estimates(
        messages, ["json_schema", "json_object"],
    )
    base, _ = residuals.count_tokens(residuals.canonical_json(messages))
    assert set(estimates) == {"json_schema", "json_object"}
    assert min(estimates.values()) > base
    assert tokenizer
    fallback = residuals.messages_for_mode(messages, "json_object")
    assert "OUTPUT_JSON_SCHEMA" in fallback[-1]["content"]


def test_provider_routing_defaults_are_auditable_and_strict_only_requires_params():
    strict = residuals.provider_routing_for_mode(
        "json_schema", provider_sort="throughput",
        provider_data_collection="deny", strict_require_parameters=True,
    )
    assert strict == {
        "sort": "throughput", "data_collection": "deny",
        "require_parameters": True,
    }
    fallback = residuals.provider_routing_for_mode(
        "json_object", provider_sort="latency",
        provider_data_collection="allow", strict_require_parameters=True,
    )
    assert fallback == {"sort": "latency", "data_collection": "allow"}


def _two_passage_fixture():
    work = SourceWork(
        title="Test manual", publisher="Fixture",
        canonical_url="urn:test:claim-window", source_family="test",
    )
    version = DocumentVersion(
        source_work_id=work.id, version_label="v1",
        content_sha256=hashlib.sha256(b"claim-window").hexdigest(),
    )
    section = Section(
        document_version_id=version.id, heading="Diagnosis",
        section_path=("Pellagra", "Diagnosis"), ordinal=0,
    )
    first = Passage(
        section_id=section.id, ordinal=0,
        text="Pellagra is characterized by ",
    )
    second = Passage(
        section_id=section.id, ordinal=1,
        text="rash and diarrhea.",
    )
    activity = ExtractionActivity(
        pipeline_name="test-claim-window", pipeline_version="1",
        extractor_type="llm", input_sha256="a" * 64,
        model="fixture", prompt_sha256="b" * 64,
    )
    records = [
        record_to_dict(value)
        for value in (work, version, section, first, second, activity)
    ]
    passages = {
        first.id: record_to_dict(first), second.id: record_to_dict(second),
    }
    text = first.text + "\n\n" + second.text
    window = {
        "window_id": "cw_fixture",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "rechunker_version": "claim-aware-test-v1",
        "section_path": ["Pellagra", "Diagnosis"],
        "primary_claim_blocks": [{
            "block_id": "block_fixture",
            "window_start_char": 0,
            "window_end_char": len(text),
            "block_type": "criteria_list",
            "structural_role": "diagnostic_criteria",
            "logic_cues": [],
            "contains_scope_cue": False,
            "eligible_for_evidence": True,
        }],
        "offset_map": [
            {
                "window_start_char": 0,
                "window_end_char": len(first.text),
                "passage_id": first.id,
                "passage_start_char": 0,
                "passage_end_char": len(first.text),
                "kind": "source",
                "eligible_for_evidence": True,
            },
            {
                "window_start_char": len(first.text) + 2,
                "window_end_char": len(text),
                "passage_id": second.id,
                "passage_start_char": 0,
                "passage_end_char": len(second.text),
                "kind": "source",
                "eligible_for_evidence": True,
            },
        ],
    }
    return records, passages, window, activity


def test_claim_window_normalization_rejects_non_lossless_map():
    _, passages, window, _ = _two_passage_fixture()
    normalized = residuals.normalize_claim_window(window, passages)
    assert normalized["offset_map_sha256"]
    broken = json.loads(json.dumps(window))
    broken["offset_map"][0]["passage_end_char"] -= 1
    try:
        residuals.normalize_claim_window(broken, passages)
    except residuals.ClaimWindowError as exc:
        assert "character preserving" in str(exc)
    else:
        raise AssertionError("lossy offset maps must be rejected")


def test_claim_window_candidate_inventory_uses_aggregated_targets():
    _, passages, raw_window, _ = _two_passage_fixture()
    raw_window["entry_title_candidates"] = ["Pellagra", "Hartnup disease"]
    window = residuals.normalize_claim_window(raw_window, passages)
    candidates = residuals.claim_window_candidate_inventory(
        window, passages,
        {"pellagra": "Pellagra", "hartnup disease": "Hartnup disease"},
    )
    labels = {item["label"] for item in candidates}
    assert {"Pellagra", "Hartnup disease"} <= labels


def test_claim_block_inventory_retains_sentence_subspans_and_no_silent_fallback():
    _, passages, raw_window, _ = _two_passage_fixture()
    window = residuals.normalize_claim_window(raw_window, passages)
    evidence, mode = residuals.claim_window_evidence_inventory(
        window, max_units=10, max_sentence_subspans=20,
    )
    assert mode == "primary_claim_block"
    assert evidence[0]["unit_type"] == "primary_claim_block"
    assert evidence[0]["start_char"] == 0
    assert evidence[0]["end_char"] == len(window["text"])
    assert evidence[0]["sentence_subspans"]

    no_blocks = {key: value for key, value in window.items() if key != "primary_claim_blocks"}
    fallback, fallback_mode = residuals.claim_window_evidence_inventory(
        no_blocks, max_units=10, max_sentence_subspans=20,
    )
    assert fallback_mode == "legacy_sentence_fallback"
    assert {item["unit_type"] for item in fallback} == {"legacy_sentence_fallback"}

    prompt_view = residuals.prompt_evidence_inventory(evidence)
    assert prompt_view[0]["text"] == evidence[0]["text"]
    assert prompt_view[0]["start_char"] == evidence[0]["start_char"]
    assert prompt_view[0]["end_char"] == evidence[0]["end_char"]
    assert "block_id" not in prompt_view[0]


def test_occurrence_selector_materializes_second_exact_match_without_model_offsets():
    evidence = [{
        "mention_id": "b001", "start_char": 100, "end_char": 119,
        "text": "rash then rash again",
    }]
    normalizations = []
    slots, rejected = residuals.materialize_occurrence_offsets(
        [{
            "evidence_mention_id": "b001",
            "feature_surface": "rash",
            "feature_occurrence_index": 2,
            "diagnostic_role": "supporting",
            "logic_operator": "atomic",
            "feature_components": [],
        }],
        evidence_inventory=evidence,
        normalizations_out=normalizations,
    )
    assert rejected == []
    assert slots[0]["feature_start_char"] == 110
    assert slots[0]["feature_end_char"] == 114
    assert "feature_occurrence_index" not in slots[0]
    assert slots[0]["direction"] == "supports"
    assert normalizations == [{
        "slot_index": 0,
        "action": "direction_derived_from_diagnostic_role",
        "diagnostic_role": "supporting",
        "normalized_value": "supports",
    }]


def test_out_of_range_occurrence_repairs_only_one_exact_match_and_records_it():
    evidence = [{
        "mention_id": "b001", "start_char": 50, "end_char": 54,
        "text": "rash",
    }]
    normalizations = []
    slots, rejected = residuals.materialize_occurrence_offsets(
        [{
            "evidence_mention_id": "b001", "feature_surface": "rash",
            "feature_occurrence_index": 99, "diagnostic_role": "excluding",
            "logic_operator": "atomic", "feature_components": [],
        }],
        evidence_inventory=evidence,
        normalizations_out=normalizations,
    )
    assert rejected == []
    assert slots[0]["feature_start_char"] == 50
    assert slots[0]["direction"] == "argues_against"
    assert [item["action"] for item in normalizations] == [
        "direction_derived_from_diagnostic_role",
        "occurrence_index_repaired_unique_exact_surface",
    ]
    assert normalizations[1]["requested_value"] == 99
    assert "feature_surface" not in normalizations[1]


def test_occurrence_selector_materializes_non_atomic_components_in_same_unit():
    evidence = [{
        "mention_id": "b001", "start_char": 20, "end_char": 40,
        "text": "rash, rash, diarrhea",
    }]
    slots, rejected = residuals.materialize_occurrence_offsets(
        [{
            "evidence_mention_id": "b001",
            "feature_surface": "rash, diarrhea",
            "feature_occurrence_index": 1,
            "diagnostic_role": "supporting",
            "logic_operator": "and",
            "feature_components": [
                {
                    "feature_surface": "rash", "feature_occurrence_index": 2,
                    "feature_type": "symptom", "polarity": "present",
                },
                {
                    "feature_surface": "diarrhea", "feature_occurrence_index": 1,
                    "feature_type": "symptom", "polarity": "present",
                },
            ],
        }],
        evidence_inventory=evidence,
    )
    assert rejected == []
    assert slots[0]["feature_start_char"] == 26
    assert slots[0]["feature_end_char"] == 40
    assert [
        (item["feature_start_char"], item["feature_end_char"])
        for item in slots[0]["feature_components"]
    ] == [(26, 30), (32, 40)]


def test_occurrence_selector_rejects_out_of_range_and_nontrimmed_quotes_atomically():
    evidence = [{
        "mention_id": "b001", "start_char": 5, "end_char": 19,
        "text": "rash then rash",
    }]
    slots, rejected = residuals.materialize_occurrence_offsets(
        [
            {
                "evidence_mention_id": "b001", "feature_surface": "rash",
                "feature_occurrence_index": 1, "logic_operator": "atomic",
                "diagnostic_role": "supporting",
                "feature_components": [],
            },
            {
                "evidence_mention_id": "b001", "feature_surface": "rash",
                "feature_occurrence_index": 3, "logic_operator": "atomic",
                "diagnostic_role": "supporting",
                "feature_components": [],
            },
        ],
        evidence_inventory=evidence,
    )
    assert slots == []
    assert rejected == [{
        "slot_index": 1,
        "errors": ["feature_occurrence_index_out_of_range"],
    }]
    slots, rejected = residuals.materialize_occurrence_offsets(
        [{
            "evidence_mention_id": "b001", "feature_surface": " rash",
            "feature_occurrence_index": 1, "logic_operator": "atomic",
            "diagnostic_role": "supporting",
            "feature_components": [],
        }],
        evidence_inventory=evidence,
    )
    assert slots == []
    assert rejected[0]["errors"] == ["feature_surface_not_trimmed"]


def test_mixed_primary_context_blocks_only_expose_eligible_evidence():
    _, passages, raw_window, _ = _two_passage_fixture()
    split = raw_window["offset_map"][0]["window_end_char"]
    raw_window["offset_map"][0]["eligible_for_evidence"] = False
    raw_window["primary_claim_blocks"] = [
        {
            "block_id": "subject_context", "window_start_char": 0,
            "window_end_char": split, "block_type": "heading",
            "structural_role": "scope_context", "logic_cues": [],
            "contains_scope_cue": False, "eligible_for_evidence": False,
        },
        {
            "block_id": "diagnostic_evidence", "window_start_char": split + 2,
            "window_end_char": len(raw_window["text"]), "block_type": "criteria_list",
            "structural_role": "diagnostic_criteria", "logic_cues": [],
            "contains_scope_cue": False, "eligible_for_evidence": True,
        },
    ]
    window = residuals.normalize_claim_window(raw_window, passages)
    evidence, mode = residuals.claim_window_evidence_inventory(
        window, max_units=10, max_sentence_subspans=20,
    )
    contexts = residuals.claim_window_context_inventory(window)
    assert mode == "primary_claim_block"
    assert [item["block_id"] for item in evidence] == ["diagnostic_evidence"]
    assert contexts and contexts[0]["text"] == passages[next(iter(passages))]["text"]
    assert all(item["eligible_for_evidence"] is False for item in contexts)


def test_high_signal_empty_detection_is_source_free_and_cache_blocking():
    candidates = [{"candidate_id": "dx001", "label": "Pellagra"}]
    high = residuals.empty_confirmation_signals(
        evidence_inventory=[{
            "mention_id": "b001", "text": "Pellagra diagnosis is clinical.",
            "diagnostic_gate_reasons": ["text:explicit_diagnostic_cue"],
            "block_type": "prose", "structural_role": "prose_claim",
            "contains_scope_cue": False,
        }],
        candidate_inventory=candidates,
        section_path=["Pellagra > Diagnosis"],
    )
    assert "block_local_diagnostic_gate" in high
    assert "candidate_diagnostic_relation_cooccurrence" in high
    assert "diagnostic_section_scope" in high
    assert residuals.requires_empty_confirmation("nothing_extractable", high)
    assert not residuals.requires_empty_confirmation("complete", high)
    assert all("Pellagra" not in code for code in high)

    low = residuals.empty_confirmation_signals(
        evidence_inventory=[{
            "mention_id": "b001", "text": "General background material.",
            "diagnostic_gate_reasons": ["upstream:chunk_type:evaluation"],
            "block_type": "prose", "structural_role": "prose_claim",
            "contains_scope_cue": False,
        }],
        candidate_inventory=candidates,
        section_path=["Introduction"],
    )
    assert low == []
    assert not residuals.requires_empty_confirmation("nothing_extractable", low)


def test_claim_window_cross_passage_evidence_projects_to_two_exact_spans():
    records, passages, raw_window, activity = _two_passage_fixture()
    window = residuals.normalize_claim_window(raw_window, passages)
    evidence = evidence_sentence_inventory(
        {"text": window["text"]}, max_sentences=None,
    )
    feature = "rash and diarrhea"
    slot = {
        "assertion_type": "diagnostic",
        "target_candidate_id": "dx001",
        "target_surface": "",
        "diagnosis_a_candidate_id": "",
        "diagnosis_b_candidate_id": "",
        "favors": "",
        "evidence_mention_id": evidence[0]["mention_id"],
        "feature_surface": feature,
        "feature_occurrence_index": 1,
        "feature_type": "symptom",
        "polarity": "present",
        "diagnostic_role": "typical",
        "direction": "supports",
        "necessity": "not_stated",
        "logic_operator": "atomic",
        "feature_components": [],
        "k": None,
        "scope_note": "",
        "confidence": 0.9,
    }
    materialized, materialization_rejections = (
        residuals.materialize_occurrence_offsets(
            [slot], evidence_inventory=evidence,
        )
    )
    assert materialization_rejections == []
    accumulator = RecordAccumulator(records)
    accepted, rejected = residuals.convert_claim_window_slots(
        window, materialized,
        candidate_inventory=[{"candidate_id": "dx001", "label": "Pellagra"}],
        evidence_inventory=evidence,
        activity_id=activity.id,
        accumulator=accumulator,
        passage_index=passages,
    )
    assert len(accepted) == 1 and rejected == []
    assertion = accumulator.records[accepted[0]]
    assert len(assertion["evidence_span_ids"]) == 2
    spans = [accumulator.records[value] for value in assertion["evidence_span_ids"]]
    assert {span["passage_id"] for span in spans} == set(passages)
    assert all(span["quote"] == passages[span["passage_id"]]["text"] for span in spans)
    assert all(span["passage_id"] != window["window_id"] for span in spans)
    assert_valid_graph(accumulator.values())


def test_claim_block_compiles_cross_sentence_k_of_n_list():
    work = SourceWork(
        title="Criteria manual", publisher="Fixture",
        canonical_url="urn:test:k-of-n", source_family="test",
    )
    version = DocumentVersion(
        source_work_id=work.id, version_label="v1",
        content_sha256=hashlib.sha256(b"k-of-n").hexdigest(),
    )
    section = Section(
        document_version_id=version.id, heading="Diagnostic criteria",
        section_path=("Pellagra", "Diagnostic criteria"), ordinal=0,
    )
    header = Passage(
        section_id=section.id, ordinal=0,
        text="Diagnosis of Pellagra requires 2 of the following:",
    )
    items = Passage(
        section_id=section.id, ordinal=1,
        text="- rash\n- diarrhea\n- dementia",
    )
    activity = ExtractionActivity(
        pipeline_name="test-claim-window", pipeline_version="1",
        extractor_type="llm", input_sha256="c" * 64,
        model="fixture", prompt_sha256="d" * 64,
    )
    records = [
        record_to_dict(value)
        for value in (work, version, section, header, items, activity)
    ]
    passages = {header.id: record_to_dict(header), items.id: record_to_dict(items)}
    text = header.text + "\n\n" + items.text
    raw_window = {
        "window_id": "cw_k_of_n", "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "rechunker_version": "claim-aware-test-v1",
        "section_paths": [["Pellagra", "Diagnostic criteria"]],
        "primary_claim_blocks": [{
            "block_id": "criteria_with_list", "window_start_char": 0,
            "window_end_char": len(text), "block_type": "criteria_list",
            "structural_role": "diagnostic_criteria",
            "logic_cues": ["k_of_n"], "contains_scope_cue": True,
            "eligible_for_evidence": True,
        }],
        "offset_map": [
            {
                "window_start_char": 0, "window_end_char": len(header.text),
                "passage_id": header.id, "passage_start_char": 0,
                "passage_end_char": len(header.text), "kind": "source",
                "eligible_for_evidence": True,
            },
            {
                "window_start_char": len(header.text) + 2,
                "window_end_char": len(text), "passage_id": items.id,
                "passage_start_char": 0, "passage_end_char": len(items.text),
                "kind": "source", "eligible_for_evidence": True,
            },
        ],
    }
    window = residuals.normalize_claim_window(raw_window, passages)
    evidence, mode = residuals.claim_window_evidence_inventory(
        window, max_units=10, max_sentence_subspans=20,
    )
    assert mode == "primary_claim_block" and len(evidence) == 1
    components = []
    for surface in ("rash", "diarrhea", "dementia"):
        components.append({
            "feature_surface": surface,
            "feature_occurrence_index": 1,
            "feature_type": "symptom",
            "polarity": "present",
        })
    feature_surface = "rash\n- diarrhea\n- dementia"
    raw_slots = [{
        "assertion_type": "diagnostic",
        "target_candidate_id": "dx001",
        "evidence_mention_id": evidence[0]["mention_id"],
        "feature_surface": feature_surface,
        "feature_occurrence_index": 1,
        "feature_type": "symptom", "polarity": "present",
        "diagnostic_role": "necessary", "direction": "supports",
        "necessity": "necessary", "logic_operator": "k_of_n",
        "feature_components": components, "k": 2, "confidence": 0.92,
    }]
    materialized, materialization_rejections = (
        residuals.materialize_occurrence_offsets(
            raw_slots, evidence_inventory=evidence,
        )
    )
    assert materialization_rejections == []
    accumulator = RecordAccumulator(records)
    accepted, rejected = residuals.convert_claim_window_slots(
        window,
        materialized,
        candidate_inventory=[{"candidate_id": "dx001", "label": "Pellagra"}],
        evidence_inventory=evidence,
        activity_id=activity.id,
        accumulator=accumulator,
        passage_index=passages,
    )
    assert len(accepted) == 1 and rejected == []
    assertion = accumulator.records[accepted[0]]
    logic = accumulator.records[assertion["criterion_id"]]
    assert logic["record_type"] == "LogicExpression"
    assert logic["operator"] == "k_of_n" and logic["k"] == 2
    assert len(assertion["evidence_span_ids"]) == 2
    assert_valid_graph(accumulator.values())


def test_context_copy_cannot_be_promoted_to_evidence():
    records, passages, raw_window, activity = _two_passage_fixture()
    raw_window["offset_map"][1]["kind"] = "context_copy"
    raw_window["offset_map"][1]["eligible_for_evidence"] = False
    window = residuals.normalize_claim_window(raw_window, passages)
    evidence = evidence_sentence_inventory({"text": window["text"]}, max_sentences=None)
    feature = "rash and diarrhea"
    start = window["text"].index(feature)
    accumulator = RecordAccumulator(records)
    accepted, rejected = residuals.convert_claim_window_slots(
        window,
        [{
            "target_candidate_id": "dx001",
            "evidence_mention_id": evidence[0]["mention_id"],
            "feature_surface": feature,
            "feature_start_char": start,
            "feature_end_char": start + len(feature),
            "feature_type": "symptom", "polarity": "present",
            "diagnostic_role": "typical", "direction": "supports",
            "necessity": "not_stated", "logic_operator": "atomic",
            "feature_components": [], "confidence": 0.9,
        }],
        candidate_inventory=[{"candidate_id": "dx001", "label": "Pellagra"}],
        evidence_inventory=evidence,
        activity_id=activity.id,
        accumulator=accumulator,
        passage_index=passages,
    )
    assert accepted == []
    assert rejected[0]["errors"] == ["source_projection_failed:ClaimWindowError"]
    assert not any(
        row["record_type"] == "DiagnosticAssertion" for row in accumulator.values()
    )


def test_claim_window_cache_key_binds_rechunker_and_offset_map(tmp_path):
    aliases = tmp_path / "aliases.json"
    aliases.write_text("{}\n", encoding="utf-8")
    args = SimpleNamespace(
        disease_aliases=aliases, structured_output="prefer",
        max_input_tokens=12000, max_source_tokens=6000,
        soft_rendered_prompt_tokens=10000, max_output_tokens=3200,
    )
    unit = {
        "semantic_mode": "claim_window", "id": "cw1", "text": "abc",
        "rechunker_version": "v1", "text_sha256": hashlib.sha256(b"abc").hexdigest(),
        "offset_map_sha256": "1" * 64,
    }
    kwargs = {
        "candidates": [{"candidate_id": "dx001", "label": "Disease"}],
        "evidence": [{"mention_id": "s001", "start_char": 0, "end_char": 3, "text": "abc"}],
        "messages": [{"role": "user", "content": "fixture"}],
        "prompt_token_estimates": {"json_schema": 200, "json_object": 300},
        "models": ["fixture"], "args": args,
    }
    first = residuals.cache_key(semantic_unit=unit, **kwargs)
    assert first != residuals.cache_key(
        semantic_unit={**unit, "rechunker_version": "v2"}, **kwargs,
    )
    assert first != residuals.cache_key(
        semantic_unit={**unit, "offset_map_sha256": "2" * 64}, **kwargs,
    )


def test_default_cli_is_claim_window_and_legacy_mode_is_explicit():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--claim-windows"' in source
    assert '"--legacy-passage-queue"' in source
    assert "legacy_mode = args.legacy_passage_queue is not None" in source


def test_source_free_replay_ledger_filters_only_by_semantic_unit_id(tmp_path):
    ledger = tmp_path / "needs_review.jsonl"
    ledger.write_text(
        json.dumps({
            "semantic_unit_id": "cw2", "coverage_status": "review_other",
            "contains_source_text": False,
        }) + "\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        include_unit_ids_from=[ledger], min_residual_priority=0,
        source=None, sample_seed=None, limit=None,
    )
    rows = [
        {"window_id": "cw1", "priority": 1, "text": "must not be copied"},
        {"window_id": "cw2", "priority": 1, "text": "internal source"},
    ]
    selected = residuals.select_queue(rows, args)
    assert [row["window_id"] for row in selected] == ["cw2"]
    assert residuals.load_included_unit_ids([ledger]) == {"cw2"}
    assert "internal source" not in ledger.read_text(encoding="utf-8")


def test_optional_private_rejection_is_mode_0600_and_public_summary_is_source_free(
    tmp_path,
):
    private = tmp_path / "private_rejections.jsonl"
    response = {
        "assertions": [{"feature_surface": "private exact quote"}],
        "coverage_status": "complete",
    }
    residuals.append_private_rejection(
        private,
        semantic_mode="claim_window", semantic_unit_id="cw1",
        cache_key_value="k" * 64, stage="fixture",
        response_object=response,
        rejections=[{"slot_index": 0, "errors": ["fixture_error"]}],
    )
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    private_row = json.loads(private.read_text(encoding="utf-8"))
    assert private_row["response"] == response
    public = {
        "semantic_unit_id": "cw1", "response_sha256": private_row["response_sha256"],
        "error": "slot_rejections",
    }
    assert "private exact quote" not in json.dumps(public)


def _provider_prepared(index: int):
    return {
        "semantic_mode": "legacy_passage",
        "semantic_unit_id": f"p{index}",
        "semantic_unit": {
            "semantic_mode": "legacy_passage", "id": f"p{index}",
            "text": f"fixture {index}",
        },
        "evidence": [],
        "evidence_unit_mode": "legacy_passage_sentence",
        "messages": [{"role": "user", "content": f"fixture {index}"}],
        "source_tokens": 3,
        "prompt_token_estimates": {"json_schema": 10, "json_object": 12},
        "rendered_prompt_tokens_worst_case": 12,
        "cache_key": f"key{index}",
    }


def _successful_provider_result(job, accounted=5):
    return residuals.ProviderCallResult(
        prepared_index=job.prepared_index,
        semantic_call=job.semantic_call,
        response_object={
            "assertions": [], "coverage_status": "nothing_extractable",
            "fixture_index": job.prepared_index,
        },
        response_model="fixture",
        telemetry_rows=[],
        provider_reported_tokens=accounted,
        budget_accounted_tokens=accounted,
        completed_monotonic=time.monotonic(),
    )


def test_workers_one_and_four_have_identical_prepared_order_results():
    jobs = [
        residuals.ProviderJob(index, index + 1, _provider_prepared(index), 20)
        for index in range(6)
    ]

    def fake_worker(job):
        # Reverse latency forces completion-order differences with concurrency.
        time.sleep((6 - job.prepared_index) * 0.002)
        return _successful_provider_result(job)

    serial, serial_budget, _, serial_stopped, _ = residuals.execute_provider_jobs(
        jobs, workers=1, budget_total_tokens=1000, worker_fn=fake_worker,
    )
    parallel, parallel_budget, _, parallel_stopped, stats = (
        residuals.execute_provider_jobs(
            jobs, workers=4, budget_total_tokens=1000, worker_fn=fake_worker,
        )
    )
    serial_ordered = [serial[index].response_object for index in range(6)]
    parallel_ordered = [parallel[index].response_object for index in range(6)]
    assert serial_ordered == parallel_ordered
    assert serial_budget == parallel_budget == 30
    assert serial_stopped == parallel_stopped == []
    assert stats["provider_jobs_submitted"] == 6
    assert stats["max_reserved_inflight_tokens"] == 80


def test_concurrent_worker_exception_is_isolated_and_conservatively_charged():
    jobs = [
        residuals.ProviderJob(index, index + 1, _provider_prepared(index), 20)
        for index in range(3)
    ]

    def fake_worker(job):
        if job.prepared_index == 1:
            raise RuntimeError("fixture worker crash")
        return _successful_provider_result(job, accounted=4)

    results, accounted, reported, stopped, stats = residuals.execute_provider_jobs(
        jobs, workers=3, budget_total_tokens=100, worker_fn=fake_worker,
    )
    assert set(results) == {0, 1, 2}
    assert results[1].response_object is None
    assert results[1].telemetry_rows[0]["status"] == "provider_worker_exception"
    assert results[1].telemetry_rows[0]["error_sha256"]
    assert "fixture worker crash" not in json.dumps(results[1].telemetry_rows)
    assert accounted == 28  # two reported successes plus full failed reservation
    assert reported == 8
    assert stopped == []
    assert stats["provider_jobs_submitted"] == 3


def test_budget_reservation_prevents_excess_inflight_and_stops_in_order():
    jobs = [
        residuals.ProviderJob(index, index + 1, _provider_prepared(index), 60)
        for index in range(3)
    ]
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_worker(job):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.005)
        with lock:
            active -= 1
        return _successful_provider_result(job, accounted=50)

    results, accounted, reported, stopped, stats = residuals.execute_provider_jobs(
        jobs, workers=4, budget_total_tokens=100, worker_fn=fake_worker,
    )
    assert set(results) == {0}
    assert accounted == reported == 50
    assert stopped == [1, 2]
    assert max_active == 1
    assert stats == {
        "provider_jobs_planned": 3,
        "provider_jobs_submitted": 1,
        "provider_jobs_budget_stopped": 2,
        "max_reserved_inflight_tokens": 60,
    }


def test_worst_case_reservation_covers_all_models_modes_and_retries():
    reserved = residuals.worst_case_provider_reservation(
        {"json_schema": 100, "json_object": 125},
        models=["primary", "fallback"],
        structured_modes=["json_schema", "json_object"],
        max_attempts_per_model=2,
        max_output_tokens=50,
    )
    assert reserved == 2 * 2 * ((100 + 50) + (125 + 50))


def test_429_retry_after_is_honored_inside_provider_worker():
    prepared = _provider_prepared(0)
    job = residuals.ProviderJob(0, 1, prepared, 100)
    attempts = 0
    sleeps = []

    def fake_post(**_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise residuals.OpenRouterError(429, "rate limited", retry_after=3.0)
        return ({
            "_parsed_content": {
                "assertions": [], "coverage_status": "nothing_extractable",
            },
            "model": "fixture", "provider": "fixture",
            "choices": [{"finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }, "json_schema")

    result = residuals.run_provider_job(
        job,
        api_key="not-a-real-key",
        models=["fixture"],
        structured_modes=["json_schema"],
        max_attempts_per_model=2,
        max_output_tokens=20,
        timeout_seconds=1,
        soft_rendered_prompt_tokens=100,
        post_fn=fake_post,
        sleep_fn=sleeps.append,
    )
    assert attempts == 2
    assert sleeps == [3.0]
    assert result.response_object["coverage_status"] == "nothing_extractable"
    assert [row["status"] for row in result.telemetry_rows] == [
        "provider_error", "provider_success",
    ]
    assert result.telemetry_rows[0]["retry_sleep_seconds"] == 3.0
    assert result.provider_reported_tokens == 12
    assert result.budget_accounted_tokens == 12


def test_gemini_schema_http_400_falls_through_to_locally_validated_json_object():
    prepared = _provider_prepared(0)
    job = residuals.ProviderJob(0, 1, prepared, 100)
    modes = []

    def fake_post(**kwargs):
        modes.append(kwargs["structured_mode"])
        if kwargs["structured_mode"] == "json_schema":
            raise residuals.OpenRouterError(
                400, "schema rejected",
                error_category="structured_schema_http_400",
            )
        return ({
            "_parsed_content": {
                "assertions": [], "coverage_status": "nothing_extractable",
            },
            "model": "google/gemini-2.5-flash", "provider": "Google",
            "choices": [{"finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }, "json_object")

    result = residuals.run_provider_job(
        job,
        api_key="not-a-real-key",
        models=["google/gemini-2.5-flash"],
        structured_modes=["json_schema", "json_object"],
        max_attempts_per_model=2,
        max_output_tokens=3200,
        timeout_seconds=1,
        soft_rendered_prompt_tokens=100,
        post_fn=fake_post,
    )
    assert modes == ["json_schema", "json_object"]
    assert result.response_object == {
        "assertions": [], "coverage_status": "nothing_extractable",
    }
    assert result.telemetry_rows[0]["error_category"] == (
        "structured_schema_http_400"
    )
    assert result.telemetry_rows[1]["structured_mode"] == "json_object"


def test_cli_workers_default_and_safe_cap_are_explicit():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--workers", type=int, default=1' in source
    assert 'if not 1 <= args.workers <= 8:' in source


def test_failed_incremental_call_validation_rolls_back_without_partial_write():
    records, passages, _window, _activity = _two_passage_fixture()
    accumulator = RecordAccumulator(
        records, merge_identity_metadata=False,
    )
    validation_index = GraphValidationIndex(records)
    original_ids = list(accumulator.records)
    original_validation_count = validation_index.record_count
    tracker = accumulator.begin_delta()
    feature = accumulator.add(FeaturePattern(
        canonical_label="rash", feature_type="symptom", surface="rash",
        temporality={"relation": "not_stated"},
    ))
    passage = next(iter(passages.values()))
    accumulator.add(EvidenceSpan(
        passage_id=passage["id"], start_char=0, end_char=8,
        quote="not text",
    ))

    try:
        residuals.commit_validated_call_delta(
            accumulator, tracker, validation_index,
        )
    except GuidelineKGValidationError as exc:
        assert any("quote must exactly equal" in error for error in exc.errors)
    else:
        raise AssertionError("invalid delta must fail atomically")
    assert list(accumulator.records) == original_ids
    assert feature["id"] not in accumulator.records
    assert validation_index.record_count == original_validation_count
