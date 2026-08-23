from analysis.mechanism_v2.manual_surrogate_adjudication import (
    _batch_assignment,
    _duplicate_assignment,
    _validate_case,
)


def test_batch_assignment_partitions_all_cases():
    cases = [f"C{i:02d}" for i in range(50)]
    batches = [_batch_assignment(cases, batch) for batch in range(5)]
    assert all(len(batch) == 10 for batch in batches)
    assert set.union(*batches) == set(cases)
    assert sum(len(batch) for batch in batches) == 50


def test_duplicate_assignment_is_deterministic():
    cases = [f"C{i:02d}" for i in range(50)]
    assert _duplicate_assignment(cases) == _duplicate_assignment(cases)
    assert len(_duplicate_assignment(cases)) == 10


def test_validate_case_requires_literal_positive_quotes():
    row = {
        "case_key": "C01",
        "core_entity": "disease",
        "core_candidate_id": "D1",
        "construction_changed": False,
        "claims": [
            {
                "manual_claim_id": "H01",
                "axis": "subtype",
                "value": "atypical",
                "availability": "explicitly_stated",
                "support_quotes": ["atypical finding"],
                "reasoning": "The record states it.",
                "confidence": "high",
                "source_urls": [],
            }
        ],
        "case_confidence": "high",
        "notes": "",
    }
    assert not _validate_case(
        row, vignette="An atypical finding was seen.", allowed_candidates={"D1"}
    )
    row["claims"][0]["support_quotes"] = ["paraphrase"]
    errors = _validate_case(
        row, vignette="An atypical finding was seen.", allowed_candidates={"D1"}
    )
    assert "C01:claim_0:nonliteral_quote" in errors
