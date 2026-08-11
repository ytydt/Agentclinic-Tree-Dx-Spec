from analysis.mechanism_v2.e1_input_factorial import (
    ARCH_AB02,
    ARCH_APHHM,
    COND_CLEAN_FIXED,
    COND_CLEAN_SHUFFLED,
    COND_OPTIONS_FIXED,
    COND_OPTIONS_SHUFFLED,
    clinical_body,
    condition_input,
    options_for_case,
    validate_response,
)


CASE = {
    "case_text": "History paragraph.\n\nTest paragraph.\n\nWhat is the most likely diagnosis?\n\nOptions:\nA. Alpha\nB. Beta",
    "annotation": {"source_options": {"A": "Alpha", "B": "Beta"}},
}


def test_factorial_inputs_have_expected_visibility_and_stability():
    assert clinical_body(CASE["case_text"]) == "History paragraph.\n\nTest paragraph."
    assert "Alpha" not in condition_input("slice/1", CASE, COND_CLEAN_FIXED)
    assert "Alpha" not in condition_input("slice/1", CASE, COND_CLEAN_SHUFFLED)
    assert "A. Alpha" in condition_input("slice/1", CASE, COND_OPTIONS_FIXED)
    shuffled = condition_input("slice/1", CASE, COND_OPTIONS_SHUFFLED)
    assert "[R" in shuffled and "Alpha" in shuffled
    assert shuffled == condition_input("slice/1", CASE, COND_OPTIONS_SHUFFLED)
    assert options_for_case(CASE) == [("A", "Alpha"), ("B", "Beta")]


def test_flat_and_hierarchical_validators():
    flat = {
        "candidates": [
            {"candidate_id": "D1", "label": "A"},
            {"candidate_id": "D2", "label": "B"},
            {"candidate_id": "D3", "label": "C"},
        ],
        "champion_id": "D1",
        "runner_up_id": "D2",
    }
    assert validate_response(ARCH_AB02, flat) is None
    hierarchical = {
        "l1_nodes": [{"node_id": "L1_1", "label": "family"}],
        "l2_candidates": [
            {"candidate_id": "D1", "label": "A", "parent_node_id": "L1_1"},
            {"candidate_id": "D2", "label": "B", "parent_node_id": "L1_1"},
            {"candidate_id": "D3", "label": "C", "parent_node_id": "L1_1"},
        ],
        "champion_id": "D1",
        "runner_up_id": "D2",
    }
    assert validate_response(ARCH_APHHM, hierarchical) is None
    hierarchical["l2_candidates"][0]["parent_node_id"] = "missing"
    assert validate_response(ARCH_APHHM, hierarchical)
