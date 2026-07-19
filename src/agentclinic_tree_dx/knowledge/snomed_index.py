"""SNOMED CT knowledge index — synonym bridging + clinical relation graph.

Loads the artifacts produced by ``scripts/build_snomed_knowledge.py``:
  - snomed_concepts.json    {cid: {fsn, preferred, tag, synonyms[]}}
  - snomed_term_index.json  {normalized_term: [cid, ...]}
  - snomed_relations.json   [{src, dst, type}]

Provides two capabilities used by the retriever (both opt-in):
  1. ``expand_synonyms(name)`` — widen a disease/finding string with SNOMED
     synonyms (improves LR-cache / phenotype matching coverage).
  2. ``two_hop_links(finding, disease)`` — does a finding connect to a disease
     through one intermediate clinical concept (syndrome chain)?  Returns the
     bridging concept names so the annotator can be told the mechanism.

Designed to fail safe: a missing/invalid artifact disables the layer rather
than raising.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")

# Relation types that point "outward" from a clinical finding toward an
# anatomical / morphological / causal intermediate useful for chaining.
_CHAIN_FORWARD = {
    "finding_site", "associated_morphology", "causative_agent", "due_to",
    "interprets", "associated_with", "pathological_process",
    "has_definitional_manifestation",
}


def _norm(term: str) -> str:
    return _WS_RE.sub(" ", (term or "").strip().lower())


class SnomedIndex:
    def __init__(
        self,
        concepts: dict,
        term_index: dict,
        relations: list,
    ):
        self.concepts = concepts
        self.term_index = term_index
        # adjacency: cid -> list[(type, dst)] and reverse dst -> list[(type, src)]
        self._fwd: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._rev: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for r in relations:
            src, dst, typ = r.get("src"), r.get("dst"), r.get("type")
            if not src or not dst:
                continue
            self._fwd[src].append((typ, dst))
            self._rev[dst].append((typ, src))

    # ── construction ──────────────────────────────────────────────────────────
    @classmethod
    def from_files(
        cls,
        concepts_path: str,
        term_index_path: str,
        relations_path: Optional[str] = None,
    ) -> Optional["SnomedIndex"]:
        try:
            concepts = json.loads(Path(concepts_path).read_text(encoding="utf-8"))
            term_index = json.loads(Path(term_index_path).read_text(encoding="utf-8"))
            relations = []
            if relations_path and Path(relations_path).exists():
                relations = json.loads(Path(relations_path).read_text(encoding="utf-8"))
            logger.info(
                "SnomedIndex loaded: %d concepts, %d terms, %d relations",
                len(concepts), len(term_index), len(relations),
            )
            return cls(concepts, term_index, relations)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("SnomedIndex load failed (%s); SNOMED layer disabled", e)
            return None

    # ── lookups ─────────────────────────────────────────────────────────────
    def resolve(self, name: str) -> list[str]:
        """Return concept ids whose preferred/synonym matches *name* (normalized)."""
        return list(self.term_index.get(_norm(name), []))

    def expand_synonyms(self, name: str, max_terms: int = 12) -> list[str]:
        """All SNOMED surface forms (preferred + synonyms) for *name*."""
        out: list[str] = []
        seen = set()
        for cid in self.resolve(name):
            c = self.concepts.get(cid, {})
            for t in [c.get("preferred", ""), *c.get("synonyms", [])]:
                nt = _norm(t)
                if t and nt not in seen:
                    seen.add(nt)
                    out.append(t)
                    if len(out) >= max_terms:
                        return out
        return out

    def preferred(self, cid: str) -> str:
        return self.concepts.get(cid, {}).get("preferred", "")

    def two_hop_links(
        self, finding: str, disease: str, max_results: int = 3
    ) -> list[dict]:
        """Find one-intermediate chains finding → X → disease.

        Returns [{"intermediate": name, "via": (type1, type2)}] for clinical
        concepts X reachable from the finding that also relate to the disease.
        """
        f_ids = set(self.resolve(finding))
        d_ids = set(self.resolve(disease))
        if not f_ids or not d_ids:
            return []
        # concepts adjacent to the disease (either direction)
        disease_adj: dict[str, str] = {}
        for did in d_ids:
            for typ, nb in self._fwd.get(did, []):
                disease_adj.setdefault(nb, typ)
            for typ, nb in self._rev.get(did, []):
                disease_adj.setdefault(nb, typ)
        results: list[dict] = []
        seen_mid = set()
        for fid in f_ids:
            for typ1, mid in self._fwd.get(fid, []) + self._rev.get(fid, []):
                if mid in disease_adj and mid not in seen_mid:
                    seen_mid.add(mid)
                    results.append({
                        "intermediate": self.preferred(mid) or mid,
                        "via": [typ1, disease_adj[mid]],
                    })
                    if len(results) >= max_results:
                        return results
        return results
