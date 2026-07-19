#!/usr/bin/env python3
"""Build a TF-IDF retrieval index over the case-report corpus.

Reads data/cpg/processed/case_report_chunks.jsonl (produced by
build_case_report_corpus.py) and writes a RAGRetriever-compatible TF-IDF index
to data/corpus/case_report_index/, so the case-report retrieval LAYER plugs into
GuidelineBranchSource / CaseReportBranchSource with zero new retrieval code.

    PYTHONPATH=src python scripts/build_case_report_index.py
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "cpg" / "processed" / "case_report_chunks.jsonl"
INDEX_DIR = ROOT / "data" / "corpus" / "case_report_index"

KEEP_META = (
    "id", "title", "section_path", "content", "article_id", "source_id",
    "source", "url", "entry_type", "chunk_type", "syndrome_anchor",
    "wiki_links", "license_note",
)


def main() -> int:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy import sparse

    if not CHUNKS.exists():
        print(f"ERROR: {CHUNKS} not found. Run build_case_report_corpus.py first.")
        return 1

    chunks: list[dict] = []
    with open(CHUNKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if (d.get("content") or "").strip():
                chunks.append({k: d.get(k) for k in KEEP_META if k in d})
    if not chunks:
        print("ERROR: no case-report chunks")
        return 1

    texts = []
    for c in chunks:
        wl = c.get("wiki_links") or []
        wl_txt = " ".join(wl) if isinstance(wl, list) else ""
        texts.append(f"{c.get('section_path') or c.get('title','')} "
                     f"{c.get('content','')} {wl_txt}")

    print(f"Building TF-IDF for {len(texts)} case-report docs ...")
    t0 = time.time()
    # min_df=1 (corpus is small vs the 200k CPG index; 2 would drop rare terms)
    vec = TfidfVectorizer(max_features=40000, ngram_range=(1, 2),
                          stop_words="english", sublinear_tf=True,
                          min_df=1, max_df=0.95)
    mat = vec.fit_transform(texts)
    print(f"  done in {time.time()-t0:.1f}s, shape={mat.shape}")

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_DIR / "tfidf_vectorizer.pkl", "wb") as f:
        pickle.dump(vec, f)
    sparse.save_npz(INDEX_DIR / "tfidf_matrix.npz", mat)
    with open(INDEX_DIR / "metadata.jsonl", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    config = {"model": "tfidf", "dim": mat.shape[1], "ntotal": mat.shape[0],
              "index_type": "TfidfSparse", "sources": ["case_report_chunks"],
              "max_features": 40000}
    with open(INDEX_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"\nCase-report index saved to {INDEX_DIR} ({mat.shape[0]} docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
