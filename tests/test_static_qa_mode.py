from agentclinic_tree_dx.adapters.static_qa_env import StaticQAEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import DiagnosticState


def _static_modules():
    return {
        "VignetteParser": {
            "vignette": "Patient with chest pain.",
            "question": "Most likely diagnosis?",
            "options": ["A", "B", "C", "D"],
            "evidence_items": [{"fact": "pain radiates to arm"}],
        },
        "SafetyController": {"interrupt_active": False, "reason": "stable", "required_actions": []},
        "RootSelector": {
            "root_label": "acute coronary syndrome syndrome",
            "time_course": "hours",
            "supporting_facts": ["chest pain"],
            "excluded_root_candidates": [],
            "confidence": 0.8,
            "need_external_knowledge": False,
        },
        "BranchCreator": {
            "branches": [{"id": "B1", "label": "ACS", "status": "live", "prior_estimate": 0.85, "danger": 0.9}],
            "frontier": ["B1"],
            "need_external_knowledge": False,
        },
        "Hypothesis": {"notes": []},
        "EvidenceAllocator": {"notes": []},
        "Challenger": {"notes": []},
        "ReasoningEconomyAuditor": {"notes": []},
        "Checklist": {"valid": True},
        "Consensus": {"type": "ANALYZE_VIGNETTE", "content": "derive key finding"},
        "TemporaryAnalyticLeafPlanner": {
            "candidate_leaves_ranked": [
                {"branch_id": "B1", "type": "ANALYZE_VIGNETTE", "content": "derive key finding", "score": 0.6}
            ],
            "selected_primary_action": {"branch_id": "B1", "type": "ANALYZE_VIGNETTE", "content": "derive key finding"},
        },
        "ToolUseGate": {"allow": True, "reason": "not needed", "justification": ""},
        "EvidenceAnnotator": {
            "result_summary": "supports ACS",
            "major_update": False,
            "calculator_applicable": False,
            "formal_rule_available": False,
            "branch_effects": {"B1": "neutral"},
            "contradiction_detected": False,
            "reopen_candidates": [],
        },
        "PostUpdateStateReviser": {
            "branch_decisions": [{"branch_id": "B1", "decision": "confirm", "rationale": "high posterior"}]
        },
        "TerminationJudge": {"ready_to_stop": False, "termination_type": "continue", "reason": "unused"},
        "AnswerMapper": {"final_answer": "A", "answer_option_mapping": {"A": 0.9, "B": 0.1}},
    }


def test_static_qa_mode_parses_vignette_and_returns_single_answer():
    env = StaticQAEnv(
        case_id="medqa-1",
        vignette="Raw vignette text",
        question="Which diagnosis is most likely?",
        options=["A", "B", "C", "D"],
        module_responses=_static_modules(),
    )
    config = ControllerConfig(execution_mode="static_diagnosis_qa", min_readiness_to_commit=0.8)
    controller = AgentClinicTreeController(env=env, config=config)

    state = DiagnosticState(case_id="medqa-1")
    result = controller.run(state)

    assert state.static_question == "Most likely diagnosis?"
    assert len(state.static_evidence_items) == 1
    assert result["final_answer"] == "A"
    assert result["answer_option_mapping"]["A"] == 0.9


def test_static_mode_rejects_interactive_action_types():
    env = StaticQAEnv(
        case_id="medqa-2",
        vignette="Raw vignette text",
        question="Q",
        options=["A", "B"],
        module_responses={},
    )
    config = ControllerConfig(execution_mode="static_diagnosis_qa")
    controller = AgentClinicTreeController(env=env, config=config)

    try:
        controller.execute_primary_action(DiagnosticState(case_id="medqa-2"), {"type": "USE_NOTEBOOK", "content": "x"})
        assert False, "Expected ValueError for illegal static QA action"
    except ValueError:
        assert True
