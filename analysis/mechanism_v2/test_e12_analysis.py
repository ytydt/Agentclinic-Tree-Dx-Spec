from __future__ import annotations

from analysis.mechanism_v2.e12_analysis import (
    exact_mcnemar,
    holm_adjust,
    primary_contrasts,
)


def test_primary_family_has_39_unique_preregistered_contrasts() -> None:
    rows = primary_contrasts()
    assert len(rows) == 39
    assert len({label for _, _, label in rows}) == 39
    assert ("s1_k10_pairwise", "raw_k10_pairwise", "raw_vs_s1_k10_pairwise") in rows
    assert ("raw_k5_pairwise", "raw_k10_pairwise", "k10_vs_k5_raw_pairwise") in rows


def test_exact_mcnemar_is_symmetric() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(2, 9) == exact_mcnemar(9, 2)
    assert 0 <= exact_mcnemar(2, 9) <= 1


def test_holm_is_monotone_in_sorted_p_order() -> None:
    rows = [
        {"label": "a", "exact_mcnemar_p": 0.04},
        {"label": "b", "exact_mcnemar_p": 0.01},
        {"label": "c", "exact_mcnemar_p": 0.02},
    ]
    adjusted = holm_adjust(rows, "q")
    by_p = sorted(adjusted, key=lambda row: row["exact_mcnemar_p"])
    assert [row["q"] for row in by_p] == sorted(row["q"] for row in by_p)
