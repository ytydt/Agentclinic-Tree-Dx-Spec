from __future__ import annotations

from analysis.mechanism_v2.common import FrozenExactSynonymBridge
from analysis.mechanism_v2.e12_e7_factorial import (
    ARMS,
    BRIDGE_PATH,
    FIRST,
    GRAPH,
    PAIRWISE,
    POINTWISE,
    RAW,
    S1,
    arm_spec,
    build_pool,
    load_jobs,
    make_payload,
    validate_response,
)


def test_arm_matrix_is_18_main_plus_2_incremental() -> None:
    assert len(ARMS) == 20
    assert arm_spec("raw_k5_first") == {
        "representation": RAW,
        "depth": 3,
        "width": 5,
        "comparator": FIRST,
        "incremental": False,
    }
    assert arm_spec("raw_depth2_k10_pairwise") == {
        "representation": RAW,
        "depth": 2,
        "width": 10,
        "comparator": PAIRWISE,
        "incremental": True,
    }


def test_pointwise_validator_requires_exact_candidate_coverage() -> None:
    ids = {"D1", "D2"}
    valid = {
        "candidate_assessments": [
            {"candidate_id": "D1", "fit": "strong", "completeness": "complete"},
            {"candidate_id": "D2", "fit": "weak", "completeness": "unsupported"},
        ],
        "champion_id": "D1",
        "runner_up_id": "D2",
        "margin": "high",
    }
    assert validate_response(valid, ids, POINTWISE) is None
    valid["candidate_assessments"] = valid["candidate_assessments"][:1]
    assert "cover every candidate" in str(validate_response(valid, ids, POINTWISE))


def test_pairwise_validator_requires_real_pair() -> None:
    ids = {"D1", "D2"}
    valid = {
        "champion_id": "D1",
        "runner_up_id": "D2",
        "margin": "medium",
        "decisive_pair": {"left_id": "D1", "right_id": "D2", "winner_id": "D1"},
    }
    assert validate_response(valid, ids, PAIRWISE) is None
    valid["decisive_pair"]["right_id"] = "D1"
    assert "decisive_pair" in str(validate_response(valid, ids, PAIRWISE))


def test_real_frozen_inputs_are_complete_nested_and_blind() -> None:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    jobs, _ = load_jobs(bridge)
    assert len(jobs) == 300
    assert sum(job["family"] == "DA" for job in jobs) == 150
    assert sum(job["family"] == "MCR" for job in jobs) == 150
    assert sum(bool(job["graph_available"]) for job in jobs) == 258
    for job in jobs:
        k5 = job["pools"]["depth3_k5"]
        k10 = job["pools"]["depth3_k10"]
        assert 2 <= k5["actual_width"] <= 5
        assert k5["actual_width"] <= k10["actual_width"] <= 10
        assert set(k5["candidate_ids_by_priority"]).issubset(
            k10["candidate_ids_by_priority"]
        )
        raw_payload = make_payload(job, arm_spec("raw_k5_pointwise"))
        s1_payload = make_payload(job, arm_spec("s1_k5_pointwise"))
        assert raw_payload["candidates"] == s1_payload["candidates"]
        assert "gold" not in raw_payload


def test_safe_identity_pool_does_not_use_substring_folding() -> None:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    renal = bridge.canonical_key("renal cancer")
    papillary = bridge.canonical_key("papillary renal cancer")
    assert renal != papillary
    registry = [
        {"concept_key": renal, "candidate_id": "D1", "label": "renal cancer"},
        {"concept_key": papillary, "candidate_id": "D2", "label": "papillary renal cancer"},
    ]
    calls = [["renal cancer", "papillary renal cancer"], [], []]
    pool = build_pool(registry, calls, [], bridge, depth=1, width=5)
    # The toy registry keys are explicit distinct concepts; pool construction
    # never performs an additional substring fold.
    assert pool["actual_width"] == 2
    assert {row["candidate_id"] for row in pool["candidates"]} == {"D1", "D2"}
