from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from agentclinic_tree_dx.state import Branch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_unobserved_test_menu.py"
SPEC = importlib.util.spec_from_file_location("unobserved_test_menu_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
menu_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = menu_eval
SPEC.loader.exec_module(menu_eval)


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


def test_tree_test_menu_is_result_unknown_deduplicated_and_bounded():
    l1 = _branch("B1", "Family", parent="ROOT", level=1)
    l1.children = ["B1.1"]
    l1.askable_discriminators = ["Is finding X present?"]
    child = _branch("B1.1", "Concrete disease", parent="B1", level=2)
    child.askable_discriminators = ["Is finding X present?"]
    child.requestable_discriminators = ["Order test Y"]
    tree = SimpleNamespace(branches={"B1": l1, "B1.1": child})

    rows = menu_eval._test_menu(tree, limit=2)
    assert [row["question_or_test"] for row in rows] == [
        "Is finding X present?",
        "Order test Y",
    ]
    assert all(row["result_status"] == "unknown_not_observed" for row in rows)
    assert rows[1]["l1_branch_id"] == "B1"
    assert rows[1]["source_branch_id"] == "B1.1"
