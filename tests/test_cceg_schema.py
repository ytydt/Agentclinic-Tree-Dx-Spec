from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from agentclinic_tree_dx.knowledge.cceg_schema import (
    CCEGValidationError,
    assert_valid_claim,
    claim_json_schema,
    validate_claim,
)

ROOT = Path(__file__).resolve().parents[1]


def _valid_claim() -> dict:
    quote = (
        "Elevated PTH supports primary hyperparathyroidism, whereas suppressed "
        "PTH favors a non-parathyroid cause of hypercalcemia."
    )
    return {
        "schema_version": 1,
        "claim_id": "cceg_0123456789ab",
        "claim_type": "direction",
        "candidate_a": {
            "name": "primary hyperparathyroidism",
            "id": "MONDO:0005200",
            "id_provenance": "MONDO test fixture",
            "l1_parent": "PTH-mediated hypercalcemia",
        },
        "candidate_b": {
            "name": "malignancy-associated hypercalcemia",
            "id": None,
            "id_provenance": None,
            "l1_parent": "non-PTH-mediated hypercalcemia",
        },
        "finding": {
            "surface": "elevated parathyroid hormone",
            "event_type": "laboratory",
            "concepts": [{
                "system": "HPO",
                "code": "HP:0003165",
                "display": "Elevated circulating parathyroid hormone level",
                "provenance": "test fixture",
                "confidence": 1.0,
            }],
            "polarity": 1,
            "value_state": "elevated",
            "value": None,
            "unit": None,
            "specimen": "serum",
            "temporal": {
                "onset": None, "duration": None,
                "relation": None, "anchor": None,
            },
            "context": {},
            "abstained": False,
        },
        "relation": "supports_a",
        "recommended_test": None,
        "strength": "explicit",
        "source_class": "cpg_prose",
        "allowed_consumers": ["audit", "p3_soft", "p4_soft"],
        "comparator": {
            "required": True,
            "has_support_excerpt": True,
            "has_contrast_excerpt": True,
            "contrast_candidates": ["malignancy-associated hypercalcemia"],
        },
        "provenance": {
            "source_id": "cpg:test",
            "chunk_id": "cpg:test:chunk:1",
            "article_id": "test-article",
            "section": "Evaluation",
            "chunk_type": "evaluation",
            "quote": quote,
            "quote_span": [10, 10 + len(quote)],
            "url": "https://example.test/guideline",
            "evidence_grade": "test-only",
        },
        "extraction": {
            "pipeline": "cceg_test",
            "model": "deterministic-test",
            "prompt_sha256": "a" * 64,
            "confidence": 1.0,
            "entailment_status": "grounded",
            "normalization_abstained": False,
            "normalization_reason": None,
        },
        "audit": {
            "enumeration_only": False,
            "pair_binding_ok": True,
            "negation_scope_ok": True,
            "value_scope_ok": True,
        },
        "review": {
            "status": "accepted",
            "reviewer_ids": ["clinician-a", "clinician-b"],
            "adjudication": "test fixture",
        },
        "split": {
            "document_family": "hypercalcemia",
            "document_split": "audit",
            "family_held_out": False,
            "pilot_scope": True,
        },
        "claim_status": "grounded",
    }


def _synthetic_review() -> dict:
    return {
        "status": "accepted",
        "reviewer_ids": ["reviewer-a", "reviewer-b"],
        "adjudication": "reviewers agreed",
        "mode": "synthetic_dual_llm",
        "reviewer_runs": [
            {
                "reviewer_id": "reviewer-a",
                "model": "test-model-a",
                "prompt": "independent reviewer prompt a",
                "prompt_sha256": "b" * 64,
                "seed": 11,
            },
            {
                "reviewer_id": "reviewer-b",
                "model": "test-model-b",
                "prompt": "independent reviewer prompt b",
                "prompt_sha256": "c" * 64,
                "seed": 29,
            },
        ],
    }


