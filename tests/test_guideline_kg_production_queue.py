"""Adversarial tests for the production ClaimWindow queue compiler."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compile_guideline_kg_extraction_queue import (  # noqa: E402
    QUEUE_COMPILER_VERSION,
    compile_production_extraction_queue,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _fixture(
    tmp_path: Path,
    evidence: list[str],
    *,
    block_types: list[str] | None = None,
) -> tuple[Path, Path, dict]:
    block_types = block_types or ["prose"] * len(evidence)
    source_texts = ["Diagnosis", *evidence]
    passages = [
        {
            "record_type": "Passage",
            "id": f"passage_{index:03d}",
            "text": text,
        }
        for index, text in enumerate(source_texts)
    ]
    text = "\n\n".join(source_texts)
    cursor = 0
    blocks: list[dict] = []
    offset_map: list[dict] = []
    synthetic: list[dict] = []
    for index, passage in enumerate(passages):
        if index:
            synthetic.append(
                {
                    "window_start_char": cursor,
                    "window_end_char": cursor + 2,
                    "kind": "fixture_separator",
                    "eligible_for_evidence": False,
                }
            )
            cursor += 2
        start = cursor
        cursor += len(passage["text"])
        eligible = index > 0
        block_type = "heading" if not eligible else block_types[index - 1]
        logic = (
            ["enumeration", "k_of_n", "threshold", "lead_in"]
            if "criteria" in block_type
            else []
        )
        structural_role = (
            "heading_context"
            if not eligible
            else "criteria_closure"
            if "criteria" in block_type
            else "prose_claim"
        )
        blocks.append(
            {
                "block_id": f"block_{index:03d}",
                "window_start_char": start,
                "window_end_char": cursor,
                "block_type": block_type,
                "structural_role": structural_role,
                "logic_cues": logic,
                "contains_scope_cue": bool(logic),
                "diagnostic_gate_reasons": ["fixture"] if eligible else [],
                "eligible_for_evidence": eligible,
            }
        )
        offset_map.append(
            {
                "window_start_char": start,
                "window_end_char": cursor,
                "passage_id": passage["id"],
                "passage_start_char": 0,
                "passage_end_char": len(passage["text"]),
                "kind": "source",
                "eligible_for_evidence": eligible,
                "source_id": "fixture",
                "source_ordinal": index,
            }
        )
    parent = {
        "record_type": "ClaimWindow",
        "id": "parent_window",
        "window_id": "parent_window",
        "rechunker_version": "fixture-v1",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "token_estimate": len(text) // 4 + 1,
        "entry_run_id": "entry",
        "entry_label": "Example disease",
        "source": "Fixture Manual",
        "source_family": "fixture",
        "source_id": "fixture",
        "source_work_id": "work",
        "document_version_id": "version",
        "source_ordinal_start": 0,
        "source_ordinal_end": len(passages) - 1,
        "section_paths": [["Example disease", "Diagnosis"]],
        "entry_title_candidates": ["Example disease"],
        "candidate_surfaces": ["Example disease"],
        "anchor_passage_ids": [row["id"] for row in passages],
        "claim_block_ids": [row["block_id"] for row in blocks],
        "claim_block_types": [row["block_type"] for row in blocks],
        "primary_claim_blocks": blocks,
        "eligible_primary_block_count": len(evidence),
        "coverage_status": "pending_llm_coverage",
        "coverage_risk": "fixture",
        "offset_map": offset_map,
        "synthetic_regions": synthetic,
        "overlap_policy": {"fixed_token_overlap": False},
        "status": "eligible",
    }
    graph = tmp_path / "graph.jsonl"
    windows = tmp_path / "windows.jsonl"
    _write_jsonl(graph, passages)
    _write_jsonl(windows, [parent])
    return windows, graph, parent


def _compile(
    tmp_path: Path,
    windows: Path,
    graph: Path,
    *,
    output_name: str = "out",
    max_evidence_blocks: int = 12,
    max_source_tokens: int = 6000,
):
    output = tmp_path / output_name
    result = compile_production_extraction_queue(
        parent_windows_path=windows,
        graph_path=graph,
        output_dir=output,
        max_evidence_blocks=max_evidence_blocks,
        max_source_tokens=max_source_tokens,
    )
    return output, result


def test_thirteen_claim_blocks_are_pre_split_without_loss(tmp_path: Path) -> None:
    windows, graph, _ = _fixture(
        tmp_path,
        [f"Finding {index} supports Example disease." for index in range(13)],
    )
    output, result = _compile(tmp_path, windows, graph)
    queue = _read_jsonl(output / "claim_windows.production.internal.jsonl")
    coverage = _read_jsonl(output / "claim_block_coverage_audit.public.jsonl")

    assert [row["eligible_primary_block_count"] for row in queue] == [12, 1]
    assert all(row["queue_action"] == "pre_split_child" for row in queue)
    assert all(row["parent_window_id"] == "parent_window" for row in queue)
    assert all(row["root_window_id"] == "parent_window" for row in queue)
    assert all(row["resplit_depth"] == 1 for row in queue)
    assert len(coverage) == 13
    assert {row["terminal_outcome"] for row in coverage} == {"fully_emitted"}
    assert result["changes"]["call_delta"] == 1
    assert result["coverage_invariants"][
        "all_well_formed_original_blocks_have_one_exact_terminal_partition"
    ]
    assert result["coverage_invariants"]["silent_drop_count"] == 0
    assert result["output"]["evidence_unit_distribution"]["max"] == 12
    assert result["extraction_lanes"]["lane_block_sum"] == 13
    assert result["extraction_lanes"]["direct_extract"]["blocks"] == 13
    assert result["extraction_lanes"]["upstream_only"] == {}
    assert result["legacy_chunk_provenance"][
        "input_windows_spanning_multiple_passages"
    ] == 1
    assert result["legacy_chunk_provenance"]["fixed_token_overlap_added"] is False


def test_small_parent_is_retained_and_public_pointer_is_source_free(
    tmp_path: Path,
) -> None:
    phrase = "Rare finding strongly supports Example disease."
    windows, graph, parent = _fixture(tmp_path, [phrase, "A second finding."])
    output, result = _compile(tmp_path, windows, graph)
    queue = _read_jsonl(output / "claim_windows.production.internal.jsonl")
    assert len(queue) == 1
    assert queue[0]["queue_action"] == "retained_parent"
    assert queue[0]["text"] == parent["text"]
    assert queue[0]["queue_compiler_version"] == QUEUE_COMPILER_VERSION
    assert result["changes"]["call_delta"] == 0
    public = (output / "claim_window_queue.production.public.jsonl").read_text()
    assert phrase not in public
    assert '"text":' not in public


def test_oversize_logic_closure_is_quarantined_intact(tmp_path: Path) -> None:
    closure = (
        "At least two of the following are required: "
        + "; ".join(f"criterion {index}" for index in range(80))
        + "."
    )
    windows, graph, _ = _fixture(
        tmp_path,
        [closure, "A compact independent finding."],
        block_types=["criteria_list", "prose"],
    )
    output, result = _compile(
        tmp_path, windows, graph, max_source_tokens=80
    )
    quarantine = _read_jsonl(
        output / "claim_window_queue_quarantine.internal.jsonl"
    )
    coverage = _read_jsonl(output / "claim_block_coverage_audit.public.jsonl")
    assert len(quarantine) == 1
    assert quarantine[0]["text"] == closure
    assert (
        quarantine[0]["reason"]
        == "indivisible_logic_closure_exceeds_source_cap"
    )
    closure_row = next(row for row in coverage if row["original_block_id"] == "block_001")
    assert closure_row["terminal_outcome"] == "fully_quarantined"
    assert result["preparation_metrics"]["oversize_logic_closures"] == 1
    public = (
        output / "claim_window_queue_quarantine.public.jsonl"
    ).read_text()
    assert closure not in public


def test_oversize_headed_prose_splits_on_sentences_and_header_is_context(
    tmp_path: Path,
) -> None:
    value = (
        "Clinical features\n"
        "First finding strongly supports Example disease. "
        "Second finding also supports Example disease. "
        "Third finding argues against the closest mimic."
    )
    windows, graph, _ = _fixture(
        tmp_path, [value], block_types=["headed_prose"]
    )
    output, result = _compile(
        tmp_path,
        windows,
        graph,
        max_evidence_blocks=2,
        max_source_tokens=25,
    )
    queue = _read_jsonl(output / "claim_windows.production.internal.jsonl")
    coverage = _read_jsonl(output / "claim_block_coverage_audit.public.jsonl")
    # The 25-token cap includes the governing heading, so each complete
    # sentence receives its own child instead of silently dropping the title.
    assert len(queue) == 3
    assert [row["eligible_primary_block_count"] for row in queue] == [1, 1, 1]
    assert all(
        block["production_subdivision"] == "complete_sentence_boundary"
        for row in queue
        for block in row["primary_claim_blocks"]
    )
    assert all(
        any(
            "Clinical features"
            in row["text"][item["window_start_char"] : item["window_end_char"]]
            and item["kind"] == "context_copy"
            and item["eligible_for_evidence"] is False
            for item in row["offset_map"]
        )
        for row in queue
    )
    assert coverage[0]["terminal_outcome"] == "transformed_with_context"
    ranges = coverage[0]["terminal_pieces"]
    assert ranges[0]["window_start_char"] == 11  # after outer Diagnosis heading
    assert all(
        left["window_end_char"] == right["window_start_char"]
        for left, right in zip(ranges, ranges[1:])
    )
    assert result["preparation_metrics"]["sentence_subdivided_original_blocks"] == 1
    assert result["coverage_invariants"]["silent_drop_count"] == 0


def test_one_overlong_sentence_is_quarantined_not_character_split(
    tmp_path: Path,
) -> None:
    sentence = "Diagnostic " + ("unbrokenword " * 200).rstrip() + "."
    windows, graph, _ = _fixture(tmp_path, [sentence])
    output, result = _compile(
        tmp_path, windows, graph, max_source_tokens=30
    )
    assert _read_jsonl(output / "claim_windows.production.internal.jsonl") == []
    quarantine = _read_jsonl(
        output / "claim_window_queue_quarantine.internal.jsonl"
    )
    assert quarantine[0]["text"] == sentence
    assert quarantine[0]["reason"] == "no_complete_sentence_boundary_within_source_cap"
    assert result["output"]["production_calls"] == 0
    assert result["coverage_invariants"]["silent_drop_count"] == 0


def test_compilation_is_byte_deterministic(tmp_path: Path) -> None:
    windows, graph, _ = _fixture(
        tmp_path,
        [f"Finding {index} supports Example disease." for index in range(15)],
    )
    first, _ = _compile(tmp_path, windows, graph, output_name="first")
    second, _ = _compile(tmp_path, windows, graph, output_name="second")
    for filename in (
        "claim_windows.production.internal.jsonl",
        "claim_window_queue.production.public.jsonl",
        "claim_window_queue_quarantine.internal.jsonl",
        "claim_window_queue_quarantine.public.jsonl",
        "claim_block_coverage_audit.public.jsonl",
        "claim_window_lane.direct_extract.public.jsonl",
        "claim_window_lane.upstream_only.public.jsonl",
        "stats.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_direct_and_upstream_lanes_are_block_exclusive_without_resplitting(
    tmp_path: Path,
) -> None:
    windows, graph, parent = _fixture(
        tmp_path, ["Direct diagnostic statement.", "Inherited candidate text."]
    )
    parent["primary_claim_blocks"][1]["diagnostic_gate_reasons"] = [
        "text:explicit_diagnostic_cue"
    ]
    parent["primary_claim_blocks"][2]["diagnostic_gate_reasons"] = [
        "upstream:chunk_type:evaluation",
        "upstream:text_diagnosis",
    ]
    _write_jsonl(windows, [parent])
    output, result = _compile(tmp_path, windows, graph)
    direct = _read_jsonl(output / "claim_window_lane.direct_extract.public.jsonl")
    upstream = _read_jsonl(output / "claim_window_lane.upstream_only.public.jsonl")
    assert direct[0]["claim_block_ids"] == ["block_001"]
    assert upstream[0]["claim_block_ids"] == ["block_002"]
    assert set(direct[0]["claim_block_ids"]).isdisjoint(
        upstream[0]["claim_block_ids"]
    )
    assert direct[0]["physical_claim_block_split"] is False
    assert upstream[0]["closure_and_offsets_unchanged"] is True
    assert result["extraction_lanes"]["lane_block_sum"] == 2
    assert result["extraction_lanes"]["mixed_lane_parent_calls"] == 1
