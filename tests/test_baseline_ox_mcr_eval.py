#!/usr/bin/env python3
"""Tests for baseline OX/MCR projection + multi-dataset runtime load."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_arms as arms  # noqa: E402
import baseline_common as bc  # noqa: E402
import build_baseline_eval_projection as bproj  # noqa: E402
from transfer_eval import mcr_metrics, ox_metrics  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

OX_SUBSET = ROOT / "data" / "benchmarks" / "open_xddx" / "subsets" / "ox_seq100_v1"
MCR_SUBSET = (
    ROOT / "data" / "benchmarks" / "medcasereasoning" / "subsets" / "mcr_val_seq100_v1"
)
DA_SUBSET = ROOT / "data" / "benchmarks" / "diagnosisarena" / "subsets" / "d2_seq100_v1"


def test_validate_list_k_ox():
    assert bc.validate_list_k("open_xddx", 5) == 5
    assert bc.validate_list_k("ox", 7) == 7
    with pytest.raises(ValueError):
        bc.validate_list_k("open_xddx", 2)


def test_prediction_row_list_k():
    case = {
        "case_id": "open_xddx__000065",
        "source_id": "65",
        "runtime_hash": "abc",
    }
    row = bc.prediction_row(
        case,
        arm="B00-direct-cot",
        replicate=1,
        top2=["Dx A", "Dx B", "Dx C", "Dx D", "Dx E"],
        cost=bc.empty_cost(),
        list_k=5,
    )
    assert row["list_k"] == 5
    assert len(row["ordered_diagnoses"]) == 5
    assert row["top2_diagnoses"] == ["Dx A", "Dx B"]


def test_clean_topk_ordered_key():
    raw = {
        "ordered_diagnoses": [
            {"diagnosis": "A", "reasoning_summary": "ra"},
            {"diagnosis": "B", "reasoning_summary": "rb"},
            {"diagnosis": "C"},
            {"diagnosis": "D"},
            {"diagnosis": "E"},
        ]
    }
    names = bc.clean_topk_from_response(raw, k=5)
    assert names == ["A", "B", "C", "D", "E"]


@pytest.mark.skipif(not OX_SUBSET.is_dir(), reason="ox subset missing")
def test_load_runtime_cases_ox_no_gold_in_payload():
    cases = bc.load_runtime_cases(
        subset_dir=OX_SUBSET,
        dataset="open_xddx",
        limit=2,
    )
    assert len(cases) == 2
    assert cases[0]["dataset"] == "open_xddx"
    assert cases[0]["options"] == {}
    payload = bc.runtime_payload(cases[0])
    bc.assert_no_gold_leak(payload)
    assert "gold" not in payload
    assert payload["vignette"]


@pytest.mark.skipif(not MCR_SUBSET.is_dir(), reason="mcr subset missing")
def test_load_runtime_cases_mcr():
    cases = bc.load_runtime_cases(
        subset_dir=MCR_SUBSET,
        dataset="medcasereasoning",
        limit=1,
    )
    assert len(cases) == 1
    assert cases[0]["case_id"].startswith("medcasereasoning__")
    bc.assert_no_gold_leak(bc.runtime_payload(cases[0]))


def test_b00_list_k5_dry():
    case = {
        "case_id": "open_xddx__000001",
        "source_id": "1",
        "vignette": "fever and cough",
        "question": "What is the most likely diagnosis?",
        "options": {},
    }
    cache = bc.SimpleCachedLLM(None, Path("/tmp/unused_baseline_ox.json"), "dry")
    ranked, trace, cost = arms.run_b00(case, cache, dry_run=True, list_k=5)
    assert len(ranked) == 5
    assert all(ranked)
    assert trace.get("list_k") == 5


def test_projection_list_k_and_reasoning(tmp_path: Path):
    pred_dir = tmp_path / "B00" / "replicate_01"
    pred_dir.mkdir(parents=True)
    preds = [
        {
            "case_id": "open_xddx__000065",
            "source_id": "65",
            "arm": "B00-direct-cot",
            "replicate": 1,
            "list_k": 5,
            "ordered_diagnoses": ["Pneumonia", "PE", "CHF", "Asthma", "COPD"],
            "top2_diagnoses": ["Pneumonia", "PE"],
            "cost": bc.empty_cost(),
            "runtime_hash": "x",
            "trace_digest": "y",
        }
    ]
    traces = [
        {
            "case_id": "open_xddx__000065",
            "arm": "B00-direct-cot",
            "trace": {
                "raw": {
                    "ordered_diagnoses": [
                        {
                            "diagnosis": "Pneumonia",
                            "reasoning_summary": "Infiltrate and fever",
                        },
                        {
                            "diagnosis": "PE",
                            "reasoning_summary": "Possible embolus",
                        },
                    ]
                }
            },
        }
    ]
    (pred_dir / "predictions.jsonl").write_text(
        "\n".join(json.dumps(r) for r in preds) + "\n", encoding="utf-8"
    )
    (pred_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(r) for r in traces) + "\n", encoding="utf-8"
    )
    (pred_dir / "manifest.json").write_text(
        json.dumps({"list_k": 5, "dataset": "open_xddx"}), encoding="utf-8"
    )

    summary = bproj.build_baseline_eval_projections(
        pred_dir, dataset="open_xddx", list_k=5
    )
    assert summary["n_written"] == 1
    doc = json.loads((pred_dir / "annotate" / "eval_projection" / "65.json").read_text())
    assert len(doc["pred_ddx"]) == 5
    assert doc["pred_diagnosis"] == "Pneumonia"
    assert doc["pred_interpretation"]["Pneumonia"] == ["Infiltrate and fever"]
    assert "Infiltrate and fever" in doc["pred_reasoning_trace"]
    assert "baseline_ordered_topk_v1" in doc["protocol_tags"]

    gold = {
        "case_id": "65",
        "ddx_set": ["Pneumonia", "Pulmonary embolism"],
        "interpretation": {
            "Pneumonia": ["fever", "infiltrate"],
            "Pulmonary embolism": ["dyspnea"],
        },
    }
    scored = ox_metrics.score_ox_case(doc, gold, LexicalJudge())
    assert scored.get("case_id") == "65"
    assert "diagnostic" in scored
    assert len(scored.get("pred_ddx_labels") or []) == 5


def test_projection_empty_trace(tmp_path: Path):
    pred_dir = tmp_path / "arm" / "replicate_01"
    pred_dir.mkdir(parents=True)
    pred = {
        "case_id": "medcasereasoning__000001",
        "source_id": "1",
        "arm": "B00-direct-cot",
        "replicate": 1,
        "list_k": 2,
        "ordered_diagnoses": ["Disease A", "Disease B"],
        "top2_diagnoses": ["Disease A", "Disease B"],
        "cost": {},
        "runtime_hash": "h",
        "trace_digest": "t",
    }
    (pred_dir / "predictions.jsonl").write_text(json.dumps(pred) + "\n", encoding="utf-8")
    (pred_dir / "trace.jsonl").write_text("", encoding="utf-8")
    bproj.build_baseline_eval_projections(
        pred_dir, dataset="medcasereasoning", list_k=2
    )
    doc = json.loads((pred_dir / "annotate" / "eval_projection" / "1.json").read_text())
    assert doc["pred_interpretation"]["Disease A"] == []
    assert "Diagnosis: Disease A" in doc["pred_reasoning_trace"]
    gold = {
        "case_id": "1",
        "final_diagnosis": "Disease A",
        "reasoning_points": ["fever"],
    }
    scored = mcr_metrics.score_mcr_case(doc, gold, LexicalJudge())
    assert scored["diagnostic_hit"] is True
    assert "reasoning_recall" in scored


@pytest.mark.skipif(not DA_SUBSET.is_dir(), reason="da subset missing")
def test_da_list_k_default_still_two():
    assert bc.default_list_k_for("diagnosisarena") == 2
    cases = bc.load_runtime_cases(subset_dir=DA_SUBSET, limit=1)
    assert cases[0]["options"]
