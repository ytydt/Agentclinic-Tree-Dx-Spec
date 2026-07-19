from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentclinic_tree_dx.state import Branch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_direct_l2_selection.py"
SPEC = importlib.util.spec_from_file_location("direct_l2_selection_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
direct_l2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = direct_l2
SPEC.loader.exec_module(direct_l2)


def _branch(branch_id: str, label: str, *, parent: str, level: int) -> Branch:
    return Branch(
        id=branch_id,
        label=label,
        parent=parent,
        level=level,
        status="live",
        prior=0.0,
        posterior=0.0,
        danger=0.0,
        actionability=0.0,
        explanatory_coverage=0.0,
    )


def test_direct_l2_candidates_are_flat_leaf_targets_with_l1_provenance():
    l1 = _branch("B1", "Family", parent="ROOT", level=1)
    l1.children = ["B1.1", "B1.2"]
    leaf1 = _branch("B1.1", "Disease A", parent="B1", level=2)
    leaf2 = _branch("B1.2", "Disease B", parent="B1", level=2)
    tree = SimpleNamespace(branches={
        branch.id: branch for branch in (l1, leaf1, leaf2)
    })

    rows = direct_l2._direct_l2_candidates(tree)
    assert [row["id"] for row in rows] == ["B1.1", "B1.2"]
    assert all(row["score"] == pytest.approx(0.5) for row in rows)
    assert all(row["l1_parent_id"] == "B1" for row in rows)
    assert all(row["leaf_exemplars"] == [] for row in rows)
