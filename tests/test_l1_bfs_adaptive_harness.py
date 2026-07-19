from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.adaptive_stopping import StopDecision, StopSnapshot

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_bfs_adaptive_stop.py"
SPEC = importlib.util.spec_from_file_location("adaptive_harness_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def _posterior(round_number: int, gold_rank: int):
    if gold_rank == 1:
        scores = {"G": 0.6, "D": 0.3, "X": 0.1}
    else:
        scores = {"D": 0.6, "G": 0.3, "X": 0.1}
    return {
        "round": round_number,
        "fact_id": None if round_number == 0 else f"F{round_number}",
        "posteriors": [
            {"id": branch_id, "label": branch_id, "posterior": score}
            for branch_id, score in sorted(
                scores.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def _full_record(case_id: str = "c1"):
    ranks = {0: 2, 1: 2, 2: 2, 3: 2, 4: 1, 5: 1, 6: 1, 7: 2, 8: 2}
    snapshots = []
    decisions = []
    for cycle, round_number in enumerate((2, 4, 6, 8), start=1):
        snapshot = StopSnapshot(
            cycle_index=cycle,
            micro_round=round_number,
            queue_length=2,
            eligible_count=8 - round_number,
            top1_id="D" if round_number in {2, 8} else "G",
            top2_id="G" if round_number in {2, 8} else "D",
            top1_stable_cycles=0 if round_number == 2 else 2,
            margin_z=math.log(2),
            cycle_js=0.1 if round_number == 2 else 0.001,
            effective_updates=1 if round_number == 2 else 0,
            target_turnover=round_number in {4, 8},
            canonical_novel_count=2,
            compiler_hit_count=1,
            provenance_hit_count=1,
            pool_exhausted=round_number == 8,
            leader_support_count=2 if round_number == 2 else 0,
            leader_against_count=0,
        )
        snapshots.append(snapshot.to_dict())
        challenge = ["F5"] if round_number == 4 else []
        decision = StopDecision(
            action=(
                "continue"
                if round_number in {2, 4}
                else "stop"
            ),
            policy="saturation_challenge",
            reason=(
                "not_saturated" if round_number == 2
                else "challenge_veto" if round_number == 4
                else "saturated_no_challenge"
            ),
            cycle_index=cycle,
            micro_round=round_number,
            shadow=True,
            advisor_called=round_number < 8,
            challenge_status=(
                "continue" if challenge
                else "none" if round_number < 8
                else ""
            ),
            challenge_fact_ids=tuple(challenge),
        )
        decisions.append(decision.to_dict())
    return {
        "status": "OK",
        "case_id": case_id,
        "profile": "p5_headline",
        "gold_branch_id": "G",
        "trace": {
            "selected_fact_ids": [f"F{i}" for i in range(1, 9)],
            "posterior_trajectory": [
                _posterior(round_number, rank)
                for round_number, rank in ranks.items()
            ],
            "stop_snapshots": snapshots,
            "stop_decisions": decisions,
        },
    }


def test_fixed_oracle_and_adaptive_prefix_selection():
    record = _full_record()
    policy = harness.SaturationPolicy()
    assert harness.choose_round(record, "F2", policy=policy) == 2
    assert harness.choose_round(record, "F4", policy=policy) == 4
    assert harness.choose_round(record, "F8", policy=policy) == 8
    assert harness.choose_round(
        record, "O-oracle-prefix", policy=policy
    ) == 4
    assert harness.choose_round(record, "S1", policy=policy) == 4
    assert harness.choose_round(record, "S2", policy=policy) == 6
    assert harness.choose_round(record, "S3", policy=policy) == 2
    anchored = harness.EvidenceAnchoredF4Policy(
        min_margin_z=math.log(1.5),
        min_effective_updates=1,
    )
    assert harness.choose_round(
        record, "S4-evidence-anchored", policy=anchored,
    ) == 2
    quorum = harness.EvidenceQuorumF4Policy(min_margin_z=math.log(1.5))
    assert harness.choose_round(
        record, "S5-evidence-quorum", policy=quorum,
    ) == 2


def test_replay_audits_cost_premature_stop_and_prefix_hash():
    record = _full_record()
    policy = harness.SaturationPolicy()
    f2 = harness.replay_record(record, "F2", policy=policy)
    f4 = harness.replay_record(record, "F4", policy=policy)
    s2 = harness.replay_record(record, "S2", policy=policy)
    assert f2["errors"]["premature_stop"]
    assert f4["gold"]["final"]["top1"]
    assert not f4["errors"]["premature_stop"]
    assert s2["cost"]["facts"] == 6
    assert s2["cost"]["advisor_calls"] == 3
    assert f4["stop"]["prefix_hash"] != f2["stop"]["prefix_hash"]


def test_metric_block_bootstrap_summary_and_loco_are_case_clustered():
    policy = harness.SaturationPolicy()
    full = [_full_record("c1"), _full_record("c2")]
    f4 = [harness.replay_record(row, "F4", policy=policy) for row in full]
    s2 = [harness.replay_record(row, "S2", policy=policy) for row in full]
    metrics = harness.metric_block(f4)
    assert metrics["gold_rank_at_1"] == 1.0
    assert metrics["facts"]["mean"] == 4
    paired = harness.paired_bootstrap(f4, s2, n_boot=100)
    assert paired["cases"] == 2
    assert paired["facts_saved"]["delta"] == pytest.approx(-2)
    summary = harness.summarize([*f4, *s2], n_boot=100)
    assert summary["independent_validation_gate"]["status"] == "not_evaluated"
    assert summary["paired_case_cluster_bootstrap"]["p5_headline::S2-F4"][
        "cases"
    ] == 2
    loco = harness.loco_replay(full, arm="S1")
    assert loco["exploratory_only"]
    assert len(loco["rows"]) == 2
    anchored_loco = harness.loco_anchored_replay(full)
    assert anchored_loco["exploratory_only"]
    assert len(anchored_loco["rows"]) == 2
    quorum_loco = harness.loco_quorum_replay(full)
    assert quorum_loco["exploratory_only"]
    assert len(quorum_loco["rows"]) == 2
    diagnosis = harness.diagnose_failure_modes(
        full,
        saturation_policy=policy,
        anchored_policy=harness.EvidenceAnchoredF4Policy(),
        quorum_policy=harness.EvidenceQuorumF4Policy(),
    )
    assert diagnosis["saturation_conjuncts"]["cycle_snapshots"] == 8
    assert diagnosis["advisor"]["called"] == 6
    assert diagnosis["f4_to_f8"]["gold_rank_worsened"] == 2
    independent = harness.independent_validation_gate([*f4, *s2])
    assert independent["status"] == "evaluated"
    assert not independent["passed"]
    assert independent["profiles"]["p5_headline"]["S2"][
        "premature_stop_upper_95"
    ] > 0.05
    assert harness._risk_upper_95(0, 59) < 0.05


def test_runtime_generation_keeps_gold_outside_stop_payload_source():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "Gold branch IDs are used only after full trajectory generation" in source
    assert "shadow_stop_policy=True" in source
    assert "answer_mapper_called" in source
