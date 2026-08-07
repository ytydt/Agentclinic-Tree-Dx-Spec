"""Tests for eval_projection + transfer_eval matching / gold parsers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
import medcasereasoning_adapter as mcr_ad  # noqa: E402
from transfer_eval import matching, ox_metrics  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402


def _mini_tree_state() -> dict:
    return {
        "branches": {
            "B1": {
                "id": "B1",
                "label": "Axis A",
                "children": ["B1.1", "B1.2"],
                "posterior": 0.5,
                "parent": "",
            },
            "B1.1": {
                "id": "B1.1",
                "label": "Disease Alpha",
                "children": [],
                "posterior": 0.40,
                "parent": "B1",
            },
            "B1.2": {
                "id": "B1.2",
                "label": "Disease Beta",
                "children": [],
                "posterior": 0.25,
                "parent": "B1",
            },
            "B2": {
                "id": "B2",
                "label": "Axis B",
                "children": ["B2.1"],
                "posterior": 0.3,
                "parent": "",
            },
            "B2.1": {
                "id": "B2.1",
                "label": "Disease Gamma",
                "children": [],
                "posterior": 0.20,
                "parent": "B2",
            },
            "B3.1": {
                "id": "B3.1",
                "label": "Disease Alpha",  # duplicate label, lower post
                "children": [],
                "posterior": 0.05,
                "parent": "B3",
            },
        }
    }


def test_top_leaf_posterior_dedup_topk():
    top = bep.top_leaf_posterior(_mini_tree_state(), k=5)
    labels = [r["label"] for r in top]
    assert labels[0] == "Disease Alpha"
    assert labels.count("Disease Alpha") == 1
    assert set(labels) == {"Disease Alpha", "Disease Beta", "Disease Gamma"}
    assert len(top) == 3


def test_projection_template_has_no_chunk_and_p5_why():
    tree = _mini_tree_state()
    p5 = {
        "rules": [
            {
                "effects": [
                    {
                        "candidate": "Disease Alpha",
                        "effect": "support",
                        "why": "Elevated creatinine supports Alpha.",
                        "evidence_ids": ["E1"],
                    },
                    {
                        "candidate": "Disease Beta",
                        "effect": "oppose",
                        "why": "No rash argues against Beta.",
                        "evidence_ids": ["E2"],
                    },
                    {
                        "candidate": "Disease Alpha",
                        "effect": "neutral",
                        "why": "Should be ignored.",
                        "evidence_ids": [],
                    },
                ]
            }
        ]
    }
    case = {
        "l1": {"selected_fact_ids": ["F1", "F2"], "l1_posteriors": [{"label": "Axis A"}]},
        "l2": {"final_ranking_labels": [{"id": "B1.1", "label": "Disease Alpha"}]},
    }
    facts = {"F1": "Fever 39C", "F2": "Cr 2.1"}
    proj = bep.build_one_projection(
        case_id="1",
        tree_state=tree,
        p5_doc=p5,
        case_doc=case,
        fact_texts=facts,
        ddx_k=5,
    )
    assert proj["pred_diagnosis"] == "Disease Alpha"
    assert len(proj["pred_ddx"]) == 3
    assert "Elevated creatinine supports Alpha." in proj["pred_interpretation"]["Disease Alpha"]
    assert "chunk" not in proj["pred_reasoning_trace"].lower()
    assert "Observed:" in proj["pred_reasoning_trace"]
    assert "Fever 39C" in proj["pred_reasoning_trace"]
    assert proj["sources"]["ddx_source"] == "shared_trees_global_leaf_posterior_topk"


def test_set_match_precision_recall():
    pred = ["Acute kidney injury", "Sepsis", "Pneumonia"]
    gold = ["AKI", "Community acquired pneumonia"]
    # leaf_match_score: AKI vs Acute kidney injury may synonymish;
    # Pneumonia vs Community acquired pneumonia should match via containment/synonym
    res = matching.greedy_set_match(pred, gold, threshold=0.7)
    assert res.n_pred == 3
    assert res.n_gold == 2
    assert res.tp >= 1
    assert 0.0 <= res.precision <= 1.0
    assert 0.0 <= res.recall <= 1.0
    # Exact controllable case
    res2 = matching.greedy_set_match(
        ["Foo", "Bar"],
        ["Foo", "Baz"],
        threshold=0.7,
    )
    assert res2.tp == 1
    assert res2.precision == pytest.approx(0.5)
    assert res2.recall == pytest.approx(0.5)
    assert res2.f1 == pytest.approx(0.5)


def test_parse_reasoning_points_numbered():
    text = (
        "1. Patient has fever.\n"
        "2. Blood culture grew GNR.\n"
        "3. Imaging showed abscess."
    )
    pts = mcr_ad.parse_reasoning_points(text)
    assert len(pts) == 3
    assert pts[0].startswith("Patient has fever")


def test_ox_score_case_lexical():
    proj = {
        "case_id": "9",
        "pred_ddx": [
            {"label": "Foo Disease", "posterior": 0.5},
            {"label": "Bar Disease", "posterior": 0.3},
        ],
        "pred_interpretation": {
            "Foo Disease": ["fever and leukocytosis"],
            "Bar Disease": ["rash"],
        },
    }
    gold = {
        "case_id": "9",
        "ddx_set": ["Foo Disease", "Other"],
        "interpretation": {
            "Foo Disease": ["fever with high WBC"],
            "Other": ["headache"],
        },
    }
    sc = ox_metrics.score_ox_case(proj, gold, LexicalJudge())
    assert sc["diagnostic"]["tp"] == 1
    assert sc["diagnostic"]["n_pred"] == 2
    assert sc["diagnostic"]["n_gold"] == 2


def test_load_subset_cases_ox_interpretation(tmp_path: Path):
    import pandas as pd
    import open_xddx_adapter as ox_ad

    interp = {"Dx A": ["reason1"], "Dx B": ["reason2", "reason3"]}
    row = {
        "id": 42,
        "Final Diagnosis": "Dx A",
        "Right Option": "A",
        "Options": {"A": "Dx A", "B": "Dx B"},
        "Case Information": "patient info",
        "Physical Examination": "",
        "Diagnostic Tests": "",
        "specialty": "IM",
        "disease_num": 2,
        "rationale_num": 3,
        "interpretation_json": json.dumps(interp),
        "gold_meta_json": "{}",
        "source_dataset": "open_xddx",
    }
    pq = tmp_path / "ox.parquet"
    pd.DataFrame([row]).to_parquet(pq)
    cases = ox_ad.load_subset_cases(pq)
    assert cases[0]["annotation"]["interpretation"]["Dx A"] == ["reason1"]
    assert cases[0]["annotation"]["ddx_set"] == ["Dx A", "Dx B"]


def test_load_subset_cases_mcr_reasoning_points(tmp_path: Path):
    import pandas as pd

    row = {
        "id": 7,
        "Final Diagnosis": "Meningitis",
        "Right Option": "A",
        "Options": {"A": "Meningitis", "B": "Migraine"},
        "Case Information": "stiff neck",
        "Physical Examination": "",
        "Diagnostic Tests": "",
        "pmcid": "PMC1",
        "title": "t",
        "journal": "j",
        "diagnostic_reasoning": "1. Fever\n2. Nuchal rigidity\n3. CSF pleocytosis",
        "source_dataset": "medcasereasoning",
        "source_split": "val",
        "source_row_key": "1",
    }
    pq = tmp_path / "mcr.parquet"
    pd.DataFrame([row]).to_parquet(pq)
    cases = mcr_ad.load_subset_cases(pq)
    pts = cases[0]["annotation"]["reasoning_points"]
    assert len(pts) == 3
    assert "Fever" in pts[0]


def test_compat_then_pad_to_k_and_empty_fallback():
    tree = _mini_tree_state()
    # Short compat list (2) should pad to K=5 with posterior (only 3 unique leaves)
    case = {
        "l2": {
            "final_ranking_labels": [
                {"id": "B2.1", "label": "Disease Gamma", "rank": 1, "parent": "B2"},
                {"id": "B1.2", "label": "Disease Beta", "rank": 2, "parent": "B1"},
            ]
        }
    }
    pred, meta = bep.ddx_compat_then_pad(case, tree, k=5)
    assert pred[0]["label"] == "Disease Gamma"
    assert pred[1]["label"] == "Disease Beta"
    assert len(pred) == 3  # only 3 unique leaves in mini tree
    assert meta.get("fallback") is None

    empty_case = {"l2": {"final_ranking_labels": []}}
    pred2, meta2 = bep.ddx_compat_then_pad(empty_case, tree, k=5)
    assert meta2.get("fallback") == "empty_compat"
    assert pred2[0]["label"] == "Disease Alpha"
    assert len(pred2) == 3

    # resolve_pred_ddx empty compat also falls back
    pred3, src, meta3, _ = bep.resolve_pred_ddx(
        case_doc=empty_case,
        tree_state=tree,
        ddx_source="compat",
        ddx_k=5,
    )
    assert src == bep.DDX_SOURCE_COMPAT
    assert meta3.get("fallback") == "empty_compat"
    assert pred3[0]["label"] == "Disease Alpha"


def test_gate_merge_pads_back_to_k(monkeypatch):
    """R3: when FineCrowdGate merges, list must pad back to K (not shrink to 1)."""
    tree = {
        "branches": {
            "B1": {"id": "B1", "label": "Axis", "children": ["B1.1", "B1.2", "B1.3"], "posterior": 0.9},
            "B1.1": {
                "id": "B1.1",
                "label": "Tuberculosis",
                "children": [],
                "posterior": 0.40,
                "parent": "B1",
            },
            "B1.2": {
                "id": "B1.2",
                "label": "Pulmonary Tuberculosis",
                "children": [],
                "posterior": 0.30,
                "parent": "B1",
            },
            "B1.3": {
                "id": "B1.3",
                "label": "Disease Other",
                "children": [],
                "posterior": 0.20,
                "parent": "B1",
            },
            "B2.1": {
                "id": "B2.1",
                "label": "Disease Extra",
                "children": [],
                "posterior": 0.10,
                "parent": "B2",
            },
        }
    }
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}

    # Force gate triggered with 1 representative so pad must refill
    def _fake_gate(ranking_labels):
        return {
            "triggered": True,
            "merge_info": {
                "representative_order": ["B1.1"],
                "member_to_rep": {"B1.1": "B1.1", "B1.2": "B1.1"},
                "rep_to_members": {"B1.1": ["B1.1", "B1.2"]},
            },
        }

    def _fake_reps(ranking_labels, merge_info):
        return [{"id": "B1.1", "label": "Tuberculosis", "parent": "B1", "rank": 1}]

    import merge_calib_compat as mcc

    monkeypatch.setattr(mcc, "fine_crowd_gate", _fake_gate)
    monkeypatch.setattr(mcc, "_rep_labels_from_merge", _fake_reps)

    pred, meta = bep.ddx_gate_on_posterior_pool(case, tree, k=4, dry_calib=True)
    assert meta.get("branch") == "merge_only_pad"
    assert len(pred) == 4
    assert pred[0]["label"] == "Tuberculosis"
    # padded with non-rep posterior leaves
    assert {r["label"] for r in pred} >= {"Tuberculosis", "Disease Other", "Disease Extra"}


def _multi_l1_tree() -> dict:
    """Two L1 parents each with 3 leaves — tests per-L1 top2 expansion."""
    return {
        "branches": {
            "L1a": {
                "id": "L1a",
                "label": "Family A",
                "children": ["A1", "A2", "A3"],
                "posterior": 0.6,
                "parent": "",
            },
            "A1": {
                "id": "A1",
                "label": "Alpha High",
                "children": [],
                "posterior": 0.50,
                "parent": "L1a",
            },
            "A2": {
                "id": "A2",
                "label": "Alpha Mid",
                "children": [],
                "posterior": 0.30,
                "parent": "L1a",
            },
            "A3": {
                "id": "A3",
                "label": "Alpha Low",
                "children": [],
                "posterior": 0.05,
                "parent": "L1a",
            },
            "L1b": {
                "id": "L1b",
                "label": "Family B",
                "children": ["B1", "B2", "B3"],
                "posterior": 0.4,
                "parent": "",
            },
            "B1": {
                "id": "B1",
                "label": "Beta High",
                "children": [],
                "posterior": 0.40,
                "parent": "L1b",
            },
            "B2": {
                "id": "B2",
                "label": "Beta Mid",
                "children": [],
                "posterior": 0.25,
                "parent": "L1b",
            },
            "B3": {
                "id": "B3",
                "label": "Beta Low",
                "children": [],
                "posterior": 0.04,
                "parent": "L1b",
            },
        }
    }


def test_top_leaf_per_l1_keeps_top2_not_global_top1():
    pool = bep.top_leaf_per_l1_posterior(_multi_l1_tree(), per_l1=2)
    labels = [r["label"] for r in pool]
    # Global Top-1 would be Alpha High only under L1a; top2/L1 keeps mid from each.
    assert set(labels) == {"Alpha High", "Alpha Mid", "Beta High", "Beta Mid"}
    assert "Alpha Low" not in labels and "Beta Low" not in labels
    assert labels[0] == "Alpha High"  # sorted by posterior


def test_l1_top2_compat_then_compress_order(monkeypatch):
    """Expand → compat on full pool → compress to K (not compress-first)."""
    tree = _multi_l1_tree()
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}
    seen_k: list[int] = []
    seen_n: list[int] = []

    def _fake_compat(**kwargs):
        ranking = list(kwargs.get("ranking_labels") or [])
        seen_k.append(int(kwargs.get("k") or 0))
        seen_n.append(len(ranking))
        # Reverse pool order to prove compat rerank is applied before compress.
        ordered = [str(r["id"]) for r in reversed(ranking)]
        return {
            "mode": "compat_parallel",
            "branch": "calib_only",
            "gate": {"triggered": False},
            "ranking_labels": [
                {**dict(r), "rank": i}
                for i, r in enumerate(
                    sorted(ranking, key=lambda x: ordered.index(str(x["id"]))),
                    start=1,
                )
            ],
            "ordered_ids": ordered,
            "calib": {"swapped": False},
        }

    import merge_calib_compat as mcc

    monkeypatch.setattr(mcc, "run_compat_parallel", _fake_compat)

    pred, meta = bep.ddx_l1_top2_compat_then_compress(
        case, tree, k=3, per_l1=2, dry_calib=True
    )
    assert meta["pool_len"] == 4
    assert seen_n == [4]
    assert seen_k[0] >= 4  # compat sees expanded pool, not final K
    assert len(pred) == 3
    # Reversed expanded pool (by posterior): Beta Mid, Alpha Mid, Beta High, Alpha High.
    assert pred[0]["label"] == "Beta Mid"
    assert pred[1]["label"] == "Alpha Mid"
    assert pred[2]["label"] == "Beta High"

    pred2, src, meta2, _ = bep.resolve_pred_ddx(
        case_doc=case,
        tree_state=tree,
        ddx_source="l1_top2_compat",
        ddx_k=3,
        dry_calib=True,
    )
    assert src == bep.DDX_SOURCE_L1_TOP2_COMPAT
    assert [r["label"] for r in pred2] == [r["label"] for r in pred]
    assert bep.normalize_ddx_source("per_l1_top2_compat") == bep.DDX_SOURCE_L1_TOP2_COMPAT


def _gated_hybrid_tree() -> dict:
    """Only L1a (rank1, close leaves) expands; L1b rank2 but leaf2 far; L1c weak."""
    return {
        "branches": {
            "L1a": {
                "id": "L1a",
                "label": "Family A",
                "children": ["A1", "A2", "A3"],
                "posterior": 0.0,
                "parent": "",
            },
            "A1": {
                "id": "A1",
                "label": "Alpha High",
                "children": [],
                "posterior": 0.40,
                "parent": "L1a",
            },
            "A2": {
                "id": "A2",
                "label": "Alpha Mid",
                "children": [],
                "posterior": 0.28,  # 0.28/0.40=0.70 → close
                "parent": "L1a",
            },
            "A3": {
                "id": "A3",
                "label": "Alpha Low",
                "children": [],
                "posterior": 0.05,
                "parent": "L1a",
            },
            "L1b": {
                "id": "L1b",
                "label": "Family B",
                "children": ["B1", "B2"],
                "posterior": 0.0,
                "parent": "",
            },
            "B1": {
                "id": "B1",
                "label": "Beta High",
                "children": [],
                "posterior": 0.35,
                "parent": "L1b",
            },
            "B2": {
                "id": "B2",
                "label": "Beta Tiny",
                "children": [],
                "posterior": 0.05,  # 0.05/0.35≈0.14 < 0.35, not competitive
                "parent": "L1b",
            },
            "L1c": {
                "id": "L1c",
                "label": "Family C",
                "children": ["C1", "C2"],
                "posterior": 0.0,
                "parent": "",
            },
            "C1": {
                "id": "C1",
                "label": "Gamma High",
                "children": [],
                "posterior": 0.12,
                "parent": "L1c",
            },
            "C2": {
                "id": "C2",
                "label": "Gamma Mid",
                "children": [],
                "posterior": 0.10,
                "parent": "L1c",
            },
        }
    }


def test_gated_hybrid_expands_only_triggered_l1():
    pool, meta = bep.top_leaf_gated_hybrid_l1(_gated_hybrid_tree())
    labels = [r["label"] for r in pool]
    # L1a mass=0.73 rank1 expand→ Alpha High+Mid
    # L1b mass=0.40 rank2 but not close/crowd → Beta High only
    # L1c mass=0.22 rank3 → Gamma High only
    assert "Alpha Mid" in labels
    assert "Beta Tiny" not in labels
    assert "Gamma Mid" not in labels
    assert set(labels) == {"Alpha High", "Alpha Mid", "Beta High", "Gamma High"}
    assert meta["n_l1_expanded"] == 1
    assert meta["expanded_l1_ids"] == ["L1a"]

    pred, meta2 = bep.ddx_gated_hybrid_top2_compress(_gated_hybrid_tree(), k=3)
    assert len(pred) == 3
    assert pred[0]["label"] == "Alpha High"
    assert meta2["compat"] is False


def test_gated_hybrid_compat_sees_selective_pool(monkeypatch):
    tree = _gated_hybrid_tree()
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}
    seen_n: list[int] = []

    def _fake_compat(**kwargs):
        ranking = list(kwargs.get("ranking_labels") or [])
        seen_n.append(len(ranking))
        ordered = [str(r["id"]) for r in ranking]
        return {
            "mode": "compat_parallel",
            "branch": "calib_only",
            "gate": {"triggered": False},
            "ranking_labels": ranking,
            "ordered_ids": ordered,
            "calib": {"swapped": False},
        }

    import merge_calib_compat as mcc

    monkeypatch.setattr(mcc, "run_compat_parallel", _fake_compat)
    pred, meta = bep.ddx_gated_hybrid_top2_compat_then_compress(
        case, tree, k=3, dry_calib=True
    )
    assert seen_n == [4]  # selective pool, not global-per-l1-top2 (would be 5+)
    assert meta["n_l1_expanded"] == 1
    assert meta["compat"] is True
    assert len(pred) == 3
    pred2, src, _, _ = bep.resolve_pred_ddx(
        case_doc=case,
        tree_state=tree,
        ddx_source="gated_hybrid_compat",
        ddx_k=3,
        dry_calib=True,
    )
    assert src == bep.DDX_SOURCE_GATED_HYBRID_COMPAT
    assert [r["label"] for r in pred2] == [r["label"] for r in pred]


def test_gated_hybrid_mcr_compat_pads_on_merge(monkeypatch):
    """MCR R3 dialect: merge pads to K; preserve_full_top2 flag in meta."""
    tree = _gated_hybrid_tree()
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}
    pool, _ = bep.top_leaf_gated_hybrid_l1(tree)

    def _fake_gate(ranking_labels):
        rid = str(ranking_labels[0]["id"])
        return {
            "triggered": True,
            "merge_info": {
                "representative_order": [rid],
                "member_to_rep": {rid: rid},
                "rep_to_members": {rid: [rid]},
            },
        }

    def _fake_reps(ranking_labels, merge_info):
        r0 = ranking_labels[0]
        return [{"id": r0["id"], "label": r0["label"], "parent": r0.get("parent"), "rank": 1}]

    import merge_calib_compat as mcc

    monkeypatch.setattr(mcc, "fine_crowd_gate", _fake_gate)
    monkeypatch.setattr(mcc, "_rep_labels_from_merge", _fake_reps)

    pred, meta = bep.ddx_gated_hybrid_top2_mcr_compat(
        case, tree, k=4, dry_calib=True
    )
    assert meta.get("compat_dialect") == "mcr_r3"
    assert meta.get("preserve_full_top2_when_no_gold") is True
    assert meta.get("branch") == "merge_only_pad"
    assert len(pred) == min(4, len(pool))
    assert pred[0]["label"] == pool[0]["label"]
    assert bep.normalize_ddx_source("gated_hybrid_mcr") == bep.DDX_SOURCE_GATED_HYBRID_MCR


def test_posterior_n_mcr_uses_pool_then_compress(monkeypatch):
    tree = {
        "branches": {
            "p1": {
                "id": "p1",
                "label": "P",
                "children": ["l%d" % i for i in range(1, 10)],
                "posterior": 1.0,
                "parent": "",
            },
            **{
                "l%d" % i: {
                    "id": "l%d" % i,
                    "label": "L%d" % i,
                    "children": [],
                    "posterior": 1.0 - 0.05 * i,
                    "parent": "p1",
                }
                for i in range(1, 10)
            },
        }
    }
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}

    def _fake_calib(**kwargs):
        # Return reverse of first k pool ids to prove MCR path ran.
        ranking = (kwargs["case"].get("l2") or {}).get("final_ranking_labels") or []
        ids = [str(r["id"]) for r in ranking]
        return {"ordered_ids": list(reversed(ids)), "swapped": True}

    import topk_calibration as calib

    monkeypatch.setattr(calib, "calibrate_case", _fake_calib)
    # Force calib branch (no merge).
    import merge_calib_compat as mcc

    monkeypatch.setattr(mcc, "fine_crowd_gate", lambda _r: {"triggered": False})

    pred, meta = bep.ddx_posterior_n_mcr_compat(
        case, tree, k=4, pool_n=7, dry_calib=True
    )
    assert meta["compat_dialect"] == "mcr_r3"
    assert meta["pool_n"] == 7
    assert meta["pool_len"] == 7
    assert len(pred) == 4
    assert pred[0]["label"] == "L7"  # reversed top-7 → first is L7
    pred2, src, meta2, _ = bep.resolve_pred_ddx(
        case_doc=case,
        tree_state=tree,
        ddx_source="post7_mcr",
        ddx_k=4,
        dry_calib=True,
        pool_n=7,
    )
    assert src == bep.DDX_SOURCE_POST_N_MCR
    assert [r["label"] for r in pred2] == [r["label"] for r in pred]
    assert meta2["pool_n"] == 7


def test_multi_arm_rrf_fuses_lists():
    tree = _mini_tree_state()
    case = {
        "l2": {
            "final_ranking": [
                {"id": "B1.2", "label": "Disease Beta", "score": 0.9},
                {"id": "B1.1", "label": "Disease Alpha", "score": 0.8},
            ],
            "final_ranking_labels": [
                {"id": "B1.2", "label": "Disease Beta"},
                {"id": "B1.1", "label": "Disease Alpha"},
            ],
        },
        "case_text": "x",
        "annotation": {"findings": []},
    }
    pred, meta = bep.ddx_multi_arm_rrf(case, tree, k=3, dry_calib=True)
    assert meta["compat_dialect"] == "multi_arm_rrf"
    assert meta["n_lists"] == 4
    assert len(pred) == 3
    labels = [r["label"] for r in pred]
    assert "Disease Alpha" in labels
    pred2, src, _, _ = bep.resolve_pred_ddx(
        case_doc=case,
        tree_state=tree,
        ddx_source="multi_arm_rrf",
        ddx_k=3,
        dry_calib=True,
    )
    assert src == bep.DDX_SOURCE_MULTI_ARM_RRF
    assert [r["label"] for r in pred2] == labels


def test_closed_pool_views_rrf_stays_in_pool():
    tree = _mini_tree_state()
    case = {
        "l2": {
            "final_ranking": [
                {"id": "B1.1", "label": "Disease Alpha", "score": 1.0},
            ],
            "final_ranking_labels": [
                {"id": "B1.1", "label": "Disease Alpha"},
            ],
        },
        "case_text": "x",
        "annotation": {"findings": []},
    }
    pred, meta = bep.ddx_closed_pool_views_rrf(
        case, tree, k=2, pool_n=12, dry_calib=True
    )
    assert meta["compat_dialect"] == "closed_pool_views_rrf"
    pool_labs = {r["label"] for r in bep.top_leaf_posterior(tree, k=12)}
    assert all(r["label"] in pool_labs for r in pred)
    assert len(pred) == 2


def test_tree_mac_pad_selective_skips_in_tree_names():
    tree = _mini_tree_state()
    case = {
        "l2": {
            "final_ranking": [
                {"id": "B1.1", "label": "Disease Alpha", "score": 1.0},
                {"id": "B1.2", "label": "Disease Beta", "score": 0.5},
            ],
            "final_ranking_labels": [
                {"id": "B1.1", "label": "Disease Alpha"},
                {"id": "B1.2", "label": "Disease Beta"},
            ],
        },
        "case_text": "x",
        "annotation": {"findings": []},
    }
    pred, meta = bep.ddx_tree_mac_pad_selective(
        case,
        tree,
        k=3,
        mac_labels=["Disease Alpha", "Truly Open Dx"],
        pad_n=2,
        dry_calib=True,
    )
    assert meta["compat_dialect"] == "tree_mac_pad_selective"
    assert meta["n_mac_skipped_in_tree"] >= 1
    assert meta["n_mac_open_only"] == 1
    assert "Truly Open Dx" in [r["label"] for r in pred]


def test_closed_live_mac_dry_falls_back():
    tree = _mini_tree_state()
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}
    pred, meta = bep.ddx_closed_live_mac_supervisor(
        case, tree, k=2, pool_n=15, closed_mac_cache=None
    )
    assert meta.get("fallback") == "dry_closed_pool_views_rrf"
    assert meta.get("live") is False
    assert len(pred) == 2

    tree = _mini_tree_state()
    case = {"l2": {}, "case_text": "x", "annotation": {"findings": []}}
    doctors = [
        ["Disease Alpha", "Open Name Not In Tree"],
        ["Disease Beta", "Disease Alpha"],
        ["Disease Gamma"],
    ]
    pred, meta = bep.ddx_closed_mac_trace_rrf(
        case, tree, k=3, pool_n=12, mac_doctor_lists=doctors
    )
    assert meta["compat_dialect"] == "closed_mac_trace_rrf"
    assert meta["n_doctor_lists"] == 3
    pool_labs = {r["label"] for r in bep.top_leaf_posterior(tree, k=12)}
    assert all(r["label"] in pool_labs for r in pred)
    assert len(pred) == 3
    # empty doctor lists → fallback closed_pool_views_rrf
    pred2, meta2 = bep.ddx_closed_mac_trace_rrf(
        case, tree, k=2, pool_n=12, mac_doctor_lists=[]
    )
    assert meta2["compat_dialect"] == "closed_pool_views_rrf"
    assert len(pred2) == 2

    tree = _mini_tree_state()
    case = {
        "l2": {
            "final_ranking": [
                {"id": "B1.1", "label": "Disease Alpha", "score": 1.0},
                {"id": "B1.2", "label": "Disease Beta", "score": 0.5},
            ],
            "final_ranking_labels": [
                {"id": "B1.1", "label": "Disease Alpha"},
                {"id": "B1.2", "label": "Disease Beta"},
            ],
        },
        "case_text": "x",
        "annotation": {"findings": []},
    }
    pred, meta = bep.ddx_tree_mac_pad(
        case,
        tree,
        k=3,
        mac_labels=["Disease Alpha", "Open Umbrella Dx", "Another Open"],
        pad_n=2,
        dry_calib=True,
    )
    assert meta["compat_dialect"] == "tree_mac_pad"
    assert meta["n_mac_padded"] == 2
    labels = [r["label"] for r in pred]
    assert "Open Umbrella Dx" in labels
    assert "Another Open" in labels
    assert any(r.get("mac_pad") for r in pred)
    pred2, src, meta2, _ = bep.resolve_pred_ddx(
        case_doc=case,
        tree_state=tree,
        ddx_source="tree_mac_pad",
        ddx_k=3,
        dry_calib=True,
        mac_labels=["Only Open"],
    )
    assert src == bep.DDX_SOURCE_TREE_MAC_PAD
    assert "Only Open" in [r["label"] for r in pred2]
    assert meta2["n_mac_padded"] >= 1
