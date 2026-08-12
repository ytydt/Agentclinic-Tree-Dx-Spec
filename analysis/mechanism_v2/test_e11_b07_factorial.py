from __future__ import annotations

from pathlib import Path

from analysis.mechanism_v2.e11_b07_factorial import (
    MerckLexicalIndex,
    _extract_top2,
    _online_chunks,
    _select_length_matched,
    _source_id_from_historical,
    _top2_validator,
    load_jobs,
)
from analysis.mechanism_v2.online_runner import assert_target_blind


def test_extract_and_validate_top2_shapes() -> None:
    mapping = {
        "top2_diagnoses": [
            {"diagnosis": "Alpha disease", "explanation": "x"},
            {"diagnosis": "Beta disease", "explanation": "y"},
        ]
    }
    strings = {"top2_diagnoses": ["Alpha disease", "Beta disease"]}
    duplicate = {"top2_diagnoses": ["Alpha disease", "Alpha disease"]}
    assert _extract_top2(mapping) == ["Alpha disease", "Beta disease"]
    assert _extract_top2(strings) == ["Alpha disease", "Beta disease"]
    assert _top2_validator(mapping) is None
    assert _top2_validator(strings) is None
    assert _top2_validator(duplicate)


def test_online_chunk_projection_hides_treatment_and_scores() -> None:
    visible = _online_chunks(
        [
            {
                "chunk_id": "c1",
                "title": "Title",
                "text": "Evidence",
                "source": "Corpus",
                "retrieval_score": 0.95,
                "treatment": "hard_negative",
            }
        ]
    )
    assert visible == [{"chunk_id": "c1", "title": "Title", "text": "Evidence", "source": "Corpus"}]
    assert_target_blind({"vignette": "x", "knowledge_chunks": visible})


def test_lexical_index_prefers_matching_document() -> None:
    chunks = [
        {"id": "a", "title": "Alpha syndrome", "content": "fever rash alpha", "article_id": "a"},
        {"id": "b", "title": "Beta syndrome", "content": "fracture trauma beta", "article_id": "b"},
        {"id": "c", "title": "Gamma", "content": "unrelated nutrition", "article_id": "c"},
    ]
    index = MerckLexicalIndex(chunks)
    ranked = index.search_scores(["alpha fever rash"])
    assert ranked
    assert ranked[0][0] == 0


def test_historical_id_normalization() -> None:
    assert _source_id_from_historical("diagnosisarena__000254") == "254"
    assert _source_id_from_historical("custom__case-a") == "case-a"


def test_length_matching_prefers_eligible_distinct_articles() -> None:
    chunks = [
        {"id": "short", "article_id": "a", "content": "x" * 5},
        {"id": "long-a", "article_id": "a", "content": "x" * 100},
        {"id": "long-b", "article_id": "b", "content": "x" * 90},
        {"id": "long-c", "article_id": "c", "content": "x" * 80},
    ]
    selected = _select_length_matched(
        [(0, 1.0), (1, 0.9), (2, 0.8), (3, 0.7)], chunks, [70, 80]
    )
    assert all(len(chunks[index]["content"]) >= target for (index, _), target in zip(selected, [70, 80]))
    assert len({chunks[index]["article_id"] for index, _ in selected}) == 2


def test_full_historical_join_is_frozen_400() -> None:
    jobs, inputs = load_jobs()
    assert len(jobs) == 400
    assert len({row["case_key"] for row in jobs}) == 400
    assert sum(row["family"] == "DA" for row in jobs) == 200
    assert sum(row["family"] == "MCR" for row in jobs) == 200
    assert all(Path(path).is_file() for path in inputs)
