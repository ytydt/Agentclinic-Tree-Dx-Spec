"""IMP-61 — Differentiated (source-stratified) CPG retriever (CPG §16).

A drop-in, ``RAGRetriever``-compatible retriever over the CPG corpus that fixes
the *source-imbalance* defect proven in CPG §16: with PMC-OA at ~88% of the
corpus, a single unified TF-IDF computes IDF globally and buries the terse
WikEM/Merck syndrome-ENTRY chunks under thousands of PMC prose chunks (WikEM
entry Recall@10 0.659, true rank median 38). This retriever instead keeps one
TF-IDF sub-index per source bucket (built offline by
``scripts/build_differentiated_cpg_index.py``) and, per query:

  1. searches every bucket independently (isolated IDF, no cross-source pollution);
  2. fuses the per-bucket rank lists by Reciprocal Rank Fusion (k=60), i.e. by
     RANK not raw score — so incomparable TF-IDF scales can't let one source
     dominate, giving every source a fair slot (anti-flooding);
  3. re-ranks the fused head with a syndrome-ENTRY boost (entry_type /
     anchor-token / section-path match) so true entry chunks surface.

It exposes the same ``search`` / ``expand_ddx_siblings`` / ``is_ready`` surface
as :class:`RAGRetriever`, so :class:`GuidelineBranchSource` consumes it
unchanged. Article-closure (``expand_ddx_siblings``) reuses the §18 mechanism:
once a syndrome entry is retrieved, the scattered DDx body is pulled in via the
``source_id`` inverted index + WikEM ``wiki_links`` synthetic chunk.
"""
from __future__ import annotations

