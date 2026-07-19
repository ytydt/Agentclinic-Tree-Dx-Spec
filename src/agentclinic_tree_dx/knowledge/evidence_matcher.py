"""EvidenceMatcher: fuzzy-match vignette evidence items to standardised phenotypes.

Primary: embedding-based semantic matching via EmbeddingIndex (if available).
Fallback: token overlap (Jaccard similarity on word tokens) + substring containment.
"""

from __future__ import annotations

import re
import logging
from typing import Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from .embedding_index import EmbeddingIndex

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "is", "was", "are", "were",
    "with", "for", "to", "and", "or", "no", "not", "has", "had",
    "this", "that", "by", "at", "from", "but", "be", "been",
    "patient", "patients", "history", "exam", "finding", "findings",
    "shows", "showed", "reveals", "revealed", "noted", "present",
    "demonstrates", "demonstrated",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower())) - _STOP_WORDS


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class EvidenceMatcher:
    """Match free-text evidence items to a set of standardised phenotype terms.

    When an EmbeddingIndex is provided, uses semantic similarity as the primary
    matching strategy (cosine similarity on sentence embeddings). Falls back to
    Jaccard token overlap when embeddings are unavailable.
    """

    def __init__(
        self,
        phenotype_vocabulary: Sequence[str],
        embedding_index: Optional["EmbeddingIndex"] = None,
    ) -> None:
        self._phenotypes = list(phenotype_vocabulary)
        self._phenotype_tokens = [_tokenize(p) for p in self._phenotypes]
        self._phenotype_lower = [p.lower() for p in self._phenotypes]
        self._phenotype_set = set(p.lower() for p in self._phenotypes)
        self._embedding_index = embedding_index

    def match(
        self,
        evidence_text: str,
        *,
        threshold: float = 0.35,
        max_matches: int = 5,
    ) -> list[dict]:
        """Find standardised phenotypes matching the evidence text.

        Returns list of {phenotype, score} dicts sorted by descending score.
        """
        if self._embedding_index and self._embedding_index.is_ready:
            emb_results = self._embedding_index.search(
                evidence_text, top_k=max_matches, threshold=max(threshold, 0.45)
            )
            if emb_results:
                matched = []
                for r in emb_results:
                    text = r["text"]
                    if text.lower() in self._phenotype_set:
                        matched.append({"phenotype": text, "score": r["score"]})
                    elif r.get("hpo_id"):
                        for p in self._phenotypes:
                            if p.lower() == text.lower():
                                matched.append({"phenotype": p, "score": r["score"]})
                                break
                if matched:
                    return matched[:max_matches]

        return self._match_jaccard(evidence_text, threshold=threshold, max_matches=max_matches)

    def _match_jaccard(
        self,
        evidence_text: str,
        *,
        threshold: float = 0.35,
        max_matches: int = 5,
    ) -> list[dict]:
        """Jaccard token overlap fallback matching."""
        ev_tokens = _tokenize(evidence_text)
        ev_lower = evidence_text.strip().lower()

        scored: list[tuple[float, str]] = []
        for i, (pheno, ptokens) in enumerate(
            zip(self._phenotypes, self._phenotype_tokens)
        ):
            jac = _jaccard(ev_tokens, ptokens)
            plow = self._phenotype_lower[i]
            if plow in ev_lower or ev_lower in plow:
                jac = max(jac, 0.6)
            if jac >= threshold:
                scored.append((jac, pheno))

        scored.sort(key=lambda x: -x[0])
        return [
            {"phenotype": pheno, "score": round(score, 3)}
            for score, pheno in scored[:max_matches]
        ]

    def match_batch(
        self,
        evidence_items: list[str],
        *,
        threshold: float = 0.35,
        max_per_item: int = 3,
    ) -> dict[str, list[dict]]:
        """Match multiple evidence items; returns {evidence_text → matches}."""
        if self._embedding_index and self._embedding_index.is_ready:
            batch_results = self._embedding_index.search_batch(
                evidence_items, top_k=max_per_item, threshold=max(threshold, 0.45)
            )
            result = {}
            for ev in evidence_items:
                emb_hits = batch_results.get(ev, [])
                matched = []
                for r in emb_hits:
                    text = r["text"]
                    if text.lower() in self._phenotype_set:
                        matched.append({"phenotype": text, "score": r["score"]})
                if matched:
                    result[ev] = matched[:max_per_item]
                else:
                    result[ev] = self._match_jaccard(ev, threshold=threshold, max_matches=max_per_item)
            return result

        return {
            ev: self.match(ev, threshold=threshold, max_matches=max_per_item)
            for ev in evidence_items
        }
