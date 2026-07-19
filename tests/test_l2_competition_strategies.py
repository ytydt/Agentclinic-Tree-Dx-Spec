import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import eval_l2_competition_strategies as l2eval  # noqa: E402
from agentclinic_tree_dx.state import Branch, DiagnosticState  # noqa: E402


def _branch(
    branch_id: str,
    label: str,
    *,
    parent: str,
    level: int,
    posterior: float,
    children=(),
    status="live",
):
    return Branch(
        id=branch_id,
        label=label,
        parent=parent,
        level=level,
        status=status,
        prior=posterior,
        posterior=posterior,
        danger=0.0,
        actionability=0.0,
        explanatory_coverage=0.0,
        children=list(children),
    )


def _state():
    state = DiagnosticState(case_id="case")
    state.branches = {
        "B1": _branch(
            "B1", "Family 1", parent="ROOT", level=1, posterior=0.8,
            children=("B1.1", "B1.2"), status="expanded",
        ),
        "B2": _branch(
            "B2", "Family 2", parent="ROOT", level=1, posterior=0.2,
            children=("B2.1", "B2.2"), status="expanded",
        ),
        "B1.1": _branch(
            "B1.1", "Disease 11", parent="B1", level=2, posterior=0.2,
        ),
        "B1.2": _branch(
            "B1.2", "Disease 12", parent="B1", level=2, posterior=0.8,
        ),
        "B2.1": _branch(
            "B2.1", "Disease 21", parent="B2", level=2, posterior=0.5,
        ),
        "B2.2": _branch(
            "B2.2", "Disease 22", parent="B2", level=2, posterior=0.5,
        ),
    }
    return state


def test_rescale_l2_scope_preserves_parent_mass_and_within_parent_ratio():
    branches = l2eval.rescale_l2_scope(
        _state(),
        [
            {"id": "B1", "posterior": 0.75},
            {"id": "B2", "posterior": 0.25},
        ],
        ["B1", "B2"],
        use_parent_mass=True,
    )
    assert sum(branch.posterior for branch in branches.values()) == pytest.approx(1)
    assert sum(
        branch.posterior for branch in branches.values()
        if branch.parent == "B1"
    ) == pytest.approx(0.75)
    assert branches["B1.2"].posterior / branches["B1.1"].posterior == pytest.approx(4)


def test_top1_scope_normalizes_inside_selected_parent():
    branches = l2eval.rescale_l2_scope(
        _state(),
        [{"id": "B1", "posterior": 0.75}],
        ["B1"],
        use_parent_mass=False,
    )
    assert set(branches) == {"B1.1", "B1.2"}
    assert sum(branch.posterior for branch in branches.values()) == pytest.approx(1)


def test_clean_l2_annotation_requires_complete_fact_candidate_matrix():
    valid = l2eval.clean_l2_annotation(
        {
            "per_fact_effects": {
                "F1": {"B1.1": "neutral", "B1.2": "strong_for"},
                "F2": {"B1.1": "weak_against", "B1.2": "moderate_for"},
            }
        },
        ["F1", "F2"],
        ["B1.1", "B1.2"],
    )
    assert valid["schema_valid"]
    invalid = l2eval.clean_l2_annotation(
        {"per_fact_effects": {"F1": {"B1.1": "neutral"}}},
        ["F1", "F2"],
        ["B1.1", "B1.2"],
    )
    assert not invalid["schema_valid"]


def test_clean_champion_ranking_requires_all_ids_once():
    assert l2eval.clean_champion_ranking(
        {"ranked_candidate_ids": ["B2.1", "B1.1"]},
        ["B1.1", "B2.1"],
    )["schema_valid"]
    assert not l2eval.clean_champion_ranking(
        {"ranked_candidate_ids": ["B1.1", "B1.1"]},
        ["B1.1", "B2.1"],
    )["schema_valid"]


def test_score_ranking_accepts_any_duplicate_gold_leaf():
    gold = {
        "status": "duplicated_across_l1",
        "acceptable_l2": [
            {"id": "B1.1", "parent_id": "B1"},
            {"id": "B2.1", "parent_id": "B2"},
        ],
    }
    audit = l2eval.score_ranking(
        ["B2.1", "B1.2"],
        gold,
        scope_ids=["B1.1", "B2.1"],
        schema_valid=True,
    )
    assert audit["top1"]
    assert audit["rr"] == 1.0
    assert audit["unique_path_top1"] is None


