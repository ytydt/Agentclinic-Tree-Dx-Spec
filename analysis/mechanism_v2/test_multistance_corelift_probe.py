from __future__ import annotations

import json

import pytest

from analysis.mechanism_v2.multistance_corelift_probe import (
    ARMS,
    DEFAULT_WORKERS,
    MAX_PARALLEL_EXTRA,
    SAMPLE_SALT,
    SELECTOR_MODEL,
    accept_selector_response,
    build_completion_payload,
    build_selector_payload,
    exact_mcnemar,
    freeze_cohort,
    pool_for_arm,
    validate_completions,
)
from analysis.mechanism_v2.online_runner import assert_target_blind
from analysis.mechanism_v2.runtime_contract import stable_seed


class ToyBridge:
    def canonical_key(self, label: str) -> str:
        key = label.lower().strip()
        return {"alpha disease": "alpha", "alpha dx": "alpha"}.get(key, key)

    def equivalent(self, left: str, right: str) -> bool:
        return self.canonical_key(left) == self.canonical_key(right)


def _parent(candidate_id: str = "R1", label: str = "Alpha disease") -> dict:
    return {
        "candidate_id": candidate_id,
        "label": label,
        "stances": ["commit"],
        "raw_support_spans": [{"start": 0, "end": 5, "text": "fever"}],
        "raw_contradict_spans": [],
        "generator_assessments": [],
        "candidate_kind": "parent",
        "parent_candidate_id": "",
        "modifier_axes": [],
    }


def _case(parents: list[dict] | None = None) -> dict:
    return {
        "case_key": "DA_d2_heldout200b/1",
        "slice_id": "DA_d2_heldout200b",
        "family": "DA",
        "source_id": "1",
        "vignette": "fever with cardiac involvement and biopsy-proven myocarditis",
        "gold": "FORBIDDEN_GOLD",
        "registry": parents or [_parent(), _parent("R2", "Beta disease")],
        "original_champion": "FORBIDDEN_CHAMPION",
        "rank_seed": 1,
    }


def test_nonliteral_span_is_rejected() -> None:
    case = _case()
    response = {
        "completions": [
            {
                "parent_id": "R1",
                "completed_label": "Viral myocarditis",
                "axes": ["etiology"],
                "support_spans": ["this span is not in the vignette"],
                "reason": "x",
            }
        ]
    }
    out = validate_completions(response, case, ToyBridge())
    assert out["accepted"] == []
    assert out["rejected"][0]["reason"] == "nonliteral_support_span"


def test_equivalent_child_is_rejected() -> None:
    case = _case()
    response = {
        "completions": [
            {
                "parent_id": "R1",
                "completed_label": "Alpha dx",
                "axes": ["etiology"],
                "support_spans": ["fever"],
                "reason": "x",
            }
        ]
    }
    out = validate_completions(response, case, ToyBridge())
    assert out["accepted"] == []
    assert out["rejected"][0]["reason"] == "completion_equivalent_to_parent"


def test_replace_width_conserved_and_parallel_capped() -> None:
    registry = [_parent("R1"), _parent("R2"), _parent("R3")]
    children = [
        {**_parent(f"R{i}C", f"Child {i}"), "candidate_kind": "completion", "parent_candidate_id": f"R{i}"}
        for i in range(1, 6)
    ]
    union = pool_for_arm(registry, children, "union")
    replace = pool_for_arm(registry, children[:3], "replace")
    parallel = pool_for_arm(registry, children, "parallel")
    assert [row["candidate_id"] for row in union] == ["R1", "R2", "R3"]
    assert len(replace) == len(union)
    assert "R1" not in {row["candidate_id"] for row in replace}
    assert {row["candidate_id"] for row in replace} == {"R1C", "R2C", "R3C"}
    assert len(parallel) == len(union) + MAX_PARALLEL_EXTRA
    extra_ids = [row["candidate_id"] for row in parallel if row["candidate_kind"] == "completion"]
    assert extra_ids == ["R1C", "R2C", "R3C"]


def test_selector_rejects_out_of_pool_champion() -> None:
    cleaned, served, flags = accept_selector_response(
        {
            "champion_id": "RX",
            "runner_up_id": "R1",
            "margin": "high",
            "decisive_items": ["fever"],
            "rationale": "x",
            "rejected": [],
        },
        {"R1", "R2"},
        "fever with cardiac involvement",
    )
    assert served is False
    assert "champion_id_not_in_pool" in flags


def test_nonverbatim_decisive_item_does_not_unserve() -> None:
    cleaned, served, flags = accept_selector_response(
        {
            "champion_id": "R1",
            "runner_up_id": "",
            "margin": "medium",
            "decisive_items": ["not in the vignette at all"],
            "rationale": "x",
            "rejected": [{"candidate_id": "R2", "why": "less specific"}],
        },
        {"R1", "R2"},
        "fever with cardiac involvement",
    )
    assert served is True
    assert cleaned["champion_id"] == "R1"
    assert cleaned["decisive_items"] == []
    assert "decisive_item_not_verbatim" in flags


def test_selector_is_multistance_llama_not_deepseek() -> None:
    assert "deepseek" not in SELECTOR_MODEL.lower()
    assert SELECTOR_MODEL == "meta-llama/llama-3.3-70b-instruct"
    assert DEFAULT_WORKERS == 25


def test_payloads_are_target_blind() -> None:
    case = _case()
    completion = build_completion_payload(case)
    selector = build_selector_payload(case, "union", case["registry"])
    blob = json.dumps(completion) + json.dumps(selector)
    assert "FORBIDDEN_GOLD" not in blob
    assert "FORBIDDEN_CHAMPION" not in blob
    assert_target_blind(completion)
    assert_target_blind(selector)
    with pytest.raises(AssertionError):
        assert_target_blind({"gold": "leak"})


def test_sampling_rank_does_not_use_gold() -> None:
    freeze = freeze_cohort()
    assert freeze["n"] == 200
    assert freeze["families"] == {"DA": 100, "MCR": 100}
    for case in freeze["cases"]:
        expected = stable_seed(SAMPLE_SALT, case["family"], case["source_id"])
        assert case["rank_seed"] == expected
        payload = build_completion_payload(case)
        assert "gold" not in payload
        assert_target_blind(payload)


def test_exact_mcnemar_symmetry() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(3, 3) == exact_mcnemar(3, 3)
    assert exact_mcnemar(10, 0) < 0.01
    assert ARMS == ("union", "replace", "parallel")
