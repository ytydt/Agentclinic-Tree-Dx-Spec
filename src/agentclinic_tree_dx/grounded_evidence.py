"""Frozen chunk access and validation for grounded L1 evidence selection."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .l1_evidence_bfs import clean_contrastive_selection, stable_hash


_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
CHAIN_EFFECTS = frozenset({"supports", "against", "weaker", "shared"})


def _norm(value: Any) -> str:
    return " ".join(_TOKEN_RE.findall(str(value or "").casefold()))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChunkExcerpt:
    """One immutable corpus excerpt routed to an observed fact."""

    access_id: str
    fact_id: str
    finding_text: str
    ev_id: str
    chunk_id: str
    source: str
    candidate: str
    text: str
    has_compare: bool = False
    has_neg: bool = False
    has_num: bool = False
    has_highspec: bool = False

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        payload = asdict(self)
        payload["text_sha256"] = _sha256_text(self.text)
        if not include_text:
            payload.pop("text")
        return payload


def load_needed_chunk_texts(
    paths: Iterable[str | Path],
    needed_chunk_ids: Iterable[str],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Load only requested chunk texts from JSONL/JSON metadata files."""
    needed = {str(value) for value in needed_chunk_ids if str(value)}
    output: dict[str, str] = {}
    source_by_id: dict[str, str] = {}
    duplicate_conflicts: list[str] = []
    scanned_rows = 0
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            with path.open(encoding="utf-8") as stream:
                rows: Iterable[Any] = (
                    json.loads(line) for line in stream if line.strip()
                )
                for row in rows:
                    scanned_rows += 1
                    if not isinstance(row, Mapping):
                        continue
                    chunk_id = str(row.get("chunk_id") or row.get("id") or "")
                    if chunk_id not in needed:
                        continue
                    text = row.get("content")
                    if text is None:
                        text = row.get("text")
                    if not isinstance(text, str) or not text.strip():
                        continue
                    if chunk_id in output and output[chunk_id] != text:
                        duplicate_conflicts.append(chunk_id)
                        continue
                    output[chunk_id] = text
                    source_by_id[chunk_id] = str(path)
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = (
                payload.get("chunks") or payload.get("rows") or [payload]
                if isinstance(payload, Mapping)
                else payload
            )
            for row in rows:
                scanned_rows += 1
                if not isinstance(row, Mapping):
                    continue
                chunk_id = str(row.get("chunk_id") or row.get("id") or "")
                if chunk_id not in needed:
                    continue
                text = row.get("content")
                if text is None:
                    text = row.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                if chunk_id in output and output[chunk_id] != text:
                    duplicate_conflicts.append(chunk_id)
                    continue
                output[chunk_id] = text
                source_by_id[chunk_id] = str(path)
    return output, {
        "requested": len(needed),
        "hydrated": len(output),
        "missing_chunk_ids": sorted(needed - set(output)),
        "duplicate_conflicts": sorted(set(duplicate_conflicts)),
        "scanned_rows": scanned_rows,
        "source_by_id": source_by_id,
    }


def excerpt_catalog_hash(excerpts: Sequence[Mapping[str, Any]]) -> str:
    """Hash the complete immutable excerpt catalogue."""
    return stable_hash(list(excerpts))


def chunk_index(
    excerpts: Sequence[Mapping[str, Any]],
    *,
    include_text: bool = False,
) -> list[dict[str, Any]]:
    """Return a deterministic catalogue view, optionally with chunk text."""
    rows: list[dict[str, Any]] = []
    for raw in excerpts:
        row = dict(raw)
        if not include_text:
            row.pop("text", None)
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            str(row.get("fact_id") or ""),
            str(row.get("candidate") or ""),
            str(row.get("ev_id") or ""),
            str(row.get("access_id") or ""),
            str(row.get("chunk_id") or ""),
        ),
    )


