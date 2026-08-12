from analysis.mechanism_v2.e8_manual_audit import MANUAL


def test_manual_codes_and_required_reasons():
    assert len(MANUAL) == 30
    for row in MANUAL.values():
        assert row["ledger_a_fidelity"] in {"faithful", "minor_error", "major_error"}
        assert row["reference_identifiability"] in {"direct", "partial", "absent"}
        assert row["reference_hard_veto_validity"] in {
            "overreach", "invalid_construction", "not_applicable"
        }
        assert row["invalid_time_meaning_change"] in {"changed", "not_applicable"}
        assert row["primary_mechanism"] and row["reason"]
