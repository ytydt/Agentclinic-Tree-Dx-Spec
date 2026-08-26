"""Tests for lossless adaptive resplitting of LLM-capacity ClaimWindows."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_guideline_kg_residuals as residuals
from resplit_guideline_kg_claim_windows import (
    RESPLITTER_VERSION,
    resplit_claim_windows,
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


def _fixture(tmp_path: Path, *, evidence_texts: list[str] | None = None):
    evidence_texts = evidence_texts or [
        "Finding alpha supports Example disease.",
        "Finding beta supports Example disease.",
        "Finding gamma argues against Example disease.",
        "Finding delta confirms Example disease.",
    ]
    passage_texts = ["Diagnosis", *evidence_texts]
    passages = [
        {
            "record_type": "Passage",
            "id": f"passage_{index}",
            "text": text,
        }
        for index, text in enumerate(passage_texts)
    ]
    text = "\n\n".join(passage_texts)
    offset_map: list[dict] = []
    synthetic: list[dict] = []
    blocks: list[dict] = []
    cursor = 0
    for index, passage in enumerate(passages):
        if index:
            synthetic.append(
                {
                    "window_start_char": cursor,
                    "window_end_char": cursor + 2,
                    "kind": "separator",
                    "eligible_for_evidence": False,
                }
            )
            cursor += 2
        start = cursor
        cursor += len(passage["text"])
        eligible = index > 0
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
                "raw_id": f"raw_{index}",
            }
        )
        blocks.append(
            {
                "block_id": f"block_{index}",
                "window_start_char": start,
                "window_end_char": cursor,
                "block_type": "heading" if index == 0 else "prose",
                "structural_role": "heading_context" if index == 0 else "prose_claim",
                "logic_cues": [],
                "contains_scope_cue": False,
                "diagnostic_gate_reasons": ["fixture"] if eligible else [],
                "eligible_for_evidence": eligible,
            }
        )
    parent = {
        "record_type": "ClaimWindow",
        "id": "parent_window",
        "window_id": "parent_window",
        "rechunker_version": "fixture-rechunker-v1",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "token_estimate": len(text) // 4 + 1,
        "entry_run_id": "fixture_run",
        "logical_scope_key": "fixture_scope",
        "entry_label": "Example disease",
        "source_family": "fixture",
        "source": "Fixture Manual",
        "source_id": "fixture",
        "source_work_id": "work_fixture",
        "document_version_id": "version_fixture",
        "source_ordinal_start": 0,
        "source_ordinal_end": len(passages) - 1,
        "section_paths": [["Example disease", "Diagnosis"]],
        "entry_title_candidates": ["Example disease"],
        "candidate_surfaces": ["Example disease"],
        "wiki_links": [],
        "anchor_passage_ids": [row["id"] for row in passages],
        "diagnostic_gate_reasons": ["fixture"],
        "window_diagnostic_gate_reasons": ["fixture"],
        "claim_block_ids": [row["block_id"] for row in blocks],
        "claim_block_types": [row["block_type"] for row in blocks],
        "primary_claim_blocks": blocks,
        "eligible_primary_block_count": len(evidence_texts),
        "contains_scope_cue": False,
        "coverage_status": "pending_llm_coverage",
        "coverage_risk": "standard",
        "offset_map": offset_map,
        "synthetic_regions": synthetic,
        "status": "eligible",
    }
    graph_path = tmp_path / "graph.jsonl"
    parents_path = tmp_path / "parents.jsonl"
    _write_jsonl(graph_path, passages)
    _write_jsonl(parents_path, [parent])
    return passages, parent, graph_path, parents_path


def _run(
    tmp_path: Path,
    parent: dict,
    graph_path: Path,
    parents_path: Path,
    *,
    reason: str,
    name: str = "out",
    max_evidence_blocks: int = 2,
    max_source_tokens: int = 1500,
    max_depth: int = 3,
    status_only: bool = False,
):
    ledger_path = tmp_path / f"ledger_{name}.jsonl"
    ledger = {
        "semantic_mode": "claim_window",
        "semantic_unit_id": parent["window_id"],
        "rechunker_version": parent["rechunker_version"],
        "window_sha256": parent["text_sha256"],
        "contains_source_text": False,
    }
    ledger["coverage_status" if status_only else "coverage_reason"] = reason
    _write_jsonl(ledger_path, [ledger])
    output = tmp_path / name
    result = resplit_claim_windows(
        parent_windows_path=parents_path,
        needs_resplit_path=ledger_path,
        graph_path=graph_path,
        output_dir=output,
        max_evidence_blocks=max_evidence_blocks,
        max_source_tokens=max_source_tokens,
        max_depth=max_depth,
    )
    return output, result


def test_too_many_assertions_splits_at_blocks_with_exact_projection(
    tmp_path: Path,
) -> None:
    passages, parent, graph, parents = _fixture(tmp_path)
    output, result = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="too_many_assertions",
        max_evidence_blocks=2,
    )
    children = _read_jsonl(output / "claim_windows.resplit.internal.jsonl")
    assert result["children"] == 2
    assert [len(row["primary_claim_blocks"]) for row in children] == [2, 2]
    assert [
        block_id for child in children for block_id in child["claim_block_ids"]
    ] == ["block_1", "block_2", "block_3", "block_4"]
    assert all(child["token_estimate"] <= 1500 for child in children)
    assert all(child["resplit_depth"] == 1 for child in children)
    assert all(RESPLITTER_VERSION in child["rechunker_version"] for child in children)

    index = {row["id"]: row for row in passages}
    for child in children:
        normalized = residuals.normalize_claim_window(child, index)
        evidence, mode = residuals.claim_window_evidence_inventory(
            normalized,
            max_units=2,
            max_sentence_subspans=100,
        )
        assert mode == "primary_claim_block"
        assert len(evidence) == 2
        # The repeated Diagnosis header remains useful but can never be cited.
        header_maps = [
            row for row in child["offset_map"] if row["passage_id"] == "passage_0"
        ]
        assert header_maps
        assert all(row["kind"] == "context_copy" for row in header_maps)
        assert all(row["eligible_for_evidence"] is False for row in header_maps)
        for item in child["offset_map"]:
            assert (
                child["text"][item["window_start_char"] : item["window_end_char"]]
                == index[item["passage_id"]]["text"][
                    item["passage_start_char"] : item["passage_end_char"]
                ]
            )

    public_text = (output / "claim_window_queue.resplit.public.jsonl").read_text()
    assert "Finding alpha" not in public_text
    assert '"text":' not in public_text


def test_output_is_deterministic_and_does_not_modify_base_graph(tmp_path: Path) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    graph_before = graph.read_bytes()
    first, _ = _run(
        tmp_path, parent, graph, parents, reason="output_budget_insufficient", name="a"
    )
    second, _ = _run(
        tmp_path, parent, graph, parents, reason="output_budget_insufficient", name="b"
    )
    assert graph.read_bytes() == graph_before
    for filename in (
        "claim_windows.resplit.internal.jsonl",
        "claim_window_queue.resplit.public.jsonl",
        "claim_window_resplit_quarantine.internal.jsonl",
        "claim_window_resplit_quarantine.public.jsonl",
        "stats.json",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_evidence_unit_too_broad_isolates_multiple_blocks(tmp_path: Path) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="evidence_unit_too_broad",
        max_evidence_blocks=16,
    )
    children = _read_jsonl(output / "claim_windows.resplit.internal.jsonl")
    assert len(children) == 4
    assert all(child["eligible_primary_block_count"] == 1 for child in children)


def test_broad_multisentence_prose_becomes_sentence_subclaims(tmp_path: Path) -> None:
    first_sentence = "Finding alpha supports Example disease."
    second_sentence = "Finding beta argues against Example disease."
    prose = f"{first_sentence} {second_sentence}"
    passages, parent, graph, parents = _fixture(
        tmp_path,
        evidence_texts=[prose],
    )
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="resplit_evidence_unit",
        status_only=True,
    )
    children = _read_jsonl(output / "claim_windows.resplit.internal.jsonl")
    assert len(children) == 2
    assert _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl") == []
    assert all(
        child["primary_claim_blocks"][0]["adaptive_subdivision"] == "sentence_boundary"
        for child in children
    )
    assert [
        child["text"][
            child["primary_claim_blocks"][0]["window_start_char"] : child[
                "primary_claim_blocks"
            ][0]["window_end_char"]
        ]
        for child in children
    ] == [
        "Finding alpha supports Example disease.",
        "Finding beta argues against Example disease.",
    ]
    index = {row["id"]: row for row in passages}
    for child in children:
        residuals.normalize_claim_window(child, index)


def test_headed_prose_header_is_context_only_after_sentence_split(
    tmp_path: Path,
) -> None:
    _, parent, graph, parents = _fixture(
        tmp_path,
        evidence_texts=[
            "Clinical features\nFinding alpha is typical. Finding beta is supporting."
        ],
    )
    parent["primary_claim_blocks"][1]["block_type"] = "headed_prose"
    parent["primary_claim_blocks"][1]["structural_role"] = "headed_claim"
    _write_jsonl(parents, [parent])
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="resplit_evidence_unit",
        status_only=True,
    )
    children = _read_jsonl(output / "claim_windows.resplit.internal.jsonl")
    assert len(children) == 2
    for child in children:
        header_maps = [
            item
            for item in child["offset_map"]
            if "Clinical features"
            in child["text"][item["window_start_char"] : item["window_end_char"]]
        ]
        assert header_maps
        assert all(item["kind"] == "context_copy" for item in header_maps)
        assert all(item["eligible_for_evidence"] is False for item in header_maps)
        assert (
            "Clinical features"
            not in child["text"][
                child["primary_claim_blocks"][0]["window_start_char"] : child[
                    "primary_claim_blocks"
                ][0]["window_end_char"]
            ]
        )


def test_broad_logic_closure_is_quarantined_not_sentence_split(
    tmp_path: Path,
) -> None:
    closure = "At least two of the following are required. Fever. Rash."
    _, parent, graph, parents = _fixture(tmp_path, evidence_texts=[closure])
    block = parent["primary_claim_blocks"][1]
    block["block_type"] = "criteria_list"
    block["structural_role"] = "criteria_closure"
    block["logic_cues"] = ["enumeration", "k_of_n", "threshold", "lead_in"]
    _write_jsonl(parents, [parent])
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="resplit_evidence_unit",
        status_only=True,
    )
    assert _read_jsonl(output / "claim_windows.resplit.internal.jsonl") == []
    quarantine = _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl")
    assert quarantine[0]["reason"] == "indivisible_logic_closure"
    assert quarantine[0]["text"] == closure


def test_new_mutually_exclusive_capacity_statuses_map_to_internal_reasons(
    tmp_path: Path,
) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    for index, status in enumerate(
        ("resplit_assertion_capacity", "resplit_output_capacity"), start=1
    ):
        output, result = _run(
            tmp_path,
            parent,
            graph,
            parents,
            reason=status,
            name=f"status_{index}",
            status_only=True,
        )
        assert result["children"] == 2
        children = _read_jsonl(output / "claim_windows.resplit.internal.jsonl")
        expected = (
            "too_many_assertions"
            if status == "resplit_assertion_capacity"
            else "output_budget_insufficient"
        )
        assert all(child["resplit_reasons"] == [expected] for child in children)


def test_single_broad_block_is_quarantined_instead_of_repeated(tmp_path: Path) -> None:
    _, parent, graph, parents = _fixture(
        tmp_path,
        evidence_texts=["One indivisible diagnostic assertion."],
    )
    output, result = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="evidence_unit_too_broad",
    )
    assert _read_jsonl(output / "claim_windows.resplit.internal.jsonl") == []
    quarantine = _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl")
    assert result["quarantines"] == 1
    assert quarantine[0]["reason"] == "no_progress_single_evidence_unit"
    assert quarantine[0]["text"] == "One indivisible diagnostic assertion."


def test_oversize_indivisible_block_is_never_truncated(tmp_path: Path) -> None:
    huge = "Diagnostic criterion " + ("unbrokenword " * 500).rstrip()
    _, parent, graph, parents = _fixture(
        tmp_path, evidence_texts=[huge, "Small finding."]
    )
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="too_many_assertions",
        max_source_tokens=100,
    )
    quarantine = _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl")
    assert any(row["text"] == huge for row in quarantine)
    assert any(
        row["reason"] == "indivisible_evidence_unit_exceeds_source_cap"
        for row in quarantine
    )
    public_quarantine = (
        output / "claim_window_resplit_quarantine.public.jsonl"
    ).read_text()
    assert huge not in public_quarantine


def test_recursive_child_at_max_depth_is_quarantined(tmp_path: Path) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    parent["resplit_depth"] = 3
    parent["root_window_id"] = "original_root"
    parent["resplit_lineage"] = ["original_root", "child_1", "child_2"]
    _write_jsonl(parents, [parent])
    output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="output_budget_insufficient",
        max_depth=3,
    )
    assert _read_jsonl(output / "claim_windows.resplit.internal.jsonl") == []
    quarantine = _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl")
    assert quarantine[0]["reason"] == "max_resplit_depth_reached"
    assert quarantine[0]["root_window_id"] == "original_root"


def test_resplit_children_can_be_recursively_resplit_with_stable_lineage(
    tmp_path: Path,
) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    first_output, _ = _run(
        tmp_path,
        parent,
        graph,
        parents,
        reason="too_many_assertions",
        name="generation_one",
    )
    first_child = _read_jsonl(first_output / "claim_windows.resplit.internal.jsonl")[0]
    child_parent_path = tmp_path / "child_parent.jsonl"
    _write_jsonl(child_parent_path, [first_child])
    second_output, _ = _run(
        tmp_path,
        first_child,
        graph,
        child_parent_path,
        reason="output_budget_insufficient",
        name="generation_two",
    )
    grandchildren = _read_jsonl(second_output / "claim_windows.resplit.internal.jsonl")
    assert len(grandchildren) == 2
    assert all(row["resplit_depth"] == 2 for row in grandchildren)
    assert all(row["root_window_id"] == parent["window_id"] for row in grandchildren)
    assert all(
        row["resplit_lineage"] == [parent["window_id"], first_child["window_id"]]
        for row in grandchildren
    )


def test_unsupported_reason_is_explicitly_quarantined(tmp_path: Path) -> None:
    _, parent, graph, parents = _fixture(tmp_path)
    output, _ = _run(tmp_path, parent, graph, parents, reason="scope_ambiguous")
    quarantine = _read_jsonl(output / "claim_window_resplit_quarantine.internal.jsonl")
    assert quarantine[0]["reason"] == "unsupported_coverage_reason"