def hydrate_chunk_requests(
    excerpts: Sequence[Mapping[str, Any]],
    requested_chunk_ids: Sequence[str],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Serve a bounded, de-duplicated request from a frozen catalogue."""
    by_id = {
        str(row.get("access_id") or row.get("chunk_id") or ""): dict(row)
        for row in excerpts
        if str(row.get("access_id") or row.get("chunk_id") or "")
    }
    served: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in requested_chunk_ids:
        access_id = str(value)
        if access_id in seen:
            continue
        seen.add(access_id)
        if len(served) >= limit:
            rejected.append({"chunk_id": access_id, "reason": "request_limit"})
            continue
        row = by_id.get(access_id)
        if row is None:
            rejected.append({"chunk_id": access_id, "reason": "unknown_chunk"})
            continue
        if not str(row.get("text") or ""):
            rejected.append({"chunk_id": access_id, "reason": "missing_text"})
            continue
        served.append(row)
    return served, rejected


def clean_chunk_request(
    response: Mapping[str, Any],
    allowed_chunk_ids: Sequence[str],
    *,
    limit: int,
) -> dict[str, Any]:
    """Validate the discovery-stage read request without adding fallbacks."""
    allowed = set(allowed_chunk_ids)
    raw = response.get("requested_chunk_ids") or ()
    if not isinstance(raw, (list, tuple)):
        raw = ()
    selected: list[str] = []
    rejected: list[dict[str, str]] = []
    for value in raw:
        access_id = str(value)
        if access_id not in allowed:
            rejected.append({"chunk_id": access_id, "reason": "unknown_chunk"})
        elif access_id not in selected and len(selected) < limit:
            selected.append(access_id)
    return {
        "requested_chunk_ids": selected,
        "focus_fact_ids": [
            str(value) for value in (response.get("focus_fact_ids") or ())
        ],
        "why": str(response.get("why") or ""),
        "rejected": rejected,
        "schema_valid": bool(selected),
    }


def _candidate_matches_branch(
    chunk_candidate: str,
    branch_id: str,
    candidates: Sequence[Mapping[str, Any]],
) -> bool:
    branch = next(
        (row for row in candidates if str(row.get("id")) == branch_id), None,
    )
    if branch is None:
        return False
    target = _norm(chunk_candidate)
    labels = [
        str(branch.get("label") or ""),
        *(str(value) for value in (branch.get("leaf_exemplars") or ())),
    ]
    for label in labels:
        normalized = _norm(label)
        if target and normalized and (
            target == normalized or target in normalized or normalized in target
        ):
            return True
    return False


def clean_grounded_selection(
    response: Mapping[str, Any],
    *,
    eligible_ids: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
    served_chunks: Sequence[Mapping[str, Any]],
    limit: int = 2,
    allowed_proposal_ids: Sequence[str] | None = None,
    require_complete_grounding: bool = True,
    require_candidate_alignment: bool = True,
) -> dict[str, Any]:
    """Validate pairwise selection plus exact, branch-aligned chunk citations."""
    branch_ids = [str(row["id"]) for row in candidates]
    base = clean_contrastive_selection(
        response, eligible_ids, branch_ids, limit=limit,
    )
    raw_rows = response.get("ranked_facts") or ()
    raw_by_id = {
        str(row.get("fact_id") or ""): row
        for row in raw_rows if isinstance(row, Mapping)
    }
    chunks = {
        str(row.get("access_id") or row.get("chunk_id") or ""): dict(row)
        for row in served_chunks
        if str(row.get("access_id") or row.get("chunk_id") or "")
    }
    allowed_proposals = (
        set(str(value) for value in allowed_proposal_ids)
        if allowed_proposal_ids is not None else None
    )
    selected: list[str] = []
    comparisons: list[dict[str, Any]] = []
    rejected = list(base.get("rejected") or ())
    citation_count = 0
    valid_citation_count = 0
    for comparison in base.get("comparisons") or ():
        fact_id = str(comparison["fact_id"])
        raw = raw_by_id.get(fact_id) or {}
        reason = ""
        if allowed_proposals is not None and fact_id not in allowed_proposals:
            reason = "outside_proposals"
        chain = raw.get("evidence_chain") or ()
        if not isinstance(chain, list) or not chain:
            reason = reason or "missing_evidence_chain"
            chain = ()
        cleaned_chain: list[dict[str, Any]] = []
        grounded_supports: set[str] = set()
        grounded_contrasts: set[str] = set()
        for item in chain:
            if not isinstance(item, Mapping):
                continue
            citation_count += 1
            access_id = str(item.get("access_id") or item.get("chunk_id") or "")
            quote = _SPACE_RE.sub(" ", str(item.get("quote") or "").strip())
            candidate_id = str(item.get("candidate_id") or "")
            effect = str(item.get("effect") or "").strip().lower()
            chunk = chunks.get(access_id)
            item_reason = ""
            if chunk is None:
                item_reason = "unserved_chunk"
            elif not quote:
                item_reason = "missing_quote"
            elif quote not in _SPACE_RE.sub(
                " ", str(chunk.get("text") or "").strip(),
            ):
                item_reason = "quote_mismatch"
            elif candidate_id not in branch_ids:
                item_reason = "unknown_candidate"
            elif effect not in CHAIN_EFFECTS:
                item_reason = "invalid_chain_effect"
            elif require_candidate_alignment and not _candidate_matches_branch(
                str(chunk.get("candidate") or ""), candidate_id, candidates,
            ):
                item_reason = "chunk_candidate_mismatch"
            if item_reason:
                rejected.append({
                    "fact_id": fact_id,
                    "chunk_id": access_id,
                    "reason": item_reason,
                })
                continue
            valid_citation_count += 1
            if effect == "supports":
                grounded_supports.add(candidate_id)
            elif effect in {"against", "weaker"}:
                grounded_contrasts.add(candidate_id)
            cleaned_chain.append({
                "access_id": access_id,
                "chunk_id": str(chunk.get("chunk_id") or ""),
                "quote": quote,
                "candidate_id": candidate_id,
                "effect": effect,
                "link": str(item.get("link") or ""),
            })
        if require_complete_grounding:
            expected_supports = set(comparison["supports"])
            expected_contrasts = set(comparison["contrasts_with"])
            if not expected_supports.issubset(grounded_supports):
                reason = reason or "ungrounded_support"
            if not expected_contrasts.issubset(grounded_contrasts):
                reason = reason or "ungrounded_contrast"
        elif not cleaned_chain:
            reason = reason or "missing_valid_retrieval_citation"
        if reason:
            rejected.append({"fact_id": fact_id, "reason": reason})
            continue
        selected.append(fact_id)
        comparisons.append({
            **comparison,
            "knowledge_status": (
                "fully_grounded"
                if require_complete_grounding else "retrieval_informed"
            ),
            "evidence_chain": cleaned_chain,
        })
    verdict = str(response.get("verdict") or "").strip().lower()
    return {
        "verdict": "select" if selected else "none",
        "best_fact_id": selected[0] if selected else "",
        "ranked_fact_ids": selected,
        "concept_keys": {
            row["fact_id"]: row["concept_key"] for row in comparisons
        },
        "comparisons": comparisons,
        "rejected": rejected,
        "schema_valid": bool(selected) or verdict in {"none", "abstain", "stop"},
        "citation_count": citation_count,
        "valid_citation_count": valid_citation_count,
        "citation_integrity": (
            valid_citation_count / citation_count if citation_count else 1.0
        ),
        "grounded_chain_count": len(comparisons),
        "attempted_chain_count": len(base.get("comparisons") or ()),
    }


def catalog_manifest(
    excerpts: Sequence[Mapping[str, Any]],
    *,
    asset_hashes: Mapping[str, str],
    hydration_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a stable metadata envelope for a frozen excerpt catalogue."""
    return {
        "schema_version": 1,
        "asset_hashes": dict(sorted(asset_hashes.items())),
        "catalog_hash": excerpt_catalog_hash(excerpts),
        "n_excerpts": len(excerpts),
        "n_facts": len({
            (str(row.get("case_id") or ""), str(row.get("fact_id") or ""))
            for row in excerpts
        }),
        "hydration_audit": dict(hydration_audit),
    }
