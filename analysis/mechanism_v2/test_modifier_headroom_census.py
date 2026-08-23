from analysis.mechanism_v2.modifier_headroom_census import (
    _axis_availability,
    _gwet_ac1,
    _validate,
)


def test_validator_requires_literal_support_for_determinable_claims():
    vignette = "Biopsy showed an ichthyosiform pattern."
    response = {
        "core_entity": "mycosis fungoides",
        "core_candidate_id": "D1",
        "modifier_claims": [
            {
                "axis": "subtype",
                "value": "ichthyosiform",
                "availability": "explicitly_stated",
                "support_quote": "ichthyosiform pattern",
            }
        ],
    }
    assert _validate(response, vignette=vignette, allowed={"D1"}) is None
    response["modifier_claims"][0]["support_quote"] = "fish-scale pattern"
    assert "verbatim substring" in str(
        _validate(response, vignette=vignette, allowed={"D1"})
    )


def test_axis_availability_ignores_wording_but_fails_closed_within_axis():
    review = {
        "modifier_claims": [
            {
                "axis": "complication",
                "value": "DAH",
                "availability": "clinically_inferable",
            },
            {
                "axis": "complication",
                "value": "respiratory failure",
                "availability": "not_determinable",
            },
            {
                "axis": "anatomy",
                "value": "left ventricle",
                "availability": "explicitly_stated",
            },
        ]
    }
    assert _axis_availability(review, True) == {
        "complication": "not_determinable",
        "anatomy": "determinable",
    }
    assert _axis_availability(review, False) == {}


def test_gwet_ac1_extremes():
    assert _gwet_ac1([("determinable", "determinable")] * 10) == 1.0
    assert _gwet_ac1(
        [("determinable", "not_determinable")] * 10
    ) < 0.0
