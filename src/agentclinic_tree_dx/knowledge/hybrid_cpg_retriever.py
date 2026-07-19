"""IMP-53 — Sparse (TF-IDF) + MedCPT-dense hybrid retriever (CPG §17 B2/L1/L2).

The §19 substrate ``cpg_index`` is TF-IDF-only: a query that shares no surface
tokens with the gold DDx chunk (mechanism/eponym phrasing — the B2 lexical gap)
cannot retrieve it, no matter how the spotter/closure is tuned. MedCPT (NCBI
PubMedBERT bi-encoder) adds a *dense* tower; fusing the two rank lists with RRF
recovers the lexical-gap misses while keeping the sparse tower's exact-term
precision.

This wraps the existing :class:`RAGRetriever` (sparse, metadata, closure) and a
MedCPT FAISS index (``build_medcpt_cpg_index.py``, ROW-ALIGNED with the sparse
metadata), exposing the SAME interface (``is_ready`` / ``search`` /
``expand_ddx_siblings``) so it is a drop-in for ``GuidelineBranchSource``.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

QUERY_ENCODER = "ncbi/MedCPT-Query-Encoder"
QUERY_MAX_LEN = 64


class HybridCPGRetriever:
    def __init__(self, sparse_index_dir: str | Path, medcpt_index_dir: str | Path,
                 *, rrf_k: int = 60, device: str = "cpu",
                 dense_mult: int = 3) -> None:
        from .rag_retriever import RAGRetriever
        self._sparse = RAGRetriever(str(sparse_index_dir), device="cpu")
        self._mdir = Path(medcpt_index_dir)
        self._rrf_k = rrf_k
        self._device = device
        self._dense_mult = dense_mult  # retrieve dense_mult*top_k from each tower
        self._faiss = None
        self._tok = None
        self._enc = None
        self._dense_ready = False
        self._load_dense()

    def _load_dense(self) -> None:
        idx_path = self._mdir / "index.faiss"
        if not idx_path.exists():
            logger.warning("MedCPT index missing at %s; hybrid degrades to sparse-only", idx_path)
            return
        try:
            import faiss
            self._faiss = faiss.read_index(str(idx_path))
            n_sparse = len(self._sparse._metadata)  # noqa: SLF001 (row-alignment check)
            if self._faiss.ntotal != n_sparse:
                logger.warning("MedCPT ntotal %d != sparse meta %d; row-alignment broken — "
                               "dense disabled", self._faiss.ntotal, n_sparse)
                self._faiss = None
                return
            self._dense_ready = True
            logger.info("MedCPT dense index loaded: %d vectors", self._faiss.ntotal)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Failed to load MedCPT index: %s", e)

    def _ensure_encoder(self) -> bool:
        if self._enc is not None:
            return True
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
            self._tok = AutoTokenizer.from_pretrained(QUERY_ENCODER)
            dev = self._device
            if dev != "cpu":
                try:
                    if not torch.cuda.is_available():
                        dev = "cpu"
                except Exception:
                    dev = "cpu"
            self._enc = AutoModel.from_pretrained(QUERY_ENCODER).to(dev).eval()
            self._enc_device = dev
            return True
        except Exception as e:  # pragma: no cover - network/model defensive
            logger.warning("MedCPT query encoder load failed: %s", e)
            return False

    @property
    def is_ready(self) -> bool:
        return bool(self._sparse.is_ready)

    # closure delegated to the sparse retriever (owns metadata + sid index)
    def expand_ddx_siblings(self, hits: list[dict]) -> list[dict]:
        return self._sparse.expand_ddx_siblings(hits)

    def _dense_search(self, query: str, k: int) -> list[tuple[int, float]]:
        if not (self._dense_ready and self._ensure_encoder()):
            return []
        import numpy as np
        import torch
        with torch.no_grad():
            enc = self._tok([query], truncation=True, padding=True,
                            max_length=QUERY_MAX_LEN, return_tensors="pt").to(self._enc_device)
            q = self._enc(**enc).last_hidden_state[:, 0, :].cpu().to(torch.float32).numpy()
        scores, idxs = self._faiss.search(q.astype(np.float32), k)
        return [(int(i), float(s)) for s, i in zip(scores[0], idxs[0]) if i >= 0]

    def search(self, query: str, *, top_k: int = 8,
               score_threshold: float = 0.0) -> list[dict]:
        """Sparse ∪ dense, fused by Reciprocal Rank Fusion (RRF). Sparse-origin
        hits keep their TF-IDF score (so the downstream ``1/(1+score)`` weight is
        unchanged); dense-only hits enter at score 0.0 (frequency dominates ties
        in the spotter anyway). Returns full chunk metadata, RRF-ranked."""
        if not self._sparse.is_ready:
            return []
        kk = max(top_k, top_k * self._dense_mult)
        sparse_hits = self._sparse.search(query, top_k=kk, score_threshold=0.0)
        meta = self._sparse._metadata  # noqa: SLF001 (row-aligned with dense idx)

        rank_sparse: dict[str, int] = {}
        hit_by_id: dict[str, dict] = {}
        for r, h in enumerate(sparse_hits):
            hid = h.get("id")
            if hid is None:
                continue
            rank_sparse.setdefault(hid, r)
            hit_by_id.setdefault(hid, h)

        rank_dense: dict[str, int] = {}
        for r, (idx, _s) in enumerate(self._dense_search(query, kk)):
            if idx >= len(meta):
                continue
            m = meta[idx]
            hid = m.get("id", f"chunk_{idx}")
            rank_dense.setdefault(hid, r)
            if hid not in hit_by_id:
                hit_by_id[hid] = self._sparse._hit_from_meta(m, idx, 0.0)  # noqa: SLF001

        if not rank_dense:  # dense unavailable → behave as sparse
            return sparse_hits[:top_k]

        fused: list[tuple[float, str]] = []
        for hid in hit_by_id:
            rrf = 0.0
            if hid in rank_sparse:
                rrf += 1.0 / (self._rrf_k + rank_sparse[hid])
            if hid in rank_dense:
                rrf += 1.0 / (self._rrf_k + rank_dense[hid])
            fused.append((rrf, hid))
        fused.sort(key=lambda x: -x[0])
        return [hit_by_id[hid] for _r, hid in fused[:top_k]]
