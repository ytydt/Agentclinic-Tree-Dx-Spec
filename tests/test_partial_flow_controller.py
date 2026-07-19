from __future__ import annotations

from collections import Counter

import pytest

from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


class FakeLLM:
    def __init__(self):
        self.calls: list[str] = []
        self.annotation_count = 0

    def call_module(self, module_name, prompt_text, payload):
        self.calls.append(module_name)
        if module_name == "VignetteParser":
            return {
                "vignette": "adult with acute chest pain",
                "question": "What is the diagnosis?",
                "options": [
                    {"id": "A", "description": "ACS"},
                    {"id": "B", "description": "GERD"},
                ],
                "evidence_items": [
                    {"id": "e1", "kind": "finding", "content": "acute chest pain"}
                ],
            }
        if module_name == "SafetyController":
            return {
                "interrupt_active": False,
                "reason": "stable",
                "required_actions": [],
            }
        if module_name == "RootSelector":
            return {
                "root_label": "acute chest pain syndrome",
                "time_course": "hours",
                "supporting_facts": ["chest pain"],
                "excluded_root_candidates": [],
                "confidence": 0.7,
                "need_external_knowledge": False,
            }
        if module_name == "BranchCreator":
            return {
                "branches": [
                    {
                        "id": "B1",
                        "label": "Coronary",
                        "status": "live",
                        "prior_estimate": 0.6,
                        "danger": 0.8,
                    },
                    {
                        "id": "B2",
                        "label": "Gastrointestinal",
                        "status": "live",
                        "prior_estimate": 0.4,
                        "danger": 0.1,
                    },
                ],
                "frontier": ["B1", "B2"],
                "need_external_knowledge": False,
            }
        if module_name in {"TemporaryLeafPlanner", "TemporaryAnalyticLeafPlanner"}:
            frontier = payload["frontier"]
            return {
                "candidate_leaves_ranked": [{
                    "branch_id": frontier[0],
                    "type": "ANALYZE_VIGNETTE",
                    "content": f"analyze turn {payload['timestep']}",
                    "score": 0.9,
                    "expected_information_gain": 0.5,
                    "target_branches": {frontier[0]: "support"},
                    "primary_function": "differentiate",
                }]
            }
        if module_name == "EvidenceAnnotator":
            self.annotation_count += 1
            branch_ids = payload["state"]["branches"]
            return {
                "result_summary": f"annotation turn {self.annotation_count}",
                "major_update": self.annotation_count == 1,
                "calculator_applicable": False,
                "formal_rule_available": False,
                "branch_effects": {
                    branch_id: "weak_for" for branch_id in branch_ids
                },
                "contradiction_detected": False,
                "reopen_candidates": [],
            }
        if module_name == "PostUpdateStateReviser":
            return {
                "branch_decisions": [
                    {
                        "branch_id": branch_id,
                        "decision": "keep_coarse",
                        "rationale": "retain for forced expansion",
                    }
                    for branch_id, branch in payload["branches"].items()
                    if branch["level"] == 1
                ]
            }
        if module_name == "SubBranchCreator":
            parent = payload["parent_branch"]
            if parent["id"] == "B2":
                return {
                    "needs_expansion": False,
                    "reason_if_not": "fixture decline",
                }
            return {
                "needs_expansion": True,
                "sub_branches": [{
                    "id": "B1.1",
                    "label": "Acute coronary syndrome",
                    "parent_id": "B1",
                    "level": 2,
                    "status": "live",
                    "prior_estimate": 1.0,
                    "danger": 0.8,
                }],
                "sub_frontier": ["B1.1"],
                "need_external_knowledge": False,
            }
        if module_name in {"TerminationJudge", "AnswerMapper", "FinalAggregator"}:
            raise AssertionError(f"{module_name} must not run in partial flow")
        raise AssertionError(f"Unexpected module call: {module_name}")


def test_partial_flow_runs_two_turns_expands_all_l1_and_stops_post_evidence(
    monkeypatch,
):
    llm = FakeLLM()
    env = MockAgentClinicEnv(case_summary="adult with acute chest pain")
    controller = AgentClinicTreeController(
        env,
        llm=llm,
        config=ControllerConfig(
            execution_mode="static_diagnosis_qa",
            partial_flow=True,
            max_timesteps=2,
            force_expand_all_l1=True,
            stop_after_evidence=True,
            max_live_frontier=10,
            talp_disc_profile="off",
        ),
    )

    update_calls = 0
    original_update = controller.apply_probability_update

    def counted_update(*args, **kwargs):
        nonlocal update_calls
        update_calls += 1
        return original_update(*args, **kwargs)

    monkeypatch.setattr(controller, "apply_probability_update", counted_update)
    result = controller.run(DiagnosticState(case_id="partial-fixture"))

    counts = Counter(llm.calls)
    assert result["trace_type"] == "partial_controller"
    assert result["timesteps_completed"] == 2
    assert [turn["timestep"] for turn in result["turns"]] == [1, 2]
    assert result["turns"][1]["checkpoint"] == "post_evidence"
    assert counts["EvidenceAnnotator"] == 2
    assert counts["TemporaryAnalyticLeafPlanner"] == 2
    assert counts["PostUpdateStateReviser"] == 1
    assert update_calls == 1

    audit = result["l1_expansion_audit"]
    assert audit["l1_total"] == 2
    assert audit["l1_expanded"] == 2
    assert audit["l1_expansion_rate"] == pytest.approx(1.0)
    assert counts["SubBranchCreator"] == 2
    assert {branch["outcome"] for branch in audit["branches"]} == {
        "expanded",
        "fallback_expanded",
    }
    assert len(result["l1_tree"]) == 2
    assert len(result["l2_tree"]) == 2
    assert all(branch["children"] for branch in result["l1_tree"])

    assert "discrimination_audit" in result
    assert result["answer_mapper_called"] is False
    assert counts["TerminationJudge"] == 0
    assert counts["AnswerMapper"] == 0
    assert counts["FinalAggregator"] == 0
