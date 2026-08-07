"""Unit tests for scripts/paper/mapper_bind_repair.py (Track B R1/R2)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import mapper_bind_repair as mbr  # noqa: E402


def _leaves_sweet():
    return [
        {
            "leaf_id": "B2.1",
            "leaf_label": "Sweet's Syndrome (Acute Febrile Neutrophilic Dermatosis)",
            "parent_id": "B2",
            "parent_label": "Inflammatory/Immune-Mediated",
        },
        {
            "leaf_id": "B2.3",
            "leaf_label": "Histiocytoid Sweet Syndrome",
            "parent_id": "B2",
            "parent_label": "Inflammatory/Immune-Mediated",
        },
        {
            "leaf_id": "B1.1",
            "leaf_label": "Leukemic cutis",
            "parent_id": "B1",
            "parent_label": "Neoplastic Infiltration",
        },
    ]


def test_repair_equivalent_empty_leaf_backfill():
    om = {
        "matched": False,
        "relation_type": "equivalent",
        "matched_leaf_ids": [],
        "confidence": "high",
    }
    out = mbr.repair_option_map(
        om, _leaves_sweet(), "Anti-TIF-1γ juvenile dermatomyositis (JDM)",
    )
    # no near leaf → no bind
    assert out["bind_repair_applied"] is False

    out2 = mbr.repair_option_map(
        om, _leaves_sweet(), "Histiocytoid Sweet syndrome",
    )
    assert out2["bind_repair_applied"] is True
    assert out2["bind_repair_rule"] == "bind_repair_equiv"
    assert "B2.3" in out2["matched_leaf_ids"]
    assert out2["matched"] is True


def test_repair_unrelated_near_exact_leaf():
    om = {
        "matched": False,
        "relation_type": "unrelated",
        "matched_leaf_ids": [],
        "confidence": "high",
        "rationale": "does not match",
    }
    out = mbr.repair_option_map(
        om, _leaves_sweet(), "Histiocytoid Sweet syndrome",
    )
    assert out["bind_repair_applied"] is True
    assert out["bind_repair_rule"] == "bind_repair_near_leaf"
    assert out["relation_type"] == "related"
    assert "B2.3" in out["matched_leaf_ids"]


def test_repair_no_near_leaf_guard():
    om = {
        "matched": False,
        "relation_type": "unrelated",
        "matched_leaf_ids": [],
    }
    out = mbr.repair_option_map(
        om, _leaves_sweet(), "Stage IV invasive renal urothelial carcinoma",
    )
    assert out["bind_repair_applied"] is False
    assert not out.get("matched_leaf_ids")


def test_repair_keeps_existing_ids():
    om = {
        "matched": True,
        "relation_type": "equivalent",
        "matched_leaf_ids": ["B1.1"],
    }
    out = mbr.repair_option_map(om, _leaves_sweet(), "Histiocytoid Sweet syndrome")
    assert out["bind_repair_applied"] is False
    assert out["matched_leaf_ids"] == ["B1.1"]


def test_v2_leaf_parent_without_mapper_bind():
    case = {
        "gold": "Histiocytoid Sweet syndrome",
        "l1": {
            "l1_posteriors": [
                {"id": "B2", "label": "Inflammatory/Immune-Mediated", "posterior": 0.5},
                {"id": "B1", "label": "Neoplastic Infiltration", "posterior": 0.4},
            ]
        },
    }
    mapper = {
        "gold_letter": "D",
        "gold_option_text": "Histiocytoid Sweet syndrome",
        "gold_diagnosis": "Histiocytoid Sweet syndrome",
        "projection": {
            "option_maps": {
                "D": {
                    "matched": False,
                    "relation_type": "unrelated",
                    "matched_leaf_ids": [],
                }
            }
        },
    }
    ap = mbr.acceptable_parents_v2(case, mapper, _leaves_sweet())
    assert ap["protocol"] == "v2_leaf_parent"
    assert "B2" in ap["acceptable_parent_ids"]
    assert ap["parent_source"] == "leaf_synonym"
    assert "B2.3" in ap["gold_leaf_ids"]


def test_v1_after_bind_repair_gets_parent():
    case = {
        "gold": "Histiocytoid Sweet syndrome",
        "l1": {
            "l1_posteriors": [
                {"id": "B2", "label": "Inflammatory/Immune-Mediated", "posterior": 0.5},
            ]
        },
    }
    mapper = {
        "gold_letter": "D",
        "gold_option_text": "Histiocytoid Sweet syndrome",
        "gold_diagnosis": "Histiocytoid Sweet syndrome",
        "projection": {
            "option_maps": {
                "D": {
                    "matched": False,
                    "relation_type": "unrelated",
                    "matched_leaf_ids": [],
                }
            }
        },
    }
    leaves = _leaves_sweet()
    repaired = mbr.apply_bind_repair_to_mapper(mapper, leaves)
    ap0 = mbr.acceptable_parents_v1(case, mapper, leaves)
    assert ap0["parent_source"] == "none"
    ap1 = mbr.acceptable_parents_v1(case, repaired, leaves)
    assert "B2" in ap1["acceptable_parent_ids"]
    assert "mapper_leaf_parent" in ap1["parent_source"]


def test_collect_tree_leaves_merges_ranking_and_tree():
    case = {
        "l2": {
            "final_ranking_labels": [
                {"id": "B1.1", "label": "Leukemic cutis", "parent": "B1"},
            ]
        }
    }
    tree_state = {
        "branches": {
            "B1": {"label": "Neo", "parent": "", "children": ["B1.1"]},
            "B1.1": {"label": "Leukemic cutis", "parent": "B1", "children": []},
            "B2": {"label": "Infl", "parent": "", "children": ["B2.3"]},
            "B2.3": {
                "label": "Histiocytoid Sweet Syndrome",
                "parent": "B2",
                "children": [],
            },
        }
    }
    leaves = mbr.collect_tree_leaves(case, tree_state)
    ids = {r["leaf_id"] for r in leaves}
    assert "B1.1" in ids and "B2.3" in ids


def test_live_inject_and_rescore_improves_gold_bind():
    case = {
        "gold": "Histiocytoid Sweet syndrome",
        "l2": {
            "final_ranking_labels": [
                {"id": "B1.1", "label": "Leukemic cutis", "parent": "B1", "rank": 1},
            ]
        },
        "l1": {
            "l1_posteriors": [
                {"id": "B1", "label": "Neo", "posterior": 0.6},
                {"id": "B2", "label": "Infl", "posterior": 0.4},
            ]
        },
    }
    tree_state = {
        "branches": {
            "B1": {"label": "Neo", "parent": "", "children": ["B1.1"], "posterior": 0.6},
            "B1.1": {
                "label": "Leukemic cutis",
                "parent": "B1",
                "children": [],
                "posterior": 0.5,
            },
            "B2": {"label": "Infl", "parent": "", "children": ["B2.3"], "posterior": 0.4},
            "B2.3": {
                "label": "Histiocytoid Sweet Syndrome",
                "parent": "B2",
                "children": [],
                "posterior": 0.35,
            },
        }
    }
    injected = mbr.build_injected_leaves(case, tree_state)
    assert any(r["leaf_id"] == "B2.3" and r.get("injected") for r in injected)
    mapper = {
        "gold_letter": "D",
        "gold_option_text": "Histiocytoid Sweet syndrome",
        "gold_diagnosis": "Histiocytoid Sweet syndrome",
        "option_top1": False,
        "option_top2": False,
        "option_rr": 0.0,
        "projection": {
            "option_maps": {
                "A": {
                    "matched": True,
                    "relation_type": "equivalent",
                    "matched_leaf_ids": ["B1.1"],
                },
                "D": {
                    "matched": False,
                    "relation_type": "unrelated",
                    "matched_leaf_ids": [],
                },
            }
        },
    }
    options = {
        "A": "Leukemic cutis",
        "D": "Histiocytoid Sweet syndrome",
    }
def test_synonym_bind_rescore_repairs_empty_gold():
    """Approach A harness helper: empty gold bind → synonym repair → ranks."""
    leaves = [
        {
            "leaf_id": "B2.3",
            "leaf_label": "Histiocytoid Sweet Syndrome",
            "parent_id": "B2",
            "parent_label": "Infl",
            "joint_rank": 1,
            "posterior": 0.4,
        },
        {
            "leaf_id": "B1.1",
            "leaf_label": "Leukemic cutis",
            "parent_id": "B1",
            "parent_label": "Neo",
            "joint_rank": 2,
            "posterior": 0.3,
        },
    ]
    mapper = {
        "gold_letter": "D",
        "gold_option_text": "Histiocytoid Sweet syndrome",
        "projection": {
            "option_maps": {
                "A": {
                    "matched": True,
                    "relation_type": "equivalent",
                    "matched_leaf_ids": ["B1.1"],
                },
                "D": {
                    "matched": False,
                    "relation_type": "unrelated",
                    "matched_leaf_ids": [],
                },
            }
        },
    }
    options = {
        "A": "Leukemic cutis",
        "D": "Histiocytoid Sweet syndrome",
    }
    out = mbr.rescore_after_synonym_bind(
        mapper,
        leaves,
        options,
        bridge_path=Path("/nonexistent_bridge_for_unit_test.json"),
    )
    gold = out["projection"]["option_maps"]["D"]
    assert out.get("synonym_bind_repair") is True
    assert out.get("bind_repair_applied") is True
    assert "B2.3" in (gold.get("matched_leaf_ids") or [])
    assert out["option_top1"] is True
    assert int(out["gold_option_rank"]) == 1


def test_synonym_bind_keeps_existing_ids():
    leaves = _leaves_sweet()
    for i, row in enumerate(leaves, start=1):
        row["joint_rank"] = i
    mapper = {
        "gold_letter": "A",
        "projection": {
            "option_maps": {
                "A": {
                    "matched": True,
                    "relation_type": "equivalent",
                    "matched_leaf_ids": ["B1.1"],
                },
            }
        },
    }
    out = mbr.apply_synonym_bind_repair_to_mapper(
        mapper,
        leaves,
        {"A": "Histiocytoid Sweet syndrome"},
        bridge_path=Path("/nonexistent_bridge_for_unit_test.json"),
    )
    a = out["projection"]["option_maps"]["A"]
    assert a["matched_leaf_ids"] == ["B1.1"]
    assert a.get("bind_repair_applied") is False


def test_bridge_pair_score_ignores_self_chunks():
    """Regression: leaf self-chunk score=1.0 must not count as option↔leaf match."""
    from agentclinic_tree_dx.knowledge.synonym_granularity_retriever import (
        SynonymGranularityRetriever,
    )

    bridge_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "knowledge_raw"
        / "disease_name_bridge.json"
    )
    if not bridge_path.is_file():
        import pytest

        pytest.skip("disease_name_bridge.json not present")
    bridge = SynonymGranularityRetriever(bridge_path)
    assert bridge.is_ready

    # Unrelated pair: search_option_leaves[0] is often syn:leaf @1.0 (bug bait).
    rag_hits = bridge.search_option_leaves(
        "Microvenular hemangioma (MVH)",
        ["Kaposi's sarcoma"],
        top_k=1,
    )
    assert rag_hits, "expected RAG self/pair hits"
    # True pair score must stay below bind threshold.
    pair = bridge.pair_match_score(
        "Microvenular hemangioma (MVH)", "Kaposi's sarcoma"
    )
    assert pair < 0.70, pair

    # True synonym still scores high via pair API.
    syn = bridge.pair_match_score("acute myeloid leukemia", "AML")
    assert syn >= 0.70, syn

    # End-to-end: empty gold must NOT bind to unrelated pred_1.
    leaves = [
        {
            "leaf_id": "pred_1",
            "leaf_label": "Kaposi's sarcoma",
            "joint_rank": 1,
            "posterior": 1.0,
        },
        {
            "leaf_id": "pred_2",
            "leaf_label": "Erythema annulare centrifugum",
            "joint_rank": 2,
            "posterior": 0.5,
        },
    ]
    mapper = {
        "gold_letter": "C",
        "projection": {
            "option_maps": {
                "A": {"matched": False, "relation_type": "unknown", "matched_leaf_ids": []},
                "B": {"matched": False, "relation_type": "unknown", "matched_leaf_ids": []},
                "C": {"matched": False, "relation_type": "unknown", "matched_leaf_ids": []},
                "D": {"matched": False, "relation_type": "unknown", "matched_leaf_ids": []},
            }
        },
    }
    options = {
        "A": "Targetoid hemosideric hemangioma",
        "B": "Tufted angioma",
        "C": "Microvenular hemangioma (MVH)",
        "D": "Kaposi's sarcoma",
    }
    out = mbr.apply_synonym_bind_repair_to_mapper(
        mapper, leaves, options, min_score=0.70, bridge_path=bridge_path
    )
    gold = out["projection"]["option_maps"]["C"]
    assert not (gold.get("matched_leaf_ids") or []), gold
    assert gold.get("bind_repair_applied") is False
    # Distractor that IS the pred label may still bind (legitimate surface match).
    d = out["projection"]["option_maps"]["D"]
    assert "pred_1" in (d.get("matched_leaf_ids") or [])
