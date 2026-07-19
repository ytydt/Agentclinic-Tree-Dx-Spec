from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import analyze_l2_a_variant_endpoint_gap as analysis  # noqa: E402


def test_loss_gate_follows_coverage_local_intergroup_order():
    assert analysis._loss_gate({
        "gold_l2_coverage": False,
        "local_champion": False,
    }) == "coverage_deleted"
    assert analysis._loss_gate({
        "gold_l2_coverage": True,
        "local_champion": False,
    }) == "local_champion_elimination"
    assert analysis._loss_gate({
        "gold_l2_coverage": True,
        "local_champion": True,
    }) == "intergroup_rank_loss"


def test_funnel_reports_conditional_conversion_rates():
    rows = [
        {
            "gold_l2_coverage": True,
            "local_champion": True,
            "actual_top2": True,
            "oracle_top2": True,
        },
        {
            "gold_l2_coverage": True,
            "local_champion": False,
            "actual_top2": False,
            "oracle_top2": True,
        },
        {
            "gold_l2_coverage": False,
            "local_champion": False,
            "actual_top2": False,
            "oracle_top2": False,
        },
    ]

    result = analysis._funnel(rows)

    assert result["coverage_count"] == 2
    assert result["local_champion_count"] == 1
    assert result["top2_count"] == 1
    assert result["local_given_coverage"] == 0.5
    assert result["top2_given_local_champion"] == 1.0
