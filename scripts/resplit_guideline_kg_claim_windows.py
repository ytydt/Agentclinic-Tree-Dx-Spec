#!/usr/bin/env python3
"""Losslessly resplit claim windows rejected for LLM coverage capacity.

The extraction runner writes a source-free ``needs_resplit.jsonl`` ledger when
the model cannot exhaustively represent a claim window.  This utility joins
that ledger back to the private ClaimWindow stream and emits smaller windows.

The only legal split boundaries are boundaries between primary claim blocks.
An evidence block is never shortened, sentence-truncated, or divided.  Every
mapped character in a child is projected to the same immutable Passage range
as its parent.  Repeated headings and other semantic context are explicitly
marked ``context_copy`` and are never evidence eligible.

Children are ordinary ClaimWindow records, so they can be supplied directly
to ``extract_guideline_kg_residuals.py --claim-windows`` without changing the
base graph.  A single indivisible evidence block, a maximum-depth request, or
any split that cannot reduce the parent is quarantined rather than silently
truncated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

from build_guideline_kg_claim_windows import (
    canonical_json,
    estimate_tokens,
    file_sha256,
    stable_hash,
)
from extract_guideline_kg_residuals import (
    ClaimWindowError,
    claim_window_evidence_inventory,
    normalize_claim_window,
    sentence_spans,
)

RESPLITTER_VERSION = "guideline-kg-adaptive-resplit-v1"
SUPPORTED_REASONS = frozenset(
    {
        "evidence_unit_too_broad",
        "too_many_assertions",
        "output_budget_insufficient",
    }
)
STATUS_REASON_ALIASES = {
    "resplit_evidence_unit": "evidence_unit_too_broad",
    "resplit_assertion_capacity": "too_many_assertions",
    "resplit_output_capacity": "output_budget_insufficient",
}
INDIVISIBLE_CLOSURE_CUES = frozenset({"enumeration", "k_of_n", "threshold", "lead_in"})
DEFAULT_GRAPH = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/build/graph.internal.jsonl"
)
DEFAULT_WINDOWS = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/claim_windows"
    / "claim_windows.internal.jsonl"
)
DEFAULT_LEDGER = (
    ROOT
    / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/llm_pilot"
    / "needs_resplit.jsonl"
)
DEFAULT_OUTPUT = (
    ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/claim_windows/resplit"
)
DEFAULT_MAX_EVIDENCE_BLOCKS = 16
DEFAULT_MAX_SOURCE_TOKENS = 1_500
DEFAULT_MAX_DEPTH = 3


class ResplitError(ValueError):
    """Raised when a parent cannot be safely and losslessly interpreted."""


@dataclass(frozen=True)
class ResplitRequest:
    parent_window_id: str
    reasons: tuple[str, ...]
    window_sha256_values: tuple[str, ...]
    rechunker_versions: tuple[str, ...]
    ledger_rows: int


@dataclass(frozen=True)
class Part:
    parent_start: int
    parent_end: int
    role: str
    block: Mapping[str, Any] | None = None
    context_reason: str | None = None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ResplitError(f"{path}:{line_number}: expected a JSON object")
            rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
            count += 1
    return count


def _window_id(row: Mapping[str, Any]) -> str:
    return str(row.get("window_id") or row.get("id") or "").strip()


def load_resplit_requests(path: Path) -> dict[str, ResplitRequest]:
    """Load and deterministically coalesce repeated model requests."""

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(path):
        if str(row.get("semantic_mode") or "claim_window") != "claim_window":
            continue
        parent_id = str(
            row.get("semantic_unit_id") or row.get("window_id") or ""
        ).strip()
        if not parent_id:
            raise ResplitError("needs_resplit row lacks semantic_unit_id/window_id")
        grouped[parent_id].append(row)
    result: dict[str, ResplitRequest] = {}
    for parent_id, rows in sorted(grouped.items()):
        raw_reasons: set[str] = set()
        for row in rows:
            explicit = str(row.get("coverage_reason") or "").strip()
            status = str(
                row.get("coverage_status") or row.get("resplit_status") or ""
            ).strip()
            reason = explicit or STATUS_REASON_ALIASES.get(status, "")
            raw_reasons.add(STATUS_REASON_ALIASES.get(reason, reason))
        reasons = tuple(sorted(raw_reasons))
        hashes = tuple(
            sorted({str(row.get("window_sha256") or "").strip() for row in rows} - {""})
        )
        versions = tuple(
            sorted(
                {str(row.get("rechunker_version") or "").strip() for row in rows} - {""}
            )
        )
        result[parent_id] = ResplitRequest(
            parent_window_id=parent_id,
            reasons=reasons,
            window_sha256_values=hashes,
            rechunker_versions=versions,
            ledger_rows=len(rows),
        )
    return result


def _select_parents(
    path: Path, wanted: set[str]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    parents: dict[str, dict[str, Any]] = {}
    passage_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ResplitError(f"{path}:{line_number}: expected a JSON object")
            row_id = _window_id(row)
            if row_id not in wanted:
                continue
            if row_id in parents:
                raise ResplitError(f"duplicate parent ClaimWindow id: {row_id}")
            parents[row_id] = row
            for item in row.get("offset_map") or row.get("source_map") or []:
                if isinstance(item, Mapping) and item.get("passage_id"):
                    passage_ids.add(str(item["passage_id"]))
    return parents, passage_ids


def _load_passage_index(path: Path, wanted: set[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ResplitError(f"{path}:{line_number}: expected a JSON object")
            row_id = str(row.get("id") or "")
            if row_id in wanted and row.get("record_type") == "Passage":
                index[row_id] = row
    return index


def _parent_blocks(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = parent.get("primary_claim_blocks")
    if not isinstance(raw, list) or not raw:
        raise ResplitError("parent has no primary_claim_blocks")
    blocks: list[dict[str, Any]] = []
    previous_end = -1
    seen: set[str] = set()
    text = str(parent.get("text") or "")
    for position, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ResplitError(f"primary_claim_blocks[{position}] is not an object")
        block = dict(item)
        block_id = str(block.get("block_id") or "").strip()
        if not block_id or block_id in seen:
            raise ResplitError(
                "primary claim blocks need unique non-empty block_id values"
            )
        seen.add(block_id)
        try:
            start = int(block["window_start_char"])
            end = int(block["window_end_char"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ResplitError(f"block {block_id!r} has invalid offsets") from exc
        if not (0 <= start < end <= len(text)) or start < previous_end:
            raise ResplitError(f"block {block_id!r} overlaps or has invalid offsets")
        block["window_start_char"] = start
        block["window_end_char"] = end
        previous_end = end
        blocks.append(block)
    return blocks


def _block_text(parent: Mapping[str, Any], block: Mapping[str, Any]) -> str:
    return str(parent["text"])[
        int(block["window_start_char"]) : int(block["window_end_char"])
    ]


def _is_indivisible_logic_closure(block: Mapping[str, Any]) -> bool:
    """Return whether sentence splitting could destroy one logical criterion."""

    block_type = str(block.get("block_type") or "").casefold()
    structural_role = str(block.get("structural_role") or "").casefold()
    cues = {str(value).casefold() for value in block.get("logic_cues") or []}
    return (
        any(value in block_type for value in ("criteria", "list", "table"))
        or structural_role
        in {"criteria_closure", "enumerated_claim_set", "tabular_claim_set"}
        or bool(cues & INDIVISIBLE_CLOSURE_CUES)
    )


def _is_prose_block(block: Mapping[str, Any]) -> bool:
    block_type = str(block.get("block_type") or "").casefold()
    return "prose" in block_type and not any(
        value in block_type for value in ("criteria", "list", "table")
    )


def _adaptive_block_id(
    parent: Mapping[str, Any],
    original: Mapping[str, Any],
    start: int,
    end: int,
    role: str,
) -> str:
    text = str(parent["text"])[start:end]
    return (
        "gkg_claim_block_resplit_"
        + stable_hash(
            RESPLITTER_VERSION,
            _window_id(parent),
            str(original["block_id"]),
            str(start),
            str(end),
            role,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )[:20]
    )


def subdivide_broad_prose_blocks(
    parent: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Split broad prose at sentence boundaries without splitting closures.

    A heading embedded in ``headed_prose`` is peeled off into a non-citable
    context block.  Criteria/list/table/k-of-n/threshold/lead-in closures are
    marked for quarantine because a sentence cut could alter their logical
    scope.  Atomic or single-sentence prose remains intact; it may still be
    isolated from sibling units, but is never shortened.
    """

    parent_text = str(parent["text"])
    result: list[dict[str, Any]] = []
    for raw in blocks:
        block = dict(raw)
        if block.get("eligible_for_evidence") is not True:
            result.append(block)
            continue
        if _is_indivisible_logic_closure(block):
            block["adaptive_resplit_quarantine_reason"] = "indivisible_logic_closure"
            result.append(block)
            continue
        if not _is_prose_block(block):
            result.append(block)
            continue

        start = int(block["window_start_char"])
        end = int(block["window_end_char"])
        body_start = start
        block_type = str(block.get("block_type") or "").casefold()
        # Only the original unsplit headed_prose contract guarantees that its
        # first line is the governing header.  A later
        # headed_prose_sentence_split piece may begin in ordinary prose.
        if block_type == "headed_prose":
            newline = parent_text.find("\n", start, end)
            if newline >= 0:
                body_start = newline + 1
        body_spans = [
            (body_start + local_start, body_start + local_end)
            for local_start, local_end, _ in sentence_spans(parent_text[body_start:end])
        ]
        # A headed block with one body sentence still benefits: the header is
        # removed from the citable evidence unit and retained only as context.
        made_progress = len(body_spans) >= 2 or (
            body_start > start and len(body_spans) >= 1
        )
        if not made_progress:
            result.append(block)
            continue

        first_body_start = body_spans[0][0]
        if first_body_start > start:
            context = dict(block)
            context.update(
                {
                    "block_id": _adaptive_block_id(
                        parent, block, start, first_body_start, "heading_context"
                    ),
                    "window_start_char": start,
                    "window_end_char": first_body_start,
                    "block_type": "heading",
                    "structural_role": "heading_context",
                    "logic_cues": [],
                    "contains_scope_cue": False,
                    "diagnostic_gate_reasons": [],
                    "eligible_for_evidence": False,
                    "adaptive_parent_block_id": str(block["block_id"]),
                    "adaptive_subdivision": "headed_prose_header_context",
                }
            )
            result.append(context)

        for sentence_index, (sentence_start, sentence_end) in enumerate(
            body_spans, start=1
        ):
            subclaim = dict(block)
            subclaim.update(
                {
                    "block_id": _adaptive_block_id(
                        parent,
                        block,
                        sentence_start,
                        sentence_end,
                        f"sentence_{sentence_index}",
                    ),
                    "window_start_char": sentence_start,
                    "window_end_char": sentence_end,
                    "block_type": "prose_sentence_resplit",
                    "structural_role": "subdivided_prose_claim",
                    "adaptive_parent_block_id": str(block["block_id"]),
                    "adaptive_subdivision": "sentence_boundary",
                    "adaptive_subclaim_index": sentence_index,
                    "adaptive_subclaim_count": len(body_spans),
                    "eligible_for_evidence": True,
                }
            )
            result.append(subclaim)
    result.sort(
        key=lambda item: (
            int(item["window_start_char"]),
            int(item["window_end_char"]),
            str(item["block_id"]),
        )
    )
    return result