import json
import logging
import pickle
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DDX_USEFUL = frozenset(
    {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"})

# Per-bucket query reshaping: each source's entry is phrased to match how that
# source organises its differential material (CPG §16.4 ③ query routing).
_QFORM = {
    "wikem": "{S}",
    "merck": "approach to {S} differential diagnosis",
    "nice": "{S} assessment diagnosis recommendations",
    "society": "{S} diagnosis evaluation management",
    "pmc": "differential diagnosis of {S} causes evaluation",
}


def _toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


class DifferentiatedCPGRetriever:
    """Source-stratified TF-IDF retriever with RRF fusion + entry boost."""

    def __init__(self, index_dir: str | Path, *, fusion: str = "rrf",
                 per_bucket: Optional[int] = None) -> None:
        self._dir = Path(index_dir)
        self._metadata: list[dict] = []
        self._buckets: dict[str, tuple] = {}  # bucket -> (vec, mat, [global_idx])
        self._sid_index: Optional[dict[str, list[int]]] = None
        self._ready = False
        # IMP-61 §19.3②: equal-weight RRF was proven DETRIMENTAL (it mixes ranks
        # and dilutes the strong PMC relevance signal). ``fusion='union'`` instead
        # takes each bucket's top-N (per-bucket-normalised score), UNIONs them, and
        # re-ranks by within-source score + entry boost — guaranteeing every source
        # contributes its best entries (anti-flooding) without RRF rank-mixing.
        self._fusion = fusion
        self._per_bucket = per_bucket
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        manifest_p = self._dir / "manifest.json"
        meta_p = self._dir / "metadata.jsonl"
        if not manifest_p.exists() or not meta_p.exists():
            logger.warning("Differentiated CPG index not found at %s", self._dir)
            return
        try:
            from scipy import sparse
            with meta_p.open(encoding="utf-8") as f:
                self._metadata = [json.loads(line) for line in f if line.strip()]
            manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
            for b, idxs in manifest.get("buckets", {}).items():
                vp = self._dir / f"{b}_vec.pkl"
                mp = self._dir / f"{b}_mat.npz"
                if not vp.exists() or not mp.exists():
                    continue
                with vp.open("rb") as f:
                    vec = pickle.load(f)
                mat = sparse.load_npz(str(mp))
                self._buckets[b] = (vec, mat, list(idxs))
            self._ready = bool(self._buckets) and bool(self._metadata)
            logger.info("Differentiated CPG index loaded: %d rows, buckets=%s",
                        len(self._metadata), list(self._buckets))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load differentiated CPG index: %s", e)
            self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ---------------------------------------------------------------- search
    @staticmethod
    def _strip_query(query: str) -> str:
        """Recover the bare syndrome from GuidelineBranchSource templates like
        'differential diagnosis of {S}' / 'approach to {S}' / 'causes ... of {S}'."""
        q = (query or "").lower().strip()
        q = re.sub(r"^(differential diagnosis of|causes and etiology of|"
                   r"approach to|causes of|etiology of)\s+", "", q)
        q = re.split(r"\.\s|clinical features:", q)[0]
        return q.strip() or query

    def _bucket_search(self, vec, mat, query: str, k: int) -> list[int]:
        qv = vec.transform([query])
        scores = (mat @ qv.T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        return [int(i) for i in order if scores[i] > 0]

    def _bucket_search_scored(self, vec, mat, query: str, k: int) -> list[tuple[int, float]]:
        qv = vec.transform([query])
        scores = (mat @ qv.T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]

    def _entry_boost(self, gi: int, S_toks: set[str]) -> float:
        d = self._metadata[gi]
        bb = 0.0
        if d.get("entry_type") == "syndrome_entry":
            bb += 0.5
        anc = _toks(d.get("syndrome_anchor") or "")
        if anc and S_toks & anc:
            bb += 1.0
        sp = _toks(d.get("section_path") or "")
        if S_toks and S_toks <= sp:
            bb += 0.5
        return bb

    def search(self, query: str, *, top_k: int = 30,
               score_threshold: float = 0.0) -> list[dict]:
        if not self._ready:
            return []
        S = self._strip_query(query)
        S_toks = _toks(S)
        if self._fusion == "union":
            return self._search_union(S, S_toks, top_k)
        ranklists: list[list[int]] = []
        for b, (vec, mat, gidx) in self._buckets.items():
            q = _QFORM.get(b, "{S}").format(S=S)
            local = self._bucket_search(vec, mat, q, top_k)
            ranklists.append([gidx[i] for i in local])
        # RRF fusion (by rank, not raw score)
        fused: dict[int, float] = defaultdict(float)
        for rl in ranklists:
            for rank, gi in enumerate(rl, start=1):
                fused[gi] += 1.0 / (60 + rank)
        reranked = sorted(fused, key=lambda gi: -(fused[gi] + 0.002 * self._entry_boost(gi, S_toks)))
        out = []
        for gi in reranked[:top_k]:
            out.append(self._hit(self._metadata[gi], fused[gi]))
        return out

    def _search_union(self, S: str, S_toks: set[str], top_k: int) -> list[dict]:
        """IMP-61 UNION: each bucket contributes its top per_bucket (within-bucket
        score-normalised) entries; union + dedup + rerank by source score + entry
        boost. Guarantees terse WikEM/Merck entries are not flooded out by PMC."""
        nbk = max(1, len(self._buckets))
        pb = self._per_bucket or max(3, (top_k + nbk - 1) // nbk)
        collected: dict[int, float] = {}
        for b, (vec, mat, gidx) in self._buckets.items():
            q = _QFORM.get(b, "{S}").format(S=S)
            scored = self._bucket_search_scored(vec, mat, q, pb)
            mx = max((s for _, s in scored), default=0.0) or 1.0
            for li, s in scored:
                gi = gidx[li]
                collected[gi] = max(collected.get(gi, 0.0), s / mx)  # per-bucket norm
        reranked = sorted(collected,
                          key=lambda gi: -(collected[gi] + 0.5 * self._entry_boost(gi, S_toks)))
        return [self._hit(self._metadata[gi], collected[gi]) for gi in reranked[:top_k]]

    @staticmethod
    def _hit(meta: dict, score: float) -> dict:
        return {
            "id": meta.get("id", ""),
            "title": meta.get("title", meta.get("section_path", "")),
            "content": meta.get("content", ""),
            "article_id": meta.get("article_id", meta.get("source_id", "")),
            "source_id": meta.get("source_id", ""),
            "chunk_type": meta.get("chunk_type"),
            "entry_type": meta.get("entry_type"),
            "syndrome_anchor": meta.get("syndrome_anchor"),
            "section_path": meta.get("section_path"),
            "wiki_links": meta.get("wiki_links"),
            "score": float(score),
        }

    # ------------------------------------------------- article closure (§18)
    def _build_sid_index(self) -> None:
        idx: dict[str, list[int]] = defaultdict(list)
        for pos, meta in enumerate(self._metadata):
            sid = meta.get("source_id")
            if sid and meta.get("chunk_type") in _DDX_USEFUL:
                idx[sid].append(pos)
        self._sid_index = dict(idx)

    @staticmethod
    def _wiki_links_hit(meta: dict) -> Optional[dict]:
        wl = meta.get("wiki_links") or []
        if isinstance(wl, str):
            wl = [wl]
        wl = [w for w in wl if w]
        if not wl:
            return None
        anchor = meta.get("syndrome_anchor") or meta.get("title") or ""
        return {
            "id": f"{meta.get('id','')}::wiki_links",
            "title": f"{anchor} > differential (linked entities)",
            "content": "Differential diagnosis includes: " + "; ".join(wl) + ".",
            "article_id": meta.get("article_id", meta.get("source_id", "")),
            "source_id": meta.get("source_id", ""),
            "chunk_type": "differential",
            "entry_type": meta.get("entry_type"),
            "syndrome_anchor": anchor,
            "section_path": f"{anchor} > Differential Diagnosis",
            "score": 0.0,
        }

    def expand_ddx_siblings(self, hits: list[dict]) -> list[dict]:
        if not self._metadata:
            return hits
        if self._sid_index is None:
            self._build_sid_index()
        source_ids = {h.get("source_id") for h in hits if h.get("source_id")}
        seen = {h.get("id") for h in hits}
        extra: list[dict] = []
        for h in hits:
            if h.get("wiki_links"):
                wh = self._wiki_links_hit(h)
                if wh and wh["id"] not in seen:
                    seen.add(wh["id"])
                    extra.append(wh)
        for sid in source_ids:
            for pos in self._sid_index.get(sid, ()):  # type: ignore[union-attr]
                meta = self._metadata[pos]
                cid = meta.get("id")
                if cid in seen:
                    continue
                seen.add(cid)
                extra.append(self._hit(meta, 0.0))
                if meta.get("wiki_links"):
                    wh = self._wiki_links_hit(meta)
                    if wh and wh["id"] not in seen:
                        seen.add(wh["id"])
                        extra.append(wh)
        return hits + extra
