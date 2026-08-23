from analysis.mechanism_v2.claim_first_modifier_calibration import (
    _availability_validator,
    _construction_validator,
    _selected_cases,
)


def test_selected_cases_are_frozen_and_deterministic():
    first = _selected_cases()
    second = _selected_cases()
    assert len(first) == 50
    assert [row["case_key"] for row in first] == [
        row["case_key"] for row in second
    ]
    assert all(row["family"] == "DA" for row in first)


def test_construction_validator_rejects_unknown_candidate_and_duplicates():
    validate = _construction_validator({"D1"})
    good = {
        "core_entity": "mycosis fungoides",
        "core_candidate_id": "D1",
        "modifier_claims": [
            {"axis": "subtype", "value": "ichthyosiform"}
        ],
    }
    assert validate(good) is None
    good["core_candidate_id"] = "D2"
    assert validate(good) == "core_candidate_id is not supplied"
    good["core_candidate_id"] = "D1"
    good["modifier_claims"].append(
        {"axis": "subtype", "value": "  ICHTHYOSIFORM  "}
    )
    assert validate(good) == "duplicate modifier claim"


def test_availability_validator_requires_exact_claim_coverage():
    validate = _availability_validator({"M01", "M02"})
    good = {
        "claims": [
            {
                "claim_id": "M01",
                "availability": "explicitly_stated",
                "support_quote": "literal",
            },
            {
                "claim_id": "M02",
                "availability": "not_determinable",
                "support_quote": "",
            },
        ]
    }
    assert validate(good) is None
    good["claims"].pop()
    assert validate(good) == (
        "claims must cover every supplied claim_id exactly once"
    )
