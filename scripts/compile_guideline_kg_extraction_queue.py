#!/usr/bin/env python3
"""Compile the lossless, bounded production ClaimWindow extraction queue.

This is a *pre-extraction* compiler, not a tokenizer and not a fixed-overlap
chunker.  It consumes source-native ClaimWindows that have already been
reassembled across legacy chunks and makes one deterministic decision:

* retain an eligible parent when it exposes at most ``--max-evidence-blocks``;
* otherwise replace it with children formed only at primary-claim-block
  boundaries;
* split an individually over-limit prose/headed-prose block only at complete
  sentence boundaries; and
* quarantine, without shortening, an over-limit logical closure or atomic
  non-prose unit.

Every evidence-eligible parent block is transactionally audited.  Its exact
parent-coordinate interval must be covered once by emitted evidence/context
pieces or by an explicit quarantine.  Context copies may repeat across
children, but can never become citable.  Every emitted source character keeps
an exact half-open mapping to the immutable Passage layer.

The internal queue and quarantine contain source text.  Their public pointer
counterparts contain hashes, identifiers, offsets, and counts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_guideline_kg_claim_windows import (  # noqa: E402
    canonical_json,
    estimate_tokens,
    file_sha256,
    stable_hash,
)
from extract_guideline_kg_residuals import (  # noqa: E402
    ClaimWindowError,
    claim_window_evidence_inventory,
    normalize_claim_window,
    sentence_spans,
)
from resplit_guideline_kg_claim_windows import (  # noqa: E402
    RESPLITTER_VERSION,
    ResplitError,
    ResplitRequest,
    _is_indivisible_logic_closure,
    _is_prose_block,
    _load_passage_index,
    _parent_blocks,
    _public_quarantine_pointer,
    _quarantine,
    _render_child,
)

QUEUE_COMPILER_VERSION = "guideline-kg-production-extraction-queue-v1"
DEFAULT_WINDOWS = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/claim_windows"
    / "claim_windows.internal.jsonl"
)
DEFAULT_GRAPH = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/build/graph.internal.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/production_queue"
)
DEFAULT_MAX_EVIDENCE_BLOCKS = 12
DEFAULT_MAX_SOURCE_TOKENS = 6_000
DEFAULT_MAX_DEPTH = 3
EXTRACTION_LANES = ("direct_extract", "upstream_only")


class QueueCompileError(ValueError):
    """Raised when a queue invariant cannot be proved."""


def _window_id(row: Mapping[str, Any]) -> str:
    value = str(row.get("window_id") or row.get("id") or "").strip()
    if not value:
        raise QueueCompileError("ClaimWindow requires window_id or id")
    return value


def _write_jsonl_row(handle: TextIO, row: Mapping[str, Any]) -> None:
    handle.write(canonical_json(row) + "\n")


def _percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction)))
    return int(ordered[index])


def _scan_parent_stream(path: Path) -> tuple[Counter[str], set[str]]:
    statuses: Counter[str] = Counter()
    passage_ids: set[str] = set()
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise QueueCompileError(f"{path}:{line_number}: expected object")
            row_id = _window_id(row)
            if row_id in seen_ids:
                raise QueueCompileError(f"duplicate parent window id: {row_id}")
            seen_ids.add(row_id)
            status = str(row.get("status") or "missing")
            statuses[status] += 1
            if status != "eligible":
                continue
            for item in row.get("offset_map") or row.get("source_map") or []:
                if isinstance(item, Mapping) and item.get("passage_id"):
                    passage_ids.add(str(item["passage_id"]))
    return statuses, passage_ids


def _production_block_id(
    parent: Mapping[str, Any],
    original: Mapping[str, Any],
    start: int,
    end: int,
    role: str,
) -> str:
    text = str(parent["text"])[start:end]
    return (
        "gkg_claim_block_queue_"
        + stable_hash(
            QUEUE_COMPILER_VERSION,
            _window_id(parent),
            str(original["block_id"]),
            str(start),
            str(end),
            role,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )[:20]
    )


def _exact_sentence_subdivision(
    parent: Mapping[str, Any], block: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Partition one prose block exactly, with a headed prefix as context.

    Sentence detection trims surrounding whitespace.  To avoid losing those
    bytes, each evidence piece extends through the whitespace before the next
    sentence; the first and last pieces also retain the body's outer
    whitespace.  Thus the returned intervals partition the original block.
    """

    parent_text = str(parent["text"])
    start = int(block["window_start_char"])
    end = int(block["window_end_char"])
    body_start = start
    headed = str(block.get("block_type") or "").casefold() == "headed_prose"
    if headed:
        newline = parent_text.find("\n", start, end)
        if newline >= 0:
            body_start = newline + 1
    raw_spans = sentence_spans(parent_text[body_start:end])
    if not raw_spans:
        return [dict(block)]

    result: list[dict[str, Any]] = []
    if body_start > start:
        heading = dict(block)
        heading.update(
            {
                "block_id": _production_block_id(
                    parent, block, start, body_start, "heading_context"
                ),
                "window_start_char": start,
                "window_end_char": body_start,
                "block_type": "heading",
                "structural_role": "heading_context",
                "logic_cues": [],
                "contains_scope_cue": False,
                "diagnostic_gate_reasons": [],
                "eligible_for_evidence": False,
                "production_origin_block_id": str(block["block_id"]),
                "production_subdivision": "headed_prose_header_context",
            }
        )
        result.append(heading)

    absolute_sentence_starts = [body_start + int(item[0]) for item in raw_spans]
    for index, sentence_start in enumerate(absolute_sentence_starts):
        piece_start = body_start if index == 0 else sentence_start
        piece_end = (
            absolute_sentence_starts[index + 1]
            if index + 1 < len(absolute_sentence_starts)
            else end
        )
        if piece_start >= piece_end:
            raise QueueCompileError("sentence subdivision produced an empty piece")
        piece = dict(block)
        piece.update(
            {
                "block_id": _production_block_id(
                    parent, block, piece_start, piece_end, f"sentence_{index + 1}"
                ),
                "window_start_char": piece_start,
                "window_end_char": piece_end,
                "block_type": "prose_sentence_resplit",
                "structural_role": "subdivided_prose_claim",
                "eligible_for_evidence": True,
                "production_origin_block_id": str(block["block_id"]),
                "production_subdivision": "complete_sentence_boundary",
                "production_subclaim_index": index + 1,
                "production_subclaim_count": len(absolute_sentence_starts),
            }
        )
        result.append(piece)
    return result


