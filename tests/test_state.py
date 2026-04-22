from agentclinic_tree_dx.state import DiagnosticState


def test_state_serialization_contains_defaults():
    state = DiagnosticState(case_id="case-1")
    as_dict = state.to_dict()
    assert as_dict["case_id"] == "case-1"
    assert as_dict["interrupt"]["active"] is False
    assert as_dict["termination"]["termination_type"] == "continue"
