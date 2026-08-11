from collections import Counter

from analysis.mechanism_v2.e6_representation_fidelity import (
    FLAT,
    GRAPH,
    RAW,
    matched_representations,
    paired,
    select_cases,
    validate_builder,
    validate_selector,
    whitespace_word_count,
)


VIGNETTE = (
    "A patient had fever before treatment. After treatment the fever resolved, "
    "but MRI showed a lesion. No cough was reported."
)


def _builder_response():
    quotes = [
        "A patient",
        "had fever",
        "before treatment",
        "After treatment",
        "the fever resolved",
        "MRI showed a lesion",
        "No cough",
        "was reported",
    ]
    facts = [
        {"fact_id": f"F{index:02d}", "text": f"fact {index}", "source_quote": quote}
        for index, quote in enumerate(quotes, 1)
    ]
    nodes = [
        {
            "node_id": f"N{index:02d}",
            "kind": "symptom" if index != 6 else "imaging",
            "text": f"node {index}",
            "polarity": "absent" if index == 7 else "present",
            "time_anchor": "unspecified",
            "scope": "patient",
            "source_quote": quote,
        }
        for index, quote in enumerate(quotes, 1)
    ]
    relations = [
        {
            "source_id": f"N{index:02d}",
            "relation": "before",
            "target_id": f"N{index + 1:02d}",
            "justification": "explicit chronology",
        }
        for index in range(1, 5)
    ]
    return {
        "flat_facts": facts,
        "graph_nodes": nodes,
        "graph_relations": relations,
    }


def _selector_response():
    return {
        "candidates": [
            {
                "candidate_id": f"D{index}",
                "label": f"diagnosis {index}",
                "confidence": 0.9 / index,
                "support_refs": ["N01"],
                "contradiction_refs": [],
                "missing_or_uncertain": [],
            }
            for index in range(1, 6)
        ],
        "champion_id": "D1",
        "runner_up_id": "D2",
        "top1_probability": 0.7,
        "margin": "medium",
        "rationale": "D1 best preserves the chronology.",
    }


def test_frozen_case_sample_is_balanced_and_challenge_enriched():
    rows = select_cases()
    assert len(rows) == len({row["case_key"] for row in rows}) == 300
    assert Counter(row["family"] for row in rows) == {"DA": 150, "MCR": 150}
    assert {
        flag: sum(bool(row["challenge"][flag]) for row in rows)
        for flag in ("temporal", "negative", "composite_target")
    } == {"temporal": 220, "negative": 165, "composite_target": 140}


def test_builder_validator_enforces_grounded_quotes_and_typed_edges():
    response = _builder_response()
    assert validate_builder(response, VIGNETTE) is None
    response["flat_facts"][0]["source_quote"] = "hallucinated quotation"
    assert "substring" in validate_builder(response, VIGNETTE)

    response = _builder_response()
    response["graph_relations"][0]["target_id"] = "N99"
    assert "endpoint" in validate_builder(response, VIGNETTE)


def test_all_representations_are_word_matched_per_case():
    matched = matched_representations(VIGNETTE, _builder_response())
    counts = {arm: whitespace_word_count(record["text"]) for arm, record in matched.items()}
    assert set(matched) == {RAW, FLAT, GRAPH}
    assert len(set(counts.values())) == 1
    assert all(record["matched_whitespace_words"] == next(iter(counts.values())) for record in matched.values())
    assert sum(record["padding_words"] > 0 for record in matched.values()) >= 1


def test_length_cap_truncates_every_overlong_condition_to_same_target():
    matched = matched_representations(VIGNETTE, _builder_response(), word_cap=12)
    assert {record["matched_whitespace_words"] for record in matched.values()} == {12}
    assert all(whitespace_word_count(record["text"]) == 12 for record in matched.values())
    assert any(record["truncated_words"] > 0 for record in matched.values())


def test_selector_validator_requires_exact_rank_contract():
    response = _selector_response()
    assert validate_selector(response) is None
    response["runner_up_id"] = "D3"
    assert "first two" in validate_selector(response)


def test_paired_contrast_excludes_failed_conditions_and_tracks_direction():
    rows = [
        {"case_key": "gain", "arm": RAW, "success": True, "strict_top1": False,
         "champion_label": "wrong", "gold_rank": 2},
        {"case_key": "gain", "arm": GRAPH, "success": True, "strict_top1": True,
         "champion_label": "gold", "gold_rank": 1},
        {"case_key": "excluded", "arm": RAW, "success": True, "strict_top1": True,
         "champion_label": "gold", "gold_rank": 1},
        {"case_key": "excluded", "arm": GRAPH, "success": False, "strict_top1": False,
         "champion_label": "", "gold_rank": None},
    ]
    result = paired(rows, RAW, GRAPH, "strict_top1")
    assert result["n_comparable"] == 1
    assert result["left_only"] == 0
    assert result["right_only"] == 1
    assert result["delta_right_minus_left"] == 1.0
