from __future__ import annotations

import math

import pytest

from agentclinic_tree_dx.adaptive_stopping import (
    BoundedAgenticPolicy,
    EvidenceAnchoredF4Policy,
    EvidenceQuorumF4Policy,
    FixedBudgetPolicy,
    SaturationPolicy,
    StopDecision,
    StopSnapshot,
    build_stop_snapshot,
    jensen_shannon_divergence,
)


def _snapshot(**overrides) -> StopSnapshot:
    values = {
        "cycle_index": 2,
        "micro_round": 4,
        "queue_length": 2,
        "eligible_count": 4,
        "top1_id": "B1",
        "top2_id": "B2",
        "top1_stable_cycles": 2,
        "margin_z": math.log(3),
        "cycle_js": 0.001,
        "effective_updates": 0,
        "target_turnover": False,
        "canonical_novel_count": 2,
        "compiler_hit_count": 1,
        "provenance_hit_count": 1,
        "pool_exhausted": False,
    }
    values.update(overrides)
    return StopSnapshot(**values)


def test_stop_contract_round_trips_and_rejects_invalid_values():
    snapshot = _snapshot()
    assert StopSnapshot.from_dict(snapshot.to_dict()) == snapshot
    decision = StopDecision(
        action="continue",
        policy="test",
        reason="budget",
        cycle_index=1,
        micro_round=2,
        challenge_fact_ids=("F1",),
    )
    assert StopDecision.from_dict(decision.to_dict()) == decision
    with pytest.raises(ValueError, match="pool_exhausted"):
        _snapshot(eligible_count=0, pool_exhausted=False).validate()
    with pytest.raises(ValueError, match="forbidden stopping field"):
        StopDecision(
            action="stop",
            policy="test",
            reason="bad",
            cycle_index=1,
            micro_round=2,
            metadata={"gold": "B1"},
        ).validate()


def test_snapshot_signals_are_deterministic_and_label_blind():
    before = {"B1": 0.6, "B2": 0.3, "B3": 0.1}
    after = {"B1": 0.7, "B2": 0.2, "B3": 0.1}
    left = build_stop_snapshot(
        cycle_index=1,
        micro_round=2,
        queue_length=2,
        eligible_count=3,
        before_scores=before,
        after_scores=after,
        previous_top1_id="B1",
        previous_stable_cycles=0,
        effective_updates=1,
        canonical_novel_count=2,
        compiler_hit_count=1,
        provenance_hit_count=0,
    )
    right = build_stop_snapshot(
        cycle_index=1,
        micro_round=2,
        queue_length=2,
        eligible_count=3,
        before_scores=before,
        after_scores=after,
        previous_top1_id="B1",
        previous_stable_cycles=0,
        effective_updates=1,
        canonical_novel_count=2,
        compiler_hit_count=1,
        provenance_hit_count=0,
    )
    assert left == right
    assert left.top1_stable_cycles == 1
    assert left.margin_z == pytest.approx(math.log(3.5))
    assert left.cycle_js == pytest.approx(
        jensen_shannon_divergence(before, after)
    )
    assert not left.target_turnover


def test_jensen_shannon_divergence_clamps_roundoff_to_non_negative():
    distribution = {
        "B1": 0.013513513513513516,
        "B2": 0.04054054054054055,
        "B3": 0.12162162162162163,
        "B4": 0.3648648648648649,
        "B5": 0.45945945945945943,
    }
    value = jensen_shannon_divergence(distribution, distribution)
    assert value >= 0
    _snapshot(cycle_js=value).validate()


def test_fixed_and_saturation_policies_obey_hard_bounds():
    fixed = FixedBudgetPolicy(4)
    assert fixed.decide(_snapshot(micro_round=2)).action == "continue"
    assert fixed.decide(_snapshot(micro_round=4)).reason == "fixed_budget_reached"
    exhausted = _snapshot(
        micro_round=2, eligible_count=0, pool_exhausted=True,
    )
    assert fixed.decide(exhausted).reason == "pool_exhausted"

    adaptive = SaturationPolicy(
        min_micro_rounds=2,
        max_micro_rounds=8,
        stable_cycles=2,
        max_cycle_js=0.01,
        max_effective_updates=0,
        min_margin_z=math.log(2),
    )
    assert adaptive.decide(_snapshot()).reason == "saturated"
    assert adaptive.decide(
        _snapshot(micro_round=1, queue_length=1)
    ).reason == "minimum_budget_not_reached"
    assert adaptive.decide(
        _snapshot(micro_round=8)
    ).reason == "max_micro_rounds_reached"


