from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


def _base_modules():
    return {
        "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
        "RootSelector": {
            "root_label": "acute chest pain syndrome",
            "time_course": "hours",
            "supporting_facts": ["substernal pain"],
            "excluded_root_candidates": [],
            "confidence": 0.7,
            "need_external_knowledge": False,
        },
        "BranchCreator": {
            "branches": [
                {"id": "B1", "label": "ACS", "status": "live", "prior_estimate": 0.5, "danger": 0.8},
                {"id": "B2", "label": "GERD", "status": "live", "prior_estimate": 0.5, "danger": 0.1},
            ],
            "frontier": ["B1", "B2"],
            "need_external_knowledge": False,
        },
        "TemporaryLeafPlanner": {
            "candidate_leaves_ranked": [
                {"branch_id": "B1", "type": "ASK_PATIENT", "content": "radiation?", "score": 0.9}
            ],
            "selected_primary_action": {"branch_id": "B1", "type": "ASK_PATIENT", "content": "radiation?"},
        },
        "EvidenceAnnotator": {
            "result_summary": "pain radiates to left arm",
            "major_update": True,
            "calculator_applicable": False,
            "formal_rule_available": False,
            "branch_effects": {"B1": "strong_for", "B2": "moderate_against"},
            "contradiction_detected": False,
            "reopen_candidates": [],
        },
        "PostUpdateStateReviser": {
            "branch_decisions": [
                {"branch_id": "B1", "decision": "expand_now", "rationale": "high posterior"},
                {"branch_id": "B2", "decision": "park", "rationale": "lower posterior"},
            ]
        },
        "TerminationJudge": {
            "ready_to_stop": True,
            "termination_type": "working_differential",
            "reason": "prototype stop",
        },
        "FinalAggregator": {
            "final_mode": "ranked_working_differential",
            "leading_diagnosis_or_parent": "acute coronary syndrome",
            "ranked_differential": ["acute coronary syndrome", "gastroesophageal reflux"],
            "coexisting_processes": [],
            "supporting_evidence": ["left arm radiation"],
            "conflicting_evidence": [],
            "immediate_actions": ["obtain ECG"],
            "recommended_next_tests_if_any": ["troponin"],
            "safety_net_or_reopen_triggers": ["worsening pain"],
            "confidence": 0.74,
        },
    }


def test_controller_run_end_to_end():
    env = MockAgentClinicEnv(module_responses=_base_modules())
    controller = AgentClinicTreeController(env)
    result = controller.run(DiagnosticState(case_id="demo"))

    assert result["leading_diagnosis_or_parent"] == "acute coronary syndrome"
    assert env.asked == ["radiation?"]


def test_interrupt_override_executes_emergent_actions():
    modules = _base_modules()
    modules["SafetyController"] = {
        "interrupt_active": True,
        "reason": "shock",
        "required_actions": ["IV fluids", "vasopressors"],
    }
    env = MockAgentClinicEnv(module_responses=modules)
    controller = AgentClinicTreeController(env)
    result = controller.run(DiagnosticState(case_id="demo"))

    assert result["final_mode"] == "ranked_working_differential"
    assert env.emergent_actions == ["IV fluids", "vasopressors"]
