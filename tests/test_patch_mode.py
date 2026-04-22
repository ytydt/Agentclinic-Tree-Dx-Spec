from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import Branch, DiagnosticState


def _patch_modules(action_type="REQUEST_TEST_OR_MEASUREMENT"):
    return {
        "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
        "RootSelector": {
            "root_label": "acute syndrome",
            "time_course": "hours",
            "supporting_facts": ["symptom"],
            "excluded_root_candidates": [],
            "confidence": 0.8,
            "need_external_knowledge": False,
        },
        "BranchCreator": {
            "branches": [{"id": "B1", "label": "Dx1", "status": "live", "prior_estimate": 0.9, "danger": 0.4}],
            "frontier": ["B1"],
            "need_external_knowledge": False,
        },
        "TemporaryLeafPlanner": {
            "candidate_leaves_ranked": [{"branch_id": "B1", "type": action_type, "content": "pulse ox", "score": 0.7}],
            "selected_primary_action": {"branch_id": "B1", "type": action_type, "content": "pulse ox"},
        },
        "EvidenceAnnotator": {
            "result_summary": "value returned",
            "major_update": False,
            "calculator_applicable": False,
            "formal_rule_available": False,
            "branch_effects": {"B1": "neutral"},
            "contradiction_detected": False,
            "reopen_candidates": [],
        },
        "PostUpdateStateReviser": {"branch_decisions": [{"branch_id": "B1", "decision": "confirm", "rationale": "enough"}]},
        "TerminationJudge": {"ready_to_stop": False, "termination_type": "continue", "reason": "wait"},
        "FinalAggregator": {
            "final_mode": "single_leading_diagnosis",
            "leading_diagnosis_or_parent": "Dx1",
            "ranked_differential": ["Dx1"],
            "coexisting_processes": [],
            "supporting_evidence": ["fact"],
            "conflicting_evidence": [],
            "immediate_actions": [],
            "recommended_next_tests_if_any": [],
            "safety_net_or_reopen_triggers": [],
            "confidence": 0.9,
        },
    }


def test_patch_mode_outputs_benchmark_string():
    env = MockAgentClinicEnv(module_responses=_patch_modules())
    config = ControllerConfig(execution_mode="agentclinic_physician_patch", min_readiness_to_commit=0.8)
    controller = AgentClinicTreeController(env, config=config)

    result = controller.run(DiagnosticState(case_id="case-patch"))

    assert result["benchmark_output"] == "Diagnosis Ready: Dx1"
    assert "internal_reasoning_state" in result


def test_patch_mode_blocks_external_knowledge_if_disabled():
    env = MockAgentClinicEnv(module_responses={})
    config = ControllerConfig(execution_mode="agentclinic_physician_patch", allow_external_knowledge=False)
    controller = AgentClinicTreeController(env, config=config)
    state = DiagnosticState(case_id="case-patch")

    try:
        controller.execute_primary_action(
            state,
            {"type": "RETRIEVE_EXTERNAL_KNOWLEDGE", "content": "query"},
        )
        assert False, "Expected PermissionError"
    except PermissionError:
        assert True


def test_patch_mode_maps_legacy_test_actions_to_benchmark_channel():
    env = MockAgentClinicEnv(module_responses={})
    config = ControllerConfig(execution_mode="agentclinic_physician_patch")
    controller = AgentClinicTreeController(env, config=config)
    state = DiagnosticState(case_id="case-patch")

    controller.execute_primary_action(state, {"type": "ORDER_LAB", "content": "cbc"})

    assert state.actions_taken[-1]["external_action"] == "REQUEST_TEST_OR_MEASUREMENT"


def test_patch_mode_readiness_blocks_if_dangerous_alternative_remains():
    env = MockAgentClinicEnv(module_responses={})
    config = ControllerConfig(execution_mode="agentclinic_physician_patch", min_readiness_to_commit=0.7)
    controller = AgentClinicTreeController(env, config=config)
    state = DiagnosticState(case_id="case-patch")
    state.branches = {
        "B1": Branch("B1", "leading", "ROOT", 1, "live", 0.7, 0.8, 0.2, 0.0, 0.0),
        "B2": Branch("B2", "dangerous alt", "ROOT", 1, "live", 0.3, 0.2, 0.9, 0.0, 0.0),
    }

    assert controller.check_diagnosis_readiness(state) is False
