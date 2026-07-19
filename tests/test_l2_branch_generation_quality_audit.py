from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit_l2_branch_generation_quality as audit  # noqa: E402


def _trace(arm: str, leaves: list[tuple[str, str, str]]) -> dict:
    branches = {
        "B1": {"id": "B1", "label": "Parent One", "level": 1, "children": []},
        "B2": {"id": "B2", "label": "Parent Two", "level": 1, "children": []},
    }
    for branch_id, label, parent_id in leaves:
        branches[branch_id] = {
            "id": branch_id,
            "label": label,
            "level": 2,
            "parent": parent_id,
            "children": [],
        }
        branches[parent_id]["children"].append(branch_id)
    tree = {"branches": branches}
    return {
        "arm": arm,
        "replicate": 1,
        "case_id": "case-1",
        "tree_hash": audit.ab.stable_hash(tree),
        "tree": tree,
    }


def _unit(
    *,
    label: str,
    parent: str,
    cluster: str,
    specific: bool = True,
    valid: bool = True,
) -> dict:
    return {
        "leaf_label": label,
        "parent_label": parent,
        "semantic_cluster_id": cluster,
        "is_specific_disease": specific,
        "is_parent_valid": valid,
    }


def test_score_trace_reports_semantic_duplicates_and_semantic_novelty():
    c_trace = _trace("C", [
        ("B1.1", "Disease A", "B1"),
        ("B2.1", "Syndrome X", "B2"),
    ])
    a_trace = _trace("A", [
        ("B1.1", "Disease A", "B1"),
        ("B2.1", "Disease Alpha", "B2"),
        ("B2.2", "Broad mechanism", "B2"),
    ])
    index = {
        ("C", 1, "case-1", "B1.1"): _unit(
            label="Disease A", parent="Parent One", cluster="disease-a",
        ),
        ("C", 1, "case-1", "B2.1"): _unit(
            label="Syndrome X", parent="Parent Two", cluster="syndrome-x",
        ),
        ("A", 1, "case-1", "B1.1"): _unit(
            label="Disease A", parent="Parent One", cluster="disease-a",
        ),
        ("A", 1, "case-1", "B2.1"): _unit(
            label="Disease Alpha", parent="Parent Two", cluster="disease-a",
        ),
        ("A", 1, "case-1", "B2.2"): _unit(
            label="Broad mechanism",
            parent="Parent Two",
            cluster="broad-mechanism",
            specific=False,
            valid=False,
        ),
    }

    row = audit.score_trace(a_trace, index, c_trace=c_trace)

    assert row["leaf_count"] == 3
    assert row["leaf_specific_rate"] == pytest.approx(2 / 3)
    assert row["leaf_parent_invalid_rate"] == pytest.approx(1 / 3)
    assert row["leaf_semantic_duplicate_rate"] == pytest.approx(2 / 3)
    assert row["leaf_exact_duplicate_rate"] == 0.0
    assert row["semantic_duplicate_excess_rate"] == pytest.approx(1 / 3)
    assert row["leaf_clean_rate"] == 0.0
    assert row["novel_vs_c_leaf_count"] == 1
    assert row["novel_vs_c_leaf_specific_rate"] == 0.0


def test_weighted_cohort_uses_leaf_occurrences_not_mean_of_tree_rates():
    rows = [
        {
            "leaf_count": 1,
            "leaf_specific_count": 1,
            "leaf_parent_invalid_count": 0,
            "leaf_semantic_duplicate_count": 0,
            "leaf_exact_duplicate_count": 0,
            "semantic_duplicate_excess_count": 0,
            "exact_duplicate_excess_count": 0,
            "leaf_clean_count": 1,
            "novel_vs_c_leaf_count": 0,
            "novel_vs_c_leaf_specific_count": 0,
            "novel_vs_c_leaf_parent_invalid_count": 0,
            "novel_vs_c_leaf_semantic_duplicate_count": 0,
            "novel_vs_c_leaf_exact_duplicate_count": 0,
            "novel_vs_c_semantic_duplicate_excess_count": 0,
            "novel_vs_c_exact_duplicate_excess_count": 0,
            "novel_vs_c_leaf_clean_count": 0,
        },
        {
            "leaf_count": 3,
            "leaf_specific_count": 0,
            "leaf_parent_invalid_count": 3,
            "leaf_semantic_duplicate_count": 2,
            "leaf_exact_duplicate_count": 0,
            "semantic_duplicate_excess_count": 1,
            "exact_duplicate_excess_count": 0,
            "leaf_clean_count": 0,
            "novel_vs_c_leaf_count": 2,
            "novel_vs_c_leaf_specific_count": 0,
            "novel_vs_c_leaf_parent_invalid_count": 2,
            "novel_vs_c_leaf_semantic_duplicate_count": 2,
            "novel_vs_c_leaf_exact_duplicate_count": 0,
            "novel_vs_c_semantic_duplicate_excess_count": 1,
            "novel_vs_c_exact_duplicate_excess_count": 0,
            "novel_vs_c_leaf_clean_count": 0,
        },
    ]

    result = audit._weighted_cohort(rows)

    assert result["leaf_specific_rate"] == 0.25
    assert result["leaf_parent_invalid_rate"] == 0.75
    assert result["leaf_semantic_duplicate_rate"] == 0.5
    assert result["novel_vs_c_leaf_parent_invalid_rate"] == 1.0


def test_unit_key_is_case_and_parent_sensitive_but_casefolded():
    first = audit._unit_key("Case-1", "Disease A", "Parent One")
    assert first == audit._unit_key("case-1", " disease  a ", "parent one")
    assert first != audit._unit_key("case-2", "Disease A", "Parent One")
    assert first != audit._unit_key("case-1", "Disease A", "Parent Two")
