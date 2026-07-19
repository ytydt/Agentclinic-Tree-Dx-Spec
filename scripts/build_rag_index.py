#!/usr/bin/env python3
"""Build FAISS vector index from StatPearls + Textbooks chunks.

Uses sentence-transformers for encoding (MedCPT or PubMedBERT fallback).
Produces:
  data/corpus/rag_index/faiss.index   — FAISS IVF-PQ or Flat index
  data/corpus/rag_index/metadata.jsonl — parallel metadata per vector
  data/corpus/rag_index/config.json   — index configuration

Usage:
  python scripts/build_rag_index.py [--model ncbi/MedCPT-Article-Encoder]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import faiss
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "corpus"
INDEX_DIR = CORPUS_DIR / "rag_index"

MODELS_PRIORITY = [
    "ncbi/MedCPT-Article-Encoder",
    "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract",
    "sentence-transformers/all-MiniLM-L6-v2",
]


def load_chunks() -> list[dict]:
    """Load all corpus chunks from JSONL files."""
    chunks = []
    for name in [
        "statpearls/statpearls_chunks.jsonl",
        "textbooks/textbooks_chunks.jsonl",
        "merck/merck_manual_19e_chunks.jsonl",
    ]:
        path = CORPUS_DIR / name
        if not path.exists():
            print(f"  SKIP {path} (not found)")
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
        print(f"  Loaded {path.name}: running total {len(chunks)}")
    return chunks


def encode_chunks(chunks: list[dict], model_name: str, batch_size: int = 64) -> np.ndarray:
    """Encode chunk texts using sentence-transformers."""
    from sentence_transformers import SentenceTransformer

    print(f"Loading encoder: {model_name} ...")
    model = SentenceTransformer(model_name)

    texts = [f"{c.get('title', '')} {c.get('content', '')}" for c in chunks]
    print(f"Encoding {len(texts)} chunks (batch_size={batch_size}) ...")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    elapsed = time.time() - t0
    print(f"Encoding done in {elapsed:.1f}s ({len(texts)/elapsed:.0f} chunks/s)")
    return np.array(embeddings, dtype=np.float32)


def build_index(embeddings: np.ndarray) -> faiss.Index:
    """Build a FAISS index. Use IVF-PQ for large corpora, Flat for small."""
    n, dim = embeddings.shape
    print(f"Building FAISS index: {n} vectors, dim={dim}")

    if n < 10000:
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings)
    else:
        nlist = min(int(n ** 0.5), 1024)
        quantizer = faiss.IndexFlatIP(dim)
        m_sub = min(dim // 4, 64)
        if m_sub < 1:
            m_sub = 1
        while dim % m_sub != 0 and m_sub > 1:
            m_sub -= 1
        index = faiss.IndexIVFPQ(quantizer, dim, nlist, m_sub, 8)
        index.train(embeddings)
        index.add(embeddings)
        index.nprobe = min(nlist // 4, 32)

    print(f"Index built: type={type(index).__name__}, ntotal={index.ntotal}")
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Sentence-transformer model name")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    print("=" * 60)
    print("Loading corpus chunks ...")
    chunks = load_chunks()
    if not chunks:
        print("ERROR: No chunks found. Run build_statpearls_corpus.py first.")
        return 1

    model_name = args.model
    if not model_name:
        from sentence_transformers import SentenceTransformer
        for m in MODELS_PRIORITY:
            try:
                SentenceTransformer(m)
                model_name = m
                break
            except Exception:
                continue
        if not model_name:
            model_name = MODELS_PRIORITY[-1]

    embeddings = encode_chunks(chunks, model_name, args.batch_size)
    index = build_index(embeddings)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "faiss.index"))
    with open(INDEX_DIR / "metadata.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    config = {
        "model": model_name,
        "dim": int(embeddings.shape[1]),
        "ntotal": int(index.ntotal),
        "index_type": type(index).__name__,
        "sources": ["statpearls", "textbooks"],
    }
    with open(INDEX_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"\nIndex saved to {INDEX_DIR}")
    print(f"  faiss.index:   {(INDEX_DIR / 'faiss.index').stat().st_size / 1e6:.1f} MB")
    print(f"  metadata.jsonl: {len(chunks)} entries")
    print(f"  config.json:   {json.dumps(config)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
