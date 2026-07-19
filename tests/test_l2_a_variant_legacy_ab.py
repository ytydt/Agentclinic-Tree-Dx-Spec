from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a_variant_legacy_ab as harness  # noqa: E402


def test_candidate_selection_uses_a_raw_top2_point_estimate():
    rows = [
        {"arm": "C-prod", "top2_pct": 47.1},
        {"arm": "A-raw", "top2_pct": 37.3},
        {"arm": "A1", "top2_pct": 39.2},
        {"arm": "A2", "top2_pct": 41.2},
        {"arm": "A3", "top2_pct": 31.4},
        {"arm": "A4", "top2_pct": 54.9},
        {"arm": "A6", "top2_pct": 37.3},
        {"arm": "A10", "top2_pct": 37.3},
        {"arm": "A17", "top2_pct": 35.3},
    ]

    assert harness.select_candidate_arms({"rows": rows}) == [
        "C-prod", "A-raw", "A1", "A2", "A4", "A6", "A10",
    ]


def test_acceptable_ids_use_stable_a_for_transforms_and_tier3_for_regeneration():
    gold = {
        "by_ab_key": {
            ("A", 1, "case"): {"acceptable_l2": ["B1.1"]},
            ("C", 1, "case"): {"acceptable_l2": ["B2.1"]},
        },
    }
    final = {
        "gold_match_by_occurrence": {
            ("A6", 1, "case"): {
                "acceptable_branch_ids": ["B3.v1"],
            },
        },
    }

    assert harness._acceptable_ids(
        arm="A2", replicate=1, case_id="case",
        gold_index=gold, final_audit=final,
    ) == ({"B1.1"}, "frozen_A_stable_ids")
    assert harness._acceptable_ids(
        arm="A6", replicate=1, case_id="case",
        gold_index=gold, final_audit=final,
    ) == ({"B3.v1"}, "tier3_proxy_semantic_gold")


def test_live_l2_ids_excludes_fallbacks():
    tree = {
        "branches": {
            "B1": {"level": 1},
            "B1.1": {"level": 2},
            "B1.2": {"level": 2, "level_role": "partial_flow_fallback"},
        },
    }
    assert harness._live_l2_ids(tree) == {"B1.1"}


def test_aggregate_reports_case_level_gain_and_loss():
    records = [
        {
            "arm": arm,
            "case_id": case,
            "replicate": 1,
            "gold_l2_coverage": True,
            "actual_top1": value,
            "actual_top2": value,
            "actual_rr": float(value),
            "oracle_top2": True,
            "local_champion": value,
            "leaf_burden": 1.0,
            "leaf_clean_rate": 1.0,
            "leaf_parent_invalid_rate": 0.0,
            "semantic_duplicate_excess_rate": 0.0,
            "production_e2e_llm_calls": 1,
        }
        for arm, case, value in (
            ("A-raw", "gain", False),
            ("A-raw", "loss", True),
            ("A2", "gain", True),
            ("A2", "loss", False),
        )
    ]

    result = harness._aggregate(
        records, ["A-raw", "A2"], bootstrap=10,
    )

    top2 = result["transitions_vs_a_raw"]["A2"]["actual_top2"]
    assert top2["gain_count"] == 1
    assert top2["loss_count"] == 1
    assert top2["net"] == 0