def _prepare_blocks(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    *,
    max_source_tokens: int,
) -> tuple[list[dict[str, Any]], dict[int, str], Counter[str]]:
    """Return exact derived blocks and explicit per-derived quarantines."""

    expanded: list[dict[str, Any]] = []
    metrics: Counter[str] = Counter()
    for raw in blocks:
        block = dict(raw)
        if block.get("eligible_for_evidence") is not True:
            expanded.append(block)
            continue
        block_text = str(parent["text"])[
            int(block["window_start_char"]) : int(block["window_end_char"])
        ]
        if estimate_tokens(block_text) <= max_source_tokens:
            expanded.append(block)
            continue
        metrics["oversize_original_citable_blocks"] += 1
        if _is_indivisible_logic_closure(block):
            block["production_queue_quarantine_reason"] = (
                "indivisible_logic_closure_exceeds_source_cap"
            )
            expanded.append(block)
            metrics["oversize_logic_closures"] += 1
            continue
        if not _is_prose_block(block):
            block["production_queue_quarantine_reason"] = (
                "indivisible_nonprose_evidence_unit_exceeds_source_cap"
            )
            expanded.append(block)
            metrics["oversize_nonprose_units"] += 1
            continue
        pieces = _exact_sentence_subdivision(parent, block)
        if len([item for item in pieces if item.get("eligible_for_evidence")]) <= 1:
            block["production_queue_quarantine_reason"] = (
                "no_complete_sentence_boundary_within_source_cap"
            )
            expanded.append(block)
            metrics["unsplittable_prose_units"] += 1
            continue
        expanded.extend(pieces)
        metrics["sentence_subdivided_original_blocks"] += 1

    expanded.sort(
        key=lambda item: (
            int(item["window_start_char"]),
            int(item["window_end_char"]),
            str(item["block_id"]),
        )
    )
    quarantined: dict[int, str] = {}
    for index, block in enumerate(expanded):
        if block.get("eligible_for_evidence") is not True:
            continue
        reason = str(block.get("production_queue_quarantine_reason") or "")
        if not reason:
            block_text = str(parent["text"])[
                int(block["window_start_char"]) : int(block["window_end_char"])
            ]
            if estimate_tokens(block_text) > max_source_tokens:
                reason = "complete_sentence_exceeds_source_cap"
        if reason:
            quarantined[index] = reason
    return expanded, quarantined, metrics


def _partition_available_blocks(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    *,
    quarantined: Mapping[int, str],
    max_evidence_blocks: int,
    max_source_tokens: int,
) -> list[list[int]]:
    def semantic_group_tokens(indexes: Sequence[int]) -> int:
        """Reserve the nearest governing heading in every child budget."""

        if not indexes:
            return 0
        parts = [
            str(parent["text"])[
                int(blocks[index]["window_start_char"]) : int(
                    blocks[index]["window_end_char"]
                )
            ]
            for index in indexes
        ]
        first = indexes[0]
        for index in range(first - 1, -1, -1):
            block = blocks[index]
            if (
                str(block.get("block_type") or "") == "heading"
                or str(block.get("structural_role") or "") == "heading_context"
            ):
                heading = str(parent["text"])[
                    int(block["window_start_char"]) : int(block["window_end_char"])
                ]
                parts.insert(0, heading)
                break
        return estimate_tokens("\n\n".join(parts))

    eligible = [
        index
        for index, block in enumerate(blocks)
        if block.get("eligible_for_evidence") is True and index not in quarantined
    ]
    groups: list[list[int]] = []
    current: list[int] = []
    for index in eligible:
        proposed = [*current, index]
        if current and (
            len(proposed) > max_evidence_blocks
            or semantic_group_tokens(proposed) > max_source_tokens
        ):
            groups.append(current)
            current = [index]
        else:
            current = proposed
    if current:
        groups.append(current)
    for group in groups:
        if len(group) > max_evidence_blocks:
            raise QueueCompileError("partition exceeded evidence-block cap")
        if semantic_group_tokens(group) > max_source_tokens:
            raise QueueCompileError(
                "evidence plus governing heading exceeds source-token cap"
            )
    return groups


