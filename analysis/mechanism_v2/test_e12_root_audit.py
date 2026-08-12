from __future__ import annotations

from analysis.mechanism_v2.e12_root_audit import (
    CODE_MAP,
    EXTRA_STRICT_DECISIONS,
    ROOT_CRITICAL_DECISION_CODES,
    SCREEN_MAP,
    critical_positive_pairs,
)
from analysis.mechanism_v2.e12_e7_factorial import DEFAULT_OUT


def test_root_decision_codes_cover_frozen_critical_pairs() -> None:
    pairs = critical_positive_pairs(DEFAULT_OUT)
    codes = ROOT_CRITICAL_DECISION_CODES.split()
    assert len(pairs) == len(codes) == 236
    assert set(codes).issubset(CODE_MAP)


def test_all_screen_relations_have_conservative_root_mapping() -> None:
    assert set(SCREEN_MAP) == {
        "exact_equivalent", "acceptable_clinical_variant",
        "broader_or_narrower_not_equivalent", "related_not_equivalent",
        "unrelated", "uncertain",
    }
    assert SCREEN_MAP["uncertain"] == "not_equivalent"


def test_strict_extra_cases_are_explicit() -> None:
    assert {case for case, _ in EXTRA_STRICT_DECISIONS} == {
        "MCR_seq200b/328", "MCR_v2_seq100/169"
    }
