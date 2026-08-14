from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analysis.mechanism_v2.ceiling_pool_census import (
    COMPLETE,
    build_relation_cards,
    classify_e12_delivery,
    classify_e5_delivery,
    compile_ab,
    compile_final,
    gwet_ac1,
    old14_frontier_adapter,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl


class _ExactBridge:
    def equivalent(self, left: str, right: str) -> bool:
        return left.strip().lower() == right.strip().lower()


def _candidate(concept_id: str, label: str) -> dict[str, str]:
    return {"concept_id": concept_id, "preferred_label": label}


def test_old14_frontier_adapter_has_explicit_schema_priority_and_no_output_fallback():
    a = _candidate("C1", "alpha")
    b = _candidate("C2", "beta")
    stage = {
        "ordered_diagnoses": ["must not be used"],
        "stages": {"registry": [a, b], "frontier": ["C2"]},
    }
    rows, metadata = old14_frontier_adapter("APHHM-C", stage)
    assert [row["preferred_label"] for row in rows] == ["beta"]
    assert metadata["frontier_field_priority"] == ["frontier"]
    assert metadata["fallback_used"] is False

    old_lite = {"stages": {"registry": [a], "frontier_after_g": [a], "frontier_final": [b]}}
    rows, metadata = old14_frontier_adapter("Lite", old_lite)
    assert rows == [a]
    assert metadata["frontier_field"] == "frontier_after_g"
    assert metadata["frontier_field_priority"] == ["frontier_after_g", "frontier_final"]

    new_lite = {"stages": {"registry": [b], "frontier_final": [b]}}
    rows, metadata = old14_frontier_adapter("Lite", new_lite)
    assert rows == [b]
    assert metadata["frontier_field"] == "frontier_final"

    missing = {"ordered_diagnoses": ["ranked output"], "stages": {"registry": [a]}}
    rows, metadata = old14_frontier_adapter("Forest", missing)
    assert rows == []
    assert metadata["missing_reason"] == "missing_or_invalid_stages.frontier_final"
    assert metadata["fallback_used"] is False


def test_e5_builder_failure_and_schema_failure_are_distinct():
    builder = classify_e5_delivery(
        {"success": False, "payload_sha256": "", "error": "construction_failure: bad perturbation"}
    )
    schema = classify_e5_delivery(
        {"success": False, "payload_sha256": "abc", "error": "invalid response schema"}
    )
    assert builder == {
        "status": "builder_failure_no_payload",
        "sent": False,
        "served": False,
        "actual_payload": False,
    }
    assert schema["status"] == "response_schema_failure_payload_sent"
    assert schema["sent"] is True
    assert schema["served"] is False
    assert schema["actual_payload"] is True


def test_e12_graph_unavailable_has_no_actual_opportunity_and_first_is_deterministic():
    unavailable = classify_e12_delivery(
        {
            "comparator": "pairwise",
            "payload_sha256": "",
            "success": False,
            "error": "frozen E6 typed graph unavailable; fail closed",
        }
    )
    assert unavailable["status"] == "graph_unavailable_no_actual_opportunity"
    assert unavailable["actual_payload"] is False
    first = classify_e12_delivery(
        {"comparator": "first", "payload_sha256": "", "success": True, "error": ""}
    )
    assert first["actual_payload"] is True
    assert first["actual_payload_kind"] == "deterministic_control"
    assert first["sent"] is False


def test_relation_cards_are_case_normalized_arm_blind_deterministic_and_chunked():
    occurrences = []
    labels = ["alpha", "beta", "gamma"]
    for arm in ("secret_arm_1", "secret_arm_2"):
        for position, label in enumerate(labels, 1):
            occurrences.append(
                {
                    "case_key": "S/1",
                    "candidate_label": label,
                    "normalized_label": label,
                    "benchmark_family": "DA",
                    "experiment_group": "E5",
                    "arm_id": arm,
                    "surface": "actual_payload",
                }
            )
    metadata = {"S/1": {"vignette": "record", "gold": "alpha"}}
    identities = {
        "S/1": {
            "reference_diagnosis": "alpha",
            "reference_identifiability": "unique_full_reference",
        }
    }
    e2 = {("S/1", "beta"): {"relation": "not_equivalent", "safe_exact": False}}
    first = build_relation_cards(
        occurrences, metadata, e2, identities, _ExactBridge(), chunk_size=1
    )
    second = build_relation_cards(
        occurrences, metadata, e2, identities, _ExactBridge(), chunk_size=1
    )
    relation_index, known, cards, card_index = first
    assert first == second
    assert len(relation_index) == 3
    assert {row["candidate_label"] for row in known} == {"alpha", "beta"}
    assert len(cards) == 3
    assert len(card_index) == 3
    serialized = json.dumps(cards, sort_keys=True)
    assert "secret_arm" not in serialized
    assert "experiment_group" not in serialized


def _review(card_id: str, values: dict[str, str]) -> dict:
    return {
        "blind_card_id": card_id,
        "success": True,
        "error": "",
        "review": {
            "candidate_relations": [
                {
                    "candidate_id": candidate_id,
                    "relation": relation,
                    "reason": "fixture",
                    "confidence": "high",
                }
                for candidate_id, relation in values.items()
            ]
        },
    }


def test_three_full_reviewers_majority_split_and_post_panel_root_override():
    temporary = tempfile.TemporaryDirectory()
    tmp_path = Path(temporary.name)
    out = tmp_path / "panel-fixture"
    cards = [
        {
            "blind_card_id": "RC1",
            "clinical_record": "record",
            "reference_diagnosis": "reference",
            "candidate_registry": [
                {"candidate_id": "C001", "label": "one"},
                {"candidate_id": "C002", "label": "two"},
            ],
        }
    ]
    index = [
        {
            "blind_card_id": "RC1",
            "candidate_id": "C001",
            "relation_id": "R1",
            "case_key": "S/1",
            "normalized_label": "one",
            "candidate_label": "one",
        },
        {
            "blind_card_id": "RC1",
            "candidate_id": "C002",
            "relation_id": "R2",
            "case_key": "S/1",
            "normalized_label": "two",
            "candidate_label": "two",
        },
    ]
    write_jsonl(out / "design/blinded_relation_cards.jsonl", cards)
    write_jsonl(out / "design/blinded_relation_index.jsonl", index)
    write_jsonl(
        out / "design/relation_universe.jsonl",
        [
            {
                "relation_id": "R1",
                "relation": COMPLETE,
                "resolution_source": "e2_root_reuse",
                "resolution_status": "root_adjudicated_reuse",
            },
            {
                "relation_id": "R2",
                "relation": "",
                "resolution_source": "three_model_adjudicated_panel_pending",
                "resolution_status": "model_panel_pending",
            },
        ],
    )
    write_jsonl(
        out / "reviewers/reviewer_a/reviews.jsonl",
        [_review("RC1", {"C001": COMPLETE, "C002": "not_equivalent"})],
    )
    write_jsonl(
        out / "reviewers/reviewer_b/reviews.jsonl",
        [_review("RC1", {"C001": COMPLETE, "C002": "partial_parent_or_component"})],
    )
    summary = compile_ab(out)
    assert summary["n_agreement"] == 1
    assert summary["n_disagreement"] == 1
    write_jsonl(
        out / "reviewers/reviewer_c/reviews.jsonl",
        [
            _review(
                "RC1",
                {
                    "C001": COMPLETE,
                    "C002": "conflicting_subtype_or_scope",
                },
            )
        ],
    )
    final_summary = compile_final(out)
    final = read_jsonl(out / "panel/three_model_adjudicated_panel.jsonl")
    assert final_summary["artifact_name"] == "three-model adjudicated panel"
    assert [row["final_relation"] for row in final] == [
        COMPLETE,
        "uncertain",
    ]
    assert final[0]["panel_status"] == "post_panel_frozen_override:e2_root_reuse"
    assert final[1]["panel_status"] == "three_way_split_mapped_to_uncertain"
    assert final[1]["post_panel_frozen_override"] is False
    assert final_summary["hidden_sentinel_calibration"]["e2_hidden_sentinels"]["reviewer_c"]["n"] == 1
    temporary.cleanup()


def test_gwet_ac1_contract():
    assert abs(gwet_ac1([COMPLETE, "not_equivalent"], [COMPLETE, "not_equivalent"]) - 1.0) < 1e-12
    value = gwet_ac1(
        [COMPLETE, COMPLETE, "not_equivalent"],
        [COMPLETE, "partial_parent_or_component", "not_equivalent"],
    )
    assert -1.0 <= value <= 1.0


class CeilingPoolCensusTests(unittest.TestCase):
    def test_old14_adapter(self):
        test_old14_frontier_adapter_has_explicit_schema_priority_and_no_output_fallback()

    def test_e5_delivery(self):
        test_e5_builder_failure_and_schema_failure_are_distinct()

    def test_e12_delivery(self):
        test_e12_graph_unavailable_has_no_actual_opportunity_and_first_is_deterministic()

    def test_blind_cards(self):
        test_relation_cards_are_case_normalized_arm_blind_deterministic_and_chunked()

    def test_three_model_panel(self):
        test_three_full_reviewers_majority_split_and_post_panel_root_override()

    def test_gwet(self):
        test_gwet_ac1_contract()


if __name__ == "__main__":
    unittest.main()
