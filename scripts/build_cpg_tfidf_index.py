#!/usr/bin/env python3
"""Build a dedicated TF-IDF index over the CPG corpus (cpg_chunks.jsonl).

Scoped IMP-31 enabler for the CPG-pipeline isolated experiment: indexes the
useful subset of cpg_chunks (WikEM + PMC-OA + Merck + NICE/society HTML) into a
**separate** dir so the live StatPearls/Textbooks index is left untouched.

Crucially, the metadata carries the full DDx schema (``source_id``,
``chunk_type``, ``entry_type``, ``syndrome_anchor``, ``wiki_links``) so that
``RAGRetriever.expand_ddx_siblings`` and ``cpg_chunk_gate`` actually fire
(unlike the live index whose metadata lacks these fields).

Filters applied:
  - chunk_type ∈ {differential, red_flag, evaluation, recommendation}
  - content length ≥ 120 chars
  - drop browser-check / cookie / JS-required noise pages

Produces:  data/corpus/cpg_index/{tfidf_vectorizer.pkl,tfidf_matrix.npz,metadata.jsonl,config.json}

    PYTHONPATH=src python scripts/build_cpg_tfidf_index.py
"""
from __future__ import annotations

import json
import pickle
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPG_CHUNKS = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
INDEX_DIR = ROOT / "data" / "corpus" / "cpg_index"

USEFUL = {"differential", "red_flag", "evaluation", "recommendation"}
NOISE = re.compile(
    r"checking your browser|verifying you are human|just a moment|enable javascript|"
    r"please enable cookies|access denied|cloudflare|are you a robot|captcha",
    re.I,
)
KEEP_META = (
    "id", "title", "section_path", "content", "article_id", "source_id",
    "source", "url", "entry_type", "chunk_type", "syndrome_anchor",
    "wiki_links", "license_note", "clinical_area", "tokens",
)


def load_useful(require_anchor: bool = False, keep_other: bool = False) -> list[dict]:
    kept: list[dict] = []
    seen_sha: set[str] = set()
    stats = {"total": 0, "noise": 0, "short": 0, "type": 0, "dup": 0}
    with open(CPG_CHUNKS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["total"] += 1
            d = json.loads(line)
            ct = d.get("chunk_type")
            if not keep_other and ct not in USEFUL:
                stats["type"] += 1
                continue
            content = (d.get("content") or "").strip()
            if len(content) < 120:
                stats["short"] += 1
                continue
            if NOISE.search(content[:200]):
                stats["noise"] += 1
                continue
            sha = d.get("sha256")
            if sha:
                if sha in seen_sha:
                    stats["dup"] += 1
                    continue
                seen_sha.add(sha)
            if require_anchor and not d.get("syndrome_anchor"):
                continue
            kept.append({k: d.get(k) for k in KEEP_META if k in d})
    print(f"  scanned={stats['total']} kept={len(kept)} "
          f"(dropped: type={stats['type']} short={stats['short']} "
          f"noise={stats['noise']} dup={stats['dup']})")
    return kept


def main() -> int:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy import sparse

    keep_other = "--keep-other" in sys.argv
    print("Loading CPG useful chunks ...")
    chunks = load_useful(keep_other=keep_other)
    if not chunks:
        print("ERROR: no chunks")
        return 1

    # index text = section_path + content + wiki_links (DDx entities boost recall)
    texts = []
    for c in chunks:
        wl = c.get("wiki_links") or []
        wl_txt = " ".join(wl) if isinstance(wl, list) else ""
        texts.append(f"{c.get('section_path') or c.get('title','')} {c.get('content','')} {wl_txt}")

    print(f"Building TF-IDF for {len(texts)} docs ...")
    t0 = time.time()
    vec = TfidfVectorizer(max_features=80000, ngram_range=(1, 2),
                          stop_words="english", sublinear_tf=True,
                          min_df=2, max_df=0.95)
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
              "index_type": "TfidfSparse", "sources": ["cpg_chunks"],
              "useful_only": not keep_other, "max_features": 80000}
    with open(INDEX_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"\nCPG index saved to {INDEX_DIR} ({mat.shape[0]} docs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
