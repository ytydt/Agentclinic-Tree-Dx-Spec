"""Offline unit tests for E7c post-run analysis."""
import hashlib
import json

from analysis.mechanism_v2.e7c_analysis import (
    _selector_wire_payloads,
    exact_mcnemar,
    flip_mechanism_census,
    index_conditions,
    lexical_direction_diagnostics,
    paired_comparison,
    relation_repeat_consistency,
)
from analysis.mechanism_v2.e7c_directional_registry import ARMS


def _row(case: str, arm: str, *, hit: bool, success: bool = True):
    return {
        "case_key": case,
        "arm": arm,
        "family": "DA",
        "success": success,
        "gold_top1": hit,
        "champion_label": f"{case}-{arm}",
        "relation_typing_success": True,
    }


def test_exact_mcnemar_symmetry():
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(1, 5) == exact_mcnemar(5, 1)


def test_ita_keeps_terminal_failure_in_denominator():
    rows = []
    for arm in ARMS:
        rows.append(_row("c1", arm, hit=arm == "directional_relation"))
        rows.append(
            _row(
                "c2",
                arm,
                hit=arm == "exact_control",
                success=arm != "directional_relation",
            )
        )
    indexed = index_conditions(rows)
    ita = paired_comparison(
        indexed, "directional_relation", "exact_control", ita=True
    )
    served = paired_comparison(
        indexed, "directional_relation", "exact_control", ita=False
    )
    assert ita["n"] == 2
    assert ita["left_only"] == 1
    assert ita["right_only"] == 1
    assert served["n"] == 1
    assert served["excluded_selector_failure"] == 1


def test_condition_blocks_must_be_complete():
    try:
        index_conditions([_row("c1", ARMS[0], hit=False)])
    except ValueError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("incomplete block was accepted")


def test_lexical_direction_diagnostic_obeys_predicate_semantics():
    chunks = [
        {
            "case_key": "c1",
            "success": True,
            "pairs": [
                {"pair_id": "P1", "left_label": "Disease", "right_label": "Acute Disease"},
                {"pair_id": "P2", "left_label": "Tumor", "right_label": "Skin Tumor"},
            ],
            "response": {
                "relations": [
                    {
                        "pair_id": "P1",
                        "relation": "subtype_of",
                        "source_endpoint": "right",
                    },
                    {
                        "pair_id": "P2",
                        "relation": "parent_of",
                        "source_endpoint": "right",
                    },
                ]
            },
        }
    ]
    result = lexical_direction_diagnostics(chunks)
    assert result["agree"] == 1
    assert result["disagree"] == 1


def test_selector_telemetry_uses_wire_not_canonical_payload_hash():
    rows = []
    for arm in ARMS:
        row = _row("c1", arm, hit=False)
        row.update(
            {
                "vignette": "A case",
                "candidates": [
                    {
                        "candidate_id": "D1",
                        "label": "Disease",
                        "support_spans": [],
                        "contradict_spans": [],
                    },
                    {
                        "candidate_id": "D2",
                        "label": "Acute Disease",
                        "support_spans": ["acute"],
                        "contradict_spans": [],
                    },
                ],
            }
        )
        rows.append(row)
    relation_rows = [
        {
            "case_key": "c1",
            "chunk_index": 0,
            "success": True,
            "pairs": [
                {
                    "pair_id": "P1",
                    "left_label": "Disease",
                    "right_label": "Acute Disease",
                }
            ],
            "response": {
                "relations": [
                    {
                        "pair_id": "P1",
                        "source_endpoint": "right",
                        "target_endpoint": "left",
                        "relation": "subtype_of",
                        "confidence": "high",
                        "qualifier_spans": ["acute"],
                    }
                ]
            },
        }
    ]
    by_hash = _selector_wire_payloads(rows, relation_rows)
    assert len(by_hash) == 4
    exact_payload = {
        "case_id": "c1",
        "vignette": "A case",
        "candidates": rows[0]["candidates"],
        "relation_graph": [],
    }
    wire_hash = hashlib.sha256(
        json.dumps(exact_payload, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    assert by_hash[wire_hash] == {"exact_control"}


def test_inverse_parent_subtype_repeats_are_consistent_but_direction_flips_are_not():
    chunks = [
        {
            "case_key": "c1",
            "success": True,
            "pairs": [
                {"pair_id": "P1", "left_label": "Disease", "right_label": "Acute Disease"},
                {"pair_id": "P2", "left_label": "Acute Disease", "right_label": "Disease"},
                {"pair_id": "P3", "left_label": "Disease", "right_label": "Acute Disease"},
            ],
            "response": {
                "relations": [
                    {
                        "pair_id": "P1",
                        "relation": "parent_of",
                        "source_endpoint": "left",
                        "target_endpoint": "right",
                    },
                    {
                        "pair_id": "P2",
                        "relation": "subtype_of",
                        "source_endpoint": "left",
                        "target_endpoint": "right",
                    },
                    {
                        "pair_id": "P3",
                        "relation": "subtype_of",
                        "source_endpoint": "left",
                        "target_endpoint": "right",
                    },
                ]
            },
        }
    ]
    result = relation_repeat_consistency(chunks)
    assert result["n_repeated_pair_groups"] == 1
    assert result["n_inconsistent_repeated_pair_groups"] == 1


def test_flip_census_tracks_graph_salience():
    rows = []
    for arm in ARMS:
        row = _row("c1", arm, hit=arm == "directional_relation")
        row["champion_id"] = "D2" if arm == "directional_relation" else "D1"
        row["champion_label"] = row["champion_id"]
        row["relation_graph"] = (
            [{"source_id": "D2", "target_id": "D3", "relation": "subtype_of"}]
            if arm == "directional_relation"
            else []
        )
        rows.append(row)
    result = flip_mechanism_census(
        index_conditions(rows), "directional_relation", "exact_control"
    )
    assert result["n_champion_flips"] == 1
    assert result["left_champion_is_graph_node"] == 1
    assert result.get("right_champion_is_graph_node", 0) == 0
