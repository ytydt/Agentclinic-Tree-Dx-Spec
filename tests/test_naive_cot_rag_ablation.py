from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "eval_naive_cot_rag_ablation",
    ROOT / "scripts" / "eval_naive_cot_rag_ablation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeRetriever:
    def __init__(self, prefix):
        self.prefix = prefix
        self.calls = []

    def search(self, query, *, top_k, score_threshold):
        self.calls.append((query, top_k, score_threshold))
        return [
            {
                "id": f"{self.prefix}-shared",
                "title": "Shared",
                "content": f"{query} shared text",
                "score": 0.9,
            },
            {
                "id": f"{self.prefix}-{query}",
                "title": "Specific",
                "content": "specific text",
                "score": 0.7,
            },
        ][:top_k]


class FakeCache:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, payload))
        return self.responses[module]


def test_search_plan_is_strict_and_deduplicated():
    valid = MODULE.clean_search_plan({
        "search_queries": [" differential diagnosis fever ", "FEVER"],
        "reasoning_summary": "reason",
    })
    assert valid["schema_valid"]
    assert valid["search_queries"] == [
        "differential diagnosis fever", "FEVER",
    ]
    invalid = MODULE.clean_search_plan({"search_queries": []})
    assert not invalid["schema_valid"]


def test_live_retrieval_fuses_indexes_and_caps_bundle():
    retrievers = {
        "rag_index": FakeRetriever("rag"),
        "cpg_index": FakeRetriever("cpg"),
    }
    chunks, audit = MODULE.retrieve_live_bundle(
        ["query one", "query two"],
        retrievers,
        per_query_per_index=2,
        max_chunks=3,
    )
    assert len(chunks) == 3
    assert audit["candidate_chunks"] == 6
    assert audit["served_chunks"] == 3
    assert all(row["access_id"].startswith("live::") for row in chunks)
    shared = next(
        row for row in chunks if row["source_chunk_id"] == "cpg-shared"
    )
    assert shared["retrieval_queries"] == ["query one", "query two"]


def test_no_rag_arm_never_calls_planner_or_retriever():
    cache = FakeCache({
        "NaiveCoTNoRAGAnswer": {
            "top2_diagnoses": [
                {
                    "diagnosis": "Disease A",
                    "reasoning_summary": "a",
                    "knowledge_access_ids": [],
                },
                {
                    "diagnosis": "Disease B",
                    "reasoning_summary": "b",
                    "knowledge_access_ids": [],
                },
            ],
        },
    })
    retrievers = {
        "rag_index": FakeRetriever("rag"),
        "cpg_index": FakeRetriever("cpg"),
    }
    record = MODULE._record(
        arm="N0-CoT-no-RAG",
        replicate=1,
        case={"id": "case", "case_text": "vignette"},
        cache=cache,
        answer_prompt="answer",
        planner_prompt="planner",
        retrievers=retrievers,
    )
    assert record["query_plan"] is None
    assert record["input"]["knowledge_chunks"] == []
    assert cache.calls[0][0] == "NaiveCoTNoRAGAnswer"
    assert not any(retriever.calls for retriever in retrievers.values())


def test_live_rag_payload_contains_only_retrieved_chunks_not_gold():
    cache = FakeCache({
        "NaiveCoTLiveRAGPlanner": {
            "search_queries": ["differential diagnosis unilateral weakness"],
            "reasoning_summary": "retrieve",
        },
        "NaiveCoTLiveProductionRAGAnswer": {
            "top2_diagnoses": [
                {
                    "diagnosis": "Disease A",
                    "reasoning_summary": "a",
                    "knowledge_access_ids": [],
                },
                {
                    "diagnosis": "Disease B",
                    "reasoning_summary": "b",
                    "knowledge_access_ids": [],
                },
            ],
        },
    })
    record = MODULE._record(
        arm="N0-CoT-live-production-RAG",
        replicate=1,
        case={"id": "case", "case_text": "vignette"},
        cache=cache,
        answer_prompt="answer",
        planner_prompt="planner",
        retrievers={
            "rag_index": FakeRetriever("rag"),
            "cpg_index": FakeRetriever("cpg"),
        },
    )
    assert record["retrieval_audit"]["served_chunks"] == 4
    assert all(
        row["access_id"].startswith("live::")
        for row in record["input"]["knowledge_chunks"]
    )
    assert "gold" not in str(record["input"]).casefold()


def test_manual_rag_ablation_fixture_is_frozen_and_complete():
    fixture, rows = MODULE._manual_fixture(MODULE.DEFAULT_MANUAL)
    assert fixture is not None
    assert len(rows) == 102
    assert fixture["adjudication_mode"].startswith("manual")
    assert all(row["reviewer"] for row in rows.values())
