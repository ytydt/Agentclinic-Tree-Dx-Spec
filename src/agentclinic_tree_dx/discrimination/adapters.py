"""Evidence adapters used by discrimination profiles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .config import DiscAgentConfig


def _norm(value: str) -> str:
    return " ".join((value or "").lower().split())


class ResearchClaimAdapter:
    """Read research-only claims without crossing into the clinical claim index."""

    def __init__(self, cfg: DiscAgentConfig):
        self.cfg = cfg
        path = Path(cfg.research_claims)
        if path.suffix.lower() == ".jsonl":
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = payload.get("claims", []) if isinstance(payload, dict) else payload
        self.claims = [
            dict(claim) for claim in rows
            if isinstance(claim, dict) and self._research_valid(claim)
        ]

    @staticmethod
    def _research_valid(claim: Mapping[str, Any]) -> bool:
        consumers = {str(value) for value in claim.get("allowed_consumers") or ()}
        return (
            claim.get("claim_status") == "research_validated"
            and any(value.startswith("research_") for value in consumers)
        )

    @staticmethod
    def _candidate_name(value: Any) -> str:
        return str(value.get("name", "") if isinstance(value, dict) else value or "")

    @staticmethod
    def _finding_surface(claim: Mapping[str, Any]) -> str:
        finding = claim.get("finding") or claim.get("finding_state") or {}
        if isinstance(finding, dict):
            return str(finding.get("surface") or finding.get("finding") or "")
        return str(finding)

    def _mode_accepts(self, claim: Mapping[str, Any]) -> bool:
        mode = self.cfg.research_evidence_mode
        claim_type = str(claim.get("claim_type") or "")
        derived = bool(claim.get("derived")) or claim_type == "derived_contrast"
        unary = claim_type == "candidate_effect"
        pair = bool(claim.get("candidate_b")) and not derived and not unary
        return (
            (mode == "pair_direct" and pair)
            or (mode == "unary" and unary)
            or (mode == "composed" and derived)
            or (mode == "graph" and (derived or pair))
        )

    @staticmethod
    def _provenance(claim: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = claim.get("provenance_bundle") or claim.get("provenance") or []
        if isinstance(rows, dict):
            rows = [rows]
        provenance = [dict(row) for row in rows if isinstance(row, dict)]
        if claim.get("quote") and not any(
            row.get("quote") == claim["quote"] for row in provenance
        ):
            provenance.append({"quote": claim["quote"]})
        return provenance

    def evidence(
        self, finding: str, candidates: list[str], top_k: int
    ) -> list[dict[str, Any]]:
        candidate_norms = {_norm(value): value for value in candidates}
        out: list[dict[str, Any]] = []
        for claim in self.claims:
            if not self._mode_accepts(claim):
                continue
            surface = self._finding_surface(claim)
            if surface and _norm(surface) != _norm(finding):
                continue
            left = self._candidate_name(claim.get("candidate_a"))
            right = self._candidate_name(claim.get("candidate_b"))
            if left and _norm(left) not in candidate_norms:
                continue
            if right and _norm(right) not in candidate_norms:
                continue
            effect = str(claim.get("candidate_effect") or claim.get("relation") or "")
            candidate = right if effect.endswith("_b") and right else left
            provenance = self._provenance(claim)
            quotes = [
                str(row.get("quote") or row.get("text"))
                for row in provenance
                if row.get("quote") or row.get("text")
            ]
            if self.cfg.research_evidence_mode == "graph" \
                    and not self.cfg.research_hydrate:
                quotes = []
            premise_ids = claim.get("premise_claim_ids") or []
            path = (
                {"claim_ids": list(premise_ids),
                 "mode": self.cfg.research_evidence_mode}
                if premise_ids or self.cfg.research_evidence_mode == "graph"
                else None
            )
            prefix = f"[research-only {self.cfg.research_evidence_mode} {effect}]"
            if path:
                prefix += " " + json.dumps(
                    path, ensure_ascii=False, sort_keys=True)
            out.append({
                "chunk_id": str(claim.get("claim_id") or ""),
                "source": "CCEG_RESEARCH_" + self.cfg.research_evidence_mode.upper(),
                "candidate": candidate,
                "text": f"{prefix} {' '.join(quotes)}".strip()[:400],
                "score": float(
                    (claim.get("extraction") or {}).get("confidence", 1.0)),
                "claim_id": str(claim.get("claim_id") or ""),
                "claim_type": str(claim.get("claim_type") or ""),
                "candidate_effect": effect,
                "path": path,
                "provenance": provenance,
            })
        out.sort(key=lambda row: (-row["score"], row["claim_id"]))
        return out[:top_k]
