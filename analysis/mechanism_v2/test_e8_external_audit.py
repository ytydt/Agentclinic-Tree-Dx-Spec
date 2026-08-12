from analysis.mechanism_v2.e8_external_audit import audit_selection, validate


def test_proxy_schema_validator():
    good = {
        "event_reviews": [{"event_id": "N1", "fidelity": "faithful", "issues": []}],
        "ledger_overall": "faithful", "reference_identifiability": "direct",
        "reference_reason": "explicit", "reference_hard_veto_validity": "overreach",
        "veto_reason": "non-obligate", "ledger_b_meaning_change": "changed",
        "ledger_b_reason": "time moved", "ranker_logic_issues": [], "overall_note": "ok",
    }
    assert validate(good, {"N1"}) is None
    good["event_reviews"][0]["event_id"] = "N2"
    assert validate(good, {"N1"}) is not None
