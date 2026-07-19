from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_promising_downstream_legacy as harness  # noqa: E402


def _records():
    values = {
        "A-raw": [False, True],
        "A14": [True, True],
        "A15": [True, False],
        "A17": [False, True],
    }
    output = []
    for arm, outcomes in values.items():
        for replicate, top2 in enumerate(outcomes, start=1):
            output.append({
                "arm": arm,
                "case_id": "case-1",
                "replicate": replicate,
                "gold_l2_coverage": True,
                "actual_top1": False,
                "actual_top2": top2,
                "actual_rr": 0.5 if top2 else 0.0,
                "oracle_top2": True,
                "local_champion": True,
            })
    return output


def test_arm_specs_match_registered_downstream_changes():
    assert harness.ARM_SPECS == {
        "A14": {"champions_per_parent": 1, "prior_temperature": 1.0},
        "A15": {"champions_per_parent": 2, "prior_temperature": 1.0},
        "A17": {"champions_per_parent": 1, "prior_temperature": 2.0},
    }


def test_aggregate_reports_paired_transitions_against_a_raw():
    summary = harness.aggregate(_records(), bootstrap=20)

    assert summary["arms"]["A14"]["top2"] == 1.0
    assert (
        summary["transitions_vs_a_raw"]["A14"]["actual_top2"]["gain_count"]
        == 1
    )
    assert (
        summary["transitions_vs_a_raw"]["A15"]["actual_top2"]["net"]
        == 0
    )
    assert (
        summary["comparisons_vs_a_raw"]["A17"]["actual_top2"]["delta"]
        == 0.0
    )