def _valid_candidate_effect() -> dict:
    claim = _valid_claim()
    claim.update({
        "schema_version": 2,
        "claim_type": "candidate_effect",
        "candidate_b": None,
        "relation": "supports_candidate",
        "allowed_consumers": [
            "audit", "research_p3_soft", "research_p4_soft",
        ],
        "comparator": {
            "required": False,
            "has_support_excerpt": True,
            "has_contrast_excerpt": False,
            "contrast_candidates": [],
        },
        "provenance_bundle": [],
        "derivation": None,
        "review": _synthetic_review(),
        "claim_status": "research_validated",
    })
    return claim


def _valid_derived_contrast() -> dict:
    claim = _valid_candidate_effect()
    second_provenance = deepcopy(claim["provenance"])
    second_provenance.update({
        "source_id": "cpg:test:second",
        "chunk_id": "cpg:test:chunk:2",
        "section": "Differential diagnosis",
    })
    claim.update({
        "claim_id": "cceg_abcdef012345",
        "claim_type": "derived_contrast",
        "candidate_b": deepcopy(_valid_claim()["candidate_b"]),
        "relation": "supports_a",
        "source_class": "composed",
        "allowed_consumers": ["audit", "research_p5_soft"],
        "comparator": {
            "required": True,
            "has_support_excerpt": True,
            "has_contrast_excerpt": True,
            "contrast_candidates": ["malignancy-associated hypercalcemia"],
        },
        "provenance_bundle": [
            deepcopy(claim["provenance"]), second_provenance,
        ],
        "provenance": None,
        "derivation": {
            "derived": True,
            "premise_claim_ids": [
                "cceg_111111111111", "cceg_222222222222",
            ],
            "composition_rule": (
                "supports_a_from_support_a_and_argues_against_b"),
        },
    })
    claim["extraction"]["pipeline"] = "deterministic_composition"
    claim["extraction"]["model"] = "deterministic-composer"
    return claim


