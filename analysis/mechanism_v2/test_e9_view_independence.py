from __future__ import annotations

from analysis.mechanism_v2.e9_view_independence import (
    DUPLICATE,
    REAL,
    ROTATED,
    SINGLE,
    build_condition_payloads,
    evidence_strings,
    validate_response,
)


class ToyBridge:
    def canonical_key(self, value: str) -> str:
        return value.lower().replace(" disease", "").strip()


def _raw(axis: str, first: str, second: str) -> dict:
    return {
        "axis": axis,
        "candidates": [
            {
                "name": first,
                "support_spans": [f"support {first}"],
                "contradict_spans": [],
                "why": f"why {first}",
                "axis_node": axis,
            },
            {
                "name": second,
                "support_spans": [f"support {second}"],
                "contradict_spans": ["shared negative"],
                "why": f"why {second}",
                "axis_node": axis,
            },
        ],
        "key_evidence_spans": [f"support {first}", "shared negative"],
    }


def _job() -> dict:
    return {
        "case_key": "DA_d2_seq100/1",
        "vignette": "A clean vignette.",
        "anchor_key": "ax_syndrome",
        "raw_views": {
            "ax_syndrome": _raw("s", "Alpha disease", "Beta"),
            "ax_mechanism": _raw("m", "Alpha", "Gamma"),
            "ax_modality": _raw("d", "Alpha", "Delta"),
        },
    }


def test_content_invariants() -> None:
    payloads = build_condition_payloads(_job(), ToyBridge())
    assert payloads[REAL]["candidate_registry"] == payloads[ROTATED]["candidate_registry"]
    assert payloads[SINGLE]["candidate_registry"] == payloads[DUPLICATE]["candidate_registry"]
    assert len(payloads[REAL]["views"]) == 3
    assert len(payloads[SINGLE]["views"]) == 1
    assert len(payloads[DUPLICATE]["views"]) == 3
    def semantic_content(view: dict) -> tuple:
        evidence = tuple(row["observation"] for row in view["evidence"])
        assessments = tuple(
            (
                row["candidate_id"], row["assessment"], row["axis_node"],
                row["protected_reason"], len(row["support_evidence_ids"]),
                len(row["contradict_evidence_ids"]),
            )
            for row in view["candidate_assessments"]
        )
        return evidence, assessments

    single_content = semantic_content(payloads[SINGLE]["views"][0])
    for view in payloads[DUPLICATE]["views"]:
        assert semantic_content(view) == single_content


def test_evidence_deduplicates() -> None:
    evidence = evidence_strings(_raw("s", "Alpha", "Beta"))
    assert evidence.count("support Alpha") == 1
    assert evidence.count("shared negative") == 1


def test_validator() -> None:
    payload = build_condition_payloads(_job(), ToyBridge())[REAL]
    valid = {
        "champion_id": payload["candidate_registry"][0]["candidate_id"],
        "runner_up_id": payload["candidate_registry"][1]["candidate_id"],
        "margin": "low",
        "decisive_evidence_ids": [payload["views"][0]["evidence"][0]["evidence_id"]],
        "view_contributions": [
            {"view_id": "V1", "contribution": "unique", "reason": "x"}
        ],
        "rationale": "x",
    }
    assert validate_response(valid, payload) is None
    valid["champion_id"] = "D999"
    assert "champion" in str(validate_response(valid, payload))