def _block_source_ids(
    parent: Mapping[str, Any], start: int, end: int
) -> set[str]:
    return {
        str(item["passage_id"])
        for item in parent.get("offset_map") or parent.get("source_map") or []
        if isinstance(item, Mapping)
        and max(start, int(item["window_start_char"]))
        < min(end, int(item["window_end_char"]))
    }


def _queue_window_source_ids(window: Mapping[str, Any]) -> set[str]:
    return {
        str(item["passage_id"])
        for item in window.get("offset_map") or []
        if isinstance(item, Mapping) and item.get("passage_id")
    }


def _enrich_retained_parent(parent: Mapping[str, Any]) -> dict[str, Any]:
    row = dict(parent)
    parent_id = _window_id(parent)
    row.update(
        {
            "queue_compiler_version": QUEUE_COMPILER_VERSION,
            "queue_action": "retained_parent",
            "root_window_id": str(parent.get("root_window_id") or parent_id),
            "resplit_depth": int(parent.get("resplit_depth") or 0),
            "resplit_lineage": list(parent.get("resplit_lineage") or []),
            "production_original_window_id": parent_id,
        }
    )
    row["overlap_policy"] = {
        **dict(parent.get("overlap_policy") or {}),
        "fixed_token_overlap": False,
        "production_claim_block_partition": True,
        "context_citable": False,
    }
    return row


def _enrich_child(child: Mapping[str, Any], parent_id: str) -> dict[str, Any]:
    row = dict(child)
    row.update(
        {
            "queue_compiler_version": QUEUE_COMPILER_VERSION,
            "queue_action": "pre_split_child",
            "production_original_window_id": parent_id,
        }
    )
    row["overlap_policy"] = {
        **dict(row.get("overlap_policy") or {}),
        "fixed_token_overlap": False,
        "production_claim_block_partition": True,
        "context_citable": False,
    }
    return row


def _block_extraction_lane(block: Mapping[str, Any]) -> str:
    """Classify a citable block from its local-vs-upstream gate evidence.

    ``text:``, ``heading:``, and ``section:`` are block-local signals emitted
    by the claim-window builder.  ``upstream:`` signals are inherited from a
    legacy chunk or reconstructed entry.  Unknown non-upstream reasons are
    conservatively treated as direct; an empty reason set is rejected so it
    cannot disappear into an implicit third lane.
    """

    reasons = [
        str(reason).strip()
        for reason in block.get("diagnostic_gate_reasons") or []
        if str(reason).strip()
    ]
    if not reasons:
        raise QueueCompileError(
            f"citable block {block.get('block_id')!r} has no diagnostic reason"
        )
    return (
        "upstream_only"
        if all(reason.startswith("upstream:") for reason in reasons)
        else "direct_extract"
    )


def _annotate_extraction_lanes(row: Mapping[str, Any]) -> dict[str, Any]:
    """Add source-local lane metadata without changing text or offsets."""

    value = dict(row)
    blocks: list[dict[str, Any]] = []
    lane_ids: dict[str, list[str]] = {lane: [] for lane in EXTRACTION_LANES}
    for raw in row.get("primary_claim_blocks") or []:
        block = dict(raw)
        if block.get("eligible_for_evidence") is True:
            lane = _block_extraction_lane(block)
            block["production_extraction_lane"] = lane
            lane_ids[lane].append(str(block["block_id"]))
        blocks.append(block)
    value["primary_claim_blocks"] = blocks
    value["production_extraction_lanes"] = {
        lane: ids for lane, ids in lane_ids.items() if ids
    }
    value["production_lane_policy"] = {
        "direct_extract": "any_non_upstream_block_local_diagnostic_reason",
        "upstream_only": "all_diagnostic_reasons_have_upstream_prefix",
        "block_assignment_mutually_exclusive": True,
        "physical_claim_block_split": False,
    }
    return value


def _lane_pointer(
    row: Mapping[str, Any], lane: str
) -> tuple[dict[str, Any], dict[str, int]] | None:
    selected = [
        block
        for block in row.get("primary_claim_blocks") or []
        if block.get("eligible_for_evidence") is True
        and block.get("production_extraction_lane") == lane
    ]
    if not selected:
        return None
    text = str(row["text"])
    citable_tokens = sum(
        estimate_tokens(
            text[int(block["window_start_char"]) : int(block["window_end_char"])]
        )
        for block in selected
    )
    # Estimate a filtered optional call using every non-citable mapped context
    # interval plus only this lane's citable units.  No source text is emitted.
    intervals = {
        (int(block["window_start_char"]), int(block["window_end_char"]))
        for block in selected
    }
    intervals.update(
        (int(item["window_start_char"]), int(item["window_end_char"]))
        for item in row.get("offset_map") or []
        if item.get("eligible_for_evidence") is False
    )
    filtered_text = "\n\n".join(text[start:end] for start, end in sorted(intervals))
    filtered_tokens = estimate_tokens(filtered_text)
    pointer = {
        "record_type": "ClaimWindowExtractionLanePointer",
        "queue_compiler_version": QUEUE_COMPILER_VERSION,
        "lane": lane,
        "queue_window_id": row["window_id"],
        "production_original_window_id": row["production_original_window_id"],
        "parent_window_id": row.get("parent_window_id"),
        "root_window_id": row.get("root_window_id"),
        "resplit_depth": row.get("resplit_depth", 0),
        "text_sha256": row["text_sha256"],
        "claim_block_ids": [str(block["block_id"]) for block in selected],
        "claim_block_count": len(selected),
        "citable_token_estimate": citable_tokens,
        "filtered_call_source_token_estimate": filtered_tokens,
        "full_parent_call_source_token_estimate": int(row["token_estimate"]),
        "contains_other_lane_blocks": len(selected)
        < int(row["eligible_primary_block_count"]),
        "physical_claim_block_split": False,
        "closure_and_offsets_unchanged": True,
        "status": "optional_lane_pointer",
    }
    return pointer, {
        "blocks": len(selected),
        "citable_tokens": citable_tokens,
        "filtered_source_tokens": filtered_tokens,
        "full_parent_source_tokens": int(row["token_estimate"]),
    }


