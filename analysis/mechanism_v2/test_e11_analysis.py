from __future__ import annotations

from analysis.mechanism_v2.e11_analysis import (
    exact_mcnemar,
    holm_adjust,
    load_arms,
    paired_contrast,
    stable_most_common,
    _runtime_payload_sha_by_case,
)
from analysis.mechanism_v2.e11_b07_factorial import DEFAULT_OUT
from analysis.mechanism_v2.online_runner import read_jsonl


def test_exact_mcnemar_known_values() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(0, 5) == 0.0625
    assert exact_mcnemar(1, 4) == 0.375


def test_holm_is_monotone_in_p_order() -> None:
    records = [
        {"exact_mcnemar_p": 0.03, "label": "b"},
        {"exact_mcnemar_p": 0.01, "label": "a"},
        {"exact_mcnemar_p": 0.5, "label": "c"},
    ]
    adjusted = holm_adjust(records, "holm")
    by_label = {row["label"]: row["holm"] for row in adjusted}
    assert by_label["a"] <= by_label["b"] <= by_label["c"]


def test_stable_most_common_breaks_frequency_ties_lexically() -> None:
    from collections import Counter

    counter = Counter(["Zulu", "Alpha", "Zulu", "Beta", "Alpha", "Beta"])
    assert stable_most_common(counter, 3) == [
        ("Alpha", 2), ("Beta", 2), ("Zulu", 2)
    ]


def test_completed_arm_join_and_primary_direction() -> None:
    arms = load_arms(DEFAULT_OUT)
    record = paired_contrast(
        arms,
        "off_refine_off",
        "relevant_refine_off",
        "gold_top1",
        "test",
        repetitions=100,
    )
    assert record["n"] == 400
    assert record["left_only"] == 5
    assert record["right_only"] == 0
    assert record["delta_right_minus_left"] == -0.0125


def test_runtime_payload_hash_reconstructs_all_telemetry_cases() -> None:
    payloads = _runtime_payload_sha_by_case(DEFAULT_OUT, "relevant_refine_off")
    telemetry = {
        row["payload_sha256"]
        for row in read_jsonl(
            DEFAULT_OUT / "arms/relevant_refine_off/telemetry.jsonl"
        )
    }
    assert len(payloads) == 400
    assert sum(value in telemetry for value in payloads.values()) == 394