def test_evidence_anchored_policy_only_exits_at_f2_or_f4():
    policy = EvidenceAnchoredF4Policy(
        min_margin_z=math.log(2),
        min_effective_updates=1,
    )
    early = policy.decide(_snapshot(
        micro_round=2,
        effective_updates=1,
        margin_z=math.log(3),
    ))
    assert early.action == "stop"
    assert early.reason == "f2_evidence_anchored_exit"
    weak = policy.decide(_snapshot(
        micro_round=2,
        effective_updates=0,
        margin_z=math.log(3),
    ))
    assert weak.action == "continue"
    assert weak.reason == "continue_to_f4_anchor"
    anchor = policy.decide(_snapshot(micro_round=4))
    assert anchor.action == "stop"
    assert anchor.reason == "f4_anchor_reached"


def test_evidence_quorum_policy_requires_support_without_contradiction():
    policy = EvidenceQuorumF4Policy(min_margin_z=0.0)
    accepted = policy.decide(_snapshot(
        micro_round=2,
        leader_support_count=2,
        leader_against_count=0,
        top1_stable_cycles=0,
    ))
    assert accepted.reason == "f2_evidence_quorum_exit"
    contradicted = policy.decide(_snapshot(
        micro_round=2,
        leader_support_count=2,
        leader_against_count=1,
        top1_stable_cycles=0,
    ))
    assert contradicted.action == "continue"


def test_bounded_advisor_can_only_veto_and_filters_fact_ids():
    governor = SaturationPolicy()
    calls = []

    def advisor(payload):
        calls.append(payload)
        return {
            "status": "continue",
            "top_pair": ["B1", "B2"],
            "challenge_fact_ids": ["F2", "NOT_ELIGIBLE", "F2"],
        }

    policy = BoundedAgenticPolicy(governor, advisor)
    decision = policy.decide(
        _snapshot(),
        context={
            "eligible_fact_ids": ["F1", "F2"],
            "advisor_payload": {
                "top_pair": [{"id": "B1"}, {"id": "B2"}],
                "eligible_fact_ids": ["F1", "F2"],
            },
        },
    )
    assert calls
    assert decision.action == "continue"
    assert decision.reason == "challenge_veto"
    assert decision.challenge_fact_ids == ("F2",)

    none_policy = BoundedAgenticPolicy(
        governor,
        lambda payload: {"status": "none", "challenge_fact_ids": []},
    )
    stopped = none_policy.decide(
        _snapshot(),
        context={
            "eligible_fact_ids": ["F1"],
            "advisor_payload": {"eligible_fact_ids": ["F1"]},
        },
    )
    assert stopped.action == "stop"
    assert stopped.reason == "saturated_no_challenge"


def test_advisor_failure_falls_back_to_f4_and_gold_leak_is_rejected():
    def failure(payload):
        raise RuntimeError("offline")

    policy = BoundedAgenticPolicy(SaturationPolicy(), failure)
    early = policy.decide(
        _snapshot(micro_round=2),
        context={"eligible_fact_ids": [], "advisor_payload": {}},
    )
    assert early.action == "continue"
    assert early.fallback
    assert early.reason == "advisor_failure_continue_to_f4"
    at_f4 = policy.decide(
        _snapshot(micro_round=4),
        context={"eligible_fact_ids": [], "advisor_payload": {}},
    )
    assert at_f4.action == "stop"
    assert at_f4.fallback

    with pytest.raises(ValueError, match="forbidden stopping field"):
        policy.decide(
            _snapshot(),
            context={
                "eligible_fact_ids": ["F1"],
                "advisor_payload": {"gold": "B1"},
            },
        )
