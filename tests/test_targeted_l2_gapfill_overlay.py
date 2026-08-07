"""Unit tests for targeted L2 gapfill pipeline overlay helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "scripts"))

import targeted_l2_gapfill_overlay as overlay  # noqa: E402


def test_parse_arm_all_b_b1():
    targeted, source, budget = overlay.parse_arm("ALL_B_b1")
    assert targeted is False
    assert source == "B"
    assert budget == 1


def test_parse_arm_t_b_b2():
    targeted, source, budget = overlay.parse_arm("T_B_b2")
    assert targeted is True
    assert source == "B"
    assert budget == 2


def test_parse_arm_rejects_a_source_for_overlay_contract():
    # parse_arm itself allows A; apply_targeted_l2_gapfill rejects A.
    targeted, source, budget = overlay.parse_arm("ALL_A_b1")
    assert source == "A"
    assert budget == 1
    assert targeted is False


def test_parse_arm_invalid():
    with pytest.raises(ValueError, match="must match"):
        overlay.parse_arm("ALL_B_b3")
