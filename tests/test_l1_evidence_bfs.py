from __future__ import annotations

import copy
import math

import pytest

from agentclinic_tree_dx.adaptive_stopping import (
    BoundedAgenticPolicy,
    FixedBudgetPolicy,
    SaturationPolicy,
)
from agentclinic_tree_dx.l1_evidence_bfs import (
    L1EvidenceBFSPipeline,
    L1ObservedFact,
    PRESETS,
    assert_no_gold_leak,
    clean_allocation,
    clean_contrastive_selection,
    l1_leaf_exemplars,
    resolve_preset,
    symmetric_rank_update,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState


def _branch(branch_id: str, label: str, posterior: float) -> Branch:
    return Branch(
        id=branch_id,
        label=label,
        parent="ROOT",
        level=1,
        status="live",
        prior=posterior,
        posterior=posterior,
        danger=0.0,
        actionability=0.0,
        explanatory_coverage=0.0,
    )


def _state() -> DiagnosticState:
    state = DiagnosticState(case_id="case")
    state.branches = {
        "B1": _branch("B1", "Family A", 0.5),
        "B2": _branch("B2", "Family B", 0.3),
        "B3": _branch("B3", "Family C", 0.2),
    }
    state.frontier = list(state.branches)
    return state


FACTS = (
    L1ObservedFact("F1", "Observed alpha", concept="alpha", polarity="present"),
    L1ObservedFact("F2", "Observed beta", concept="beta", polarity="absent"),
    L1ObservedFact("F3", "Observed gamma", concept="gamma", polarity="present"),
)


def test_presets_are_explicit_and_reject_metrics_only_track_b():
    assert resolve_preset("p5_single_direct").allocation_contract == "p5_single"
    assert resolve_preset("bfs_sparse_dual_ro").ruleout_selector == "dedicated"
    assert set(PRESETS) >= {
        "p5_eval_compat",
        "p5_single_direct",
        "p5_contrastive_direct",
        "p5_anti_anchor_direct",
        "e1q_legacy",
        "bfs_sparse",
        "bfs_sparse_dual_ro",
    }
    with pytest.raises(ValueError, match="Track B"):
        resolve_preset("p5_eval_compat", track="B")


def test_contrastive_selection_requires_pairwise_effect_and_deduplicates_concepts():
    cleaned = clean_contrastive_selection(
        {
            "verdict": "select",
            "ranked_facts": [
                {
                    "fact_id": "F1",
                    "concept_key": "right upper quadrant pain",
                    "supports": ["B1"],
                    "contrasts_with": ["B2"],
                    "candidate_effects": {"B1": 2, "B2": 0, "B3": 0},
                    "why": "more expected in B1 than B2",
                },
                {
                    "fact_id": "F2",
                    "concept_key": "right_upper-quadrant pain",
                    "supports": ["B1"],
                    "contrasts_with": ["B3"],
                },
                {
                    "fact_id": "F3",
                    "concept_key": "alcohol exposure",
                    "supports": ["B1"],
                    "contrasts_with": [],
                },
            ],
        },
        ["F1", "F2", "F3"],
        ["B1", "B2", "B3"],
    )
    assert cleaned["ranked_fact_ids"] == ["F1"]
    assert cleaned["concept_keys"] == {"F1": "right upper quadrant pain"}
    assert cleaned["rejected"] == [
        {"fact_id": "F2", "reason": "duplicate_concept"},
        {"fact_id": "F3", "reason": "missing_pairwise_contrast"},
    ]


@pytest.mark.parametrize(
    "preset", ["p5_contrastive_direct", "p5_anti_anchor_direct"],
)
def test_matrix_selector_pipeline_blocks_alias_selected_in_later_cycle(preset):
    calls = 0

    def selector(payload):
        nonlocal calls
        calls += 1
        fact_id = "F1" if calls == 1 else "F2"
        return {
            "verdict": "select",
            "best_fact_id": fact_id,
            "ranked_fact_ids": [fact_id],
            "concept_keys": {fact_id: "same clinical concept"},
        }

    none = lambda payload: {"favored": "none"}
    _, trace = L1EvidenceBFSPipeline(
        preset=preset,
        global_selector=selector,
        rule_in_allocator=none,
        rule_out_allocator=lambda payload: {"argues_against": "none"},
        max_micro_rounds=3,
        facts_per_cycle=1,
    ).run(
        _state(),
        case_context="case",
        facts=FACTS,
        compiler_master_blocks={},
    )
    assert trace["selected_fact_ids"] == ["F1"]
    assert trace["selection_cycles"][1]["semantic_rejected"] == [
        {"fact_id": "F2", "reason": "semantic_duplicate"},
    ]


def test_runtime_payload_gold_fields_are_rejected_recursively():
    assert_no_gold_leak({"candidates": [{"id": "B1"}]})
    with pytest.raises(ValueError, match="direction_target"):
        assert_no_gold_leak({"nested": [{"direction_target": "B1"}]})


def test_frozen_l2_leaf_labels_are_exposed_as_l1_exemplars():
    branches = _state().branches
    child = _branch("B1.1", "Concrete disease leaf", 0.0)
    child.level = 2
    child.parent = "B1"
    branches["B1"].children = [child.id]
    branches[child.id] = child
    exemplars = l1_leaf_exemplars(branches)
    assert exemplars["B1"] == [
        {"id": "B1.1", "label": "Concrete disease leaf"},
    ]
    assert exemplars["B2"] == []


def test_sparse_none_and_invalid_schema_do_not_mint_candidates():
    branches = _state().branches
    ranked, audit = clean_allocation(
        {"verdict": "none", "ranked_candidates": []},
        branches,
        contract="sparse_ranked",
        axis="rule_in",
    )
    assert ranked == []
    assert audit["schema_valid"]

    ranked, audit = clean_allocation(
        {"verdict": "none", "ranked_candidates": ["B1"]},
        branches,
        contract="sparse_ranked",
        axis="rule_in",
    )
    assert ranked == []
    assert not audit["schema_valid"]


def test_symmetric_rank_update_is_bounded_conservative_and_conflict_safe():
    branches = _state().branches
    result = symmetric_rank_update(
        branches, ["B1", "B2"], ["B3"], eta=math.log(3), evidence_id="F1"
    )
    assert sum(result["posteriors"].values()) == pytest.approx(1.0)
    assert branches["B1"].posterior > branches["B2"].posterior
    assert branches["B3"].posterior < 0.2
    assert branches["B1"].evidence_for == ["F1"]
    assert branches["B3"].evidence_against == ["F1"]

    before = {key: value.posterior for key, value in branches.items()}
    conflict = symmetric_rank_update(branches, ["B1"], ["B1"], evidence_id="F2")
    assert conflict["conflicts"] == ["B1"]
    assert conflict["posteriors"] == pytest.approx(before)
    assert not conflict["updated"]


def test_pipeline_keeps_semantics_immutable_and_consumes_each_fact_once():
    original = _state()
    selector_payloads = []
    allocation_payloads = []

    def selector(payload):
        selector_payloads.append(copy.deepcopy(payload))
        eligible = payload["eligible_fact_ids"]
        return {
            "verdict": "select" if eligible else "none",
            "best_fact_id": eligible[0] if eligible else "",
            "ranked_fact_ids": eligible[:2],
        }

    def rule_in(payload):
        allocation_payloads.append(copy.deepcopy(payload))
        if payload["selected_fact"]["id"] == "F1":
            return {"verdict": "specific", "ranked_candidates": ["B1"]}
        return {"verdict": "none", "ranked_candidates": []}

    def rule_out(payload):
        if payload["selected_fact"]["id"] == "F2":
            return {"verdict": "specific", "ranked_candidates": ["B3"]}
        return {"verdict": "none", "ranked_candidates": []}

    final, trace = L1EvidenceBFSPipeline(
        preset="bfs_sparse",
        global_selector=selector,
        rule_in_allocator=rule_in,
        rule_out_allocator=rule_out,
        max_micro_rounds=3,
    ).run(
        original,
        case_context="Immutable vignette",
        facts=FACTS,
        compiler_master_blocks={
            "F1": {"select": ["prefer alpha"], "direction": ["alpha -> A"]},
            "F2": {"ruleout": ["beta against C"]},
            "F3": {},
        },
    )

    assert trace["selected_fact_ids"] == ["F1", "F2", "F3"]
    assert len(set(trace["selected_fact_ids"])) == 3
    assert trace["selection_status_by_id"] == {
        "F1": "consumed", "F2": "consumed", "F3": "consumed"
    }
    assert all(
        payload["case_context"] == "Immutable vignette"
        for payload in selector_payloads + allocation_payloads
    )
    assert all(
        payload["fact_catalog_core"] == selector_payloads[0]["fact_catalog_core"]
        for payload in selector_payloads
    )
    assert original.branches["B1"].posterior == 0.5
    assert final.branches["B1"].posterior > final.branches["B3"].posterior
    assert not trace["answer_mapper_called"]


def test_trace_selected_fact_ids_follow_consumption_not_catalog_order():
    def selector(payload):
        eligible = payload["eligible_fact_ids"]
        preferred = [
            fact_id for fact_id in ("F3", "F1", "F2")
            if fact_id in eligible
        ]
        return {
            "verdict": "select",
            "best_fact_id": preferred[0],
            "ranked_fact_ids": preferred[:2],
        }

    none = lambda payload: {"verdict": "none", "ranked_candidates": []}
    _, trace = L1EvidenceBFSPipeline(
        preset="bfs_sparse",
        global_selector=selector,
        rule_in_allocator=none,
        rule_out_allocator=none,
        max_micro_rounds=3,
    ).run(
        _state(),
        case_context="Immutable vignette",
        facts=FACTS,
        compiler_master_blocks={},
    )
    assert trace["selected_fact_ids"] == ["F3", "F1", "F2"]
    assert trace["consumption_order_fact_ids"] == ["F3", "F1", "F2"]
    assert trace["consumed_fact_ids_catalog_order"] == ["F1", "F2", "F3"]


def test_dual_lane_uses_ruleout_fact_for_second_slot_and_audits_displacement():
    def global_selector(payload):
        return {
            "verdict": "select",
            "best_fact_id": "F1",
            "ranked_fact_ids": ["F1", "F2"],
        }

    def ro_selector(payload):
        assert payload["selection_goal"] == "rule_out"
        return {
            "verdict": "select",
            "best_fact_id": "F3",
            "ranked_fact_ids": ["F3"],
        }

    none = lambda payload: {"verdict": "none", "ranked_candidates": []}
    _, trace = L1EvidenceBFSPipeline(
        preset="bfs_sparse_dual_ro",
        global_selector=global_selector,
        ruleout_selector=ro_selector,
        rule_in_allocator=none,
        rule_out_allocator=none,
        max_micro_rounds=2,
    ).run(
        _state(),
        case_context="case",
        facts=FACTS,
        compiler_master_blocks={},
    )
    assert trace["selected_fact_ids"] == ["F1", "F3"]
    assert trace["selection_cycles"][0]["displaced_global_ids"] == ["F2"]


def test_forced_selector_cannot_silently_abstain():
    none = lambda payload: {"favored": "none"}
    pipeline = L1EvidenceBFSPipeline(
        preset="p5_single_direct",
        global_selector=lambda payload: {"ranked_fact_ids": []},
        rule_in_allocator=none,
        rule_out_allocator=lambda payload: {"argues_against": "none"},
    )
    with pytest.raises(ValueError, match="forced selector"):
        pipeline.run(
            _state(),
            case_context="case",
            facts=FACTS,
            compiler_master_blocks={},
        )


def test_explicit_f4_policy_preserves_fixed_budget_state_and_trace_prefix():
    def selector(payload):
        eligible = payload["eligible_fact_ids"]
        return {
            "best_fact_id": eligible[0],
            "ranked_fact_ids": eligible[:2],
        }

    def rule_in(payload):
        return {"favored": "Family A"}

    def rule_out(payload):
        return {"argues_against": "none"}

    kwargs = {
        "preset": "p5_single_direct",
        "global_selector": selector,
        "rule_in_allocator": rule_in,
        "rule_out_allocator": rule_out,
        "max_micro_rounds": 3,
        "facts_per_cycle": 2,
    }
    default_state, default_trace = L1EvidenceBFSPipeline(**kwargs).run(
        _state(),
        case_context="case",
        facts=FACTS,
        compiler_master_blocks={},
    )
    fixed_state, fixed_trace = L1EvidenceBFSPipeline(
        **kwargs,
        stop_policy=FixedBudgetPolicy(3),
    ).run(
        _state(),
        case_context="case",
        facts=FACTS,
        compiler_master_blocks={},
    )
    assert fixed_trace["selected_fact_ids"] == default_trace["selected_fact_ids"]
    assert fixed_trace["posterior_trajectory"] == default_trace[
        "posterior_trajectory"
    ]
    assert {
        key: branch.posterior for key, branch in fixed_state.branches.items()
    } == pytest.approx({
        key: branch.posterior for key, branch in default_state.branches.items()
    })
    assert fixed_trace["stop_decisions"][-1]["reason"] == "pool_exhausted"


def test_shadow_agentic_policy_records_veto_without_shortening_f8_prefix():
    facts = tuple(
        L1ObservedFact(f"F{index}", f"Observed {index}", concept=f"c{index}")
        for index in range(1, 9)
    )

    def selector(payload):
        eligible = payload["eligible_fact_ids"]
        return {
            "best_fact_id": eligible[0],
            "ranked_fact_ids": eligible[:2],
        }

    advisor_payloads = []

    def advisor(payload):
        advisor_payloads.append(copy.deepcopy(payload))
        eligible = payload["eligible_fact_ids"]
        return {
            "status": "continue" if eligible else "none",
            "challenge_fact_ids": eligible[:1],
        }

    policy = BoundedAgenticPolicy(
        SaturationPolicy(
            stable_cycles=1,
            max_cycle_js=1.0,
            max_effective_updates=2,
            min_margin_z=0.0,
        ),
        advisor,
        audit_all_cycles=True,
    )
    _, trace = L1EvidenceBFSPipeline(
        preset="p5_single_direct",
        global_selector=selector,
        rule_in_allocator=lambda payload: {"favored": "none"},
        rule_out_allocator=lambda payload: {"argues_against": "none"},
        max_micro_rounds=8,
        facts_per_cycle=2,
        stop_policy=policy,
        shadow_stop_policy=True,
    ).run(
        _state(),
        case_context="immutable case",
        facts=facts,
        compiler_master_blocks={},
    )
    assert len(trace["selected_fact_ids"]) == 8
    assert [row["micro_round"] for row in trace["stop_snapshots"]] == [2, 4, 6, 8]
    assert trace["stop_decisions"][0]["action"] == "continue"
    assert trace["stop_decisions"][0]["reason"] == "challenge_veto"
    assert advisor_payloads
    assert all("gold" not in payload for payload in advisor_payloads)
