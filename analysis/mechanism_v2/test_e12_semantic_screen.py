from __future__ import annotations

from analysis.mechanism_v2.e12_semantic_screen import RELATIONS, _validator, case_documents


def test_validator_requires_exact_candidate_coverage() -> None:
    validate = _validator({"D1", "D2"})
    valid = {"candidate_relations": [
        {"candidate_id": "D1", "relation": "exact_equivalent", "reason": "same"},
        {"candidate_id": "D2", "relation": "unrelated", "reason": "different"},
    ]}
    assert validate(valid) is None
    valid["candidate_relations"].pop()
    assert "exactly once" in str(validate(valid))


def test_relation_vocabulary_is_conservative_and_closed() -> None:
    assert set(RELATIONS) == {
        "exact_equivalent", "acceptable_clinical_variant",
        "broader_or_narrower_not_equivalent", "related_not_equivalent",
        "unrelated", "uncertain",
    }


def test_real_documents_use_only_frozen_ids_and_isolate_s3_only() -> None:
    documents = case_documents(__import__("analysis.mechanism_v2.e12_e7_factorial", fromlist=["DEFAULT_OUT"]).DEFAULT_OUT)
    assert len(documents) == 300
    assert sum(row["family"] == "DA" for row in documents) == 150
    for row in documents:
        ids = [candidate["candidate_id"] for candidate in row["candidates"]]
        assert len(ids) == len(set(ids))
        assert all(candidate["origin"] in {"frozen_s2_pool", "historical_s3_only_excluded_from_e12"} for candidate in row["candidates"])
