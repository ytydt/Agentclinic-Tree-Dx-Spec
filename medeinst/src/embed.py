"""
MedCPT embeddings for Eq. 2 cosine(e_pscript, e_pobs).

Paper 2601.06636 does not name an encoder. This repo already uses NCBI MedCPT
in HybridCPGRetriever / eval_medcpt_dir_coverage.py:

  QUERY_ENCODER = "ncbi/MedCPT-Query-Encoder"
  CLS pooling, max_length=64

Both p_script and p_obs are short clinical phrases, so Query-Encoder is used
on both sides (symmetric cosine), then L2-normalized.
"""

from __future__ import annotations

import math
import threading
from typing import Sequence

# Parent: src/agentclinic_tree_dx/knowledge/hybrid_cpg_retriever.py
QUERY_ENCODER = "ncbi/MedCPT-Query-Encoder"
QUERY_MAX_LEN = 64


class MedCPTEmbedder:
    """Lazy-load NCBI MedCPT query encoder (cached under ~/.cache/huggingface)."""

    def __init__(self, model_name: str = QUERY_ENCODER, device: str | None = None) -> None:
        import os
        import torch
        from transformers import AutoModel, AutoTokenizer

        if device is None:
            device = os.environ.get("MEDCPT_DEVICE", "cpu")
            if device.startswith("cuda"):
                try:
                    if not torch.cuda.is_available():
                        device = "cpu"
                except Exception:
                    device = "cpu"
        self.device = device
        self.tok = AutoTokenizer.from_pretrained(model_name)
        self.enc = AutoModel.from_pretrained(model_name).to(device).eval()
        self._cache: dict[str, tuple[float, ...]] = {}
        self._lock = threading.Lock()

    def encode_one(self, text: str) -> list[float]:
        with self._lock:
            cached = self._cache.get(text)
            if cached is not None:
                return list(cached)
            import torch

            with torch.no_grad():
                batch = self.tok(
                    [text or " "],
                    truncation=True,
                    padding=True,
                    max_length=QUERY_MAX_LEN,
                    return_tensors="pt",
                ).to(self.device)
                hidden = self.enc(**batch).last_hidden_state[:, 0, :].float()
                vec = hidden[0].cpu().tolist()
            n = math.sqrt(sum(x * x for x in vec)) or 1.0
            out = [x / n for x in vec]
            self._cache[text] = tuple(out)
            return out

    def cosine(self, text_a: str, text_b: str) -> float:
        a = self.encode_one(text_a)
        b = self.encode_one(text_b)
        return sum(x * y for x, y in zip(a, b))


_ACTIVE: MedCPTEmbedder | None = None
_MODE = "bow_l2"


def configure_embedding(name: str) -> str:
    """Install the global Eq. 2 embedder. name: medcpt | bow_l2."""
    global _ACTIVE, _MODE
    name = (name or "medcpt").lower()
    if name in {"medcpt", "ncbi/medcpt-query-encoder", "ncbi/medcpt"}:
        if _ACTIVE is None:
            _ACTIVE = MedCPTEmbedder()
        _MODE = "medcpt"
        return _MODE
    _MODE = "bow_l2"
    return _MODE


def active_mode() -> str:
    return _MODE


def medcpt_cosine(text_a: str, text_b: str) -> float:
    if _ACTIVE is None:
        configure_embedding("medcpt")
    assert _ACTIVE is not None
    return _ACTIVE.cosine(text_a, text_b)
