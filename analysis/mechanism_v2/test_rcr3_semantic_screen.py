from __future__ import annotations

import json
import importlib.util

from analysis.mechanism_v2.online_runner import read_jsonl
from analysis.mechanism_v2.rcr3_end_to_end import DEFAULT_OUT
from analysis.mechanism_v2.rcr3_semantic_screen import (
    _proxy_summary,
    screen_payload,
    validate_screen,
)


def test_screen_payload_is_method_blind() -> None:
    document = read_jsonl(DEFAULT_OUT / "semantic_screen_inputs.jsonl")[0]
    payload = screen_payload(document)
    encoded = json.dumps(payload, sort_keys=True)
    for forbidden in ("lite3_safe", "rcr3_default", "compact4_true3gen"):
        assert forbidden not in encoded

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {item for child in value.values() for item in keys(child)}
        if isinstance(value, list):
            return {item for child in value for item in keys(child)}
        return set()

    assert not keys(payload) & {"arm_outcomes", "appearances", "strict_top1", "success"}


def test_screen_validator_requires_complete_candidate_coverage() -> None:
    response = {
        "reference_identifiability": {
            "judgment": "family_only_not_full_specificity",
            "decisive_spans": [],
            "unsupported_components": ["subtype"],
        },
        "candidate_relations": [
            {"candidate_id": "J001", "relation": "complete_equivalent"},
            {"candidate_id": "J002", "relation": "partial_parent_or_component"},
        ],
        "case_quality_flags": [],
    }
    assert validate_screen(response, {"J001", "J002"}) is None
    response["candidate_relations"] = response["candidate_relations"][:1]
    assert "cover every candidate" in str(validate_screen(response, {"J001", "J002"}))


def test_frozen_screen_inputs_are_complete() -> None:
    rows = read_jsonl(DEFAULT_OUT / "semantic_screen_inputs.jsonl")
    assert len(rows) == 300
    assert sum(len(row["candidate_registry"]) for row in rows) == 3533
    assert all(
        len({candidate["candidate_id"] for candidate in row["candidate_registry"]})
        == len(row["candidate_registry"])
        for row in rows
    )


def test_repository_client_is_importable_from_script_environment() -> None:
    assert importlib.util.find_spec("agentclinic_tree_dx") is not None


def test_proxy_summary_fails_closed_on_malformed_relation_container() -> None:
    rows = [{
        "success": False,
        "screen_response": {"candidate_relations": {"J001": {}}},
        "arm_outcomes": {
            arm: {"success": False}
            for arm in ("lite3_safe", "rcr3_default", "compact4_true3gen")
        },
    }]
    summary = _proxy_summary(rows)
    assert all(
        values["complete_top1"] == 0
        for values in summary["arm_endpoints"].values()
    )