def _public_queue_pointer(row: Mapping[str, Any]) -> dict[str, Any]:
    source_refs = sorted(
        {
            (
                str(item["passage_id"]),
                int(item.get("passage_start_char", item.get("source_start_char"))),
                int(item.get("passage_end_char", item.get("source_end_char"))),
            )
            for item in row.get("offset_map") or []
            if isinstance(item, Mapping) and item.get("passage_id")
        }
    )
    return {
        "record_type": "ClaimWindowPointer",
        "window_id": row["window_id"],
        "queue_compiler_version": row["queue_compiler_version"],
        "queue_action": row["queue_action"],
        "rechunker_version": row["rechunker_version"],
        "parent_window_id": row.get("parent_window_id"),
        "root_window_id": row.get("root_window_id"),
        "resplit_depth": row.get("resplit_depth", 0),
        "resplit_lineage": list(row.get("resplit_lineage") or []),
        "production_original_window_id": row["production_original_window_id"],
        "text_sha256": row["text_sha256"],
        "token_estimate": int(row["token_estimate"]),
        "source_family": row.get("source_family"),
        "source": row.get("source"),
        "source_id": row.get("source_id"),
        "document_version_id": row.get("document_version_id"),
        "source_ordinal_start": row.get("source_ordinal_start"),
        "source_ordinal_end": row.get("source_ordinal_end"),
        "claim_block_ids": list(row.get("claim_block_ids") or []),
        "claim_block_types": list(row.get("claim_block_types") or []),
        "production_extraction_lanes": row.get("production_extraction_lanes"),
        "eligible_primary_block_count": int(
            row.get("eligible_primary_block_count") or 0
        ),
        "source_refs": [
            {
                "passage_id": passage_id,
                "passage_start_char": start,
                "passage_end_char": end,
            }
            for passage_id, start, end in source_refs
        ],
        "coverage_status": row.get("coverage_status"),
        "status": row.get("status"),
        "overlap_policy": row.get("overlap_policy"),
    }


def _coverage_partition(
    original: Mapping[str, Any], pieces: Sequence[Mapping[str, Any]]
) -> None:
    start = int(original["window_start_char"])
    end = int(original["window_end_char"])
    ranges = sorted(
        (
            int(piece["window_start_char"]),
            int(piece["window_end_char"]),
            str(piece["coverage_kind"]),
        )
        for piece in pieces
    )
    if not ranges:
        raise QueueCompileError(
            f"citable block {original['block_id']!r} has no terminal coverage"
        )
    cursor = start
    for left, right, _kind in ranges:
        if left != cursor or right <= left or right > end:
            raise QueueCompileError(
                f"citable block {original['block_id']!r} has gap/overlap: {ranges}"
            )
        cursor = right
    if cursor != end:
        raise QueueCompileError(
            f"citable block {original['block_id']!r} is not fully covered"
        )


def _parent_coverage_rows(
    parent: Mapping[str, Any],
    original_blocks: Sequence[Mapping[str, Any]],
    expanded_blocks: Sequence[Mapping[str, Any]],
    *,
    emitted_indexes: set[int],
    quarantined: Mapping[int, str],
) -> list[dict[str, Any]]:
    by_origin: dict[str, list[dict[str, Any]]] = {
        str(block["block_id"]): []
        for block in original_blocks
        if block.get("eligible_for_evidence") is True
    }
    for index, block in enumerate(expanded_blocks):
        origin = str(block.get("production_origin_block_id") or block["block_id"])
        if origin not in by_origin:
            continue
        if index in emitted_indexes:
            kind = "emitted_evidence"
        elif index in quarantined:
            kind = "explicit_quarantine"
        elif block.get("eligible_for_evidence") is not True:
            kind = "noncitable_heading_context"
        else:
            raise QueueCompileError(
                f"derived citable block {block['block_id']!r} has no terminal outcome"
            )
        by_origin[origin].append(
            {
                "derived_block_id": str(block["block_id"]),
                "window_start_char": int(block["window_start_char"]),
                "window_end_char": int(block["window_end_char"]),
                "coverage_kind": kind,
                "quarantine_reason": quarantined.get(index),
            }
        )

    rows: list[dict[str, Any]] = []
    for original in original_blocks:
        if original.get("eligible_for_evidence") is not True:
            continue
        original_id = str(original["block_id"])
        pieces = by_origin[original_id]
        _coverage_partition(original, pieces)
        kinds = sorted({str(piece["coverage_kind"]) for piece in pieces})
        outcome = (
            "fully_emitted"
            if kinds == ["emitted_evidence"]
            else "fully_quarantined"
            if kinds == ["explicit_quarantine"]
            else "transformed_with_context"
            if "explicit_quarantine" not in kinds
            else "partially_quarantined"
        )
        rows.append(
            {
                "record_type": "ClaimBlockQueueCoverage",
                "queue_compiler_version": QUEUE_COMPILER_VERSION,
                "parent_window_id": _window_id(parent),
                "original_block_id": original_id,
                "original_window_start_char": int(original["window_start_char"]),
                "original_window_end_char": int(original["window_end_char"]),
                "original_text_sha256": hashlib.sha256(
                    str(parent["text"])[
                        int(original["window_start_char"]) : int(
                            original["window_end_char"]
                        )
                    ].encode("utf-8")
                ).hexdigest(),
                "terminal_outcome": outcome,
                "terminal_pieces": pieces,
            }
        )
    return rows


