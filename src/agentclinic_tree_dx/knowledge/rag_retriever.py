"""Layer 3: RAG retriever backed by FAISS dense index or TF-IDF sparse index.

Provides search over ~500K clinical snippets (StatPearls + Textbooks) as a
fallback when structured knowledge layers (DxS, PrimeKG, LR cache) miss.

Supports two backends (auto-detected from index_dir):
  - FAISS dense: built by scripts/build_rag_index.py (requires sentence-transformers)
  - TF-IDF sparse: built by scripts/build_tfidf_index.py (sklearn only, much faster)
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# sklearn TfidfVectorizer.transform / sparse matmul are not documented as
# thread-safe; serialize the sparse path the same way FAISS search is locked.
_TFIDF_LOCK = threading.Lock()


class RAGRetriever:
    """Search over StatPearls + Textbooks corpus.

    Auto-detects backend: FAISS dense (faiss.index) or TF-IDF (tfidf_matrix.npz).
    """

    def __init__(
        self,
        index_dir: str | Path,
        *,
        model_name: Optional[str] = None,
        device: str = "cuda",
    ) -> None:
        self._index_dir = Path(index_dir)
        self._metadata: list[dict] = []
        self._model_name = model_name
        self._device = device
        self._ready = False

        self._backend = None  # "faiss" or "tfidf"
        self._faiss_index = None
        self._encoder = None
        self._encoder_pool = None  # multi-GPU EncoderPool when configured
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._sid_index: Optional[dict[str, list[int]]] = None

        self._load()

    def _load(self) -> None:
        meta_path = self._index_dir / "metadata.jsonl"
        config_path = self._index_dir / "config.json"

        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                self._metadata = [json.loads(line) for line in f if line.strip()]

        config = {}
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            self._model_name = self._model_name or config.get("model")

        # Try FAISS first
        faiss_path = self._index_dir / "faiss.index"
        if faiss_path.exists():
            try:
                import faiss
                self._faiss_index = faiss.read_index(str(faiss_path))
                self._backend = "faiss"
                self._ready = True
                logger.info("RAG FAISS index loaded: %d vectors", self._faiss_index.ntotal)
                return
            except Exception as e:
                logger.warning("Failed to load FAISS index: %s", e)

        # Try TF-IDF
        tfidf_path = self._index_dir / "tfidf_matrix.npz"
        vec_path = self._index_dir / "tfidf_vectorizer.pkl"
        if tfidf_path.exists() and vec_path.exists():
            try:
                import pickle
                from scipy import sparse
                with open(vec_path, "rb") as f:
                    self._tfidf_vectorizer = pickle.load(f)
                self._tfidf_matrix = sparse.load_npz(str(tfidf_path))
                self._backend = "tfidf"
                self._ready = True
                logger.info("RAG TF-IDF index loaded: %d docs, %d features",
                            self._tfidf_matrix.shape[0], self._tfidf_matrix.shape[1])
                return
            except Exception as e:
                logger.warning("Failed to load TF-IDF index: %s", e)

        logger.warning("No RAG index found at %s; Layer 3a disabled", self._index_dir)

    @staticmethod
    def _resolve_device(preferred: str) -> str:
        """Return *preferred* if usable, else fall back to CPU.

        An explicit ``TREE_DX_EMBED_DEVICE`` env var overrides *preferred* so
        offline index builds can pin a specific free GPU (e.g. "cuda:2").
        """
        import os
        forced = os.environ.get("TREE_DX_EMBED_DEVICE", "").strip()
        if forced:
            preferred = forced
        if preferred == "cpu":
            return "cpu"
        alloc_conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
        if "max_split_size_mb:" in alloc_conf:
            try:
                val = int(alloc_conf.split("max_split_size_mb:")[1].split(",")[0])
                if val < 32:
                    logger.info("PYTORCH_CUDA_ALLOC_CONF max_split_size_mb=%d too small, using CPU", val)
                    return "cpu"
            except (ValueError, IndexError):
                pass
        try:
            import torch
            if torch.cuda.is_available():
                free_mb = torch.cuda.mem_get_info()[0] / (1024 * 1024)
                if free_mb >= 512:
                    return preferred
                logger.info("GPU free memory %.0f MB < 512 MB, falling back to CPU", free_mb)
        except Exception:
            pass
        return "cpu"

    def _ensure_encoder(self) -> bool:
        if self._encoder is not None or self._encoder_pool is not None:
            return True
        if not self._model_name or self._model_name == "tfidf":
            return False
        # Multi-GPU pool: replicate the RAG encoder across the configured GPUs so
        # per-disease RAG queries encode in parallel (removes the global lock).
        try:
            from .embedding_index import EncoderPool, _multi_devices
            devices = _multi_devices()
            if len(devices) >= 2:
                pool = EncoderPool([self._model_name], devices)
                if pool.size >= 1:
                    self._encoder_pool = pool
                    self._encoder = pool.representative
                    logger.info("RAG encoder POOL loaded: %s (%d replicas)",
                                self._model_name, pool.size)
                    return True
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("RAG encoder pool init failed (%s); single encoder", e)
        device = self._resolve_device(self._device)
        try:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self._model_name, device=device)
            logger.info("RAG encoder loaded: %s (device=%s)", self._model_name, device)
            return True
        except RuntimeError as e:
            if "CUDA" in str(e) or "out of memory" in str(e):
                logger.warning("GPU load failed (%s), retrying on CPU", e)
                try:
                    from sentence_transformers import SentenceTransformer
                    self._encoder = SentenceTransformer(self._model_name, device="cpu")
                    logger.info("RAG encoder loaded: %s (device=cpu, fallback)", self._model_name)
                    return True
                except Exception as e2:
                    logger.warning("CPU fallback also failed: %s", e2)
                    return False
            logger.warning("Failed to load RAG encoder '%s': %s", self._model_name, e)
            return False
        except Exception as e:
            logger.warning("Failed to load RAG encoder '%s': %s", self._model_name, e)
            return False

    @property
    def is_ready(self) -> bool:
        return self._ready

    @staticmethod
    def _hit_from_meta(meta: dict, idx: int, score: float) -> dict:
        return {
            "id": meta.get("id", f"chunk_{idx}"),
            "title": meta.get("title", meta.get("section_path", "")),
            "content": meta.get("content", ""),
            "article_id": meta.get("article_id", meta.get("source_id", "")),
            "source_id": meta.get("source_id", ""),
            "chunk_type": meta.get("chunk_type"),
            "entry_type": meta.get("entry_type"),
            "syndrome_anchor": meta.get("syndrome_anchor"),
            "section_path": meta.get("section_path"),
            "score": float(score),
        }

    _DDX_USEFUL = frozenset(
        {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"})

    def _build_sid_index(self) -> None:
        """Lazily build ``source_id -> [meta positions]`` inverted index so
        ``expand_ddx_siblings`` is O(hits) instead of O(corpus) per query.

        The DDx body of a syndrome entry is scattered across SIBLING chunks of
        the same article (CPG §18: c1/Pancoast gold lives only in PMC siblings,
        not the entry chunk). Closing over ``source_id`` is therefore a recall
        REQUIREMENT, not an optimisation — so we make it cheap enough for the
        per-disease RAG hot path.
        """
        from collections import defaultdict
        idx: dict[str, list[int]] = defaultdict(list)
        for pos, meta in enumerate(self._metadata):
            sid = meta.get("source_id")
            if sid and meta.get("chunk_type") in self._DDX_USEFUL:
                idx[sid].append(pos)
        self._sid_index = dict(idx)

    @staticmethod
    def _wiki_links_hit(meta: dict, idx: int) -> Optional[dict]:
        """Synthesise a chunk from a WikEM page's ``wiki_links`` — an EXPLICIT
        DDx entity list that the spotter can mine directly even when those
        entities are not written out in prose (CPG §16/§18 scattered info)."""
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
        """Append useful DDx chunks sharing ``source_id`` with any hit (article
        closure), PLUS a synthetic chunk built from each hit's WikEM
        ``wiki_links`` DDx entity list. Together these turn an "entry chunk"
        retrieval into the article's full scattered differential (CPG §18)."""
        source_ids = {h.get("source_id") for h in hits if h.get("source_id")}
        if not self._metadata:
            return hits
        if getattr(self, "_sid_index", None) is None:
            self._build_sid_index()
        seen = {h.get("id") for h in hits}
        extra: list[dict] = []
        # (1) wiki_links of the retrieved hits themselves (explicit DDx lists)
        for h in hits:
            wh = self._wiki_links_hit(h, -1) if h.get("wiki_links") else None
            if wh and wh["id"] not in seen:
                seen.add(wh["id"])
                extra.append(wh)
        # (2) article closure over source_id (scattered sibling chunks)
        if source_ids:
            for sid in source_ids:
                for pos in self._sid_index.get(sid, ()):  # type: ignore[union-attr]
                    meta = self._metadata[pos]
                    cid = meta.get("id")
                    if cid in seen:
                        continue
                    seen.add(cid)
                    extra.append(self._hit_from_meta(meta, pos, 0.0))
                    wh = self._wiki_links_hit(meta, pos) if meta.get("wiki_links") else None
                    if wh and wh["id"] not in seen:
                        seen.add(wh["id"])
                        extra.append(wh)
        return hits + extra

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        score_threshold: float = 0.1,
    ) -> list[dict]:
        """Search the corpus for relevant snippets."""
        if not self._ready:
            return []
        if self._backend == "faiss":
            return self._search_faiss(query, top_k, score_threshold)
        elif self._backend == "tfidf":
            return self._search_tfidf(query, top_k, score_threshold)
        return []

    def _search_faiss(self, query: str, top_k: int, threshold: float) -> list[dict]:
        if not self._ensure_encoder() or self._faiss_index is None:
            return []
        import numpy as np
        if self._encoder_pool is not None and self._encoder_pool.size > 1:
            q_emb = self._encoder_pool.encode(
                [query], normalize_embeddings=True
            ).astype(np.float32)
        else:
            from .embedding_index import _ENCODE_LOCK
            with _ENCODE_LOCK:
                q_emb = self._encoder.encode(
                    [query], normalize_embeddings=True
                ).astype(np.float32)
        from .embedding_index import _FAISS_SEARCH_LOCK
        with _FAISS_SEARCH_LOCK:  # §30: serialize FAISS search (segfault fix)
            scores, indices = self._faiss_index.search(q_emb, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or score < threshold:
                continue
            meta = self._metadata[idx] if idx < len(self._metadata) else {}
            results.append(self._hit_from_meta(meta, idx, float(score)))
        return results

    def _search_tfidf(self, query: str, top_k: int, threshold: float) -> list[dict]:
        if self._tfidf_vectorizer is None or self._tfidf_matrix is None:
            return []
        import numpy as np
        with _TFIDF_LOCK:
            q_vec = self._tfidf_vectorizer.transform([query])
            scores = (self._tfidf_matrix @ q_vec.T).toarray().flatten()
            top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            s = float(scores[idx])
            if s < threshold:
                break
            meta = self._metadata[idx] if idx < len(self._metadata) else {}
            results.append(self._hit_from_meta(meta, idx, s))
        return results

    def search_for_disease(
        self,
        disease: str,
        finding: str,
        *,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for snippets about a specific finding in the context of a disease."""
        query = f"{finding} in {disease}: clinical significance, diagnosis, likelihood ratio"
        return self.search(query, top_k=top_k)

    def search_for_differential(
        self,
        diseases: list[str],
        finding: str,
        *,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for differential diagnosis information about a finding."""
        disease_str = " vs ".join(diseases[:4])
        query = f"differential diagnosis {disease_str}: {finding}"
        return self.search(query, top_k=top_k)

    def extract_lr_from_snippets(
        self,
        snippets: list[dict],
        finding: str,
        disease: str,
    ) -> Optional[dict]:
        """Extract a numeric LR (LR+ AND LR-) from retrieved snippets.

        Two-tier conversion (see :mod:`knowledge.lr_quant`):
          A. explicit numeric Sn/Sp or LR text → ``confidence="rag_extracted"``;
          B. qualitative frequency language ("seen in most patients", "rarely")
             → calibrated Sn → LR via the build-time frequency scale, flagged
             ``confidence="rag_qualitative"`` so Bayesian updating can attenuate.

        Returns the highest-confidence entry across snippets, or None when no
        snippet carries a usable quantitative signal (caller keeps context-only).
        """
        from .lr_quant import quantify_snippet, neutralize_entry, purify_entry

        detox = getattr(self, "_lr_detox", False)
        purify = getattr(self, "_lr_purify", False)
        best: Optional[dict] = None
        _rank = {"rag_extracted": 2, "rag_qualitative": 1}
        for s in snippets:
            entry = quantify_snippet(
                s.get("content", ""), finding, disease,
                article_id=s.get("article_id", "unknown"),
                title=s.get("title", ""),
                score=s.get("score", 0),
            )
            # §26.5(1): collapse fabricated strong-exclusion LRs toward neutral
            # (or drop demographic/normal-exam findings) at the live RAG path so
            # cache misses don't re-introduce the poison the detox removed.
            # §27.6(1): purify (strip ungrounded heuristic LR → context-only)
            # takes precedence; else §26.5(1) detox softening.
            if purify:
                entry = purify_entry(entry)
                # context-only purify result carries no usable LR → treat as miss
                if entry is not None and entry.get("lr_positive") is None \
                        and entry.get("lr_negative") is None:
                    entry = None
            elif detox:
                entry = neutralize_entry(entry)
            if entry is None:
                continue
            if best is None or _rank.get(entry["confidence"], 0) > _rank.get(best["confidence"], 0):
                best = entry
                if entry["confidence"] == "rag_extracted":
                    break  # can't do better
        return best