def _audit_module():
    spec = importlib.util.spec_from_file_location(
        "cceg_audit_test", ROOT / "scripts/audit_cceg_claims.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_grounded_pair_claim_satisfies_frozen_v1_contract():
    claim = _valid_claim()
    assert validate_claim(claim) == []
    assert_valid_claim(claim)


def test_case_report_cannot_emit_direction_claim():
    claim = _valid_claim()
    claim["source_class"] = "case_report_list"
    claim["strength"] = "anecdotal"
    errors = validate_claim(claim)
    assert any("source_policy" in error for error in errors)


def test_case_report_enumeration_can_only_ground_membership():
    claim = _valid_claim()
    claim["claim_type"] = "membership"
    claim["candidate_b"] = None
    claim["relation"] = "member_of"
    claim["source_class"] = "case_report_list"
    claim["strength"] = "anecdotal"
    claim["allowed_consumers"] = ["audit", "p5_veto"]
    claim["comparator"] = {
        "required": False,
        "has_support_excerpt": False,
        "has_contrast_excerpt": False,
        "contrast_candidates": [],
    }
    claim["audit"]["enumeration_only"] = True
    claim["review"]["reviewer_ids"] = ["clinician-a"]
    assert validate_claim(claim) == []


def test_pair_claim_requires_contrast_and_two_reviewers():
    claim = _valid_claim()
    claim["candidate_b"] = None
    claim["comparator"]["has_contrast_excerpt"] = False
    claim["comparator"]["contrast_candidates"] = []
    claim["review"]["reviewer_ids"] = ["clinician-a"]
    errors = validate_claim(claim)
    assert any("candidate_b" in error for error in errors)
    assert any("has_contrast_excerpt" in error for error in errors)
    assert any("requires 2 reviewer" in error for error in errors)


def test_normalization_abstention_never_fabricates_concepts():
    claim = _valid_claim()
    claim["finding"]["concepts"] = []
    claim["finding"]["abstained"] = True
    claim["extraction"]["normalization_abstained"] = True
    claim["extraction"]["normalization_reason"] = "no licensed mapping"
    assert validate_claim(claim) == []


def test_invalid_claim_raises_all_errors():
    claim = _valid_claim()
    claim["provenance"]["quote_span"] = [0, 1]
    with pytest.raises(CCEGValidationError) as exc:
        assert_valid_claim(claim)
    assert any("quote_span" in error for error in exc.value.errors)


def test_batch_audit_rejects_duplicate_claim_ids():
    module = _audit_module()
    claim = _valid_claim()
    report = module.audit([claim, deepcopy(claim)])
    assert report["invalid_claims"] == 1
    assert report["duplicate_ids"] == [claim["claim_id"]]
    assert not report["publishable"]


def test_exported_json_schema_matches_python_contract():
    exported = json.loads(
        (ROOT / "data/eval/cceg_claim_schema_v1.json").read_text())
    assert exported == claim_json_schema()


def test_v2_synthetic_candidate_effect_is_research_only():
    claim = _valid_candidate_effect()
    assert validate_claim(claim) == []

    claim["allowed_consumers"].append("p4_soft")
    errors = validate_claim(claim)
    assert any("cannot grant clinical consumers" in error for error in errors)


def test_v2_candidate_effect_cannot_bypass_composition_for_p5():
    claim = _valid_candidate_effect()
    claim["allowed_consumers"] = ["audit", "research_p5_soft"]
    errors = validate_claim(claim)
    assert any("cannot enter a P5 consumer" in error for error in errors)

    claim = _valid_candidate_effect()
    claim["relation"] = "associated_with"
    errors = validate_claim(claim)
    assert any("audit-only" in error for error in errors)


@pytest.mark.parametrize(
    "source_class", ["cpg_enumeration", "case_report_list", "case_report_prose"])
def test_v2_candidate_effect_obeys_source_permissions(source_class):
    claim = _valid_candidate_effect()
    claim["source_class"] = source_class
    if source_class.startswith("case_report"):
        claim["strength"] = "anecdotal"
    errors = validate_claim(claim)
    assert any("source_policy" in error for error in errors)


def test_v2_synthetic_review_cannot_masquerade_as_human_grounded():
    claim = _valid_candidate_effect()
    claim["claim_status"] = "grounded"
    claim["allowed_consumers"] = ["audit", "p3_soft"]
    errors = validate_claim(claim)
    assert any(
        "requires claim_status=research_validated" in error for error in errors)
    assert any("cannot grant clinical consumers" in error for error in errors)

    claim = _valid_candidate_effect()
    claim["review"]["reviewer_runs"] = claim["review"]["reviewer_runs"][:1]
    errors = validate_claim(claim)
    assert any("two independent reviewer runs" in error for error in errors)


def test_v2_derived_contrast_requires_complete_composition_provenance():
    claim = _valid_derived_contrast()
    assert validate_claim(claim) == []

    claim["provenance"] = deepcopy(claim["provenance_bundle"][0])
    claim["provenance_bundle"] = claim["provenance_bundle"][:1]
    claim["derivation"]["derived"] = False
    errors = validate_claim(claim)
    assert any("must not fabricate a single source" in error for error in errors)
    assert any("at least two premise provenances" in error for error in errors)
    assert any("derivation.derived" in error for error in errors)


def test_v2_derived_contrast_is_composed_only():
    claim = _valid_derived_contrast()
    claim["source_class"] = "cpg_prose"
    errors = validate_claim(claim)
    assert any("requires source_class=composed" in error for error in errors)

    claim = _valid_derived_contrast()
    claim["allowed_consumers"] = ["audit", "research_p4_soft"]
    errors = validate_claim(claim)
    assert any("composed-only P5 research evidence" in error for error in errors)

    claim = _valid_derived_contrast()
    claim["extraction"]["pipeline"] = "llm_direct_extraction"
    errors = validate_claim(claim)
    assert any("deterministic_composition" in error for error in errors)


def test_v1_rejects_v2_claim_types_and_keeps_default_schema_api():
    claim = _valid_candidate_effect()
    claim["schema_version"] = 1
    errors = validate_claim(claim)
    assert any("claim_type: invalid" in error for error in errors)
    assert claim_json_schema()["properties"]["schema_version"] == {"const": 1}


def test_exported_v2_json_schema_matches_python_contract():
    exported = json.loads(
        (ROOT / "data/eval/cceg_claim_schema_v2.json").read_text())
    assert exported == claim_json_schema(2)
