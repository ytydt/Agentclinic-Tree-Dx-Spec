from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.corelift_cross_chain_comparability import (  # noqa: E402
    build,
    corelift_case_universe,
)


def _mig(case: str, family: str, arm: str, *, task: bool, complete: bool) -> dict:
    return {
        "experiment_id": "E14x",
        "arm_id": arm,
        "benchmark_family": family,
        "case_key": case,
        "task": task,
        "clinical_complete": complete,
        "complete_or_compatible_partial": complete,
    }


def _cl(case: str, family: str, arm: str, *, task: bool, complete: bool) -> dict:
    return {
        "arm": arm,
        "family": family,
        "case_key": case,
        "official_task": task,
        "clinical_complete": complete,
        "complete_or_compatible_partial": complete,
    }


def test_case_universe_groups_by_family() -> None:
    universe = corelift_case_universe(
        [_cl("c1", "DA", "A0", task=True, complete=False),
         _cl("c2", "MCR", "A0", task=False, complete=False)]
    )
    assert universe == {"DA": {"c1"}, "MCR": {"c2"}}


def test_reference_arm_subset_flag_detects_out_of_universe_cases() -> None:
    migration = [
        _mig("c1", "DA", "mosaic_lite_v1", task=True, complete=False),
        _mig("cX", "DA", "mosaic_lite_v1", task=False, complete=False),
    ]
    corelift = [_cl("c1", "DA", "A0_control", task=True, complete=False)]
    report = build(migration, corelift)
    da = report["canonical_chain_reference_arms"][0]["families"]["DA"]
    assert da["task"] == {"n": 2, "hits": 1, "rate": 0.5}
    assert da["cases_inside_corelift_universe"] == 1
    assert da["case_universe_is_subset"] is False


def test_corelift_arms_report_official_task_field() -> None:
    corelift = [
        _cl("c1", "DA", "B1_corelift", task=True, complete=True),
        _cl("c2", "DA", "B1_corelift", task=False, complete=False),
    ]
    report = build([], corelift)
    assert report["canonical_chain_reference_arms"] == []
    families = report["corelift_arms"][0]["families"]
    assert families["DA"]["task"]["rate"] == 0.5
    assert families["DA"]["clinical_complete"]["rate"] == 0.5
    assert "MCR" not in families


def test_empty_arm_reports_none_rate_rather_than_zero() -> None:
    report = build([], [])
    assert report["corelift_arms"] == []
    assert "must never be tabulated together" in report["warning"]
