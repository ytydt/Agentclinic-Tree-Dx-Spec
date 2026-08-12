from analysis.mechanism_v2.e11_split_screen import (
    candidate_validator,
    expand_retrieval_response,
    retrieval_validator,
)


def test_candidate_validator_requires_exact_coverage() -> None:
    validate = candidate_validator({"C1", "C2"})
    valid = {"candidate_relations": [
        {"candidate_id": "C1", "relation": "exact_equivalent"},
        {"candidate_id": "C2", "relation": "unrelated"},
    ]}
    assert validate(valid) is None
    assert validate({"candidate_relations": valid["candidate_relations"][:1]})


def test_retrieval_validator_and_expansion() -> None:
    validate = retrieval_validator({"R1", "N1", "H1"})
    valid = {
        "chunks": [["R1", "E", "D", "F"], ["N1", "G", "N", "N"], ["H1", "C", "I", "P"]],
        "bundles": [
            ["relevant", "D", "D", "B", "N"],
            ["random", "A", "A", "B", "N"],
            ["hard_negative", "M", "P", "G", "Y"],
        ],
    }
    assert validate(valid) is None
    expanded = expand_retrieval_response(valid)
    assert expanded["chunk_assessments"][0]["relation_to_reference"] == "direct_same_disease"
    assert expanded["bundle_assessments"][2]["clinically_misleading"] == "yes"
    invalid = dict(valid)
    invalid["chunks"] = valid["chunks"][:-1]
    assert validate(invalid)
