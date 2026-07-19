from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    assert_gold_blind,
    build_clone_groups,
    infer_question_target,
    leaf_rows_from_tree,
)
from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
)


def _leaves():
    return [
        {
            "leaf_id": "B1.1",
            "leaf_label": "Chronic Myeloid Leukemia",
            "parent_id": "B1",
            "parent_label": "Myeloid",
            "joint_rank": 2,
            "posterior": 0.2,
        },
        {
            "leaf_id": "B2.1",
            "leaf_label": "Chronic Myelogenous Leukemia (CML)",
            "parent_id": "B2",
            "parent_label": "Neoplastic",
            "joint_rank": 1,
            "posterior": 0.7,
        },
        {
            "leaf_id": "B3.1",
            "leaf_label": "Acute Myeloid Leukemia",
            "parent_id": "B3",
            "parent_label": "Acute",
            "joint_rank": 3,
            "posterior": 0.1,
        },
    ]


class _FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.modules = []

    def call_module(self, module, _prompt, payload):
        assert_gold_blind(payload)
        self.modules.append(module)
        return self.responses.pop(0)


class _FakeRetriever:
    is_ready = True

    def search(self, query, *, top_k, score_threshold):
        assert top_k == 3
        assert score_threshold == 0.0
        return [{
            "id": "chunk-1",
            "title": "CML",
            "content": "CML is chronic myeloid leukemia.",
            "score": 0.9,
            "query": query,
        }]


def _typed_response(confidence="high", ids=None):
    return {
        "question_target": "diagnosis",
        "option_relations": [
            {
                "option_letter": "A",
                "relation_type": "equivalent",
                "matched_leaf_ids": ids or ["B1.1"],
                "confidence": confidence,
                "confidence_score": 0.95 if confidence == "high" else 0.4,
                "rationale": "same disease",
            },
            {
                "option_letter": "B",
                "relation_type": "equivalent",
                "matched_leaf_ids": ["B3.1"],
                "confidence": "high",
                "confidence_score": 0.95,
                "rationale": "same disease",
            },
        ],
        "semantic_clone_groups": [["B1.1", "B2.1"]],
    }


def test_gold_blind_guard_rejects_nested_evaluation_keys():
    with pytest.raises(AssertionError):
        assert_gold_blind({"safe": [{"gold_letter": "A"}]})


def test_question_target_heuristics_cover_non_diagnosis_questions():
    assert infer_question_target("Which organism is the likely cause?") == (
        "etiology_pathogen"
    )
    assert infer_question_target("What is the mechanism?") == "mechanism"
    assert infer_question_target("Best treatment?") == "treatment"


def test_leaf_extraction_keeps_parent_rank_and_posterior():
    tree = {
        "branches": {
            "B1": {"label": "Parent", "children": ["B1.1"]},
            "B1.1": {
                "label": "Disease", "parent": "B1", "children": [],
                "posterior": 0.4,
            },
        },
    }
    rows = leaf_rows_from_tree(tree, ["B1.1"])
    assert rows == [{
        "leaf_id": "B1.1",
        "leaf_label": "Disease",
        "parent_id": "B1",
        "parent_label": "Parent",
        "joint_rank": 1,
        "posterior": 0.4,
    }]


def test_clone_closure_crosses_parents_and_uses_best_rank_without_sum():
    resolver = DiseaseNameResolver()
    mapper = RelationAwareAnswerMapper(resolver=resolver)
    result = mapper.map(
        case_id="c1",
        vignette="v",
        question="What is the diagnosis?",
        options={"A": "CML", "B": "Acute myeloid leukemia"},
        leaves=_leaves(),
        mode="deterministic_gold_blind",
    )
    cml = result["option_maps"]["A"]
    assert cml["clone_leaf_ids"] == ["B1.1", "B2.1"]
    assert cml["best_rank"] == 1
    assert cml["posterior"] == 0.7
    assert cml["support_score"] == 1.0
    assert result["option_maps"]["B"]["best_rank"] == 3


def test_typed_mapper_schema_repair_and_semantic_clone_closure():
    bad = {"question_target": "diagnosis", "option_relations": []}
    llm = _FakeLLM([bad, _typed_response()])
    mapper = RelationAwareAnswerMapper(
        resolver=DiseaseNameResolver(),
        llm=llm,
        relation_prompt="prompt",
    )
    result = mapper.map(
        case_id="c1",
        vignette="v",
        question="Most likely diagnosis?",
        options={"A": "CML", "B": "AML"},
        leaves=_leaves(),
        mode="typed_llm",
    )
    assert llm.modules == [
        "L2RelationAnswerMapper", "L2RelationAnswerMapperRepair",
    ]
    assert result["audit"]["typed"]["schema_repair_used"] is True
    assert result["option_maps"]["A"]["clone_leaf_ids"] == ["B1.1", "B2.1"]


def test_rag_is_called_only_for_triggered_dispute_and_overrides_mapping():
    typed = _typed_response(confidence="low", ids=["B1.1"])
    critic = {
        "decisions": [{
            "option_letter": "A",
            "relation_type": "equivalent",
            "matched_leaf_ids": ["B2.1"],
            "confidence": "high",
            "confidence_score": 0.9,
            "rationale": "retrieved equivalence",
        }],
    }
    llm = _FakeLLM([typed, critic])
    mapper = RelationAwareAnswerMapper(
        resolver=DiseaseNameResolver(),
        llm=llm,
        relation_prompt="relation",
        critic_prompt="critic",
        retrievers={"rag": _FakeRetriever()},
    )
    result = mapper.map(
        case_id="c1",
        vignette="v",
        question="Most likely diagnosis?",
        options={"A": "CML", "B": "AML"},
        leaves=_leaves(),
        mode="typed_llm_disagreement_rag",
    )
    assert result["audit"]["rag"]["called"] is True
    assert result["option_maps"]["A"]["source"] == "rag_critic"
    assert result["option_maps"]["A"]["best_rank"] == 1


def test_no_rag_mode_never_calls_retriever():
    llm = _FakeLLM([_typed_response()])
    mapper = RelationAwareAnswerMapper(
        resolver=DiseaseNameResolver(),
        llm=llm,
        retrievers={"rag": _FakeRetriever()},
    )
    result = mapper.map(
        case_id="c1",
        vignette="v",
        question="Most likely diagnosis?",
        options={"A": "CML", "B": "AML"},
        leaves=_leaves(),
        mode="typed_llm",
    )
    assert result["audit"]["rag"]["called"] is False
