from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gold_branch_metrics",
    ROOT / "scripts" / "eval_partial_flow_gold_branch_metrics.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_evaluate_record_computes_level_ranks_and_path():
    record = {
        "profile": "p5_headline",
        "case_id": "case",
        "gold_diagnosis": "Gold",
        "metrics": {"l1_assigned_index": 1},
        "trace": {
            "l1_tree": [
                {"id": "A", "label": "Other", "posterior": 0.7},
                {"id": "B", "label": "Gold family", "posterior": 0.3},
            ],
            "l2_tree": [
                {"id": "A1", "parent": "A", "label": "Distractor", "posterior": 0.5},
                {"id": "B1", "parent": "B", "label": "Gold disease", "posterior": 0.2},
                {"id": "B2", "parent": "B", "label": "Other subtype", "posterior": 0.1},
            ],
        },
    }
    row = module.evaluate_record(record, lambda gold, labels: labels.index("Gold disease"))
    assert row["l1"]["exists"] is True
    assert row["l1"]["rank"] == 2
    assert row["l1"]["top1"] is False
    assert row["l2"]["rank"] == 2
    assert row["gold_path_consistent"] is True


def test_summary_uses_all_cases_as_rate_denominator():
    rows = [
        {
            "profile": "p5_headline",
            "gold_path_consistent": True,
            "l1": {"exists": True, "rank": 1, "top1": True, "residual": False},
            "l2": {"exists": True, "rank": 2, "top1": False, "residual": False},
        },
        {
            "profile": "p5_headline",
            "gold_path_consistent": False,
            "l1": {"exists": True, "rank": 2, "top1": False, "residual": True},
            "l2": {"exists": False, "rank": None, "top1": False, "residual": None},
        },
    ]
    summary = module.summarize(rows)["overall"]
    assert summary["l1"]["existence_rate"] == 1.0
    assert summary["l1"]["structured_existence_rate"] == 0.5
    assert summary["l1"]["posterior_top1_rate"] == 0.5
    assert summary["l2"]["existence_rate"] == 0.5
    assert summary["l2"]["posterior_top3_rate"] == 0.5
    assert summary["gold_path_consistency_rate"] == 0.5
