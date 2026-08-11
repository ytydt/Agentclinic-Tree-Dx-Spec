from analysis.mechanism_v2.e5_analysis import (
    exact_mcnemar,
    holm_adjust,
    paired_contrast,
)
from analysis.mechanism_v2.e5_candidate_interference import ADD_PARENT, BASE, REMOVE
from analysis.mechanism_v2.e5_manual_adjudications import (
    CONSTRUCTION_CODES,
    CONSTRUCTION_NOTES,
    CONSTRUCTION_ORDER,
    STATUS_BY_CODE,
)


def _row(case_key, arm, champion, hit, candidates, relation="base"):
    return {
        "case_key": case_key,
        "arm": arm,
        "success": True,
        "strict_top1": hit,
        "gold_rank": 1 if hit else 2,
        "top1_probability": 0.7,
        "champion_id": champion,
        "champion_label": next(row["label"] for row in candidates if row["candidate_id"] == champion),
        "champion_relation": relation,
        "candidates": candidates,
    }


def test_pair_decomposes_direct_harm_and_context_gain():
    base_candidates = [
        {"candidate_id": "B1", "label": "gold"},
        {"candidate_id": "B2", "label": "wrong"},
    ]
    added = base_candidates + [{"candidate_id": "X_PARENT", "label": "broad"}]
    rows = [
        _row("harm", BASE, "B1", True, base_candidates),
        _row("harm", ADD_PARENT, "X_PARENT", False, added, "parent"),
        _row("gain", BASE, "B2", False, base_candidates),
        _row("gain", ADD_PARENT, "B1", True, added),
    ]
    result = paired_contrast(rows, BASE, ADD_PARENT, "test")
    assert result["n_comparable"] == 2
    assert result["left_only_harms"] == 1
    assert result["right_only_gains"] == 1
    assert result["direct_new_candidate_harm_n"] == 1
    assert result["shared_candidate_context_harm_n"] == 0
    assert result["shared_candidate_context_gain_n"] == 1
    assert result["new_candidate_champion_relations"] == {"parent": 1}


def test_remove_rescue_requires_eliminated_base_champion():
    base_candidates = [
        {"candidate_id": "B1", "label": "gold"},
        {"candidate_id": "B2", "label": "wrong"},
    ]
    rows = [
        _row("rescue", BASE, "B2", False, base_candidates),
        _row("rescue", REMOVE, "B1", True, base_candidates[:1]),
    ]
    result = paired_contrast(rows, BASE, REMOVE, "test-remove")
    assert result["removed_candidate_rescue_n"] == 1
    assert result["removed_left_champion_n"] == 1
    assert result["shared_candidate_context_gain_n"] == 0


def test_holm_is_monotone_in_sorted_p_values():
    records = [
        {"right": name, "exact_mcnemar_p": value}
        for name, value in (
            (REMOVE, 0.04),
            (ADD_PARENT, 0.001),
            ("add_sibling5", 0.02),
            ("add_unrelated5", 0.5),
            ("add_synonym5", 1.0),
            ("add_component5", 0.2),
            ("nested_width6", 0.03),
            ("nested_width8", 0.0001),
        )
    ]
    adjusted = holm_adjust(records)
    by_right = {row["right"]: row for row in adjusted}
    assert by_right["nested_width8"]["holm_adjusted_p_across_8_primary"] == 0.0008
    assert by_right[ADD_PARENT]["holm_adjusted_p_across_8_primary"] == 0.007
    ordered = sorted(adjusted, key=lambda row: row["exact_mcnemar_p"])
    assert [row["holm_adjusted_p_across_8_primary"] for row in ordered] == sorted(
        row["holm_adjusted_p_across_8_primary"] for row in ordered
    )
    assert exact_mcnemar(0, 0) == 1.0


def test_manual_construction_vectors_are_complete_and_noted():
    assert len(CONSTRUCTION_CODES) == 20
    nonvalid = set()
    for case_key, codes in CONSTRUCTION_CODES.items():
        assert len(codes) == len(CONSTRUCTION_ORDER) == 9
        assert set(codes) <= set(STATUS_BY_CODE)
        nonvalid.update(
            (case_key, relation)
            for relation, code in zip(CONSTRUCTION_ORDER, codes)
            if code != "V"
        )
    assert nonvalid == set(CONSTRUCTION_NOTES)
