from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_l1_bfs_f4_runs.py"
SPEC = importlib.util.spec_from_file_location("f4_replicate_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


def _row(case_id: str, *, leader: str, rank: int, selected: list[str]):
    return {
        "run": "r",
        "case_id": case_id,
        "gold_branch_id": "G",
        "gold_rank": rank,
        "gold_top1": rank == 1,
        "gold_top3": rank <= 3,
        "mrr": 1 / rank,
        "facts": 4,
        "leader_id": leader,
        "selected_fact_ids": selected,
        "rule_in": [["G"]],
        "rule_out": [[]],
    }


def test_f4_run_comparison_reports_case_level_variability():
    baseline = [
        _row("c1", leader="G", rank=1, selected=["F1", "F2"]),
        _row("c2", leader="D", rank=2, selected=["F3", "F4"]),
    ]
    rerun = [
        _row("c1", leader="G", rank=1, selected=["F1", "F2"]),
        _row("c2", leader="G", rank=1, selected=["F3", "F5"]),
    ]
    metrics = comparison.metric_block(rerun)
    assert metrics["gold_rank_at_1"] == 1.0
    audit = comparison.agreement(baseline, rerun)
    assert audit["leader"]["matches"] == 1
    assert audit["selected_order_exact"]["matches"] == 1
    assert audit["selected_jaccard_mean"] == pytest.approx(2 / 3)
    paired = comparison.paired_bootstrap(baseline, rerun, n_boot=100)
    assert paired["cases"] == 2
    assert paired["gold_top1"]["delta"] == pytest.approx(0.5)
