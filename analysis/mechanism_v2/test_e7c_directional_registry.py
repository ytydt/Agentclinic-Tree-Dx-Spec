from analysis.mechanism_v2.e7c_directional_registry import (
    ARM_BOUNDED,
    RELATION_TYPES,
    build_relation_graph,
    inheritance_policy,
    make_relation_payload,
    validate_relation_response,
)


def _source_row():
    return {
        "case_key": "slice/1",
        "vignette": "A chronic site-specific process.",
        "candidates": [
            {
                "candidate_id": "D1",
                "label": "Disease",
                "support_spans": ["process"],
                "contradict_spans": [],
            },
            {
                "candidate_id": "D2",
                "label": "Chronic site-specific Disease",
                "support_spans": ["chronic site-specific"],
                "contradict_spans": [],
            },
        ],
    }


def test_relation_validator_requires_every_pair_once():
    response = {
        "relations": [
            {
                "pair_id": "P1",
                "source_endpoint": "right",
                "target_endpoint": "left",
                "relation": "temporal_refinement_of",
                "confidence": "high",
                "qualifier_spans": ["chronic"],
            }
        ]
    }
    assert validate_relation_response(response, {"P1"}) is None
    assert validate_relation_response(response, {"P1", "P2"}) is not None
    assert "temporal_refinement_of" in RELATION_TYPES


def test_bounded_graph_keeps_entities_separate_and_adds_policy():
    row = _source_row()
    pairs = [{"pair_id": "P1", "left_label": "Disease", "right_label": "Chronic site-specific Disease"}]
    response = {
        "relations": [
            {
                "pair_id": "P1",
                "source_endpoint": "right",
                "target_endpoint": "left",
                "relation": "temporal_refinement_of",
                "confidence": "high",
                "qualifier_spans": ["chronic"],
            }
        ]
    }
    graph = build_relation_graph(row, pairs, response, ARM_BOUNDED)
    assert graph[0]["source_id"] == "D2"
    assert graph[0]["target_id"] == "D1"
    assert "independent qualifier" in graph[0]["inheritance_policy"]
    assert "target(base)->source(refinement)" in inheritance_policy("temporal_refinement_of")


def test_relation_payload_contains_no_evaluator_fields():
    payload = make_relation_payload(
        _source_row(),
        [{"pair_id": "P1", "left_label": "Disease", "right_label": "Chronic site-specific Disease"}],
    )
    assert "gold" not in payload
    assert "options" not in payload
    assert payload["pairs"][0]["right"]["support_spans"] == ["chronic site-specific"]
