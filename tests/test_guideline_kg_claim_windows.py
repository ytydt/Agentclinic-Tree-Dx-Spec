"""Tests for source-aware guideline claim-window reconstruction."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_guideline_kg_claim_windows import (  # noqa: E402
    RECHUNKER_VERSION,
    build_claim_windows,
    detect_claim_blocks,
    estimate_tokens,
    group_entry_runs,
    iter_admitted_occurrences,
)


def _write_passages(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _passage(
    passage_id: str,
    text: str,
    ordinal: int,
    *,
    source: str = "NICE",
    source_family: str = "cpg",
    source_id: str = "nice_example",
    section_path: str = "Recommendations > Diagnosis > 1.2 Assessment",
    entry_title: str | None = None,
    admitted: bool = True,
) -> dict:
    metadata = {
        "section_path": section_path,
        "title": section_path,
    }
    if entry_title is not None:
        metadata["entry_title"] = entry_title
    provenance = {
        "source_family": source_family,
        "source": source,
        "source_id": source_id,
        "source_work_id": "gkg_work_example",
        "document_version_id": "gkg_version_" + source_id,
        "section_id": "gkg_section_example",
        "source_ordinal": ordinal,
        "raw_id": f"{source_id}__chunk_{ordinal:05d}",
        "admitted": admitted,
        "metadata": metadata,
    }
    return {
        "record_type": "Passage",
        "id": passage_id,
        "section_id": "gkg_section_example",
        "ordinal": ordinal,
        "text": text,
        "extensions": {
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "provenances": [provenance],
        },
    }


def _assert_offset_map_exact(window: dict, passages: dict[str, str]) -> None:
    for item in window["offset_map"]:
        assert item["window_end_char"] > item["window_start_char"]
        assert item["passage_end_char"] > item["passage_start_char"]
        assert item["window_end_char"] - item["window_start_char"] == (
            item["passage_end_char"] - item["passage_start_char"]
        )
        assert window["text"][item["window_start_char"]:item["window_end_char"]] == passages[
            item["passage_id"]
        ][item["passage_start_char"]:item["passage_end_char"]]


def test_cross_chunk_criteria_are_reassembled_as_one_claim_block(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    rows = [
        _passage(
            "p1",
            "Diagnostic criteria require two of the following:",
            1,
        ),
        _passage(
            "p2",
            "\u2022 Fever for at least 5 days\n\u2022 Rash\n\u2022 No alternative diagnosis",
            2,
        ),
    ]
    _write_passages(passages_path, rows)
    occurrences = list(iter_admitted_occurrences(passages_path))
    runs = group_entry_runs(occurrences)
    assert len(runs) == 1
    assert len(runs[0].occurrence_group) == 2
    blocks = detect_claim_blocks(runs[0])
    assert len(blocks) == 1
    assert blocks[0].block_type.startswith("criteria_")
    assert "Diagnostic criteria" in runs[0].text[blocks[0].start:blocks[0].end]
    assert "No alternative diagnosis" in runs[0].text[blocks[0].start:blocks[0].end]
    assert blocks[0].contains_scope_cue is True

    output = tmp_path / "out"
    build_claim_windows(
        passages_path=passages_path,
        output_dir=output,
        target_min_tokens=20,
        target_max_tokens=80,
        hard_max_tokens=100,
    )
    windows = _read_jsonl(output / "claim_windows.internal.jsonl")
    assert len(windows) == 1
    assert set(item["passage_id"] for item in windows[0]["offset_map"]) == {"p1", "p2"}
    assert len(windows[0]["primary_claim_blocks"]) == 1
    assert windows[0]["coverage_status"] == "pending_llm_coverage"
    assert windows[0]["coverage_risk"] == "standard"
    primary = windows[0]["primary_claim_blocks"][0]
    assert primary["structural_role"] == "criteria_closure"
    assert {"enumeration", "k_of_n", "negation", "temporal"}.issubset(primary["logic_cues"])
    assert primary["eligible_for_evidence"] is True
    assert windows[0]["text"][primary["window_start_char"]:primary["window_end_char"]].startswith(
        "Diagnostic criteria"
    )
    assert windows[0]["text_sha256"] == hashlib.sha256(windows[0]["text"].encode()).hexdigest()
    assert windows[0]["rechunker_version"] == RECHUNKER_VERSION
    _assert_offset_map_exact(windows[0], {row["id"]: row["text"] for row in rows})


def test_ordinal_gap_is_never_bridged(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    rows = [
        _passage("p1", "Diagnosis requires finding A.", 1),
        _passage("p3", "Finding B supports diagnosis.", 3),
    ]
    _write_passages(passages_path, rows)
    runs = group_entry_runs(list(iter_admitted_occurrences(passages_path)))
    assert len(runs) == 2
    assert [(run.ordinal_start, run.ordinal_end) for run in runs] == [(1, 1), (3, 3)]


def test_section_paths_are_soft_and_post_window_gate_blocks_treatment_edges(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    rows = [
        _passage(
            "p1",
            "Offer oral treatment once daily.",
            1,
            section_path="Recommendations > Treatment > 1.1",
        ),
        _passage(
            "p2",
            "Continue treatment for seven days.",
            2,
            section_path="Recommendations > Follow-up > 1.2",
        ),
    ]
    # Simulate all-clean admission: these passages have no diagnostic seed.
    for row in rows:
        row["extensions"]["provenances"][0]["admission"] = {
            "seed": False,
            "via_context_closure": True,
            "diagnostic_reasons": [],
        }
        row["extensions"]["admission_reasons"] = ["context_closure"]
    _write_passages(passages_path, rows)
    runs = group_entry_runs(list(iter_admitted_occurrences(passages_path)))
    assert len(runs) == 1
    assert len(runs[0].occurrence_group) == 2

    output = tmp_path / "out"
    build_claim_windows(
        passages_path=passages_path,
        output_dir=output,
        target_min_tokens=10,
        target_max_tokens=100,
        hard_max_tokens=120,
    )
    windows = _read_jsonl(output / "claim_windows.internal.jsonl")
    assert len(windows) == 1
    assert windows[0]["status"] == "not_diagnostic"
    assert windows[0]["coverage_status"] == "not_applicable"
    assert windows[0]["window_diagnostic_gate_reasons"] == []
    assert all(
        block["eligible_for_evidence"] is False
        for block in windows[0]["primary_claim_blocks"]
    )
    assert all(
        item["eligible_for_evidence"] is False
        for item in windows[0]["offset_map"]
    )
    pointer = _read_jsonl(output / "claim_window_queue.public.jsonl")[0]
    assert pointer["status"] == "not_diagnostic"
    stats = json.loads((output / "stats.json").read_text(encoding="utf-8"))
    assert stats["not_diagnostic_windows"] == 1
    assert stats.get("eligible_windows", 0) == 0


def test_semantic_overlap_is_mapped_but_ineligible_as_primary_evidence(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    text = (
        "Diagnosis\n"
        "Finding alpha is characteristic of the disorder and persists for five days.\n"
        "Finding beta supports the disorder when exposure occurred recently.\n"
        "Finding gamma argues against it if testing is negative.\n"
        "Finding delta confirms it after the acute period."
    )
    rows = [_passage("p1", text, 1)]
    _write_passages(passages_path, rows)
    output = tmp_path / "out"
    build_claim_windows(
        passages_path=passages_path,
        output_dir=output,
        target_min_tokens=10,
        target_max_tokens=24,
        hard_max_tokens=45,
    )
    windows = _read_jsonl(output / "claim_windows.internal.jsonl")
    assert len(windows) >= 2
    assert all(window["token_estimate"] <= 45 for window in windows)
    assert any(
        item["kind"] in {"context_copy", "overlap"}
        for window in windows
        for item in window["offset_map"]
    )
    assert all(
        item["eligible_for_evidence"] is (item["kind"] == "source")
        for window in windows
        for item in window["offset_map"]
    )
    assert all(
        region["eligible_for_evidence"] is False
        for window in windows
        for region in window["synthetic_regions"]
    )
    _assert_offset_map_exact(windows[-1], {"p1": text})
    public = (output / "claim_window_queue.public.jsonl").read_text(encoding="utf-8")
    assert "Finding alpha" not in public
    assert '"text":' not in public


def test_many_evidence_blocks_are_flagged_without_prejudging_resplit(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    text = "\n".join(
        f"Diagnostic finding {index} supports the disorder."
        for index in range(25)
    )
    row = _passage("p1", text, 1)
    row["extensions"]["provenances"][0]["admission"] = {
        "seed": True,
        "via_context_closure": False,
        "diagnostic_reasons": ["chunk_type:evaluation"],
    }
    _write_passages(passages_path, [row])
    output = tmp_path / "out"
    build_claim_windows(
        passages_path=passages_path,
        output_dir=output,
        target_min_tokens=10,
        target_max_tokens=1000,
        hard_max_tokens=1200,
        max_primary_blocks_per_window=48,
    )
    windows = _read_jsonl(output / "claim_windows.internal.jsonl")
    assert len(windows) == 1
    assert windows[0]["eligible_primary_block_count"] == 25
    assert windows[0]["coverage_status"] == "pending_llm_coverage"
    assert windows[0]["coverage_risk"] == "high_evidence_unit_density"


def test_indivisible_oversize_is_quarantined_not_truncated(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    huge = "Criterion " + ("unbrokenword " * 180).rstrip()
    rows = [_passage("p1", huge, 1)]
    _write_passages(passages_path, rows)
    output = tmp_path / "out"
    build_claim_windows(
        passages_path=passages_path,
        output_dir=output,
        target_min_tokens=10,
        target_max_tokens=20,
        hard_max_tokens=25,
    )
    assert _read_jsonl(output / "claim_windows.internal.jsonl") == []
    quarantine = _read_jsonl(output / "claim_window_quarantine.internal.jsonl")
    assert len(quarantine) == 1
    assert quarantine[0]["text"] == huge
    assert quarantine[0]["token_estimate"] > 25
    assert quarantine[0]["reason"] == "indivisible_claim_block_exceeds_hard_max"


def test_outputs_are_deterministic_and_public_queue_has_no_prose(tmp_path: Path) -> None:
    passages_path = tmp_path / "passages.jsonl"
    rows = [
        _passage("p1", "Symptoms and Signs\nFever is typical.", 1),
        _passage("p2", "Absence of fever argues against disease.", 2),
        _passage(
            "unadmitted",
            "This occurrence must not enter a window.",
            3,
            admitted=False,
        ),
    ]
    _write_passages(passages_path, rows)
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    for output in (out_a, out_b):
        build_claim_windows(
            passages_path=passages_path,
            output_dir=output,
            target_min_tokens=20,
            target_max_tokens=60,
            hard_max_tokens=80,
        )
    for name in (
        "claim_windows.internal.jsonl",
        "claim_window_queue.public.jsonl",
        "claim_window_quarantine.internal.jsonl",
        "stats.json",
    ):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes()
    public_rows = _read_jsonl(out_a / "claim_window_queue.public.jsonl")
    assert all("text" not in row for row in public_rows)
    assert all("entry_label" not in row for row in public_rows)
    stats = json.loads((out_a / "stats.json").read_text(encoding="utf-8"))
    assert stats["provenance_occurrences_unadmitted"] == 1
    assert stats["eligible_windows"] >= 1
    assert estimate_tokens("short text") > 0
