"""New method (CPG §19) — Anchor-augmented entry retrieval + article closure.

Motivation (CPG §16/§18 validation, ``eval_diff_retriever_validation.py``):
the §18 oracle ceiling (8/8) is reached by selecting syndrome ENTRY ARTICLES via
``syndrome_anchor`` / ``section_path`` match and then closing over the article —
NOT by TF-IDF query→doc similarity. Pure closure (IMP-31) is therefore entry-
retrieval-bound (it can only expand articles already retrieved), and pure source-
differentiation (IMP-61) dilutes the PMC backbone that actually carries the gold.

This wrapper fixes both: it keeps a BASE retriever's ranked hits (the PMC prose
backbone) and UNIONs in chunks whose ``syndrome_anchor``/``section_path`` token-
overlap the presenting syndrome AND the clinical-feature context (parsed from the
GuidelineBranchSource query template "... clinical features: <ctx>"). Those
structurally-selected entry chunks then seed ``expand_ddx_siblings`` so the
scattered DDx body is pulled in. Union (not replace) guarantees recall ≥ base.

Note: this recovers cases whose presentation terms surface in an entry anchor.
Cases that need MECHANISM/EPONYM bridging (e.g. arm+hand weakness + Horner →
apical lung tumour) are out of scope for any retriever and are handled by the
IMP-58 normalisation + eponym/pathognomonic direct-nomination path.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

_STOP = {
    "the", "and", "with", "of", "to", "in", "a", "an", "for", "on", "patient",
    "presents", "history", "year", "old", "male", "female", "man", "woman",
    "acute", "chronic", "differential", "diagnosis", "causes", "etiology",
    "approach", "clinical", "features", "syndrome", "disorder", "deficit",
    "focal", "diffuse", "unilateral", "bilateral", "undifferentiated", "his",
    "her", "she", "he", "states", "experienced", "department", "emergency",
}


def _terms(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower())
            if len(t) > 3 and t not in _STOP}


class AnchorAugmentedRetriever:
    """Wrap a base retriever; union in anchor/section-matched entry chunks."""

    def __init__(self, base, *, max_anchor_hits: int = 25,
                 min_overlap: int = 1) -> None:
        self._base = base
        self._max_anchor = max_anchor_hits
        self._min_overlap = min_overlap
        self._anchor_rows: Optional[list[tuple[int, set[str], dict]]] = None

    @property
    def is_ready(self) -> bool:
        return bool(getattr(self._base, "is_ready", False))

    def _build_anchor_rows(self) -> None:
        meta = getattr(self._base, "_metadata", None) or []
        rows: list[tuple[int, set[str], dict]] = []
        for pos, m in enumerate(meta):
            anc = m.get("syndrome_anchor") or ""
            sec = m.get("section_path") or m.get("title") or ""
            # only index rows that carry entry semantics (anchor or a section name)
            key = _terms(anc) | _terms(sec)
            if not key:
                continue
            # prefer true entry chunks / DDx-bearing chunks as seeds
            rows.append((pos, key, m))
        self._anchor_rows = rows
        logger.info("AnchorAugmentedRetriever: %d anchorable rows", len(rows))

    @staticmethod
    def _parse_query(query: str) -> tuple[str, str]:
        """Split GuidelineBranchSource template into (syndrome, context)."""
        q = query or ""
        ctx = ""
        m = re.search(r"clinical features:\s*(.+)$", q, re.I)
        if m:
            ctx = m.group(1)
            q = q[: m.start()]
        q = re.sub(r"^(differential diagnosis of|causes and etiology of|"
                   r"approach to|causes of|etiology of)\s+", "", q.strip().lower())
        return q.strip(" ."), ctx

    def search(self, query: str, *, top_k: int = 30,
               score_threshold: float = 0.0) -> list[dict]:
        base_hits = []
        try:
            base_hits = self._base.search(
                query, top_k=top_k, score_threshold=score_threshold)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("base search failed: %s", e)
        if self._anchor_rows is None:
            self._build_anchor_rows()
        syn, ctx = self._parse_query(query)
        qterms = _terms(syn) | _terms(ctx)
        if not qterms or not self._anchor_rows:
            return base_hits
        scored: list[tuple[float, int, dict]] = []
        for pos, key, m in self._anchor_rows:
            ov = len(qterms & key)
            if ov < self._min_overlap:
                continue
            bonus = 0.5 if m.get("entry_type") == "syndrome_entry" else 0.0
            bonus += 0.3 if m.get("wiki_links") else 0.0
            scored.append((ov + bonus, pos, m))
        scored.sort(key=lambda t: -t[0])
        seen = {h.get("id") for h in base_hits}
        out = list(base_hits)
        hit_from = getattr(self._base, "_hit_from_meta", None) or \
            getattr(self._base, "_hit", None)
        for sc, pos, m in scored[: self._max_anchor]:
            cid = m.get("id")
            if cid in seen:
                continue
            seen.add(cid)
            try:
                h = hit_from(m, pos, float(sc)) if hit_from is getattr(
                    self._base, "_hit_from_meta", None) else hit_from(m, float(sc))
            except TypeError:
                h = hit_from(m, float(sc))
            out.append(h)
        return out

    def expand_ddx_siblings(self, hits: list[dict]) -> list[dict]:
        if hasattr(self._base, "expand_ddx_siblings"):
            return self._base.expand_ddx_siblings(hits)
        return hits
