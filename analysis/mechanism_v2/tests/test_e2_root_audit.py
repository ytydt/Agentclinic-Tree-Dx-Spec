from __future__ import annotations

from analysis.mechanism_v2.e2_root_audit import (
    _bootstrap_delta,
    _weighted_rate,
)


def test_weighted_rate_uses_design_weights() -> None:
    rows = [
        {"weight": 1.0, "hit": True},
        {"weight": 3.0, "hit": False},
    ]
    result = _weighted_rate(rows, "hit")
    assert result["sample_positive_n"] == 1
    assert result["weighted_rate"] == 0.25


def test_stratified_bootstrap_observed_delta() -> None:
    rows = [
        {
            "family": "DA",
            "slice": "x",
            "primary_stratum": "a",
            "weight": 2.0,
            "left": False,
            "right": True,
        },
        {
            "family": "DA",
            "slice": "x",
            "primary_stratum": "a",
            "weight": 2.0,
            "left": True,
            "right": True,
        },
    ]
    result = _bootstrap_delta(rows, "left", "right", "test", 200)
    assert result["delta"] == 0.5
    assert len(result["ci95"]) == 2
