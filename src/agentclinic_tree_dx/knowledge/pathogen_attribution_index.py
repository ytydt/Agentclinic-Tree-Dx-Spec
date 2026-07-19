"""Provenance-preserving pathogen attribution index for evaluation adapters."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class PathogenEdge:
    syndrome: str
    organism_id: str
    organism: str
    relation: str
    source: str
    provenance: str
    strength: str = "weak"


@dataclass(frozen=True)
class Attribution:
    organism_id: str | None
    organism: str | None
    decision: str
    strength: str
    evidence: tuple[PathogenEdge, ...]
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class PathogenAttributionIndex:
    """Combines typed edges without converting co-mentions into likelihoods."""

    def __init__(self, edges: Iterable[PathogenEdge] = ()):
        self.edges = list(edges)

    @classmethod
    def from_json(cls, path: str | Path) -> "PathogenAttributionIndex":
        payload = json.loads(Path(path).read_text())
        return cls(PathogenEdge(**e) for e in payload.get("edges", []))

    @staticmethod
    def _norm(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())

    def query(self, syndrome: str, relation: str | None = None) -> list[PathogenEdge]:
        s = self._norm(syndrome)
        return [
            edge for edge in self.edges
            if (self._norm(edge.syndrome) == s
                or self._norm(edge.syndrome) in s
                or s in self._norm(edge.syndrome))
            and (relation is None or edge.relation == relation)
        ]

    @classmethod
    def _syndrome_compatible(cls, requested: str, indexed: str) -> bool:
        """Conservative family/subtype compatibility for culture-confirmed use."""
        req, idx = cls._norm(requested), cls._norm(indexed)
        if req in idx or idx in req:
            return True
        req_tokens, idx_tokens = req.split(), idx.split()
        # Clinical syndrome heads such as meningitis/endocarditis/pneumonia are
        # stable across organism-specific subtype labels. This is used only
        # after the culture has already named the organism.
        return bool(req_tokens and idx_tokens and req_tokens[-1] == idx_tokens[-1]
                    and len(req_tokens[-1]) >= 6)

    def attribute(
        self,
        syndrome: str,
        *,
        culture_result: str | None = None,
        host_factors: Iterable[str] = (),
        vignette_only: bool = False,
    ) -> Attribution:
        edges = self.query(syndrome)
        if culture_result:
            culture = self._norm(culture_result)
            matches = [
                e for e in self.edges if e.relation in {
                    "culture_confirms", "causative_agent"
                }
                and (self._norm(e.organism) in culture
                     or self._norm(e.organism_id) in culture)
                and self._syndrome_compatible(syndrome, e.syndrome)
            ]
            if matches:
                max_specificity = max(
                    len(self._norm(e.organism).split()) for e in matches)
                matches = [
                    e for e in matches
                    if len(self._norm(e.organism).split()) == max_specificity
                ]
            ids = {e.organism_id for e in matches}
            ncbi_ids = {identifier for identifier in ids
                        if identifier.startswith("NCBITaxon:")}
            if len(ids) > 1 and len(ncbi_ids) == 1:
                canonical = next(iter(ncbi_ids))
                matches = [e for e in matches if e.organism_id == canonical]
                ids = {canonical}
            if len(ids) == 1:
                edge = matches[0]
                return Attribution(edge.organism_id, edge.organism, "resolved",
                                   "decisive", tuple(matches),
                                   "culture identifies organism; KB validates "
                                   "the syndrome-causative-agent edge")
            if matches:
                return Attribution(
                    None, None, "abstain", "none", tuple(matches),
                    f"ambiguous organism identities: {sorted(ids)}")
        if vignette_only or not culture_result:
            priors = [e for e in edges if e.relation in {
                "causative_agent", "host_factor_shifts_prior"
            }]
            # Etiologic associations and host factors narrow a differential but
            # do not identify a species in an individual patient.
            return Attribution(None, None, "abstain", "none", tuple(priors),
                               "request culture/PCR; phenotype alone is insufficient")
        return Attribution(None, None, "abstain", "none", tuple(),
                           "no provenance-grounded confirming edge")
