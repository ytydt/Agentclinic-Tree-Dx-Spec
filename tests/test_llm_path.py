from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState
from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv


class FakeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call_module(self, module_name, prompt_text, payload):
        self.calls.append((module_name, prompt_text, payload))
        return self.responses[module_name]


def test_controller_uses_llm_module_calls_when_llm_is_provided():
    responses = {
        "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
        "RootSelector": {
            "root_label": "acute chest pain syndrome",
            "time_course": "hours",
            "supporting_facts": ["pain"],
            "excluded_root_candidates": [],
            "need_external_knowledge": False,
            "confidence": 0.6,
        },
        "BranchCreator": {
            "branches": [{"id": "B1", "label": "ACS", "prior_estimate": 1.0, "danger": 0.8}],
            "frontier": ["B1"],
            "need_external_knowledge": False,
        },
        "TemporaryLeafPlanner": {
            "candidate_leaves_ranked": [{"branch_id": "B1", "type": "ASK_PATIENT", "content": "onset?", "score": 1.0}],
            "selected_primary_action": {"branch_id": "B1", "type": "ASK_PATIENT", "content": "onset?"},
        },
        "EvidenceAnnotator": {
            "result_summary": "sudden onset",
            "major_update": False,
            "calculator_applicable": False,
            "formal_rule_available": False,
            "branch_effects": {"B1": "neutral"},
            "contradiction_detected": False,
            "reopen_candidates": [],
        },
        "PostUpdateStateReviser": {"branch_decisions": [{"branch_id": "B1", "decision": "confirm", "rationale": "enough"}]},
        "TerminationJudge": {"ready_to_stop": True, "termination_type": "confirmation", "reason": "done"},
        "FinalAggregator": {
            "final_mode": "single_leading_diagnosis",
            "leading_diagnosis_or_parent": "ACS",
            "ranked_differential": ["ACS"],
            "coexisting_processes": [],
            "supporting_evidence": ["onset"],
            "conflicting_evidence": [],
            "immediate_actions": ["ecg"],
            "recommended_next_tests_if_any": [],
            "safety_net_or_reopen_triggers": [],
            "confidence": 0.8,
        },
    }
    env = MockAgentClinicEnv(module_responses={})
    llm = FakeLLM(responses)
    controller = AgentClinicTreeController(env=env, llm=llm)

    result = controller.run(DiagnosticState(case_id="c1"))

    assert result["leading_diagnosis_or_parent"] == "ACS"
    assert [c[0] for c in llm.calls][:3] == ["SafetyController", "RootSelector", "BranchCreator"]
    assert env.asked == ["onset?"]
