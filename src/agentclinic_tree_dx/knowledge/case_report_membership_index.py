"""Case-report membership/phenotype lookup with no directional semantics."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .cceg_claim_index import (
    candidate_key,
    claim_to_evidence_excerpt,
    finding_matches,
)
from .cceg_schema import validate_claim

ALLOWED_TYPES = frozenset({"membership", "phenotype_assertion"})
ALLOWED_SOURCES = frozenset({"case_report_list", "case_report_prose"})


class CaseReportMembershipIndex:
    """Serve only anecdotal candidate membership and phenotype assertions."""

    def __init__(self, claims: Iterable[Mapping[str, Any]] = ()) -> None:
        self.claims: list[dict[str, Any]] = []
        self.rejected: list[dict[str, Any]] = []
        self._candidate: dict[str, list[int]] = defaultdict(list)
        seen: set[str] = set()
        for raw in claims:
            claim = dict(raw)
            errors = validate_claim(claim)
            claim_id = str(claim.get("claim_id", ""))
            if claim_id in seen:
                errors.append("claim_id: duplicate within membership index")
            if claim.get("claim_status") != "grounded":
                errors.append("claim_status: membership index requires grounded")
            if claim.get("claim_type") not in ALLOWED_TYPES:
                errors.append("claim_type: case-report index forbids direction")
            if claim.get("source_class") not in ALLOWED_SOURCES:
                errors.append("source_class: case-report source required")
            if claim.get("strength") != "anecdotal":
                errors.append("strength: case-report evidence must be anecdotal")
            if "p5_veto" not in (claim.get("allowed_consumers") or []):
                errors.append("allowed_consumers: p5_veto required for serving")
            if errors:
                self.rejected.append({"claim_id": claim_id, "errors": errors})
                continue
            seen.add(claim_id)
            position = len(self.claims)
            self.claims.append(claim)
            self._candidate[candidate_key(claim["candidate_a"])].append(position)

    @property
    def is_ready(self) -> bool:
        return bool(self.claims)

    @classmethod
    def from_path(cls, path: str | Path) -> "CaseReportMembershipIndex":
        path = Path(path)
        if path.is_dir():
            path = path / "claims.jsonl"
        if path.suffix.lower() == ".jsonl":
            rows = [
                json.loads(line) for line in path.read_text(
                    encoding="utf-8").splitlines() if line.strip()
            ]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("claims", []) if isinstance(payload, dict) else payload
        return cls(rows)

    from_file = from_path

    def lookup(
        self,
        candidate: str | Mapping[str, Any],
        finding: str | Mapping[str, Any] | None = None,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        out = [
            self.claims[position]
            for position in self._candidate.get(candidate_key(candidate), ())
            if finding_matches(self.claims[position]["finding"], finding)
        ]
        out.sort(key=lambda row: (
            -float(row.get("extraction", {}).get("confidence", 0.0)),
            str(row["claim_id"]),
        ))
        return out[:top_k] if top_k is not None else out

    search = lookup
    query = lookup

    def evidence_excerpts(
        self,
        candidate: str | Mapping[str, Any],
        finding: str | Mapping[str, Any] | None = None,
        *,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        excerpts = []
        for index, claim in enumerate(
            self.lookup(candidate, finding, top_k=top_k), 1
        ):
            excerpt = claim_to_evidence_excerpt(claim, evidence_id=f"E{index}")
            # Explicitly expose the safe consumer semantics.  These records must
            # never be interpreted as rule-in/rule-out directions.
            excerpt["evidence_kind"] = (
                "membership" if claim["claim_type"] == "membership"
                else "phenotype"
            )
            excerpt["direction"] = None
            excerpts.append(excerpt)
        return excerpts

    def audit_report(self) -> dict[str, Any]:
        return {
            "served_claims": len(self.claims),
            "rejected_claims": len(self.rejected),
            "rejections": self.rejected,
            "emits_direction": False,
        }
