"""Bounded CCEG graph traversal with provenance and quote hydration."""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable, Mapping

from .cceg_claim_index import (
    CCEGClaimIndex,
    candidate_key,
    claim_to_evidence_excerpt,
    finding_matches,
)
from .cceg_compose import CCEGComposer


def load_chunk_texts(path: str | Path) -> dict[str, str]:
    """Load ``chunk_id/id -> content/text`` from JSON or JSONL corpus metadata."""
    path = Path(path)
    rows: Iterable[Any]
    if path.suffix.lower() == ".jsonl":
        rows = (
            json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()
        )
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            rows = payload.get("chunks") or payload.get("rows") or [payload]
        else:
            rows = payload
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        chunk_id = row.get("chunk_id") or row.get("id")
        text = row.get("content")
        if text is None:
            text = row.get("text")
        if chunk_id and isinstance(text, str):
            out[str(chunk_id)] = text
    return out


def hydrate_quote(
    claim: Mapping[str, Any],
    chunk_texts: Mapping[str, str],
) -> tuple[str | None, str | None]:
    """Return the source-resident quote, or an audit reason on failure."""
    provenance = claim["provenance"]
    chunk_id = str(provenance["chunk_id"])
    text = chunk_texts.get(chunk_id)
    if text is None:
        return None, "missing_chunk"
    quote = str(provenance["quote"])
    span = provenance.get("quote_span") or ()
    if len(span) == 2 and 0 <= span[0] < span[1] <= len(text):
        sliced = text[span[0]:span[1]]
        if sliced == quote:
            return sliced, None
    if quote in text:
        return quote, None
    return None, "quote_mismatch"


