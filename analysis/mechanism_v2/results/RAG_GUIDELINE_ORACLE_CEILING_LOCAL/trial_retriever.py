#!/usr/bin/env python3
"""Hybrid retriever over the ceiling-audit corpus, with document reassembly.

Sparse TF-IDF and MiniLM dense scores are fused by reciprocal rank.  A hit is
returned as a *passage*: the hit chunk glued to its neighbours inside the same
document, because the audit found the median chunk is 36-154 tokens and
multi-sentence criteria routinely straddle a chunk boundary.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[4]
INDEX = ROOT / "data/corpus/ceiling_trial_index"
INDEX_V2 = ROOT / "data/corpus/ceiling_trial_index_v2"

SOURCE_PATHS = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
}

RRF_K = 60


class TrialRetriever:
    def __init__(self, device: str = "cuda:1", use_dense: bool = True,
                 index: Path | str | None = None) -> None:
        # The index carries the corpus files it was built over, so pointing at
        # ceiling_trial_index_v2 also switches the byte offsets to the repaired
        # corpus.  Reading them from config.json rather than the module-level
        # constant is what keeps the two from drifting apart.
        # a bare name such as "ceiling_trial_index_v2" resolves under
        # data/corpus/ so callers do not have to know the layout
        self.index = INDEX
        if index:
            self.index = Path(index)
            if not self.index.is_dir():
                self.index = ROOT / "data/corpus" / str(index)
        cfg = json.loads((self.index / "config.json").read_text(encoding="utf-8"))
        self.sources = {k: ROOT / v for k, v in (cfg.get("sources") or {}).items()} \
            or dict(SOURCE_PATHS)

        self.meta = [json.loads(l) for l in (self.index / "meta.jsonl").open(encoding="utf-8")]
        self.n = len(self.meta)
        with (self.index / "tfidf_vec.pkl").open("rb") as fh:
            self.vec = pickle.load(fh)
        self.mat = sp.load_npz(self.index / "tfidf_mat.npz").tocsr()
        # doc_key -> used to decide whether gid+-1 is the same document.  An
        # empty article_id collapses a whole source into one pseudo-document and
        # silently lets the window run across article boundaries, which is what
        # happened to StatPearls in the first build (report S33).
        self.doc_key = [f"{m['source']}|{m['article_id']}" for m in self.meta]
        blank = {m["source"] for m in self.meta if not m["article_id"]}
        if blank:
            print(f"warning: article_id empty for {sorted(blank)}; the +-1 "
                  f"window cannot see document boundaries in those sources")
        self._handles: dict[str, object] = {}

        self.use_dense = use_dense and (self.index / "dense.npy").exists()
        if self.use_dense:
            import torch
            from sentence_transformers import SentenceTransformer

            self.torch = torch
            self.device = device
            emb = np.load(self.index / "dense.npy")
            self.dense = torch.from_numpy(emb).to(device)
            self.encoder = SentenceTransformer(cfg["dense_model"], device=device)
            self.encoder.max_seq_length = 256

    # ------------------------------------------------------------------ text
    def text(self, gid: int) -> str:
        m = self.meta[gid]
        handle = self._handles.get(m["source"])
        if handle is None:
            handle = self.sources[m["source"]].open("rb")
            self._handles[m["source"]] = handle
        handle.seek(m["offset"])
        row = json.loads(handle.readline())
        return row.get("text") or row.get("content") or ""

    def passage(self, gid: int, window: int = 1) -> dict:
        """Hit chunk plus same-document neighbours, in reading order."""
        lo = gid
        while lo - 1 >= 0 and gid - (lo - 1) <= window and self.doc_key[lo - 1] == self.doc_key[gid]:
            lo -= 1
        hi = gid
        while hi + 1 < self.n and (hi + 1) - gid <= window and self.doc_key[hi + 1] == self.doc_key[gid]:
            hi += 1
        gids = list(range(lo, hi + 1))
        m = self.meta[gid]
        return {
            "gid": gid,
            "window_gids": gids,
            "source": m["source"],
            "doc_key": self.doc_key[gid],
            "title": m["title"],
            "section_path": m["section_path"],
            "text": "\n".join(self.text(g) for g in gids),
        }

    # ------------------------------------------------------------- retrieval
    def _sparse_ranks(self, queries: list[str], top_k: int) -> list[list[int]]:
        q = self.vec.transform(queries)
        out = []
        for i in range(q.shape[0]):
            scores = (self.mat @ q[i].T).toarray().ravel()
            k = min(top_k, scores.size)
            idx = np.argpartition(-scores, k - 1)[:k]
            idx = idx[np.argsort(-scores[idx])]
            out.append([int(j) for j in idx if scores[j] > 0])
        return out

    def _dense_ranks(self, queries: list[str], top_k: int) -> list[list[int]]:
        if not self.use_dense:
            return [[] for _ in queries]
        emb = self.encoder.encode(queries, convert_to_numpy=True, normalize_embeddings=True,
                                  show_progress_bar=False)
        qt = self.torch.from_numpy(emb).to(self.device).to(self.dense.dtype)
        scores = qt @ self.dense.T
        _, idx = self.torch.topk(scores.float(), k=top_k, dim=1)
        return idx.cpu().tolist()

    def search(self, queries: list[str], top_k: int = 10, pool: int = 200) -> list[list[dict]]:
        """Per query: RRF-fused top_k chunk hits."""
        sparse = self._sparse_ranks(queries, pool)
        dense = self._dense_ranks(queries, pool)
        results = []
        for s_ranks, d_ranks in zip(sparse, dense):
            fused: dict[int, float] = {}
            lanes: dict[int, dict[str, int]] = {}
            for lane, ranks in (("sparse", s_ranks), ("dense", d_ranks)):
                for rank, gid in enumerate(ranks):
                    fused[gid] = fused.get(gid, 0.0) + 1.0 / (RRF_K + rank + 1)
                    lanes.setdefault(gid, {})[lane] = rank + 1
            order = sorted(fused, key=lambda g: -fused[g])[:top_k]
            results.append([{"gid": g, "rrf": round(fused[g], 6), "lane_ranks": lanes[g]}
                            for g in order])
        return results