def _whole_parent_quarantine(
    parent: Mapping[str, Any], reason: str, detail: str
) -> dict[str, Any]:
    request = ResplitRequest(
        parent_window_id=_window_id(parent),
        reasons=("production_queue_compile",),
        window_sha256_values=(),
        rechunker_versions=(),
        ledger_rows=0,
    )
    row = _quarantine(parent, request, reason, detail=detail)
    row.update(
        {
            "queue_compiler_version": QUEUE_COMPILER_VERSION,
            "original_citable_block_ids": [
                str(block.get("block_id") or "")
                for block in parent.get("primary_claim_blocks") or []
                if isinstance(block, Mapping)
                and block.get("eligible_for_evidence") is True
            ],
        }
    )
    return row


def _block_quarantine(
    parent: Mapping[str, Any], block: Mapping[str, Any], reason: str
) -> dict[str, Any]:
    request = ResplitRequest(
        parent_window_id=_window_id(parent),
        reasons=("production_queue_compile",),
        window_sha256_values=(),
        rechunker_versions=(),
        ledger_rows=0,
    )
    row = _quarantine(parent, request, reason, block=block)
    row.update(
        {
            "queue_compiler_version": QUEUE_COMPILER_VERSION,
            "original_citable_block_id": str(
                block.get("production_origin_block_id") or block.get("block_id") or ""
            ),
            "derived_block_id": str(block.get("block_id") or ""),
        }
    )
    return row


def _atomic_open(path: Path) -> tuple[Path, TextIO]:
    temporary = path.with_name(path.name + ".tmp")
    return temporary, temporary.open("w", encoding="utf-8", newline="\n")


