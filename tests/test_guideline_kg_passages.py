"""Tests for the deterministic guideline-KG passage admission layer."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_guideline_kg_passages import (  # noqa: E402
    InputSpec,
    MERCK_POLLUTION_REASON,
    build_passage_corpus,
    diagnostic_gate,
    merck_pollution_reason,
)
from agentclinic_tree_dx.knowledge.guideline_kg_schema import validate_graph  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_merck_pollution_rule_is_exact_and_preserves_true_chapter() -> None:
    base = {
        "source_id": "merck19e_ch353_the-dying-patient",
        "chapter_num": 353,
    }
    assert merck_pollution_reason({**base, "id": base["source_id"] + "__chunk_00018"}, "merck") is None
    assert (
        merck_pollution_reason({**base, "id": base["source_id"] + "__chunk_00019"}, "merck")
        == MERCK_POLLUTION_REASON
    )
    assert (
        merck_pollution_reason(
            {**base, "source_id": "another_ch353_document", "id": "another_ch353_document__chunk_00019"},
            "merck",
        )
        is None
    )
    assert merck_pollution_reason({**base, "id": base["source_id"] + "__chunk_00019"}, "cpg") is None


def test_high_recall_gate_combines_type_section_and_text() -> None:
    assert diagnostic_gate({"chunk_type": "differential", "content": "A list."}) == [
        "chunk_type:differential"
    ]
    assert "section_symptoms_signs" in diagnostic_gate(
        {"chunk_type": "background", "section_path": "Disease > Symptoms and Signs", "content": "Pain."}
    )
    assert "text_confirmation" in diagnostic_gate(
        {"chunk_type": "recommendation", "section_path": "Treatment", "content": "Biopsy confirms the disorder."}
    )
    assert not diagnostic_gate(
        {"chunk_type": "recommendation", "section_path": "Treatment", "content": "Offer oral therapy daily."}
    )


def test_end_to_end_closure_dedup_provenance_and_stable_ids(tmp_path: Path) -> None:
    merck_path = tmp_path / "merck.jsonl"
    cpg_path = tmp_path / "manifest.jsonl"
    wikem_path = tmp_path / "wikem.jsonl"

    merck_id = "merck19e_ch353_the-dying-patient"
    _write_jsonl(
        merck_path,
        [
            {
                "id": merck_id + "__chunk_00018",
                "source": "Merck-Manual-19e",
                "source_id": merck_id,
                "chapter_title": "The Dying Patient",
                "chapter_num": 353,
                "section_path": "Chapter 353 > Introduction",
                "chunk_type": "background",
                "content": "Ordinary final-chapter prose.",
                "license_note": "internal",
            },
            {
                "id": merck_id + "__chunk_00019",
                "source": "Merck-Manual-19e",
                "source_id": merck_id,
                "chapter_title": "The Dying Patient",
                "chapter_num": 353,
                "section_path": "Chapter 353 > Introduction",
                "chunk_type": "evaluation",
                "content": "Appendix spill that must not be admitted.",
            },
        ],
    )
    _write_jsonl(
        cpg_path,
        [
            {
                "id": "nice_doc__chunk_00001",
                "source": "NICE",
                "source_id": "nice_doc",
                "title": "Example guideline > Treatment",
                "section_path": "Example guideline > Treatment",
                "chunk_type": "recommendation",
                "content": "Context immediately before the key evidence.",
                "url": "https://example.test/nice",
                "sha256": "source-file-hash",
                "custom_field": "must survive",
            },
            {
                "id": "nice_doc__chunk_00002",
                "source": "NICE",
                "source_id": "nice_doc",
                "title": "Example guideline > Diagnosis",
                "section_path": "Example guideline > Diagnosis",
                "chunk_type": "evaluation",
                "content": "The shared diagnostic statement.",
            },
            {
                "id": "nice_doc__chunk_00003",
                "source": "NICE",
                "source_id": "nice_doc",
                "title": "Example guideline > Treatment",
                "section_path": "Example guideline > Treatment",
                "chunk_type": "recommendation",
                "content": "Context immediately after the key evidence.",
            },
            {
                "id": "nice_doc__chunk_00004",
                "source": "NICE",
                "source_id": "nice_doc",
                "title": "Example guideline > Treatment",
                "section_path": "Example guideline > Treatment",
                "chunk_type": "recommendation",
                "content": "Far treatment-only text.",
            },
        ],
    )
    _write_jsonl(
        wikem_path,
        [
            {
                "id": "wikem_entry__chunk_0001",
                "source": "WikEM",
                "source_id": "wikem_entry",
                "section_path": "Example > Differential Diagnosis",
                "title": "Example",
                "chunk_type": "differential",
                "content": "The shared diagnostic statement.",
                "wiki_links": ["Disease A"],
            }
        ],
    )

    out_a = tmp_path / "out_a"
    inputs = [InputSpec("merck", merck_path), InputSpec("cpg", cpg_path), InputSpec("wikem", wikem_path)]
    manifest = build_passage_corpus(inputs=inputs, output_dir=out_a, closure=1)

    stats = json.loads((out_a / "stats.json").read_text())
    assert stats["pollution_rows_dropped"] == 1
    assert stats["drop_reasons"][MERCK_POLLUTION_REASON] == 1
    assert stats["seed_occurrences"] == 2
    assert stats["closure_occurrences_added"] == 2
    assert stats["selected_occurrences"] == 4
    assert stats["unique_selected_passages"] == 3
    assert stats["selected_duplicate_occurrences_collapsed"] == 1
    assert manifest["parameters"]["context_closure_radius"] == 1
    assert manifest["parameters"]["context_mode"] == "neighbors"

    passages = _read_jsonl(out_a / "passages.jsonl")
    by_content = {row["text"]: row for row in passages}
    assert set(by_content) == {
        "Context immediately before the key evidence.",
        "The shared diagnostic statement.",
        "Context immediately after the key evidence.",
    }
    shared = by_content["The shared diagnostic statement."]
    assert len(shared["extensions"]["provenances"]) == 2
    assert {p["source"] for p in shared["extensions"]["provenances"]} == {"NICE", "WikEM"}
    nice_shared = next(
        p for p in shared["extensions"]["provenances"] if p["source"] == "NICE"
    )
    assert nice_shared["source_ordinal"] == 2
    assert nice_shared["selected_ordinal"] == 2
    assert nice_shared["selected_prev_passage_id"] == by_content[
        "Context immediately before the key evidence."
    ]["id"]
    assert nice_shared["selected_next_passage_id"] == by_content[
        "Context immediately after the key evidence."
    ]["id"]
    before = by_content["Context immediately before the key evidence."]["extensions"]["provenances"][0]
    assert before["admission"]["via_context_closure"] is True
    assert before["metadata"]["custom_field"] == "must survive"
    assert "content" not in before["metadata"]

    documents = _read_jsonl(out_a / "document_versions.jsonl")
    assert len(documents) == 3
    source_works = _read_jsonl(out_a / "source_works.jsonl")
    assert len(source_works) == 3
    sections = _read_jsonl(out_a / "sections.jsonl")
    assert any(row["extensions"]["admitted_occurrence_count"] == 0 for row in sections)
    assert validate_graph([*source_works, *documents, *sections, *passages]) == []

    # Entity streams, unlike the timestamped manifest, must be byte-stable.
    out_b = tmp_path / "out_b"
    build_passage_corpus(inputs=inputs, output_dir=out_b, closure=1)
    for name in (
        "source_works.jsonl",
        "document_versions.jsonl",
        "sections.jsonl",
        "passages.jsonl",
        "stats.json",
    ):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()


def test_document_context_restores_all_chunks_only_in_seed_documents(tmp_path: Path) -> None:
    source = tmp_path / "cpg.jsonl"
    _write_jsonl(
        source,
        [
            {
                "id": "seeded__chunk_00001",
                "source": "NICE",
                "source_id": "seeded",
                "section_path": "Example > Background",
                "chunk_type": "recommendation",
                "content": "Remote list header without cue words:",
            },
            {
                "id": "seeded__chunk_00002",
                "source": "NICE",
                "source_id": "seeded",
                "section_path": "Example > Treatment",
                "chunk_type": "recommendation",
                "content": "Unrelated intervening text.",
            },
            {
                "id": "seeded__chunk_00003",
                "source": "NICE",
                "source_id": "seeded",
                "section_path": "Example > Diagnosis",
                "chunk_type": "evaluation",
                "content": "Diagnosis is confirmed by the following findings.",
            },
            {
                "id": "no_seed__chunk_00001",
                "source": "NICE",
                "source_id": "no_seed",
                "section_path": "Other > Treatment",
                "chunk_type": "recommendation",
                "content": "Give medicine daily.",
            },
        ],
    )
    output = tmp_path / "document_context"
    manifest = build_passage_corpus(
        inputs=[InputSpec("cpg", source)],
        output_dir=output,
        context_mode="document",
    )
    passages = _read_jsonl(output / "passages.jsonl")
    assert {row["text"] for row in passages} == {
        "Remote list header without cue words:",
        "Unrelated intervening text.",
        "Diagnosis is confirmed by the following findings.",
    }
    assert manifest["parameters"]["context_mode"] == "document"
    assert manifest["outputs"]["passages"]["records"] == 3

    all_output = tmp_path / "all_context"
    all_manifest = build_passage_corpus(
        inputs=[InputSpec("cpg", source)],
        output_dir=all_output,
        context_mode="all",
    )
    all_passages = _read_jsonl(all_output / "passages.jsonl")
    assert {row["text"] for row in all_passages} == {
        "Remote list header without cue words:",
        "Unrelated intervening text.",
        "Diagnosis is confirmed by the following findings.",
        "Give medicine daily.",
    }
    assert all_manifest["parameters"]["context_mode"] == "all"
    assert all_manifest["outputs"]["passages"]["records"] == 4


def test_source_filter_and_limit_are_auditable(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    _write_jsonl(
        path,
        [
            {
                "id": "a__chunk_00001",
                "source": "NICE",
                "source_id": "a",
                "section_path": "A > Diagnosis",
                "chunk_type": "evaluation",
                "content": "First.",
            },
            {
                "id": "b__chunk_00001",
                "source": "ACR",
                "source_id": "b",
                "section_path": "B > Diagnosis",
                "chunk_type": "evaluation",
                "content": "Second.",
            },
            {
                "id": "c__chunk_00001",
                "source": "NICE",
                "source_id": "c",
                "section_path": "C > Diagnosis",
                "chunk_type": "evaluation",
                "content": "Third.",
            },
        ],
    )
    output = tmp_path / "filtered"
    manifest = build_passage_corpus(
        inputs=[InputSpec("cpg", path)],
        output_dir=output,
        source_filters=["nice"],
        closure=0,
        limit=1,
    )
    assert manifest["parameters"]["source_filters"] == ["nice"]
    assert manifest["inputs"][0]["complete_file_scan"] is False
    assert len(_read_jsonl(output / "passages.jsonl")) == 1
    stats = json.loads((output / "stats.json").read_text())
    assert stats["rows_matching_source_filter"] == 1


def test_duplicate_source_documents_collapse_without_duplicate_schema_ids(tmp_path: Path) -> None:
    path = tmp_path / "manifest.jsonl"
    rows = []
    for source_id in ("alias_a", "alias_b"):
        rows.append(
            {
                "id": source_id + "__chunk_00001",
                "source": "NICE",
                "source_id": source_id,
                "title": "Same guideline > Diagnosis",
                "section_path": "Same guideline > Diagnosis",
                "chunk_type": "evaluation",
                "content": "Identical clinical source content.",
                "url": "https://example.test/same-guideline",
            }
        )
    _write_jsonl(path, rows)
    output = tmp_path / "dedup_documents"
    build_passage_corpus(
        inputs=[InputSpec("cpg", path)], output_dir=output, closure=0
    )
    source_works = _read_jsonl(output / "source_works.jsonl")
    versions = _read_jsonl(output / "document_versions.jsonl")
    sections = _read_jsonl(output / "sections.jsonl")
    passages = _read_jsonl(output / "passages.jsonl")
    assert [len(value) for value in (source_works, versions, sections, passages)] == [1, 1, 1, 1]
    assert source_works[0]["extensions"]["source_ids"] == ["alias_a", "alias_b"]
    assert versions[0]["extensions"]["source_ids"] == ["alias_a", "alias_b"]
    assert len(passages[0]["extensions"]["provenances"]) == 2
    assert validate_graph([*source_works, *versions, *sections, *passages]) == []
