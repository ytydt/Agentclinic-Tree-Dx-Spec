from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_a4_downstream_combinations as combos  # noqa: E402


def _rows():
    output = []
    values = {
        "A-raw": [False, True],
        "A4": [True, True],
        "A4+A14": [True, False],
        "A4+A17": [True, True],
    }
    for arm, top2_values in values.items():
        for replicate, top2 in enumerate(top2_values, start=1):
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
                "leaf_burden": 2.0,
            })
    return output


def test_registered_a4_combinations_fix_local_mechanism_and_temperature():
    assert combos.COMBOS["A4+A14"] == {
        "terminal_arm": "A14",
        "prior_temperature": 1.0,
    }
    assert combos.COMBOS["A4+A17"] == {
        "terminal_arm": "A17",
        "prior_temperature": 2.0,
    }


def test_aggregate_reports_comparisons_against_a_raw_and_a4():
    summary = combos.aggregate(_rows(), bootstrap=20)

    assert summary["arms"]["A4+A17"]["top2"] == 1.0
    assert (
        summary["transitions"]["A-raw"]["A4+A17"]["actual_top2"]["gain_count"]
        == 1
    )
    assert (
        summary["transitions"]["A4"]["A4+A14"]["actual_top2"]["loss_count"]
        == 1
    )
    assert (
        summary["comparisons"]["A4"]["A4+A17"]["actual_top2"]["delta"]
        == 0.0
    )


def test_normalise_control_accepts_unified_mrr_field():
    row = combos._normalise_control({
        "arm": "A4",
        "case_id": "case-1",
        "replicate": 1,
        "gold_l2_coverage": True,
        "actual_top1": False,
        "actual_top2": True,
        "mrr_at_2": 0.5,
        "oracle_parent_f4_local_top2": True,
        "ranking": ["B1.1", "B2.1"],
    }, endpoint="unified_direct")

    assert row["actual_rr"] == 0.5
    assert row["oracle_top2"] is True
    assert row["ranking"] == ["B1.1", "B2.1"]