def test_select_n_star_uses_top1_then_mrr_then_smallest_budget():
    assert l2eval.select_n_star([
        {"budget": 2, "top1": 0.5, "mrr": 0.7},
        {"budget": 4, "top1": 0.6, "mrr": 0.72},
        {"budget": 6, "top1": 0.6, "mrr": 0.75},
        {"budget": 8, "top1": 0.6, "mrr": 0.75},
    ]) == 6


def test_l2_budget_specs_add_explicit_exhaustion_arm():
    assert l2eval.l2_evidence_budget_specs(6) == (
        ("F2", 2), ("F4", 4), ("F6", 6), ("EXH", None),
    )


def test_selected_facts_for_budget_uses_frozen_selection_order():
    record = {
        "facts": [
            {"id": "F1", "text": "one"},
            {"id": "F2", "text": "two"},
            {"id": "F3", "text": "three"},
        ],
        "trace": {"selected_fact_ids": ["F3", "F1", "F2"]},
    }
    assert [
        row["id"] for row in l2eval.selected_facts_for_budget(record, 2)
    ] == ["F3", "F1"]
    assert [
        row["id"] for row in l2eval.selected_facts_for_budget(record, None)
    ] == ["F3", "F1", "F2"]


def test_budget_marginals_isolate_gold_parent_and_frozen_champions(
    monkeypatch,
):
    annotation_calls = []
    arbitration_calls = []

    def fake_annotate_scope(**kwargs):
        candidate_ids = list(kwargs["branches"])
        annotation_calls.append({
            "candidate_ids": candidate_ids,
            "fact_count": len(kwargs["selected_facts"]),
        })
        return {
            "schema_valid": True,
            "repair_used": False,
            "ranking": ["B2.1", "B2.2"],
        }

    def fake_arbitrate_champions(**kwargs):
        champion_ids = [row["id"] for row in kwargs["champions"]]
        arbitration_calls.append({
            "champion_ids": champion_ids,
            "fact_count": len(kwargs["selected_facts"]),
        })
        return {
            "schema_valid": True,
            "repair_used": False,
            "ranking": champion_ids,
            "champions": list(kwargs["champions"]),
        }

    monkeypatch.setattr(l2eval, "_annotate_scope", fake_annotate_scope)
    monkeypatch.setattr(
        l2eval, "_arbitrate_champions", fake_arbitrate_champions,
    )
    facts = [
        {"id": f"F{index}", "text": str(index)}
        for index in range(1, 5)
    ]
    champions = [
        {"id": "B1.1", "parent_id": "B1"},
        {"id": "B2.1", "parent_id": "B2"},
    ]
    result = l2eval._budget_case_records(
        replicate=1,
        case={"id": "case", "case_text": "vignette"},
        auto_asset={"full_findings": facts},
        frozen_asset={
            "l1_posteriors": [
                {"id": "B1", "posterior": 0.7},
                {"id": "B2", "posterior": 0.3},
            ],
        },
        full_record={
            "facts": facts,
            "trace": {"selected_fact_ids": [row["id"] for row in facts]},
        },
        gold={
            "status": "unique",
            "acceptable_l2": [{"id": "B2.1", "parent_id": "B2"}],
        },
        tree_state=_state(),
        frozen_champions=champions,
        cache=object(),
        annotator_prompt="annotate",
        arbiter_prompt="arbitrate",
        max_micro_rounds=4,
    )
    assert len(result["within"]) == 3
    assert all(
        set(call["candidate_ids"]) == {"B2.1", "B2.2"}
        for call in annotation_calls
    )
    assert [call["fact_count"] for call in annotation_calls] == [2, 4, 4]
    assert all(
        call["champion_ids"] == ["B1.1", "B2.1"]
        for call in arbitration_calls
    )
    assert [call["fact_count"] for call in arbitration_calls] == [2, 4, 4]


def test_frozen_gold_fixture_validates_when_present():
    path = ROOT / "eval_fixtures" / "l2_competition_gold_v1.json"
    if not path.is_file():
        pytest.skip("gold fixture is generated in the adjudication stage")
    gold = json.loads(path.read_text(encoding="utf-8"))
    cases = l2eval.validate_l2_gold(gold, tree_dir=l2eval.DEFAULT_TREE_DIR)
    assert len(cases) == 17
    assert sum(row["status"] != "absent" for row in cases.values()) == 14
    assert sum(
        row["status"] == "duplicated_across_l1" for row in cases.values()
    ) == 5
    assert sum(row["status"] == "absent" for row in cases.values()) == 3
