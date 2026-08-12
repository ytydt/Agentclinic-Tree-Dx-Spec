from __future__ import annotations

from analysis.mechanism_v2.common import FrozenExactSynonymBridge
from analysis.mechanism_v2.rcr3_end_to_end import (
    ARMS,
    BRIDGE_PATH,
    COMPACT4,
    LITE3,
    LOGICAL_CALLS,
    RCR3,
    _grounded_span,
    build_registry,
    load_jobs,
    sanitize_skeleton,
    selector_payload,
    validate_selector,
)


def test_arm_budget_contract() -> None:
    assert ARMS == (LITE3, RCR3, COMPACT4)
    assert LOGICAL_CALLS == {LITE3: 3, RCR3: 3, COMPACT4: 4}


def test_grounded_span_rejects_paraphrase_and_overlong_text() -> None:
    vignette = "QTc was 380 ms. The patient denied fever."
    assert _grounded_span("QTc was 380 ms", vignette)
    assert not _grounded_span("QTc was prolonged", vignette)
    assert not _grounded_span("x" * 181, "x" * 181)


def test_skeleton_drops_ungrounded_fact_and_relation() -> None:
    raw = {
        "observations": [
            {
                "fact_id": "F01", "kind": "laboratory", "raw_span": "QTc was 380 ms",
                "normalized_fact": "QTc 380 ms", "polarity": "present", "subject": "patient",
                "time_anchor": "presentation", "scope": "heart", "epistemic_status": "observed",
            },
            {
                "fact_id": "F02", "kind": "sign", "raw_span": "prolonged QTc",
                "normalized_fact": "QT prolonged", "polarity": "present", "subject": "patient",
                "time_anchor": "presentation", "scope": "heart", "epistemic_status": "observed",
            },
        ],
        "relations": [
            {"source_fact_id": "F02", "relation": "causes", "target_fact_id": "F01", "justification_span": "QTc was 380 ms"}
        ],
        "diagnostic_assertions": [],
        "requested_object": {"kind": "disease", "obligations": []},
    }
    clean = sanitize_skeleton(raw, "QTc was 380 ms. The patient denied fever.")
    assert [row["fact_id"] for row in clean["observations"]] == ["F01"]
    assert clean["relations"] == []
    assert clean["grounding_audit"]["dropped_observation_n"] == 1


def test_safe_registry_separates_substring_entities_and_neutralizes_payload() -> None:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    evidence = [
        {"fact_id": "E1", "raw_span": "renal mass", "polarity": "present"},
        {"fact_id": "E2", "raw_span": "papillary pattern", "polarity": "present"},
    ]
    candidates = [
        {"label": "renal cancer", "candidate_type": "disease", "view": "a", "support_fact_ids": ["E1"], "counter_fact_ids": [], "unique_evidence_fact_ids": [], "satisfies_obligations": [], "missing_obligations": [], "rare_or_low_prior": False},
        {"label": "papillary renal cancer", "candidate_type": "subtype", "view": "b", "support_fact_ids": ["E1", "E2"], "counter_fact_ids": [], "unique_evidence_fact_ids": ["E2"], "satisfies_obligations": [], "missing_obligations": [], "rare_or_low_prior": False},
    ]
    registry = build_registry(
        case_key="toy/1", bridge=bridge, evidence_rows=evidence,
        candidate_rows=candidates, requested_object={"kind": "disease", "obligations": []},
    )
    assert len(registry["registry"]) == 2
    assert len(registry["payload_candidates"]) == 2
    assert all("registry_priority_score" not in row for row in registry["payload_candidates"])
    assert all("generator_views" not in row for row in registry["payload_candidates"])


def test_selector_validator_requires_complete_candidate_coverage() -> None:
    ids = {"C001", "C002"}
    response = {
        "candidate_assessments": [
            {"candidate_id": "C001", "fit": "strong", "completeness": "complete", "temporal_scope_fit": "fits"},
            {"candidate_id": "C002", "fit": "weak", "completeness": "partial", "temporal_scope_fit": "unknown"},
        ],
        "decisive_pair": {"left_id": "C001", "right_id": "C002", "winner_id": "C001"},
        "champion_id": "C001", "runner_up_id": "C002", "margin": "medium",
    }
    assert validate_selector(response, ids) is None
    response["candidate_assessments"] = response["candidate_assessments"][:1]
    assert "cover each candidate" in str(validate_selector(response, ids))


def test_real_jobs_are_frozen_and_online_payload_is_target_blind() -> None:
    jobs, _ = load_jobs()
    assert len(jobs) == 300
    assert sum(job["family"] == "DA" for job in jobs) == 150
    assert sum(job["family"] == "MCR" for job in jobs) == 150
    toy_registry = {
        "requested_object": {"kind": "disease", "obligations": []},
        "payload_candidates": [
            {"candidate_id": "C001", "label": "A"},
            {"candidate_id": "C002", "label": "B"},
        ],
    }
    payload = selector_payload(jobs[0], toy_registry, None)
    assert "gold" not in payload
    assert "options" not in payload
