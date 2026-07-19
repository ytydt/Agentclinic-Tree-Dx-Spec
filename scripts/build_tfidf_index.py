#!/usr/bin/env python3
"""Build a lightweight TF-IDF index over StatPearls + Textbooks corpus.

Much faster than dense encoding (~1-2 min total), provides good lexical recall.
Uses sklearn TfidfVectorizer + scipy sparse matrix for retrieval.

Produces:
  data/corpus/rag_index/tfidf_vectorizer.pkl
  data/corpus/rag_index/tfidf_matrix.npz
  data/corpus/rag_index/metadata.jsonl
  data/corpus/rag_index/config.json
"""

from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "data" / "corpus"
INDEX_DIR = CORPUS_DIR / "rag_index"


def load_chunks() -> list[dict]:
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


def main():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy import sparse

    print("Loading corpus chunks ...")
    chunks = load_chunks()
    if not chunks:
        print("ERROR: No chunks found.")
        return 1

    texts = [f"{c.get('title', '')} {c.get('content', '')}" for c in chunks]
    print(f"Building TF-IDF vectorizer for {len(texts)} documents ...")

    t0 = time.time()
    vectorizer = TfidfVectorizer(
        max_features=50000,
        ngram_range=(1, 2),
        stop_words="english",
        sublinear_tf=True,
        min_df=2,
        max_df=0.95,
    )
    tfidf_matrix = vectorizer.fit_transform(texts)
    elapsed = time.time() - t0
    print(f"TF-IDF done in {elapsed:.1f}s: matrix shape {tfidf_matrix.shape}")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    with open(INDEX_DIR / "tfidf_vectorizer.pkl", "wb") as f:
        pickle.dump(vectorizer, f)

    sparse.save_npz(INDEX_DIR / "tfidf_matrix.npz", tfidf_matrix)

    with open(INDEX_DIR / "metadata.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    config = {
        "model": "tfidf",
        "dim": tfidf_matrix.shape[1],
        "ntotal": tfidf_matrix.shape[0],
        "index_type": "TfidfSparse",
        "sources": ["statpearls", "textbooks", "merck"],
        "max_features": 50000,
    }
    with open(INDEX_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"\nIndex saved to {INDEX_DIR}")
    print(f"  tfidf_matrix.npz:    {(INDEX_DIR / 'tfidf_matrix.npz').stat().st_size / 1e6:.1f} MB")
    print(f"  tfidf_vectorizer.pkl: {(INDEX_DIR / 'tfidf_vectorizer.pkl').stat().st_size / 1e6:.1f} MB")
    print(f"  metadata.jsonl:      {len(chunks)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
