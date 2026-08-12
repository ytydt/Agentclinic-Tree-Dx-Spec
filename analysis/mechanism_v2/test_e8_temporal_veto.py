from analysis.mechanism_v2.e8_temporal_veto import (
    INVALID,
    LEGAL,
    SOFT,
    permute_ledger,
    redacted_context,
    selector_ledger,
    validate_builder,
    validate_selector,
)


EVENTS = [
    {
        "event_id": "N1", "source_quote": "Initially no fever was present.",
        "observation": "fever absent", "negation_kind": "absence",
        "time_anchor": "initially", "episode_id": "initial presentation",
        "scope": "patient", "anatomy": "systemic", "test_context": "unspecified",
        "sensitivity": "unknown", "sensitivity_basis": "unspecified",
    },
    {
        "event_id": "N2", "source_quote": "Later blood cultures were negative.",
        "observation": "blood cultures negative", "negation_kind": "test_negative",
        "time_anchor": "later", "episode_id": "later admission", "scope": "patient",
        "anatomy": "blood", "test_context": "blood cultures", "sensitivity": "adequate",
        "sensitivity_basis": "unspecified",
    },
]


def test_builder_and_redaction_contract():
    vignette = "Initially no fever was present. She worsened. Later blood cultures were negative."
    response = {"negative_events": EVENTS}
    assert validate_builder(response, vignette) is None
    redacted = redacted_context(vignette, EVENTS)
    assert "Initially no fever" not in redacted
    assert "NEGATIVE_EVENT_N1" in redacted and "NEGATIVE_EVENT_N2" in redacted


def test_legal_changes_only_order_and_invalid_changes_only_time_episode():
    base = selector_ledger(EVENTS)
    legal = permute_ledger("case/1", EVENTS, LEGAL)
    assert sorted(legal, key=lambda row: row["event_id"]) == base
    invalid = permute_ledger("case/1", EVENTS, INVALID)
    assert [row["observation"] for row in invalid] == [row["observation"] for row in base]
    assert [row["time_anchor"] for row in invalid] == ["later", "initially"]
    assert [row["episode_id"] for row in invalid] == ["later admission", "initial presentation"]


def test_selector_rejects_unknown_ids():
    good = {
        "champion_id": "D1", "runner_up_id": "D2",
        "active_vetoes": [{"candidate_id": "D2", "event_ids": ["N1"], "severity": "soft", "reason": "early"}],
        "margin": "low", "rationale": "contrast",
    }
    assert validate_selector(good, {"D1", "D2"}, {"N1", "N2"}) is None
    bad = dict(good)
    bad["active_vetoes"] = [{"candidate_id": "D9", "event_ids": ["N1"], "severity": "hard", "reason": "x"}]
    assert validate_selector(bad, {"D1", "D2"}, {"N1", "N2"}) is not None
