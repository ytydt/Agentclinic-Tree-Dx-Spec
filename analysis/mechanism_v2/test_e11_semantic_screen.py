from __future__ import annotations

from analysis.mechanism_v2.e11_b07_factorial import DEFAULT_OUT
from analysis.mechanism_v2.e11_semantic_screen import (
    BUNDLE_NAMES,
    _validator,
    case_documents,
)


def test_case_documents_have_complete_masked_factorial() -> None:
    documents = case_documents(DEFAULT_OUT)
    assert len(documents) == 400
    assert all(len(row["chunks"]) == 18 for row in documents)
    assert all({bundle["bundle"] for bundle in row["bundles"]} == set(BUNDLE_NAMES) for row in documents)
    assert all(2 <= len(row["candidate_registry"]) <= 9 for row in documents)


def test_validator_accepts_complete_minimal_response() -> None:
    validate = _validator({"C1", "C2"}, {"R1", "N1", "H1"})
    response = {
        "candidate_relations": [
            {"candidate_id": "C1", "relation": "exact_equivalent"},
            {"candidate_id": "C2", "relation": "unrelated"},
        ],
        "chunk_assessments": [
            {
                "chunk_id": chunk_id,
                "relation_to_reference": "generic_or_unrelated",
                "relation_to_generated_top1": "not_about",
                "vignette_applicability": "no_fit",
            }
            for chunk_id in ("R1", "N1", "H1")
        ],
        "bundle_assessments": [
            {
                "bundle": bundle,
                "reference_support": "absent",
                "generated_top1_support": "absent",
                "confirmation_pressure": "balanced_or_neutral",
                "clinically_misleading": "no",
            }
            for bundle in BUNDLE_NAMES
        ],
    }
    assert validate(response) is None
    response["bundle_assessments"][0]["bundle"] = "wrong"
    assert validate(response)
