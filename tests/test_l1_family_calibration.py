#!/usr/bin/env python3
"""Unit tests for L1 family calibration (Track B)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import l1_family_calibration as l1c  # noqa: E402


def _rows():
    return [
        {"id": "A", "label": "Family A", "posterior": 0.40},
        {"id": "B", "label": "Family B", "posterior": 0.35},
        {"id": "C", "label": "Family C", "posterior": 0.25},
    ]


def test_far_gap_skips():
    rows = [
        {"id": "A", "label": "Family A", "posterior": 0.80},
        {"id": "B", "label": "Family B", "posterior": 0.15},
        {"id": "C", "label": "Family C", "posterior": 0.05},
    ]
    out = l1c.calibrate_l1_families(
        rows, "v", [], arm="b12", dry_run=True, tau_post=0.15,
    )
    assert out["skipped_gate"] is True
    assert [r["id"] for r in out["ordered_rows"]] == ["A", "B", "C"]


def test_support_rerank_with_injected_counts():
    rows = _rows()
    counts = {
        "A": {"n_support": 1, "n_contradict": 2},
        "B": {"n_support": 5, "n_contradict": 0},
        "C": {"n_support": 0, "n_contradict": 0},
    }
    out = l1c.calibrate_l1_families(
        rows,
        "vignette",
        [{"id": "F1", "text": "finding"}],
        arm="support",
        dry_run=True,
        tau_post=0.15,
        injected_counts=counts,
        m=3,
        gamma=0.1,
    )
    assert out["skipped_gate"] is False
    ids = [r["id"] for r in out["ordered_rows"]]
    assert ids[0] == "B"
    assert set(ids) == {"A", "B", "C"}
    posts = [r["posterior"] for r in out["ordered_rows"]]
    assert abs(sum(posts) - 1.0) < 1e-6
    assert posts[0] >= posts[1] >= posts[2]


def test_pair_dry_run_swap():
    rows = [
        {"id": "A", "label": "Family A", "posterior": 0.51},
        {"id": "B", "label": "Family B", "posterior": 0.49},
    ]
    counts = {
        "A": {"n_support": 0, "n_contradict": 0},
        "B": {"n_support": 3, "n_contradict": 0},
    }
    out = l1c.calibrate_l1_families(
        rows,
        "v",
        [],
        arm="pair",
        dry_run=True,
        tau_post=0.15,
        tau_score=10.0,  # force pair step; dry_run picks higher support
        injected_counts=counts,
    )
    assert out["swapped"] is True
    assert out["ordered_rows"][0]["id"] == "B"


def test_b12_closed_set():
    rows = _rows()
    counts = {
        "A": {"n_support": 0, "n_contradict": 1},
        "B": {"n_support": 4, "n_contradict": 0},
        "C": {"n_support": 1, "n_contradict": 0},
    }
    out = l1c.calibrate_l1_families(
        rows,
        "v",
        [{"id": "F1", "text": "x"}],
        arm="b12",
        dry_run=True,
        tau_post=0.15,
        injected_counts=counts,
        m=3,
    )
    ids = [r["id"] for r in out["ordered_rows"]]
    assert set(ids) == {"A", "B", "C"}
    assert len(ids) == 3


def test_gold_leak_rejected():
    try:
        l1c._assert_no_gold({"gold": "x"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_force_calibrate_bypasses_tau():
    rows = [
        {"id": "A", "label": "Family A", "posterior": 0.80},
        {"id": "B", "label": "Family B", "posterior": 0.15},
        {"id": "C", "label": "Family C", "posterior": 0.05},
    ]
    counts = {
        "A": {"n_support": 0, "n_contradict": 2},
        "B": {"n_support": 5, "n_contradict": 0},
        "C": {"n_support": 0, "n_contradict": 0},
    }
    skipped = l1c.calibrate_l1_families(
        rows, "v", [], arm="support", dry_run=True, tau_post=0.15,
        injected_counts=counts,
    )
    assert skipped["skipped_gate"] is True
    forced = l1c.calibrate_l1_families(
        rows, "v", [], arm="support", dry_run=True, tau_post=0.15,
        injected_counts=counts, force_calibrate=True, m=3, gamma=0.1,
    )
    assert forced["skipped_gate"] is False
    assert forced["ordered_rows"][0]["id"] == "B"


def test_tau_zero_never_skips():
    rows = [
        {"id": "A", "label": "Family A", "posterior": 0.80},
        {"id": "B", "label": "Family B", "posterior": 0.15},
        {"id": "C", "label": "Family C", "posterior": 0.05},
    ]
    out = l1c.calibrate_l1_families(
        rows, "v", [], arm="b12", dry_run=True, tau_post=0.0,
        injected_counts={
            "A": {"n_support": 0, "n_contradict": 0},
            "B": {"n_support": 0, "n_contradict": 0},
            "C": {"n_support": 0, "n_contradict": 0},
        },
    )
    assert out["skipped_gate"] is False


if __name__ == "__main__":
    test_far_gap_skips()
    test_support_rerank_with_injected_counts()
    test_pair_dry_run_swap()
    test_b12_closed_set()
    test_gold_leak_rejected()
    test_force_calibrate_bypasses_tau()
    test_tau_zero_never_skips()
    print("ok")
