"""Isolated index for synthetic CCEG research-review artifacts.

This index deliberately does not adapt records into clinical evidence excerpts.
Research decisions are experiment outputs, never validated clinical claims.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .cceg_claim_index import candidate_key, canonical_pair
from .cceg_schema import validate_claim

RESEARCH_INDEX_VERSION = 1


def validate_research_claim(record: Mapping[str, Any]) -> list[str]:
    """Admit only schema-v2 claims promoted by synthetic dual review."""
    errors = validate_claim(record)
    consumers = {
        str(value) for value in record.get("allowed_consumers") or ()}
    if record.get("schema_version") != 2:
        errors.append("schema_version: research index requires v2")
    if record.get("claim_status") != "research_validated":
        errors.append("claim_status: expected research_validated")
    if (record.get("review") or {}).get("mode") != "synthetic_dual_llm":
        errors.append("review.mode: expected synthetic_dual_llm")
    if not any(value.startswith("research_") for value in consumers):
        errors.append("allowed_consumers: research consumer required")
    return errors


class CCEGResearchClaimIndex:
    """In-memory lookup that admits only explicitly research-only records."""

    def __init__(self, claims: Iterable[Mapping[str, Any]] = ()) -> None:
        self.claims: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []
        self._pairs: dict[tuple[str, str], list[int]] = defaultdict(list)
        self._candidate: dict[str, list[int]] = defaultdict(list)
        seen: set[str] = set()
        for raw in claims:
            record = dict(raw)
            errors = validate_research_claim(record)
            record_id = str(record.get("claim_id") or "")
            if record_id in seen:
                errors.append("claim_id: duplicate within index")
            if errors:
                self.rejected.append({
                    "claim_id": record_id,
                    "errors": errors,
                })
                continue
            seen.add(record_id)
            position = len(self.claims)
            self.claims.append(record)
            self._candidate[candidate_key(record["candidate_a"])].append(position)
            if record.get("candidate_b"):
                self._candidate[candidate_key(record["candidate_b"])].append(position)
                pair, _ = canonical_pair(record["candidate_a"], record["candidate_b"])
                self._pairs[pair].append(position)

    @property
    def is_ready(self) -> bool:
        return bool(self.claims)

    @classmethod
    def from_path(cls, path: str | Path) -> "CCEGResearchClaimIndex":
        path = Path(path)
        if path.is_dir():
            path = path / "research_claims.jsonl"
        if path.suffix == ".jsonl":
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("claims", []) if isinstance(payload, dict) else payload
        return cls(rows)

    from_file = from_path

    def lookup(
        self,
        candidate_a: str | Mapping[str, Any],
        candidate_b: str | Mapping[str, Any] | None = None,
        *,
        decisions: Iterable[str] | None = None,
    ) -> list[dict[str, Any]]:
        allowed = set(decisions) if decisions is not None else None
        if candidate_b is None:
            positions = self._candidate.get(candidate_key(candidate_a), ())
        else:
            pair, _ = canonical_pair(candidate_a, candidate_b)
            positions = self._pairs.get(pair, ())
        result = [
            self.claims[position]
            for position in positions
            if allowed is None or "accept" in allowed
        ]
        return sorted(result, key=lambda row: str(row["claim_id"]))

    search = lookup
    query = lookup

    def audit_report(self) -> dict[str, Any]:
        return {
            "artifact_kind": "cceg_research_claim_index",
            "research_only": True,
            "index_version": RESEARCH_INDEX_VERSION,
            "indexed_claims": len(self.claims),
            "rejected_claims": len(self.rejected),
            "rejections": self.rejected,
        }
