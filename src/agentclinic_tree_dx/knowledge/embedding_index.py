"""Embedding-based semantic matching index for HPO phenotype terms.

Loads pre-computed embeddings from build_hpo_embeddings.py and provides
fast cosine-similarity search via FAISS IndexFlatIP.

Usage:
    index = EmbeddingIndex.from_files("hpo_embeddings.npy", "hpo_embedding_metadata.json")
    results = index.search("weight loss", top_k=5)
    # → [{"text": "Decreased body weight", "hpo_id": "HP:0004325", "score": 0.92}, ...]
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_model = None
# Serializes model load and GPU encode across concurrent worker threads — a
# single shared SentenceTransformer is not safe under concurrent CUDA calls.
_MODEL_LOCK = threading.Lock()
_ENCODE_LOCK = threading.Lock()
# §30 SEGFAULT FIX: a PROCESS-WIDE FAISS search lock shared by EmbeddingIndex
# (IndexFlatIP) and RAGRetriever (IndexIVFPQ, 493k vec). The fork RCA pinpointed
# concurrent `IndexIVFPQ.search` from 9 worker threads as the dominant native
# crash (segfault / double-free): FAISS search mutates internal scan state and
# is not thread-safe in this build. Search is sub-ms while the wall time is
# dominated by the 240s remote LLM, so serializing it costs ~0 throughput but
# eliminates the crash. Single lock across both indices (both hit FAISS in the
# same 9-thread burst).
_FAISS_SEARCH_LOCK = threading.Lock()

# Multi-GPU encoder pool (opt-in via TREE_DX_EMBED_DEVICES="cuda:0,cuda:1,...").
# A pool of independent model replicas — one per device — checked out via a
# thread-safe queue lets up to N encode() calls run TRULY in parallel across
# GPUs, removing the single global _ENCODE_LOCK serialization bottleneck. Falls
# back to the legacy single-model + lock path when fewer than 2 devices are
# configured, so default behaviour is unchanged.
_POOL = None
_POOL_INIT = False

_LOCAL_MODEL_PATHS = [
    "/data2/wanghongyi/models/all-MiniLM-L6-v2",
    "sentence-transformers/all-MiniLM-L6-v2",
]


def _multi_devices() -> list[str]:
    """Parse TREE_DX_EMBED_DEVICES into a validated device list.

    Returns [] when the var is unset or names <2 devices (→ legacy single-model
    path). CUDA devices are kept only if CUDA is actually available.
    """
    raw = os.environ.get("TREE_DX_EMBED_DEVICES", "").strip()
    if not raw:
        return []
    devs = [d.strip() for d in raw.split(",") if d.strip()]
    if len(devs) < 2:
        return []
    if any(d.startswith("cuda") for d in devs):
        _repair_alloc_conf()
        try:
            import torch
            if not torch.cuda.is_available():
                logger.info("TREE_DX_EMBED_DEVICES set but CUDA unavailable; ignoring")
                return []
        except Exception:
            return []
    return devs


class EncoderPool:
    """Pool of SentenceTransformer replicas across devices for parallel encode.

    Each replica is handed to exactly one thread at a time via a blocking queue,
    so encode() calls do not need a shared lock and run concurrently on distinct
    GPUs. The model (all-MiniLM-L6-v2, ~90 MB) is tiny, so replicating it per GPU
    is cheap.
    """

    def __init__(self, model_paths: list[str], devices: list[str]) -> None:
        import queue as _queue
        self._pool: "_queue.Queue" = _queue.Queue()
        self._members: list = []
        self._devices: list[str] = []
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning("sentence-transformers not installed; pool disabled")
            return
        for dev in devices:
            enc = None
            for path in model_paths:
                try:
                    enc = SentenceTransformer(path, device=dev)
                    break
                except Exception as e:  # pragma: no cover - device/load specific
                    logger.warning("EncoderPool load failed %s on %s: %s", path, dev, e)
                    enc = None
            if enc is not None:
                self._pool.put(enc)
                self._members.append(enc)
                self._devices.append(dev)
        if self._members:
            logger.info("EncoderPool ready: %d replicas across %s",
                        len(self._members), self._devices)

    @property
    def size(self) -> int:
        return len(self._members)

    @property
    def representative(self):
        return self._members[0] if self._members else None

    def encode(self, texts, **kw):
        enc = self._pool.get()
        try:
            return enc.encode(texts, **kw)
        finally:
            self._pool.put(enc)


def _get_pool() -> Optional["EncoderPool"]:
    """Lazily build the shared multi-GPU encoder pool (or None for legacy path)."""
    global _POOL, _POOL_INIT
    if _POOL_INIT:
        return _POOL
    with _MODEL_LOCK:
        if _POOL_INIT:
            return _POOL
        devices = _multi_devices()
        if len(devices) >= 2:
            pool = EncoderPool(_LOCAL_MODEL_PATHS, devices)
            _POOL = pool if pool.size >= 1 else None
        _POOL_INIT = True
        return _POOL


def _encode(model, texts, **kw):
    """Encode texts. Uses the multi-GPU pool (parallel) when configured, else the
    legacy single-model path serialized by _ENCODE_LOCK."""
    pool = _get_pool()
    if pool is not None and pool.size > 1:
        return pool.encode(texts, **kw)
    with _ENCODE_LOCK:
        return model.encode(texts, **kw)


def _repair_alloc_conf() -> None:
    """Repair a too-small PYTORCH_CUDA_ALLOC_CONF (max_split_size_mb<21) that
    would otherwise crash CUDA init. Must run before the first torch CUDA call.
    The server default of max_split_size_mb:4 is invalid for CUDA init."""
    conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
    if "max_split_size_mb:" in conf:
        try:
            val = int(conf.split("max_split_size_mb:")[1].split(",")[0])
        except (ValueError, IndexError):
            val = None
        if val is None or val < 21:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ""
            logger.info("Cleared invalid PYTORCH_CUDA_ALLOC_CONF (%s) for GPU embed", conf)


def _embed_batch_size(default: int = 128) -> int:
    """Encoding batch size; raise via TREE_DX_EMBED_BATCH for GPU index builds."""
    try:
        return max(1, int(os.environ.get("TREE_DX_EMBED_BATCH", str(default))))
    except (TypeError, ValueError):
        return default


def _resolve_device() -> str:
    """Pick best available device: CUDA if enough memory and allocator OK, else CPU.

    An explicit ``TREE_DX_EMBED_DEVICE`` env var (e.g. "cuda:2") takes top
    priority — used by offline index-build scripts to pin a specific free GPU
    with a large batch size while the concurrent runtime stays on CPU.
    """
    forced = os.environ.get("TREE_DX_EMBED_DEVICE", "").strip()
    if forced:
        if forced.startswith("cuda"):
            _repair_alloc_conf()
            try:
                import torch
                if torch.cuda.is_available():
                    return forced
                logger.info("TREE_DX_EMBED_DEVICE=%s requested but CUDA unavailable; CPU", forced)
                return "cpu"
            except Exception:
                return "cpu"
        return forced  # "cpu" or explicit
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
                return "cuda"
            logger.info("GPU free memory %.0f MB < 512 MB, falling back to CPU", free_mb)
    except Exception:
        pass
    return "cpu"


def _get_model():
    """Lazy-load the sentence-transformers model (singleton), preferring local cache.

    When the multi-GPU pool is active, returns a representative replica so callers
    that do `model = _get_model(); _encode(model, ...)` and `if model is None`
    checks keep working — the actual encode is dispatched to the pool by _encode.
    """
    pool = _get_pool()
    if pool is not None and pool.size > 0:
        return pool.representative
    global _model
    if _model is not None:
        return _model
    with _MODEL_LOCK:
        if _model is not None:  # double-checked: another thread loaded it
            return _model
        return _load_model_locked()


def _load_model_locked():
    global _model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        logger.warning("sentence-transformers not installed; embedding search disabled")
        return None
    device = _resolve_device()
    for path in _LOCAL_MODEL_PATHS:
        try:
            _model = SentenceTransformer(path, device=device)
            logger.info("Loaded embedding model from: %s (device=%s)", path, device)
            return _model
        except RuntimeError as e:
            if "CUDA" in str(e) or "out of memory" in str(e):
                logger.warning("GPU load failed (%s), retrying on CPU", e)
                try:
                    _model = SentenceTransformer(path, device="cpu")
                    logger.info("Loaded embedding model from: %s (device=cpu, fallback)", path)
                    return _model
                except Exception:
                    continue
            continue
        except Exception:
            continue
    logger.warning("Could not load embedding model from any path")
    return None


class EmbeddingIndex:
    """Pre-computed embedding index with FAISS-accelerated similarity search."""

    _QUERY_CACHE_SIZE = 256

    def __init__(self) -> None:
        self._faiss_index = None
        self._metadata: list[dict] = []
        self._text_to_idx: dict[str, int] = {}
        self._hpo_to_indices: dict[str, list[int]] = {}
        self._query_cache: dict[str, list[dict]] = {}

    @classmethod
    def from_files(
        cls,
        embeddings_path: str | Path,
        metadata_path: str | Path,
    ) -> "EmbeddingIndex":
        inst = cls()
        emb_path = Path(embeddings_path)
        meta_path = Path(metadata_path)

        if not emb_path.exists() or not meta_path.exists():
            logger.warning("Embedding files not found: %s / %s", emb_path, meta_path)
            return inst

        embeddings = np.load(emb_path).astype(np.float32)
        with open(meta_path, encoding="utf-8") as f:
            inst._metadata = json.load(f)

        try:
            import faiss
            dim = embeddings.shape[1]
            inst._faiss_index = faiss.IndexFlatIP(dim)
            inst._faiss_index.add(embeddings)
        except ImportError:
            logger.warning("faiss not installed; falling back to numpy (slower)")
            inst._numpy_embeddings = embeddings

        for i, m in enumerate(inst._metadata):
            text_lower = m.get("text", "").lower()
            if text_lower not in inst._text_to_idx:
                inst._text_to_idx[text_lower] = i
            hpo_id = m.get("hpo_id", "")
            if hpo_id:
                inst._hpo_to_indices.setdefault(hpo_id, []).append(i)

        logger.info(
            "EmbeddingIndex loaded: %d vectors (%d dim), %d unique texts, backend=%s",
            len(inst._metadata), embeddings.shape[1],
            len(inst._text_to_idx),
            "faiss" if inst._faiss_index else "numpy",
        )
        return inst

    @property
    def is_ready(self) -> bool:
        return (self._faiss_index is not None or hasattr(self, "_numpy_embeddings")) and len(self._metadata) > 0

    def _search_vectors(self, q_emb: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        """Return (scores, indices) for top-k. q_emb shape: (n, dim)."""
        if self._faiss_index is not None:
            with _FAISS_SEARCH_LOCK:  # §30: serialize FAISS search (segfault fix)
                return self._faiss_index.search(q_emb, k)
        all_scores = self._numpy_embeddings @ q_emb.T
        if q_emb.shape[0] == 1:
            scores_flat = all_scores.flatten()
            if k >= len(scores_flat):
                top_idx = np.argsort(-scores_flat)
            else:
                top_idx = np.argpartition(-scores_flat, k)[:k]
                top_idx = top_idx[np.argsort(-scores_flat[top_idx])]
            return scores_flat[top_idx].reshape(1, -1), top_idx.reshape(1, -1)
        scores_out, indices_out = [], []
        for col in range(q_emb.shape[0]):
            s = all_scores[:, col]
            if k >= len(s):
                ti = np.argsort(-s)
            else:
                ti = np.argpartition(-s, k)[:k]
                ti = ti[np.argsort(-s[ti])]
            scores_out.append(s[ti])
            indices_out.append(ti)
        return np.array(scores_out), np.array(indices_out)

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        threshold: float = 0.5,
    ) -> list[dict]:
        """Find the most semantically similar terms to the query."""
        if not self.is_ready:
            return []

        cache_key = f"{query.strip().lower()}|{top_k}|{threshold}"
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        model = _get_model()
        if model is None:
            return []

        q_lower = query.strip().lower()
        if q_lower in self._text_to_idx:
            idx = self._text_to_idx[q_lower]
            meta = self._metadata[idx]
            result = [{"text": meta["text"], "hpo_id": meta.get("hpo_id", ""), "score": 1.0, "source": meta.get("source", "")}]
            self._query_cache[cache_key] = result
            return result

        q_emb = _encode(model, [query], normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
        fetch_k = top_k * 3
        scores, indices = self._search_vectors(q_emb, fetch_k)

        results = []
        seen_hpo: set[str] = set()
        for score_val, idx_val in zip(scores[0], indices[0]):
            if idx_val < 0 or score_val < threshold:
                break
            meta = self._metadata[int(idx_val)]
            hpo_id = meta.get("hpo_id", "")
            if hpo_id and hpo_id in seen_hpo:
                continue
            if hpo_id:
                seen_hpo.add(hpo_id)
            results.append({
                "text": meta["text"],
                "hpo_id": hpo_id,
                "score": round(float(score_val), 4),
                "source": meta.get("source", ""),
            })
            if len(results) >= top_k:
                break

        if len(self._query_cache) >= self._QUERY_CACHE_SIZE:
            oldest = next(iter(self._query_cache))
            del self._query_cache[oldest]
        self._query_cache[cache_key] = results
        return results

    def search_batch(
        self,
        queries: list[str],
        *,
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> dict[str, list[dict]]:
        """Search multiple queries efficiently in a single batch encode + FAISS search."""
        if not self.is_ready:
            return {q: [] for q in queries}

        model = _get_model()
        if model is None:
            return {q: [] for q in queries}

        exact_results: dict[str, list[dict]] = {}
        to_encode: list[tuple[int, str]] = []

        for i, q in enumerate(queries):
            q_lower = q.strip().lower()
            if q_lower in self._text_to_idx:
                idx = self._text_to_idx[q_lower]
                meta = self._metadata[idx]
                exact_results[q] = [{"text": meta["text"], "hpo_id": meta.get("hpo_id", ""), "score": 1.0, "source": meta.get("source", "")}]
            else:
                to_encode.append((i, q))

        if not to_encode:
            return exact_results

        encode_texts = [q for _, q in to_encode]
        q_embs = _encode(model, encode_texts, normalize_embeddings=True, batch_size=_embed_batch_size(), show_progress_bar=False).astype(np.float32)
        fetch_k = top_k * 3
        all_scores, all_indices = self._search_vectors(q_embs, fetch_k)

        result_map = dict(exact_results)
        for row, (_, query) in enumerate(to_encode):
            results = []
            seen_hpo: set[str] = set()
            for score_val, idx_val in zip(all_scores[row], all_indices[row]):
                if idx_val < 0 or score_val < threshold:
                    break
                meta = self._metadata[int(idx_val)]
                hpo_id = meta.get("hpo_id", "")
                if hpo_id and hpo_id in seen_hpo:
                    continue
                if hpo_id:
                    seen_hpo.add(hpo_id)
                results.append({
                    "text": meta["text"],
                    "hpo_id": hpo_id,
                    "score": round(float(score_val), 4),
                    "source": meta.get("source", ""),
                })
                if len(results) >= top_k:
                    break
            result_map[query] = results

        return result_map

    def cosine(self, text_a: str, text_b: str) -> Optional[float]:
        """Cosine similarity between two free-text strings via the loaded model.

        Used by MarkerDisambiguator T1b (context vs candidate-sense prototype).
        Returns None if the model is unavailable.
        """
        model = _get_model()
        if model is None:
            return None
        embs = _encode(
            model, [text_a, text_b], normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)
        return float(embs[0] @ embs[1])

    def get_text_by_hpo(self, hpo_id: str) -> Optional[str]:
        """Get the primary HPO term name for an HPO ID."""
        indices = self._hpo_to_indices.get(hpo_id, [])
        for idx in indices:
            meta = self._metadata[idx]
            if not meta.get("is_synonym", False):
                return meta["text"]
        if indices:
            return self._metadata[indices[0]]["text"]
        return None
