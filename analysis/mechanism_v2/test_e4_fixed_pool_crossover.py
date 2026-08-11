from analysis.mechanism_v2.common import FrozenExactSynonymBridge, ROOT
from analysis.mechanism_v2.e4_fixed_pool_crossover import (
    ARM_DETERMINISTIC,
    build_pool,
    deterministic_response,
    extract_source_candidates,
    validate_response,
)


def test_extractors_ignore_historical_champion_and_scores():
    stage = {
        "champion": "Forbidden old winner",
        "stages": {
            "s3": {
                "raw": {"shortlist": [{"label": "A", "why_kept": "finding"}]},
                "shortlist": ["A"],
            }
        },
    }
    assert extract_source_candidates("e7", stage) == [
        {"label": "A", "support": ["finding"], "contradict": []}
    ]


def test_pool_payload_is_source_and_score_blind():
    bridge = FrozenExactSynonymBridge(ROOT / "data/knowledge_raw/disease_name_bridge.json")
    stages = {
        "e7": {"stages": {"s3": {"raw": {"shortlist": [{"label": "Disease A", "why_kept": "x"}]}}}},
        "forest": {"stages": {"evidence": [{"evidence_id": "E1", "raw_span": "y"}], "registry": [{"preferred_name": "Disease B", "supporting_evidence": ["E1"], "score_logit": 99, "status": "live"}]}},
        "collapse": {"stages": {"registry": [{"preferred_label": "Disease C", "support_spans": ["z"], "status": "active"}]}},
    }
    pool = build_pool("case/1", stages, bridge)
    payload_text = str(pool["payload_candidates"])
    assert "audit_sources" not in payload_text
    assert "score" not in payload_text
    assert len(pool["payload_candidates"]) == 3


def test_response_schema_and_deterministic_control():
    response = {"champion_id": "D1", "runner_up_id": "D2", "margin": "low"}
    assert validate_response(response, {"D1", "D2"}) is None
    assert validate_response({**response, "champion_id": "D9"}, {"D1", "D2"})
    job = {
        "case_key": "case/1",
        "pool": {
            "candidates": [
                {"candidate_id": "D1", "concept_key": "a", "support_items": ["x"], "contradict_items": []},
                {"candidate_id": "D2", "concept_key": "b", "support_items": [], "contradict_items": []},
            ]
        },
    }
    result = deterministic_response(job)
    assert result["champion_id"] == "D1"
    assert ARM_DETERMINISTIC == "evidence_count_control"
