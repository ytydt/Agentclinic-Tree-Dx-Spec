from agentclinic_tree_dx.adapters.sdbench_env import SDbenchEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


class DummyGatekeeper:
    def __init__(self):
        self.asks = []
        self.tests = []
        self.diagnosis = None

    def get_case_abstract(self):
        return "42-year-old with dyspnea"

    def ask(self, question: str):
        self.asks.append(question)
        return {"answer": "yes"}

    def test(self, test_name_or_panel: str):
        self.tests.append(test_name_or_panel)
        return {"result": "abnormal"}

    def diagnose(self, diagnosis: str):
        self.diagnosis = diagnosis
        return {"accepted": True, "diagnosis": diagnosis}


class AltMethodGatekeeper:
    def __init__(self):
        self.questions = []
        self.ordered_tests = []
        self.submitted = None
        self.initial_case_info = "57-year-old with chest pain"

    def ask_question(self, question: str):
        self.questions.append(question)
        return "no"

    def order_test(self, test_name_or_panel: str):
        self.ordered_tests.append(test_name_or_panel)
        return "normal"

    def submit_diagnosis(self, diagnosis: str):
        self.submitted = diagnosis
        return "submitted"


def _sdbench_modules(action_type="ASK_PATIENT", leading="Pulmonary embolism"):
    return {
        "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
        "RootSelector": {
            "root_label": "acute respiratory syndrome",
            "time_course": "hours",
            "supporting_facts": ["dyspnea"],
            "excluded_root_candidates": [],
            "confidence": 0.8,
            "need_external_knowledge": False,
        },
        "BranchCreator": {
            "branches": [
                {"id": "B1", "label": "PE", "status": "live", "prior_estimate": 0.60, "danger": 0.9},
                {"id": "B2", "label": "PNA", "status": "live", "prior_estimate": 0.20, "danger": 0.6},
                {"id": "B3", "label": "CHF", "status": "live", "prior_estimate": 0.12, "danger": 0.4},
                {"id": "B4", "label": "ANX", "status": "live", "prior_estimate": 0.08, "danger": 0.1},
            ],
            "frontier": ["B1", "B2", "B3", "B4"],
            "need_external_knowledge": False,
        },
        "Hypothesis": {"top_hypotheses": ["PE"]},
        "TestChooser": {"candidates": [{"action_type": "ASK", "content": "from_test_chooser"}]},
        "Challenger": {"risks": []},
        "Stewardship": {"notes": []},
        "Checklist": {"valid": True, "issues": []},
        "Consensus": {"type": "ASK_PATIENT", "content": "from_consensus"},
        "TemporaryLeafPlanner": {
            "candidate_leaves_ranked": [{"branch_id": "B1", "type": action_type, "content": "from_planner", "score": 0.8}],
            "selected_primary_action": {"branch_id": "B1", "type": action_type, "content": "from_planner"},
        },
        "EvidenceAnnotator": {
            "result_summary": "answer supports PE",
            "major_update": False,
            "calculator_applicable": False,
            "formal_rule_available": False,
            "branch_effects": {"B1": "neutral", "B2": "neutral", "B3": "neutral", "B4": "neutral"},
            "contradiction_detected": False,
            "reopen_candidates": [],
        },
        "PostUpdateStateReviser": {
            "branch_decisions": [
                {"branch_id": "B1", "decision": "confirm", "rationale": "high posterior"},
                {"branch_id": "B2", "decision": "park", "rationale": "lower posterior"},
                {"branch_id": "B3", "decision": "park", "rationale": "lower posterior"},
                {"branch_id": "B4", "decision": "park", "rationale": "lower posterior"},
            ]
        },
        "TerminationJudge": {"ready_to_stop": False, "termination_type": "continue", "reason": "not used in this test"},
        "FinalDiagnosisEmitter": {"final_diagnosis": leading},
    }


def test_sdbench_mode_uses_consensus_action_and_submits_diagnosis():
    gatekeeper = DummyGatekeeper()
    env = SDbenchEnv(case_id="sd1", gatekeeper=gatekeeper, module_responses=_sdbench_modules())
    config = ControllerConfig(execution_mode="sdbench_patch", min_readiness_to_commit=0.55)
    controller = AgentClinicTreeController(env=env, config=config)

    result = controller.run(DiagnosticState(case_id="sd1"))

    assert gatekeeper.asks == ["from_consensus"]
    assert result["diagnosis"] == "Pulmonary embolism"
    assert result["submission"]["accepted"] is True


def test_sdbench_mode_enforces_top3_and_other_mass_tracking():
    gatekeeper = DummyGatekeeper()
    env = SDbenchEnv(case_id="sd-top3", gatekeeper=gatekeeper, module_responses=_sdbench_modules())
    config = ControllerConfig(execution_mode="sdbench_patch", min_readiness_to_commit=0.99, max_turn_budget=1)
    controller = AgentClinicTreeController(env=env, config=config)
    state = DiagnosticState(case_id="sd-top3")

    controller.run(state)

    assert len(state.frontier) <= 3
    assert state.other_mass > 0.0
    assert len(state.differential_history) >= 1


def test_sdbench_mode_rejects_illegal_outbound_action():
    gatekeeper = DummyGatekeeper()
    env = SDbenchEnv(case_id="sd2", gatekeeper=gatekeeper, module_responses={})
    config = ControllerConfig(execution_mode="sdbench_patch")
    controller = AgentClinicTreeController(env=env, config=config)

    try:
        controller.execute_primary_action(DiagnosticState(case_id="sd2"), {"type": "USE_NOTEBOOK", "content": "x"})
        assert False, "Expected ValueError for illegal SDbench action"
    except ValueError:
        assert True


def test_sdbench_env_supports_alternative_gatekeeper_method_names():
    gk = AltMethodGatekeeper()
    env = SDbenchEnv(case_id="sd3", gatekeeper=gk, module_responses={})

    assert env.get_case_summary() == "57-year-old with chest pain"
    assert env.ask_gatekeeper("Any fever?") == {"answer": "no"}
    assert env.request_test("troponin") == {"result": "normal"}
    assert env.submit_diagnosis("ACS") == {"submission": "submitted"}


def test_sdbench_env_supports_callable_hooks_for_custom_gatekeeper_shapes():
    class CustomGatekeeper:
        def __init__(self):
            self.summary = "custom summary"
            self.log = []

        def q(self, text: str):
            self.log.append(("q", text))
            return "answer"

        def t(self, text: str):
            self.log.append(("t", text))
            return "test-result"

        def d(self, text: str):
            self.log.append(("d", text))
            return "ok"

    gk = CustomGatekeeper()
    env = SDbenchEnv(
        case_id="sd4",
        gatekeeper=gk,
        case_summary_getter=lambda x: x.summary,
        ask_fn=lambda x, q: x.q(q),
        test_fn=lambda x, t: x.t(t),
        diagnose_fn=lambda x, d: x.d(d),
        module_responses={},
    )

    assert env.get_case_summary() == "custom summary"
    assert env.ask_gatekeeper("question") == {"answer": "answer"}
    assert env.request_test("test") == {"result": "test-result"}
    assert env.submit_diagnosis("dx") == {"submission": "ok"}