class CCEGGraphRetriever:
    """Traverse candidate-pair claim edges for at most one or two hops."""

    def __init__(
        self,
        claim_index: CCEGClaimIndex,
        *,
        chunk_texts: Mapping[str, str] | None = None,
        adjacency_path: str | Path | None = None,
        max_hops: int = 2,
        degree_cap: int = 20,
    ) -> None:
        if max_hops not in (1, 2):
            raise ValueError("max_hops must be 1 or 2")
        if degree_cap < 1:
            raise ValueError("degree_cap must be positive")
        self.claim_index = claim_index
        self.chunk_texts = dict(chunk_texts or {})
        self.max_hops = max_hops
        self.degree_cap = degree_cap
        self.audit: list[dict[str, str]] = []
        self.compose_audit: dict[str, Any] = {"rejected": 0, "reasons": {}}
        self._adjacency: dict[str, list[tuple[str, int]]] = defaultdict(list)
        compose_claim_ids: set[str] | None = None
        if adjacency_path is not None:
            payload = json.loads(Path(adjacency_path).read_text(encoding="utf-8"))
            rows_by_node = payload.get("adjacency", payload)
            compose_claim_ids = set()
            by_claim_id = {
                str(claim["claim_id"]): position
                for position, claim in enumerate(claim_index.claims)
            }
            for node, edges in rows_by_node.items():
                for edge in edges:
                    claim_id = str(edge.get("claim_id") or "")
                    if claim_id not in by_claim_id:
                        raise ValueError(
                            f"adjacency references unknown claim_id: {claim_id}")
                    self._adjacency[str(node)].append((
                        str(edge["neighbor"]), by_claim_id[claim_id]))
                    compose_claim_ids.add(claim_id)
            bipartite = payload.get("bipartite", {})
            for edge in bipartite.get("edges", ()):
                claim_id = str(edge.get("claim_id") or "")
                if claim_id not in by_claim_id:
                    raise ValueError(
                        f"bipartite adjacency references unknown claim_id: {claim_id}")
                compose_claim_ids.add(claim_id)
        else:
            for position, claim in enumerate(claim_index.claims):
                if not claim.get("candidate_b"):
                    continue
                left = candidate_key(claim["candidate_a"])
                right = candidate_key(claim["candidate_b"])
                self._adjacency[left].append((right, position))
                self._adjacency[right].append((left, position))
        self.composer = CCEGComposer(
            claim_index, allowed_claim_ids=compose_claim_ids)
        unary_claim_ids = {
            row["claim_id"] for row in claim_index.unary_edges()}
        self._compose_edge_count = len(
            unary_claim_ids
            if compose_claim_ids is None
            else unary_claim_ids & compose_claim_ids
        )
        for node in self._adjacency:
            self._adjacency[node].sort(
                key=lambda item: str(claim_index.claims[item[1]]["claim_id"]))

    @classmethod
    def from_paths(
        cls,
        claim_index: str | Path,
        corpus_metadata: str | Path,
        **kwargs: Any,
    ) -> "CCEGGraphRetriever":
        return cls(
            CCEGClaimIndex.from_path(claim_index),
            chunk_texts=load_chunk_texts(corpus_metadata),
            **kwargs,
        )

    @property
    def is_ready(self) -> bool:
        return self.claim_index.is_ready and bool(
            self._adjacency or self._compose_edge_count)

    def _hydrated_claim(self, position: int) -> dict[str, Any] | None:
        claim = self.claim_index.claims[position]
        quote, reason = hydrate_quote(claim, self.chunk_texts)
        if reason:
            self.audit.append({
                "claim_id": str(claim["claim_id"]),
                "chunk_id": str(claim["provenance"]["chunk_id"]),
                "reason": reason,
            })
            return None
        hydrated = dict(claim)
        hydrated["provenance"] = dict(claim["provenance"])
        hydrated["provenance"]["quote"] = quote
        return hydrated

    def retrieve(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any],
        finding: str | Mapping[str, Any] | None = None,
        *,
        max_hops: int | None = None,
        degree_cap: int | None = None,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Return hydrated simple paths, shortest then deterministic by claim id."""
        self.audit = []
        hop_limit = self.max_hops if max_hops is None else max_hops
        cap = self.degree_cap if degree_cap is None else degree_cap
        if hop_limit not in (1, 2):
            raise ValueError("max_hops must be 1 or 2")
        if cap < 1:
            raise ValueError("degree_cap must be positive")
        start, target = candidate_key(candidate_a), candidate_key(candidate_b)
        queue = deque([(start, (start,), ())])
        results: list[dict[str, Any]] = []
        seen_claim_paths: set[tuple[str, ...]] = set()
        while queue:
            node, nodes, edge_positions = queue.popleft()
            if len(edge_positions) >= hop_limit:
                continue
            for neighbor, position in self._adjacency.get(node, ())[:cap]:
                if neighbor in nodes:
                    continue
                claim = self.claim_index.claims[position]
                if not finding_matches(claim["finding"], finding):
                    continue
                new_nodes = (*nodes, neighbor)
                new_edges = (*edge_positions, position)
                if neighbor == target:
                    hydrated: list[dict[str, Any]] = []
                    for edge_position in new_edges:
                        row = self._hydrated_claim(edge_position)
                        if row is None:
                            hydrated = []
                            break
                        hydrated.append(row)
                    if not hydrated:
                        continue
                    provenance = tuple(str(row["claim_id"]) for row in hydrated)
                    if provenance in seen_claim_paths:
                        continue
                    seen_claim_paths.add(provenance)
                    excerpts = [
                        claim_to_evidence_excerpt(
                            row,
                            candidate_order=(
                                str(row["candidate_a"]["name"]),
                                str(row["candidate_b"]["name"]),
                            ) if candidate_key(row["candidate_a"]) == new_nodes[
                                offset - 1] else (
                                str(row["candidate_b"]["name"]),
                                str(row["candidate_a"]["name"]),
                            ),
                            evidence_id=f"E{len(results) + 1}.{offset}",
                            path_provenance=provenance,
                        )
                        for offset, row in enumerate(hydrated, 1)
                    ]
                    results.append({
                        "hops": len(new_edges),
                        "nodes": list(new_nodes),
                        "claim_ids": list(provenance),
                        "path_provenance": list(provenance),
                        "evidence_excerpts": excerpts,
                    })
                    if len(results) >= top_k:
                        return results
                elif len(new_edges) < hop_limit:
                    queue.append((neighbor, new_nodes, new_edges))
        results.sort(key=lambda row: (row["hops"], row["claim_ids"]))
        return results[:top_k]

    def compose(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any],
        finding: Mapping[str, Any] | None = None,
        *,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Compose and hydrate both independent source edges."""
        self.audit = []
        derived_rows = self.composer.compose(
            candidate_a, candidate_b, finding, top_k=top_k)
        self.compose_audit = self.composer.audit_report()
        results: list[dict[str, Any]] = []
        for derived in derived_rows:
            premise_ids = derived["derivation"]["premise_claim_ids"]
            positions_by_id = {
                str(claim["claim_id"]): position
                for position, claim in enumerate(self.claim_index.claims)
            }
            hydrated = [
                self._hydrated_claim(positions_by_id[claim_id])
                for claim_id in premise_ids
            ]
            if any(row is None for row in hydrated):
                continue
            claims = [row for row in hydrated if row is not None]
            item = dict(derived)
            item["provenance_bundle"] = [
                dict(row["provenance"]) for row in claims]
            item["evidence_excerpts"] = [
                claim_to_evidence_excerpt(
                    row,
                    evidence_id=f"D{len(results) + 1}.{offset}",
                    path_provenance=premise_ids,
                )
                for offset, row in enumerate(claims, 1)
            ]
            results.append(item)
        return results

    retrieve_composed = compose

    search = retrieve
    query = retrieve

    def audit_report(self) -> dict[str, Any]:
        unique = {
            (row["claim_id"], row["chunk_id"], row["reason"]): row
            for row in self.audit
        }
        rows = list(unique.values())
        return {
            "missing_hydration": len(rows),
            "audit_only": rows,
            "composition": self.compose_audit,
        }
