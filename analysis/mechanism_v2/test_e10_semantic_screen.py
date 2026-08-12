from analysis.mechanism_v2.e10_semantic_screen import _validator


def test_screen_validator_requires_complete_registry():
    validate = _validator({"I1", "S1"})
    assert validate({"candidate_relations": [
        {"candidate_id": "I1", "relation": "exact_equivalent"},
        {"candidate_id": "S1", "relation": "unrelated"},
    ]}) is None
    assert validate({"candidate_relations": [
        {"candidate_id": "I1", "relation": "exact_equivalent"},
    ]})
    assert validate({"candidate_relations": [
        {"candidate_id": "I1", "relation": "invented"},
        {"candidate_id": "S1", "relation": "unrelated"},
    ]})
