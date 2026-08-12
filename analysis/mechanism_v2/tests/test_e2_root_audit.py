from __future__ import annotations

from analysis.mechanism_v2.e2_root_audit import (
    _binary_metrics,
    _bootstrap_delta,
    _weighted_rate,
)
from analysis.mechanism_v2.e2_root_consensus_decisions import (
    CONSENSUS_SWEEP_RELATION_CODES,
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


def test_binary_metrics_exposes_false_positive_precision() -> None:
    result = _binary_metrics(
        [
            (True, True),
            (True, False),
            (False, True),
            (False, False),
            (False, False),
        ]
    )
    assert result["true_positive"] == 1
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1
    assert result["true_negative"] == 2
    assert result["precision"] == 0.5
    assert result["accuracy"] == 0.6


def test_consensus_sweep_decisions_cover_frozen_queue() -> None:
    assert len(CONSENSUS_SWEEP_RELATION_CODES) == 1070
    assert set(CONSENSUS_SWEEP_RELATION_CODES).issubset({"C", "P", "X", "M", "N", "U"})
