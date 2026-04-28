from agentclinic_tree_dx.adapters.agentclinic_env import AgentClinicEnv
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


class DummyPatient:
    def answer_question(self, question: str):
        return {"patient_answer": f"A:{question}"}


class DummyTester:
    def perform_test(self, test_type: str, request: str):
        return {"type": test_type, "request": request, "result": "ok"}


class DummyModerator:
    def __init__(self):
        self.last_payload = None

    def review_case(self, payload):
        self.last_payload = payload
        return {"grade": "pass", "reason": "coherent"}

class UpstreamStylePatient:
    def inference_patient(self, question: str):
        return f"Patient says: {question}"


class UpstreamStyleMeasurement:
    def inference_measurement(self, request: str):
        return f"Measurement: {request}"


class DummyLLM:
    def __init__(self):
        self.responses = {
            "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
            "RootSelector": {
                "root_label": "respiratory syndrome",
                "time_course": "acute",
                "supporting_facts": ["dyspnea"],
                "excluded_root_candidates": [],
                "need_external_knowledge": False,
                "confidence": 0.6,
            },
            "BranchCreator": {
                "branches": [{"id": "B1", "label": "pneumonia", "prior_estimate": 1.0, "danger": 0.7}],
                "frontier": ["B1"],
                "need_external_knowledge": False,
            },
            "TemporaryLeafPlanner": {
                "candidate_leaves_ranked": [{"branch_id": "B1", "type": "ORDER_LAB", "content": "cbc", "score": 0.9}],
                "selected_primary_action": {"branch_id": "B1", "type": "ORDER_LAB", "content": "cbc"},
            },
            "EvidenceAnnotator": {
                "result_summary": "wbc elevated",
                "major_update": False,
                "calculator_applicable": False,
                "formal_rule_available": False,
                "branch_effects": {"B1": "moderate_for"},
                "contradiction_detected": False,
                "reopen_candidates": [],
            },
            "PostUpdateStateReviser": {
                "branch_decisions": [{"branch_id": "B1", "decision": "confirm", "rationale": "sufficient"}]
            },
            "TerminationJudge": {"ready_to_stop": True, "termination_type": "confirmation", "reason": "done"},
            "FinalAggregator": {
                "final_mode": "single_leading_diagnosis",
                "leading_diagnosis_or_parent": "pneumonia",
                "ranked_differential": ["pneumonia"],
                "coexisting_processes": [],
                "supporting_evidence": ["wbc elevated"],
                "conflicting_evidence": [],
                "immediate_actions": ["antibiotics"],
                "recommended_next_tests_if_any": [],
                "safety_net_or_reopen_triggers": [],
                "confidence": 0.8,
            },
        }

    def call_module(self, module_name, prompt_text, payload):
        return self.responses[module_name]


def test_agentclinic_env_routes_patient_and_tester_calls():
    env = AgentClinicEnv(
        case_id="c1",
        initial_summary="dyspnea",
        patient_agent=DummyPatient(),
        tester_agent=DummyTester(),
        moderator_agent=DummyModerator(),
    )

    assert env.ask_patient("cough?") == {"patient_answer": "A:cough?"}
    assert env.order_lab("cbc")["type"] == "lab"


def test_controller_attaches_moderator_review_with_agentclinic_env():
    moderator = DummyModerator()
    env = AgentClinicEnv(
        case_id="c2",
        initial_summary="dyspnea",
        patient_agent=DummyPatient(),
        tester_agent=DummyTester(),
        moderator_agent=moderator,
    )
    controller = AgentClinicTreeController(env=env, llm=DummyLLM())

    result = controller.run(DiagnosticState(case_id="c2"))

    assert result["leading_diagnosis_or_parent"] == "pneumonia"
    assert result["moderator_review"]["grade"] == "pass"
    assert moderator.last_payload["case_id"] == "c2"


def test_agentclinic_env_supports_upstream_agentclinic_agent_interfaces():
    env = AgentClinicEnv(
        case_id="c3",
        initial_summary="fever",
        patient_agent=UpstreamStylePatient(),
        tester_agent=UpstreamStyleMeasurement(),
        moderator_agent=DummyModerator(),
    )

    assert env.ask_patient("How long?") == {"patient_answer": "Patient says: How long?"}
    assert env.request_test_or_measurement("temperature") == {
        "type": "measurement",
        "request": "temperature",
        "result": "Measurement: temperature",
    }


def test_controller_uses_skip_payload_when_moderator_is_not_configured():
    env = AgentClinicEnv(
        case_id="c4",
        initial_summary="cough",
        patient_agent=DummyPatient(),
        tester_agent=DummyTester(),
    )
    controller = AgentClinicTreeController(env=env, llm=DummyLLM())

    result = controller.run(DiagnosticState(case_id="c4"))

    assert result["moderator_review"]["status"] == "skipped"