def _evidence_group_tokens(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    indexes: Sequence[int],
) -> int:
    return estimate_tokens(
        "\n\n".join(_block_text(parent, blocks[index]) for index in indexes)
    )


def partition_evidence_blocks(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    *,
    reasons: Sequence[str],
    max_evidence_blocks: int,
    max_source_tokens: int,
) -> tuple[list[list[int]], dict[int, str]]:
    """Partition eligible indexes; return groups and explicit quarantines.

    A model-requested split must make progress even when the parent already
    satisfies the static caps.  Broad prose is subdivided before this function;
    remaining broad units are isolated.  Logic closures are quarantined rather
    than cut.  The other reasons force at least a two-way split.
    """

    eligible = [
        index
        for index, block in enumerate(blocks)
        if block.get("eligible_for_evidence") is True
    ]
    if not eligible:
        return [], {}
    quarantined: dict[int, str] = {}
    for index in eligible:
        block = blocks[index]
        forced = str(block.get("adaptive_resplit_quarantine_reason") or "")
        if forced:
            quarantined[index] = forced
        elif estimate_tokens(_block_text(parent, block)) > max_source_tokens:
            quarantined[index] = "indivisible_evidence_unit_exceeds_source_cap"
    available = [index for index in eligible if index not in quarantined]
    if not available:
        return [], quarantined

    effective_max_blocks = max_evidence_blocks
    if "evidence_unit_too_broad" in reasons:
        effective_max_blocks = 1
    elif len(available) > 1:
        # A coverage failure is an empirical signal that the static cap was
        # insufficient.  Force a smaller load instead of reproducing the same
        # request and cache key.
        effective_max_blocks = min(effective_max_blocks, (len(available) + 1) // 2)

    groups: list[list[int]] = []
    current: list[int] = []
    for index in available:
        proposed = [*current, index]
        if current and (
            len(proposed) > effective_max_blocks
            or _evidence_group_tokens(parent, blocks, proposed) > max_source_tokens
        ):
            groups.append(current)
            current = [index]
        else:
            current = proposed
    if current:
        groups.append(current)

    if len(groups) == 1 and len(groups[0]) == 1 and len(eligible) == 1:
        only = groups[0][0]
        if not blocks[only].get("adaptive_subdivision"):
            # The exact empirical request would be repeated; no progress is
            # possible without illegally splitting an indivisible claim block.
            quarantined[only] = "no_progress_single_evidence_unit"
            return [], quarantined
    if len(groups) == 1 and len(groups[0]) > 1:
        # Defensive fallback: force a deterministic, approximately balanced
        # block-boundary split if future reason policies relax the cap above.
        group = groups[0]
        best = min(
            range(1, len(group)),
            key=lambda split: (
                abs(
                    _evidence_group_tokens(parent, blocks, group[:split])
                    - _evidence_group_tokens(parent, blocks, group[split:])
                ),
                split,
            ),
        )
        groups = [group[:best], group[best:]]
    return groups, dict(sorted(quarantined.items()))


def _slice_map_item(
    raw: Mapping[str, Any],
    *,
    parent_start: int,
    parent_end: int,
    child_start: int,
    evidence: bool,
) -> dict[str, Any] | None:
    left = max(parent_start, int(raw["window_start_char"]))
    right = min(parent_end, int(raw["window_end_char"]))
    if left >= right:
        return None
    result = dict(raw)
    original_window_start = int(raw["window_start_char"])
    original_passage_start = int(
        raw.get("passage_start_char", raw.get("source_start_char"))
    )
    result.update(
        {
            "window_start_char": child_start + left - parent_start,
            "window_end_char": child_start + right - parent_start,
            "passage_start_char": original_passage_start + left - original_window_start,
            "passage_end_char": original_passage_start + right - original_window_start,
            "kind": "source" if evidence else "context_copy",
            "eligible_for_evidence": evidence,
        }
    )
    result.pop("source_start_char", None)
    result.pop("source_end_char", None)
    return result


def _slice_synthetic_regions(
    parent: Mapping[str, Any],
    *,
    parent_start: int,
    parent_end: int,
    child_start: int,
    mapped: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return a complete, non-overlapping synthetic partition for one part."""

    known: list[dict[str, Any]] = []
    for raw in parent.get("synthetic_regions") or []:
        if not isinstance(raw, Mapping):
            continue
        left = max(parent_start, int(raw.get("window_start_char", -1)))
        right = min(parent_end, int(raw.get("window_end_char", -1)))
        if left < right:
            known.append(
                {
                    "window_start_char": child_start + left - parent_start,
                    "window_end_char": child_start + right - parent_start,
                    "kind": str(raw.get("kind") or "inherited_synthetic"),
                    "eligible_for_evidence": False,
                }
            )
    mapped_intervals = sorted(
        (int(item["window_start_char"]), int(item["window_end_char"]))
        for item in mapped
    )
    known.sort(key=lambda item: (item["window_start_char"], item["window_end_char"]))
    occupied = sorted(
        [(left, right, "mapped") for left, right in mapped_intervals]
        + [
            (
                int(item["window_start_char"]),
                int(item["window_end_char"]),
                "synthetic",
            )
            for item in known
        ]
    )
    region_start = child_start
    region_end = child_start + parent_end - parent_start
    cursor = region_start
    gaps: list[dict[str, Any]] = []
    for left, right, _ in occupied:
        if left < cursor:
            raise ResplitError("parent source and synthetic regions overlap")
        if left > cursor:
            gap = str(parent["text"])[
                parent_start + cursor - child_start : parent_start + left - child_start
            ]
            if gap.strip():
                raise ResplitError("unmapped non-whitespace parent text would be lost")
            gaps.append(
                {
                    "window_start_char": cursor,
                    "window_end_char": left,
                    "kind": "inherited_unmapped_whitespace",
                    "eligible_for_evidence": False,
                }
            )
        cursor = right
    if cursor < region_end:
        gap = str(parent["text"])[parent_start + cursor - child_start : parent_end]
        if gap.strip():
            raise ResplitError("unmapped non-whitespace parent text would be lost")
        gaps.append(
            {
                "window_start_char": cursor,
                "window_end_char": region_end,
                "kind": "inherited_unmapped_whitespace",
                "eligible_for_evidence": False,
            }
        )
    return sorted([*known, *gaps], key=lambda item: item["window_start_char"])


def _candidate_context_parts(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    group: Sequence[int],
    *,
    previous_group_last: int | None,
    is_first: bool,
    is_last: bool,
) -> list[Part]:
    """Select exact semantic context ranges in deterministic priority order."""

    candidates: list[Part] = []
    first = group[0]
    last = group[-1]
    # Reuse the nearest active heading even when it was evidence in another
    # child.  Its copy is explicitly non-citable.
    for index in range(first - 1, -1, -1):
        block = blocks[index]
        if (
            str(block.get("block_type") or "") == "heading"
            or str(block.get("structural_role") or "") == "heading_context"
        ):
            candidates.append(
                Part(
                    int(block["window_start_char"]),
                    int(block["window_end_char"]),
                    "context",
                    block,
                    "active_heading",
                )
            )
            break

    context_start = 0 if previous_group_last is None else previous_group_last + 1
    for index in range(context_start, first):
        block = blocks[index]
        if block.get("eligible_for_evidence") is not True:
            candidates.append(
                Part(
                    int(block["window_start_char"]),
                    int(block["window_end_char"]),
                    "context",
                    block,
                    "intervening_nondiagnostic_block",
                )
            )
    if is_last:
        for index in range(last + 1, len(blocks)):
            block = blocks[index]
            if block.get("eligible_for_evidence") is not True:
                candidates.append(
                    Part(
                        int(block["window_start_char"]),
                        int(block["window_end_char"]),
                        "context",
                        block,
                        "trailing_nondiagnostic_block",
                    )
                )

    if blocks and is_first and int(blocks[0]["window_start_char"]) > 0:
        candidates.append(
            Part(
                0,
                int(blocks[0]["window_start_char"]),
                "context",
                None,
                "inherited_prefix_context",
            )
        )
    if (
        blocks
        and is_last
        and int(blocks[-1]["window_end_char"]) < len(str(parent["text"]))
    ):
        candidates.append(
            Part(
                int(blocks[-1]["window_end_char"]),
                len(str(parent["text"])),
                "context",
                None,
                "inherited_suffix_context",
            )
        )

    # Exact duplicate ranges are common when the active heading is also an
    # intervening non-diagnostic block.  Keep the higher-priority first reason.
    deduplicated: list[Part] = []
    seen: set[tuple[int, int]] = set()
    for part in candidates:
        key = (part.parent_start, part.parent_end)
        if key not in seen:
            seen.add(key)
            deduplicated.append(part)
    return deduplicated


def _render_parts(
    parent: Mapping[str, Any],
    parts: Sequence[Part],
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, tuple[int, int]],
    list[dict[str, Any]],
]:
    text_parts: list[str] = []
    offset_map: list[dict[str, Any]] = []
    synthetic_regions: list[dict[str, Any]] = []
    block_positions: dict[str, tuple[int, int]] = {}
    context_inventory: list[dict[str, Any]] = []
    cursor = 0
    sorted_parts = sorted(
        parts, key=lambda part: (part.parent_start, part.parent_end, part.role)
    )
    previous_end = -1
    for part_index, part in enumerate(sorted_parts):
        if part.parent_start < previous_end:
            raise ResplitError("selected child parts overlap")
        previous_end = part.parent_end
        if part_index:
            text_parts.append("\n\n")
            synthetic_regions.append(
                {
                    "window_start_char": cursor,
                    "window_end_char": cursor + 2,
                    "kind": "adaptive_resplit_separator",
                    "eligible_for_evidence": False,
                }
            )
            cursor += 2
        part_text = str(parent["text"])[part.parent_start : part.parent_end]
        child_part_start = cursor
        text_parts.append(part_text)
        raw_map = parent.get("offset_map") or parent.get("source_map") or []
        part_map = [
            value
            for value in (
                _slice_map_item(
                    raw,
                    parent_start=part.parent_start,
                    parent_end=part.parent_end,
                    child_start=child_part_start,
                    evidence=part.role == "evidence",
                )
                for raw in raw_map
                if isinstance(raw, Mapping)
            )
            if value is not None
        ]
        offset_map.extend(part_map)
        synthetic_regions.extend(
            _slice_synthetic_regions(
                parent,
                parent_start=part.parent_start,
                parent_end=part.parent_end,
                child_start=child_part_start,
                mapped=part_map,
            )
        )
        cursor += len(part_text)
        if part.block is not None:
            block_id = str(part.block["block_id"])
            if part.role == "evidence":
                block_positions[block_id] = (child_part_start, cursor)
            else:
                context_inventory.append(
                    {
                        "block_id": block_id,
                        "window_start_char": child_part_start,
                        "window_end_char": cursor,
                        "context_reason": part.context_reason,
                        "eligible_for_evidence": False,
                    }
                )
        elif part.role == "context":
            context_inventory.append(
                {
                    "block_id": None,
                    "window_start_char": child_part_start,
                    "window_end_char": cursor,
                    "context_reason": part.context_reason,
                    "eligible_for_evidence": False,
                }
            )
    return (
        "".join(text_parts),
        offset_map,
        synthetic_regions,
        block_positions,
        context_inventory,
    )


def _render_child(
    parent: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    group: Sequence[int],
    *,
    reasons: Sequence[str],
    child_index: int,
    child_count: int,
    previous_group_last: int | None,
    max_source_tokens: int,
) -> dict[str, Any]:
    evidence_parts = [
        Part(
            int(blocks[index]["window_start_char"]),
            int(blocks[index]["window_end_char"]),
            "evidence",
            blocks[index],
        )
        for index in group
    ]
    candidates = _candidate_context_parts(
        parent,
        blocks,
        group,
        previous_group_last=previous_group_last,
        is_first=child_index == 1,
        is_last=child_index == child_count,
    )
    # Context is useful but cannot be allowed to push the new source window
    # above its explicit bound.  Every omission is recorded as a parent range;
    # no source bytes are shortened or silently discarded.
    chosen = list(evidence_parts)
    omitted: list[dict[str, Any]] = []
    for candidate in candidates:
        trial_ranges = {(part.parent_start, part.parent_end) for part in chosen}
        if (candidate.parent_start, candidate.parent_end) in trial_ranges:
            continue
        trial = [*chosen, candidate]
        trial_text, *_ = _render_parts(parent, trial)
        if estimate_tokens(trial_text) <= max_source_tokens:
            chosen.append(candidate)
        else:
            value = str(parent["text"])[candidate.parent_start : candidate.parent_end]
            omitted.append(
                {
                    "parent_start_char": candidate.parent_start,
                    "parent_end_char": candidate.parent_end,
                    "text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                    "token_estimate": estimate_tokens(value),
                    "context_reason": candidate.context_reason,
                }
            )
    text, offset_map, synthetic, positions, context_inventory = _render_parts(
        parent, chosen
    )
    token_estimate = estimate_tokens(text)
    if token_estimate > max_source_tokens:
        raise ResplitError("evidence-only child exceeds max source tokens")

    primary_blocks: list[dict[str, Any]] = []
    for index in group:
        original = dict(blocks[index])
        block_id = str(original["block_id"])
        start, end = positions[block_id]
        original.update(
            {
                "window_start_char": start,
                "window_end_char": end,
                "eligible_for_evidence": True,
            }
        )
        primary_blocks.append(original)

    parent_id = _window_id(parent)
    root_id = str(parent.get("root_window_id") or parent_id)
    parent_depth = int(parent.get("resplit_depth") or 0)
    depth = parent_depth + 1
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    block_ids = [str(block["block_id"]) for block in primary_blocks]
    child_id = (
        "gkg_claim_window_resplit_"
        + stable_hash(
            RESPLITTER_VERSION,
            root_id,
            parent_id,
            str(depth),
            *sorted(reasons),
            *block_ids,
            text_sha,
        )[:20]
    )

    excluded = {
        "id",
        "window_id",
        "text",
        "text_sha256",
        "token_estimate",
        "offset_map",
        "source_map",
        "offset_map_sha256",
        "synthetic_regions",
        "primary_claim_blocks",
        "claim_block_ids",
        "claim_block_types",
        "eligible_primary_block_count",
        "coverage_status",
        "coverage_risk",
        "status",
        "overlap_policy",
        "parent_window_id",
        "root_window_id",
        "resplit_depth",
        "resplit_reason",
        "resplit_reasons",
        "resplit_lineage",
        "child_index",
        "child_count",
        "context_claim_blocks",
        "omitted_parent_context_ranges",
    }
    child = {key: value for key, value in parent.items() if key not in excluded}
    lineage = list(parent.get("resplit_lineage") or [])
    lineage.append(parent_id)
    source_maps = [item for item in offset_map if item.get("kind") == "source"]
    source_ordinals = [
        int(item["source_ordinal"])
        for item in source_maps
        if item.get("source_ordinal") is not None
    ]
    child.update(
        {
            "record_type": "ClaimWindow",
            "id": child_id,
            "window_id": child_id,
            "rechunker_version": str(parent.get("rechunker_version") or "")
            + "+"
            + RESPLITTER_VERSION,
            "adaptive_resplit_version": RESPLITTER_VERSION,
            "parent_window_id": parent_id,
            "root_window_id": root_id,
            "resplit_depth": depth,
            "resplit_reason": min(reasons) if len(reasons) == 1 else "multiple",
            "resplit_reasons": sorted(reasons),
            "resplit_lineage": lineage,
            "child_index": child_index,
            "child_count": child_count,
            "text": text,
            "text_sha256": text_sha,
            "token_estimate": token_estimate,
            "source_ordinal_start": min(source_ordinals)
            if source_ordinals
            else parent.get("source_ordinal_start"),
            "source_ordinal_end": max(source_ordinals)
            if source_ordinals
            else parent.get("source_ordinal_end"),
            "anchor_passage_ids": sorted(
                {str(item["passage_id"]) for item in source_maps}
            ),
            "claim_block_ids": block_ids,
            "claim_block_types": [
                str(block.get("block_type") or "other") for block in primary_blocks
            ],
            "primary_claim_blocks": primary_blocks,
            "context_claim_blocks": context_inventory,
            "omitted_parent_context_ranges": omitted,
            "eligible_primary_block_count": len(primary_blocks),
            "coverage_status": "pending_llm_coverage",
            "coverage_risk": "standard",
            "offset_map": offset_map,
            "offset_map_sha256": hashlib.sha256(
                canonical_json(
                    [
                        {
                            "window_start_char": int(item["window_start_char"]),
                            "window_end_char": int(item["window_end_char"]),
                            "passage_id": str(item["passage_id"]),
                            "passage_start_char": int(item["passage_start_char"]),
                            "passage_end_char": int(item["passage_end_char"]),
                            "kind": str(item["kind"]),
                            "eligible_for_evidence": bool(
                                item["eligible_for_evidence"]
                            ),
                        }
                        for item in sorted(
                            offset_map,
                            key=lambda value: (
                                int(value["window_start_char"]),
                                int(value["window_end_char"]),
                                str(value["passage_id"]),
                            ),
                        )
                    ]
                ).encode("utf-8")
            ).hexdigest(),
            "synthetic_regions": synthetic,
            "overlap_policy": {
                "fixed_token_overlap": False,
                "adaptive_semantic_context": True,
                "context_citable": False,
                "omitted_context_ranges_audited": bool(omitted),
            },
            "status": "eligible",
        }
    )
    return child


def _public_pointer(child: Mapping[str, Any]) -> dict[str, Any]:
    source_refs = sorted(
        {
            (
                str(item["passage_id"]),
                int(item["passage_start_char"]),
                int(item["passage_end_char"]),
            )
            for item in child["offset_map"]
            if item.get("kind") == "source"
        }
    )
    return {
        "record_type": "ClaimWindowPointer",
        "window_id": child["window_id"],
        "rechunker_version": child["rechunker_version"],
        "adaptive_resplit_version": child["adaptive_resplit_version"],
        "parent_window_id": child["parent_window_id"],
        "root_window_id": child["root_window_id"],
        "resplit_depth": child["resplit_depth"],
        "resplit_reasons": child["resplit_reasons"],
        "child_index": child["child_index"],
        "child_count": child["child_count"],
        "text_sha256": child["text_sha256"],
        "token_estimate": child["token_estimate"],
        "source_family": child.get("source_family"),
        "source": child.get("source"),
        "source_id": child.get("source_id"),
        "document_version_id": child.get("document_version_id"),
        "source_ordinal_start": child.get("source_ordinal_start"),
        "source_ordinal_end": child.get("source_ordinal_end"),
        "claim_block_ids": child["claim_block_ids"],
        "eligible_primary_block_count": child["eligible_primary_block_count"],
        "source_refs": [
            {
                "passage_id": passage_id,
                "passage_start_char": start,
                "passage_end_char": end,
            }
            for passage_id, start, end in source_refs
        ],
        "omitted_parent_context_ranges": child["omitted_parent_context_ranges"],
        "coverage_status": child["coverage_status"],
        "status": child["status"],
    }


def _quarantine(
    parent: Mapping[str, Any] | None,
    request: ResplitRequest,
    reason: str,
    *,
    detail: str = "",
    block: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    parent_id = request.parent_window_id
    parent_text = str(parent.get("text") or "") if parent else ""
    if block is not None and parent is not None:
        start = int(block["window_start_char"])
        end = int(block["window_end_char"])
        text = parent_text[start:end]
        block_id = str(block.get("block_id") or "")
    else:
        start, end = 0, len(parent_text)
        text = parent_text
        block_id = None
    offset_map: list[dict[str, Any]] = []
    synthetic_regions: list[dict[str, Any]] = []
    provenance_projection_error: str | None = None
    if parent is not None and start < end:
        try:
            for raw in parent.get("offset_map") or parent.get("source_map") or []:
                if not isinstance(raw, Mapping):
                    continue
                sliced = _slice_map_item(
                    raw,
                    parent_start=start,
                    parent_end=end,
                    child_start=0,
                    evidence=bool(raw.get("eligible_for_evidence", False)),
                )
                if sliced is not None:
                    # Quarantine is not an LLM input.  Retain the parent's
                    # original map kind and evidence-eligibility as provenance.
                    sliced["kind"] = str(raw.get("kind") or "source")
                    sliced["eligible_for_evidence"] = bool(
                        raw.get("eligible_for_evidence", False)
                    )
                    offset_map.append(sliced)
            synthetic_regions = _slice_synthetic_regions(
                parent,
                parent_start=start,
                parent_end=end,
                child_start=0,
                mapped=offset_map,
            )
        except (KeyError, TypeError, ValueError, ResplitError) as exc:
            # The quarantine must itself remain writable for malformed parents.
            # The parent offsets and hash still identify the exact untouched
            # source; the failed projection is made explicit for manual repair.
            offset_map = []
            synthetic_regions = []
            provenance_projection_error = f"{type(exc).__name__}:{exc}"
    quarantine_id = (
        "gkg_claim_resplit_quarantine_"
        + stable_hash(
            RESPLITTER_VERSION,
            parent_id,
            reason,
            block_id or "",
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )[:20]
    )
    return {
        "record_type": "ClaimWindowResplitQuarantine",
        "id": quarantine_id,
        "parent_window_id": parent_id,
        "root_window_id": (
            str(parent.get("root_window_id") or parent_id) if parent else parent_id
        ),
        "resplit_depth": int(parent.get("resplit_depth") or 0) if parent else None,
        "adaptive_resplit_version": RESPLITTER_VERSION,
        "requested_reasons": list(request.reasons),
        "reason": reason,
        "detail": detail,
        "block_id": block_id,
        "parent_start_char": start,
        "parent_end_char": end,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "token_estimate": estimate_tokens(text),
        "offset_map": offset_map,
        "synthetic_regions": synthetic_regions,
        "provenance_projection_error": provenance_projection_error,
        "status": "quarantined",
    }


def _public_quarantine_pointer(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"text", "detail", "offset_map", "synthetic_regions"}
    }


def resplit_claim_windows(
    *,
    parent_windows_path: Path,
    needs_resplit_path: Path,
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
    requests = load_resplit_requests(needs_resplit_path)
    parents, wanted_passages = _select_parents(parent_windows_path, set(requests))
    passage_index = _load_passage_index(graph_path, wanted_passages)

    children: list[dict[str, Any]] = []
    quarantines: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    for parent_id, request in sorted(requests.items()):
        parent = parents.get(parent_id)
        if parent is None:
            quarantines.append(_quarantine(None, request, "parent_window_not_found"))
            counters["parent_window_not_found"] += 1
            continue
        unsupported = sorted(set(request.reasons) - SUPPORTED_REASONS)
        if unsupported or not request.reasons:
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "unsupported_coverage_reason",
                    detail=",".join(unsupported or ["empty"]),
                )
            )
            counters["unsupported_coverage_reason"] += 1
            continue
        actual_hash = hashlib.sha256(
            str(parent.get("text") or "").encode("utf-8")
        ).hexdigest()
        if request.window_sha256_values and request.window_sha256_values != (
            actual_hash,
        ):
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "ledger_window_hash_mismatch",
                    detail=canonical_json(
                        {
                            "ledger": request.window_sha256_values,
                            "actual": actual_hash,
                        }
                    ),
                )
            )
            counters["ledger_window_hash_mismatch"] += 1
            continue
        version = str(parent.get("rechunker_version") or "")
        if request.rechunker_versions and request.rechunker_versions != (version,):
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "ledger_rechunker_version_mismatch",
                    detail=canonical_json(
                        {
                            "ledger": request.rechunker_versions,
                            "actual": version,
                        }
                    ),
                )
            )
            counters["ledger_rechunker_version_mismatch"] += 1
            continue
        if int(parent.get("resplit_depth") or 0) >= max_depth:
            quarantines.append(
                _quarantine(parent, request, "max_resplit_depth_reached")
            )
            counters["max_resplit_depth_reached"] += 1
            continue
        parent_missing = sorted(
            {
                str(item.get("passage_id") or "")
                for item in parent.get("offset_map") or []
                if str(item.get("passage_id") or "") not in passage_index
            }
        )
        if parent_missing:
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "missing_base_passage",
                    detail=canonical_json(parent_missing),
                )
            )
            counters["missing_base_passage"] += 1
            continue
        try:
            normalize_claim_window(parent, passage_index)
            blocks = _parent_blocks(parent)
            if "evidence_unit_too_broad" in request.reasons:
                blocks = subdivide_broad_prose_blocks(parent, blocks)
        except (ClaimWindowError, ResplitError, KeyError, TypeError, ValueError) as exc:
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "invalid_parent_claim_window",
                    detail=f"{type(exc).__name__}:{exc}",
                )
            )
            counters["invalid_parent_claim_window"] += 1
            continue

        groups, quarantined_blocks = partition_evidence_blocks(
            parent,
            blocks,
            reasons=request.reasons,
            max_evidence_blocks=max_evidence_blocks,
            max_source_tokens=max_source_tokens,
        )
        for index, reason in quarantined_blocks.items():
            block = blocks[index]
            quarantines.append(_quarantine(parent, request, reason, block=block))
            counters[reason] += 1
        if not groups:
            if not quarantined_blocks:
                quarantines.append(
                    _quarantine(parent, request, "no_evidence_eligible_blocks")
                )
                counters["no_evidence_eligible_blocks"] += 1
            continue

        parent_children: list[dict[str, Any]] = []
        previous_group_last: int | None = None
        try:
            for child_position, group in enumerate(groups, start=1):
                child = _render_child(
                    parent,
                    blocks,
                    group,
                    reasons=request.reasons,
                    child_index=child_position,
                    child_count=len(groups),
                    previous_group_last=previous_group_last,
                    max_source_tokens=max_source_tokens,
                )
                normalized = normalize_claim_window(child, passage_index)
                evidence, mode = claim_window_evidence_inventory(
                    normalized,
                    max_units=max_evidence_blocks,
                    max_sentence_subspans=10_000,
                )
                if mode != "primary_claim_block" or len(evidence) != len(group):
                    raise ResplitError(
                        "child evidence inventory changed during validation"
                    )
                parent_children.append(child)
                previous_group_last = group[-1]
        except (ClaimWindowError, ResplitError, KeyError, TypeError, ValueError) as exc:
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "child_projection_validation_failed",
                    detail=f"{type(exc).__name__}:{exc}",
                )
            )
            counters["child_projection_validation_failed"] += 1
            continue

        expected = [
            str(block["block_id"])
            for index, block in enumerate(blocks)
            if block.get("eligible_for_evidence") is True
            and index not in quarantined_blocks
        ]
        actual = [
            block_id
            for child in parent_children
            for block_id in child["claim_block_ids"]
        ]
        if actual != expected or len(actual) != len(set(actual)):
            quarantines.append(
                _quarantine(
                    parent,
                    request,
                    "non_lossless_evidence_partition",
                    detail=canonical_json({"expected": expected, "actual": actual}),
                )
            )
            counters["non_lossless_evidence_partition"] += 1
            continue
        if (
            len(parent_children) == 1
            and parent_children[0]["text_sha256"] == actual_hash
        ):
            quarantines.append(
                _quarantine(parent, request, "no_progress_identical_child")
            )
            counters["no_progress_identical_child"] += 1
            continue
        children.extend(parent_children)
        counters["parents_resplit"] += 1
        counters["children_emitted"] += len(parent_children)
        counters["evidence_blocks_emitted"] += len(actual)
        counters["omitted_context_ranges"] += sum(
            len(child["omitted_parent_context_ranges"]) for child in parent_children
        )

    children.sort(
        key=lambda row: (
            str(row["parent_window_id"]),
            int(row["child_index"]),
            str(row["window_id"]),
        )
    )
    quarantines.sort(key=lambda row: (str(row["parent_window_id"]), str(row["id"])))
    internal_path = output_dir / "claim_windows.resplit.internal.jsonl"
    public_path = output_dir / "claim_window_queue.resplit.public.jsonl"
    quarantine_path = output_dir / "claim_window_resplit_quarantine.internal.jsonl"
    quarantine_public_path = output_dir / "claim_window_resplit_quarantine.public.jsonl"
    _write_jsonl(internal_path, children)
    _write_jsonl(public_path, (_public_pointer(child) for child in children))
    _write_jsonl(quarantine_path, quarantines)
    _write_jsonl(
        quarantine_public_path,
        (_public_quarantine_pointer(row) for row in quarantines),
    )
    stats = {
        "adaptive_resplit_version": RESPLITTER_VERSION,
        "requests": len(requests),
        "parents_found": len(parents),
        "passage_references": len(wanted_passages),
        "passages_loaded": len(passage_index),
        "max_evidence_blocks": max_evidence_blocks,
        "max_source_tokens": max_source_tokens,
        "max_depth": max_depth,
        "children": len(children),
        "quarantines": len(quarantines),
        "counters": dict(sorted(counters.items())),
        "child_token_estimate": {
            "min": min((int(row["token_estimate"]) for row in children), default=0),
            "max": max((int(row["token_estimate"]) for row in children), default=0),
            "sum": sum(int(row["token_estimate"]) for row in children),
        },
    }
    stats_path = output_dir / "stats.json"
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "guideline-diagnostic-kg-v0.1",
        "adaptive_resplit_version": RESPLITTER_VERSION,
        "source_parent_windows": str(parent_windows_path),
        "source_parent_windows_sha256": file_sha256(parent_windows_path),
        "source_needs_resplit": str(needs_resplit_path),
        "source_needs_resplit_sha256": file_sha256(needs_resplit_path),
        "source_graph": str(graph_path),
        "source_graph_sha256": file_sha256(graph_path),
        "outputs": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in (
                internal_path,
                public_path,
                quarantine_path,
                quarantine_public_path,
                stats_path,
            )
        },
        "contains_source_text": {
            internal_path.name: True,
            public_path.name: False,
            quarantine_path.name: True,
            quarantine_public_path.name: False,
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
    parser.add_argument("--needs-resplit", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--max-evidence-blocks",
        type=int,
        default=DEFAULT_MAX_EVIDENCE_BLOCKS,
    )
    parser.add_argument(
        "--max-source-tokens",
        type=int,
        default=DEFAULT_MAX_SOURCE_TOKENS,
    )
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_DEPTH)
    args = parser.parse_args()
    result = resplit_claim_windows(
        parent_windows_path=args.parent_windows,
        needs_resplit_path=args.needs_resplit,
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
