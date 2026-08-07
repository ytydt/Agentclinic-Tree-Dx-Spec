"""Tests for DiagnosisArena paper baseline contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_aggregate as agg
import baseline_arms as arms
import baseline_common as bc
import baseline_mapper_score as mapper_score


SUBSET = ROOT / "data" / "benchmarks" / "diagnosisarena" / "subsets" / "d2_seq100_v1"


class _FakeCache:
    """Records modules and returns schema-shaped stubs (no network)."""

    def __init__(self) -> None:
        self.client = object()
        self.modules: list[str] = []

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.modules.append(module)
        bc.assert_no_gold_leak(payload)
        if "Forward" in module or "Reflect" in module:
            return {
                "diagnoses": {
                    "Acute myeloid leukemia": ["blasts", "fever"],
                    "Chronic myeloid leukemia": ["leukocytosis"],
                }
            }
        if "Backward" in module:
            return {
                "book_knowledge": {
                    "Acute myeloid leukemia": ["blasts", "fever", "anemia"],
                    "Chronic myeloid leukemia": ["leukocytosis", "splenomegaly"],
                }
            }
        if "Examine" in module:
            return {
                "refined": {
                    "Acute myeloid leukemia": ["blasts", "fever"],
                    "Chronic myeloid leukemia": ["leukocytosis"],
                },
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ],
            }
        if "MDComplexity" in module:
            return {"complexity": "moderate", "rationale": "multi-system"}
        if "MDRecruit" in module:
            return {"roles": ["Primary Care Physician", "Hematologist"]}
        if "MDAgent" in module or "MDConsensus" in module:
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        if "MACDoctor" in module:
            return {
                "ranked_diagnoses": [
                    "Acute myeloid leukemia",
                    "Chronic myeloid leukemia",
                    "ALL",
                    "MDS",
                    "Infection",
                ],
                "commentary": "ok",
            }
        if "MACSupervisor" in module:
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        if "FlatCandidates" in module or "CandidatePool" in module:
            return {
                "candidates": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                    {"diagnosis": "ALL"},
                    {"diagnosis": "MDS"},
                    {"diagnosis": "Lymphoma"},
                ]
            }
        if "FlatRerank" in module or "FlatUnion" in module:
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        if "MedRAGDiffs" in module:
            return {
                "candidate_diseases": [
                    "Acute myeloid leukemia",
                    "Chronic myeloid leukemia",
                ],
                "diagnostic_differences": [
                    {
                        "pair": [
                            "Acute myeloid leukemia",
                            "Chronic myeloid leukemia",
                        ],
                        "differences": ["blast crisis vs chronic phase"],
                    }
                ],
            }
        if "FlatBeam" in module:
            return {
                "beam": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                    {"diagnosis": "ALL"},
                ],
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ],
            }
        if "MedDxOrchestrate" in module:
            return {
                "need_retrieval": True,
                "retrieval_queries": ["blasts fever anemia differential"],
                "strategy_notes": "hematologic malignancy workup",
            }
        if "MedDxDiagnose" in module or "MedDxRefine" in module:
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        if "IMedRAGAsk" in module:
            return {
                "analysis": "blasts and fever suggest acute leukemia",
                "queries": [
                    "acute myeloid leukemia blast criteria",
                    "chronic myeloid leukemia vs AML distinguishing features",
                ],
            }
        if "IMedRAGInner" in module:
            return {
                "answer": "AML presents with circulating blasts and cytopenias.",
                "reasoning_summary": "from docs",
            }
        if "IMedRAGFinal" in module:
            return {
                "analysis": "context favors AML",
                "answer": "Acute myeloid leukemia",
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ],
            }
        if "MedRAGReason" in module or "MedPrompt" in module or "Emulation" in module:
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        if "Taxonomy" in module or module.startswith("Paper"):
            return {
                "top2_diagnoses": [
                    {"diagnosis": "Acute myeloid leukemia"},
                    {"diagnosis": "Chronic myeloid leukemia"},
                ]
            }
        raise AssertionError(f"unexpected module {module}")


def _toy_case() -> dict[str, Any]:
    return {
        "case_id": "diagnosisarena__000001",
        "source_id": "1",
        "vignette": (
            "A 55-year-old man presents with fever, fatigue, and circulating blasts. "
            "CBC shows anemia and thrombocytopenia."
        ),
        "question": "What is the most likely diagnosis?",
        "options": {
            "A": "Acute myeloid leukemia",
            "B": "Chronic myeloid leukemia",
            "C": "Iron deficiency",
            "D": "Viral illness",
        },
        "_gold_letter": "A",
        "_gold_text": "Acute myeloid leukemia",
        "runtime_hash": "x",
    }


@pytest.mark.skipif(not SUBSET.is_dir(), reason="d2_seq100_v1 subset missing")
def test_load_runtime_cases_gold_isolation():
    cases = bc.load_runtime_cases(subset_dir=SUBSET, limit=3)
    assert len(cases) == 3
    for case in cases:
        payload = bc.runtime_payload(case)
        bc.assert_no_gold_leak(payload)
        assert "options" not in payload
        assert case["_gold_letter"] in case["options"]
        assert len(case["vignette"]) > 20
        assert "Options:" not in case["vignette"]


def test_top2_to_synthetic_leaves_shape():
    leaves = mapper_score.top2_to_synthetic_leaves(
        ["Acute myeloid leukemia", "Chronic myeloid leukemia"],
    )
    assert len(leaves) == 2
    assert leaves[0]["leaf_id"] == "pred_1"
    assert leaves[0]["joint_rank"] == 1
    assert leaves[0]["posterior"] == 1.0
    assert leaves[1]["joint_rank"] == 2


def test_rrf_and_borda_aggregate():
    lists = [
        ["AML", "CML", "ALL"],
        ["CML", "AML", "MDS"],
        ["AML", "MDS", "CML"],
    ]
    rrf = agg.rrf_aggregate(lists, top_n=2)
    assert len(rrf) == 2
    assert rrf[0] == "AML"
    borda = agg.borda_aggregate(lists, list_len=3, top_n=2)
    assert len(borda) == 2


def test_assert_no_gold_leak_raises():
    with pytest.raises(AssertionError):
        bc.assert_no_gold_leak({"vignette": "x", "gold": "secret"})


@pytest.mark.skipif(not SUBSET.is_dir(), reason="d2_seq100_v1 subset missing")
def test_mapper_deterministic_scores_top2(tmp_path: Path):
    cases = bc.load_runtime_cases(subset_dir=SUBSET, limit=2)
    out = tmp_path / "B00-direct-cot" / "replicate_01"
    out.mkdir(parents=True)
    for case in cases:
        # Use gold option text as pred_1 to force option_top1 when resolvable.
        gold_text = case["options"][case["_gold_letter"]]
        other = next(
            text for letter, text in case["options"].items()
            if letter != case["_gold_letter"]
        )
        bc.append_jsonl(
            out / "predictions.jsonl",
            bc.prediction_row(
                case,
                arm="B00-direct-cot",
                replicate=1,
                top2=[gold_text, other],
                cost=bc.empty_cost(),
            ),
        )
    summary = mapper_score.score_predictions_dir(
        out,
        cases,
        mode="deterministic_gold_blind",
        model="dummy",
        dry_run=True,
    )
    assert summary["n"] == 2
    assert summary["option_top1"] == 1.0
    assert summary["option_top2"] == 1.0
    records = json.loads((out / "mapper" / "records.json").read_text(encoding="utf-8"))
    assert all(row["option_top1"] for row in records["records"])


def test_b02_is_not_b01_alias():
    cache = _FakeCache()
    case = _toy_case()
    top2, trace, cost = arms.run_b02(case, cache, dry_run=False, retrievers=None)
    assert top2[0] == "Acute myeloid leukemia"
    assert trace["method"] == "flat_matched_rerank"
    assert cost["llm_calls"] == 2
    assert any("FlatCandidates" in m for m in cache.modules)
    assert any("FlatRerank" in m for m in cache.modules)
    assert not any("RAGPlanner" in m or "B01" in m for m in cache.modules)


def test_b04_dual_inf_multistep():
    cache = _FakeCache()
    top2, trace, cost = arms.run_b04(_toy_case(), cache, dry_run=False)
    assert top2[0]
    assert trace["method"] == "dual_inf"
    assert cost["llm_calls"] >= 3
    assert any("Forward" in m for m in cache.modules)
    assert any("Backward" in m for m in cache.modules)
    assert any("Examine" in m for m in cache.modules)


def test_b05_mdagents_and_b06_mac_multistep():
    case = _toy_case()
    cache5 = _FakeCache()
    top2, trace, cost = arms.run_b05(case, cache5, dry_run=False)
    assert top2[0]
    assert trace["method"] == "mdagents"
    assert cost["llm_calls"] >= 4
    cache6 = _FakeCache()
    top2, trace, cost = arms.run_b06(case, cache6, dry_run=False)
    assert top2[0]
    assert trace["method"] == "mac_single_vendor"
    assert cost["llm_calls"] == 4


def test_b15_medprompt_and_b16_medrag_not_aliases():
    case = _toy_case()
    cache15 = _FakeCache()
    top2, trace, cost = arms.run_b15(
        case, cache15, dry_run=False, retrievers=None, ensemble_rounds=3,
    )
    assert top2[0]
    assert trace["method"] == "medprompt_shared_kb"
    assert cost["llm_calls"] == 3
    assert sum("MedPrompt" in m for m in cache15.modules) == 3

    cache16 = _FakeCache()
    top2, trace, cost = arms.run_b16(case, cache16, dry_run=False, retrievers=None)
    assert top2[0]
    assert trace["method"] == "medrag_elicited_shared_kb"
    assert cost["llm_calls"] == 2
    assert any("MedRAGDiffs" in m for m in cache16.modules)
    assert any("MedRAGReason" in m for m in cache16.modules)


def test_b14_does_not_use_mcq_options_as_pool():
    cache = _FakeCache()
    case = _toy_case()
    top2, trace, cost = arms.run_b14(case, cache, dry_run=False, retrievers=None)
    assert top2[0]
    assert trace["pool_source"] == "shared_kb_proposed"
    assert "Iron deficiency" not in trace["pool"]
    assert "Viral illness" not in trace["pool"]
    assert cost["llm_calls"] >= 2


def test_b03_flat_beam_and_b07_meddx():
    case = _toy_case()
    cache3 = _FakeCache()
    top2, trace, cost = arms.run_b03(
        case, cache3, dry_run=False, retrievers=None, beam_width=3, beam_depth=1,
    )
    assert top2[0]
    assert trace["method"] == "flat_beam"
    assert cost["llm_calls"] >= 3  # init + expand + select
    assert any("FlatBeamInit" in m for m in cache3.modules)

    cache7 = _FakeCache()
    top2, trace, cost = arms.run_b07(case, cache7, dry_run=False, retrievers=None)
    assert top2[0]
    assert trace["method"] == "meddxagent_complete_profile"
    assert cost["llm_calls"] >= 3
    assert any("MedDx" in m for m in cache7.modules)


def test_b08_b09_b10_gated():
    case = _toy_case()
    cache = _FakeCache()
    with pytest.raises(RuntimeError, match="DeepRare"):
        arms.run_b08(case, cache)
    with pytest.raises(RuntimeError, match="phenotype"):
        arms.run_b09(case, cache)
    with pytest.raises(RuntimeError, match="mixed-vendor"):
        arms.run_b10(case, cache)


def test_b17_imedrag_loop():
    case = _toy_case()
    cache = _FakeCache()
    top2, trace, cost = arms.run_b17(
        case,
        cache,
        dry_run=False,
        retrievers=None,
        n_rounds=2,
        n_queries=2,
    )
    assert top2[0] == "Acute myeloid leukemia"
    assert trace["method"] == "imedrag"
    assert trace["kb"] == "shared_rag_index+cpg_index"
    # 2 rounds * (1 ask + 2 inners) + 1 final = 7
    assert cost["llm_calls"] == 7
    assert any("IMedRAGAsk" in m for m in cache.modules)
    assert any("IMedRAGFinal" in m for m in cache.modules)