def compile_production_extraction_queue(
    *,
    parent_windows_path: Path,
    graph_path: Path,
    output_dir: Path,
    max_evidence_blocks: int = DEFAULT_MAX_EVIDENCE_BLOCKS,
    max_source_tokens: int = DEFAULT_MAX_SOURCE_TOKENS,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    if max_evidence_blocks < 1:
        raise ValueError("max_evidence_blocks must be positive")
    if max_source_tokens < 1:
        raise ValueError("max_source_tokens must be positive")
    if max_depth < 1:
        raise ValueError("max_depth must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)

    input_statuses, wanted_passages = _scan_parent_stream(parent_windows_path)
    passage_index = _load_passage_index(graph_path, wanted_passages)
    missing_passages = sorted(wanted_passages - set(passage_index))
    if missing_passages:
        raise QueueCompileError(
            f"graph lacks {len(missing_passages)} referenced Passages; "
            f"first={missing_passages[0]!r}"
        )

    paths = {
        "internal": output_dir / "claim_windows.production.internal.jsonl",
        "public": output_dir / "claim_window_queue.production.public.jsonl",
        "quarantine_internal": output_dir
        / "claim_window_queue_quarantine.internal.jsonl",
        "quarantine_public": output_dir
        / "claim_window_queue_quarantine.public.jsonl",
        "coverage": output_dir / "claim_block_coverage_audit.public.jsonl",
        "lane_direct_extract": output_dir
        / "claim_window_lane.direct_extract.public.jsonl",
        "lane_upstream_only": output_dir
        / "claim_window_lane.upstream_only.public.jsonl",
    }
    temporary_handles: dict[str, tuple[Path, TextIO]] = {
        key: _atomic_open(path) for key, path in paths.items()
    }
    counters: Counter[str] = Counter()
    preparation_metrics: Counter[str] = Counter()
    source_tokens_before = 0
    citable_tokens_before = 0
    source_tokens_after = 0
    citable_tokens_after = 0
    output_tokens: list[int] = []
    output_evidence_counts: list[int] = []
    original_citable_blocks = 0
    output_citable_blocks = 0
    coverage_rows = 0
    quarantines = 0
    input_all_primary_blocks_crossing_passages = 0
    input_cross_chunk_blocks = 0
    output_cross_chunk_blocks = 0
    input_multi_chunk_windows = 0
    output_multi_chunk_windows = 0
    old_passage_refs_before = 0
    old_passage_refs_after = 0
    lane_metrics: dict[str, Counter[str]] = {
        lane: Counter() for lane in EXTRACTION_LANES
    }
    mixed_lane_calls = 0

    try:
        with parent_windows_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                parent = json.loads(line)
                if not isinstance(parent, dict):
                    raise QueueCompileError(
                        f"{parent_windows_path}:{line_number}: expected object"
                    )
                if str(parent.get("status") or "") != "eligible":
                    counters["ineligible_parents_excluded"] += 1
                    continue
                parent_id = _window_id(parent)
                counters["eligible_parents"] += 1
                source_tokens_before += int(
                    parent.get("token_estimate") or estimate_tokens(str(parent["text"]))
                )
                parent_source_ids = _queue_window_source_ids(parent)
                old_passage_refs_before += len(parent_source_ids)
                if len(parent_source_ids) > 1:
                    input_multi_chunk_windows += 1

                try:
                    normalized_parent = normalize_claim_window(parent, passage_index)
                    original_blocks = _parent_blocks(parent)
                    evidence_inventory, mode = claim_window_evidence_inventory(
                        normalized_parent,
                        max_units=1_000_000,
                        max_sentence_subspans=1_000_000,
                    )
                    if mode != "primary_claim_block":
                        raise QueueCompileError("production parent used legacy inventory")
                    original_eligible = [
                        block
                        for block in original_blocks
                        if block.get("eligible_for_evidence") is True
                    ]
                    if not original_eligible:
                        raise QueueCompileError("eligible parent has no citable block")
                except (
                    ClaimWindowError,
                    ResplitError,
                    QueueCompileError,
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:
                    row = _whole_parent_quarantine(
                        parent,
                        "invalid_parent_claim_window",
                        f"{type(exc).__name__}:{exc}",
                    )
                    _write_jsonl_row(
                        temporary_handles["quarantine_internal"][1], row
                    )
                    _write_jsonl_row(
                        temporary_handles["quarantine_public"][1],
                        _public_quarantine_pointer(row),
                    )
                    quarantines += 1
                    counters["invalid_parents_quarantined"] += 1
                    # Malformed parents cannot satisfy an exact interval proof;
                    # the whole immutable parent is nevertheless explicit.
                    continue

                original_citable_blocks += len(original_eligible)
                for block in original_blocks:
                    if (
                        len(
                            _block_source_ids(
                                parent,
                                int(block["window_start_char"]),
                                int(block["window_end_char"]),
                            )
                        )
                        > 1
                    ):
                        input_all_primary_blocks_crossing_passages += 1
                for block in original_eligible:
                    value = str(parent["text"])[
                        int(block["window_start_char"]) : int(
                            block["window_end_char"]
                        )
                    ]
                    citable_tokens_before += estimate_tokens(value)
                    if (
                        len(
                            _block_source_ids(
                                parent,
                                int(block["window_start_char"]),
                                int(block["window_end_char"]),
                            )
                        )
                        > 1
                    ):
                        input_cross_chunk_blocks += 1

                expanded, quarantined_indexes, prep = _prepare_blocks(
                    parent,
                    original_blocks,
                    max_source_tokens=max_source_tokens,
                )
                preparation_metrics.update(prep)
                available = [
                    index
                    for index, block in enumerate(expanded)
                    if block.get("eligible_for_evidence") is True
                    and index not in quarantined_indexes
                ]
                requires_split = (
                    len(original_eligible) > max_evidence_blocks
                    or bool(quarantined_indexes)
                    or any(
                        block.get("production_origin_block_id")
                        for block in expanded
                    )
                    or int(
                        parent.get("token_estimate")
                        or estimate_tokens(str(parent["text"]))
                    )
                    > max_source_tokens
                )
                groups = (
                    _partition_available_blocks(
                        parent,
                        expanded,
                        quarantined=quarantined_indexes,
                        max_evidence_blocks=max_evidence_blocks,
                        max_source_tokens=max_source_tokens,
                    )
                    if requires_split
                    else [available]
                )
                emitted_indexes = {index for group in groups for index in group}
                coverage = _parent_coverage_rows(
                    parent,
                    original_blocks,
                    expanded,
                    emitted_indexes=emitted_indexes,
                    quarantined=quarantined_indexes,
                )
                if len(coverage) != len(original_eligible):
                    raise QueueCompileError("parent coverage row count mismatch")

                parent_queue_rows: list[dict[str, Any]] = []
                if not requires_split:
                    retained = _annotate_extraction_lanes(
                        _enrich_retained_parent(parent)
                    )
                    if len(evidence_inventory) > max_evidence_blocks:
                        raise QueueCompileError("retained parent exceeds evidence cap")
                    parent_queue_rows.append(retained)
                    counters["retained_parents"] += 1
                else:
                    previous_group_last: int | None = None
                    for child_position, group in enumerate(groups, start=1):
                        child = _render_child(
                            parent,
                            expanded,
                            group,
                            reasons=("production_evidence_unit_cap",),
                            child_index=child_position,
                            child_count=len(groups),
                            previous_group_last=previous_group_last,
                            max_source_tokens=max_source_tokens,
                        )
                        if any(
                            str(item.get("context_reason") or "")
                            == "active_heading"
                            for item in child.get("omitted_parent_context_ranges") or []
                        ):
                            raise QueueCompileError(
                                "governing heading would be omitted from child"
                            )
                        if int(child.get("resplit_depth") or 0) > max_depth:
                            raise QueueCompileError("child exceeds max resplit depth")
                        child = _annotate_extraction_lanes(
                            _enrich_child(child, parent_id)
                        )
                        normalized_child = normalize_claim_window(child, passage_index)
                        evidence, child_mode = claim_window_evidence_inventory(
                            normalized_child,
                            max_units=max_evidence_blocks,
                            max_sentence_subspans=1_000_000,
                        )
                        if child_mode != "primary_claim_block" or len(evidence) != len(
                            group
                        ):
                            raise QueueCompileError(
                                "child inventory differs from partition"
                            )
                        if int(child["token_estimate"]) > max_source_tokens:
                            raise QueueCompileError("child exceeds source-token cap")
                        parent_queue_rows.append(child)
                        previous_group_last = group[-1]
                    counters["parents_pre_split"] += 1
                    counters["pre_split_children"] += len(parent_queue_rows)

                for index, reason in sorted(quarantined_indexes.items()):
                    row = _block_quarantine(parent, expanded[index], reason)
                    _write_jsonl_row(
                        temporary_handles["quarantine_internal"][1], row
                    )
                    _write_jsonl_row(
                        temporary_handles["quarantine_public"][1],
                        _public_quarantine_pointer(row),
                    )
                    quarantines += 1
                    counters[f"quarantine:{reason}"] += 1

                for row in parent_queue_rows:
                    evidence_blocks = [
                        block
                        for block in row.get("primary_claim_blocks") or []
                        if block.get("eligible_for_evidence") is True
                    ]
                    if not (1 <= len(evidence_blocks) <= max_evidence_blocks):
                        raise QueueCompileError("queue row violates evidence-block cap")
                    _write_jsonl_row(temporary_handles["internal"][1], row)
                    _write_jsonl_row(
                        temporary_handles["public"][1], _public_queue_pointer(row)
                    )
                    row_lanes = 0
                    for lane in EXTRACTION_LANES:
                        lane_result = _lane_pointer(row, lane)
                        if lane_result is None:
                            continue
                        pointer, metrics = lane_result
                        _write_jsonl_row(
                            temporary_handles[f"lane_{lane}"][1], pointer
                        )
                        row_lanes += 1
                        lane_metrics[lane]["calls"] += 1
                        lane_metrics[lane]["blocks"] += metrics["blocks"]
                        lane_metrics[lane]["citable_tokens"] += metrics[
                            "citable_tokens"
                        ]
                        lane_metrics[lane]["filtered_source_tokens"] += metrics[
                            "filtered_source_tokens"
                        ]
                        lane_metrics[lane]["full_parent_source_tokens"] += metrics[
                            "full_parent_source_tokens"
                        ]
                        if pointer["contains_other_lane_blocks"]:
                            lane_metrics[lane]["mixed_parent_calls"] += 1
                        else:
                            lane_metrics[lane]["single_lane_parent_calls"] += 1
                    if row_lanes != len(row["production_extraction_lanes"]):
                        raise QueueCompileError("lane pointer count mismatch")
                    if row_lanes == 2:
                        mixed_lane_calls += 1
                    counters["production_calls"] += 1
                    source_tokens_after += int(row["token_estimate"])
                    output_tokens.append(int(row["token_estimate"]))
                    output_evidence_counts.append(len(evidence_blocks))
                    output_citable_blocks += len(evidence_blocks)
                    source_ids = _queue_window_source_ids(row)
                    old_passage_refs_after += len(source_ids)
                    if len(source_ids) > 1:
                        output_multi_chunk_windows += 1
                    for block in evidence_blocks:
                        value = str(row["text"])[
                            int(block["window_start_char"]) : int(
                                block["window_end_char"]
                            )
                        ]
                        citable_tokens_after += estimate_tokens(value)
                        if (
                            len(
                                _block_source_ids(
                                    row,
                                    int(block["window_start_char"]),
                                    int(block["window_end_char"]),
                                )
                            )
                            > 1
                        ):
                            output_cross_chunk_blocks += 1

                for row in coverage:
                    _write_jsonl_row(temporary_handles["coverage"][1], row)
                    coverage_rows += 1

        lane_block_sum = sum(
            lane_metrics[lane]["blocks"] for lane in EXTRACTION_LANES
        )
        lane_token_sum = sum(
            lane_metrics[lane]["citable_tokens"] for lane in EXTRACTION_LANES
        )
        if lane_block_sum != output_citable_blocks:
            raise QueueCompileError(
                "mutually exclusive lane block coverage does not equal queue coverage"
            )
        if lane_token_sum != citable_tokens_after:
            raise QueueCompileError(
                "mutually exclusive lane token accounting does not equal queue accounting"
            )
        for temporary, handle in temporary_handles.values():
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        for key, path in paths.items():
            os.replace(temporary_handles[key][0], path)
    except Exception:
        for temporary, handle in temporary_handles.values():
            if not handle.closed:
                handle.close()
            if temporary.exists():
                temporary.unlink()
        raise

    input_calls = int(counters["eligible_parents"])
    output_calls = int(counters["production_calls"])
    stats: dict[str, Any] = {
        "queue_compiler_version": QUEUE_COMPILER_VERSION,
        "adaptive_renderer_version": RESPLITTER_VERSION,
        "configuration": {
            "max_evidence_blocks": max_evidence_blocks,
            "max_source_tokens": max_source_tokens,
            "max_depth": max_depth,
            "fixed_token_overlap": False,
            "closure_splitting": False,
            "prose_split_boundary": "complete_sentence",
        },
        "input": {
            "parent_windows": sum(input_statuses.values()),
            "status_counts": dict(sorted(input_statuses.items())),
            "eligible_parents": input_calls,
            "passage_references_loaded": len(passage_index),
            "eligible_source_token_estimate": source_tokens_before,
            "eligible_citable_token_estimate": citable_tokens_before,
            "original_citable_blocks": original_citable_blocks,
        },
        "output": {
            "production_calls": output_calls,
            "retained_parents": int(counters["retained_parents"]),
            "pre_split_children": int(counters["pre_split_children"]),
            "parents_pre_split": int(counters["parents_pre_split"]),
            "source_token_estimate": source_tokens_after,
            "citable_token_estimate": citable_tokens_after,
            "citable_blocks": output_citable_blocks,
            "quarantines": quarantines,
            "coverage_audit_rows": coverage_rows,
            "token_distribution": {
                "min": min(output_tokens, default=0),
                "median": _percentile(output_tokens, 0.5),
                "p90": _percentile(output_tokens, 0.9),
                "p95": _percentile(output_tokens, 0.95),
                "max": max(output_tokens, default=0),
                "sum": source_tokens_after,
            },
            "evidence_unit_distribution": {
                "min": min(output_evidence_counts, default=0),
                "median": _percentile(output_evidence_counts, 0.5),
                "p90": _percentile(output_evidence_counts, 0.9),
                "p95": _percentile(output_evidence_counts, 0.95),
                "max": max(output_evidence_counts, default=0),
            },
        },
        "changes": {
            "call_delta": output_calls - input_calls,
            "call_multiplier": (output_calls / input_calls) if input_calls else None,
            "source_token_delta": source_tokens_after - source_tokens_before,
            "source_token_multiplier": (
                source_tokens_after / source_tokens_before
                if source_tokens_before
                else None
            ),
            "citable_token_delta": citable_tokens_after - citable_tokens_before,
            "citable_token_retention_ratio": (
                citable_tokens_after / citable_tokens_before
                if citable_tokens_before
                else None
            ),
            "noncitable_context_token_delta_approx": (
                (source_tokens_after - citable_tokens_after)
                - (source_tokens_before - citable_tokens_before)
            ),
        },
        "legacy_chunk_provenance": {
            "input_windows_spanning_multiple_passages": input_multi_chunk_windows,
            "output_windows_spanning_multiple_passages": output_multi_chunk_windows,
            "input_all_primary_blocks_crossing_passages": (
                input_all_primary_blocks_crossing_passages
            ),
            "input_citable_blocks_crossing_passages": input_cross_chunk_blocks,
            "output_citable_blocks_crossing_passages": output_cross_chunk_blocks,
            "passage_refs_across_input_calls": old_passage_refs_before,
            "passage_refs_across_output_calls": old_passage_refs_after,
            "fixed_token_overlap_added": False,
        },
        "coverage_invariants": {
            "original_citable_blocks": original_citable_blocks,
            "coverage_audit_rows": coverage_rows,
            "all_well_formed_original_blocks_have_one_exact_terminal_partition": (
                coverage_rows == original_citable_blocks
            ),
            "silent_drop_count": 0,
            "duplicate_citable_coverage_count": 0,
        },
        "extraction_lanes": {
            "classification": {
                "direct_extract": (
                    "at_least_one_text_heading_section_or_other_local_reason"
                ),
                "upstream_only": "all_reasons_have_upstream_prefix",
                "block_assignment_mutually_exclusive": True,
                "physical_claim_block_split": False,
                "lane_files_are_source_free_optional_indexes": True,
            },
            "direct_extract": dict(sorted(lane_metrics["direct_extract"].items())),
            "upstream_only": dict(sorted(lane_metrics["upstream_only"].items())),
            "mixed_lane_parent_calls": mixed_lane_calls,
            "lane_block_sum": sum(
                lane_metrics[lane]["blocks"] for lane in EXTRACTION_LANES
            ),
            "lane_citable_token_sum": sum(
                lane_metrics[lane]["citable_tokens"] for lane in EXTRACTION_LANES
            ),
        },
        "preparation_metrics": dict(sorted(preparation_metrics.items())),
        "counters": dict(sorted(counters.items())),
    }
    stats_path = output_dir / "stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "guideline-diagnostic-kg-v0.1",
        "queue_compiler_version": QUEUE_COMPILER_VERSION,
        "source_parent_windows": str(parent_windows_path),
        "source_parent_windows_sha256": file_sha256(parent_windows_path),
        "source_graph": str(graph_path),
        "source_graph_sha256": file_sha256(graph_path),
        "outputs": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in (*paths.values(), stats_path)
        },
        "contains_source_text": {
            paths["internal"].name: True,
            paths["public"].name: False,
            paths["quarantine_internal"].name: True,
            paths["quarantine_public"].name: False,
            paths["coverage"].name: False,
            paths["lane_direct_extract"].name: False,
            paths["lane_upstream_only"].name: False,
            stats_path.name: False,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**stats, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-windows", type=Path, default=DEFAULT_WINDOWS)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--max-evidence-blocks",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_BLOCKS,
    )
    parser.add_argument(
        "--max-source-tokens", type=int, default=DEFAULT_MAX_SOURCE_TOKENS
    )
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    args = parser.parse_args()
    result = compile_production_extraction_queue(
        parent_windows_path=args.parent_windows,
        graph_path=args.graph,
        output_dir=args.output_dir,
        max_evidence_blocks=args.max_evidence_blocks,
        max_source_tokens=args.max_source_tokens,
        max_depth=args.max_depth,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
