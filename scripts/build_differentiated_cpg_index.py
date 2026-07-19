#!/usr/bin/env python3
"""Build the DIFFERENTIATED (source-stratified) CPG index for IMP-61 (CPG §16).

Unlike the single unified TF-IDF (``build_cpg_tfidf_index.py``), this produces
**one TF-IDF sub-index per source bucket** so each source's IDF is computed in
isolation — killing the PMC-OA IDF pollution that buries terse WikEM/Merck
syndrome-entry chunks under thousands of PMC prose chunks (§16.2 defect: WikEM
entry true rank median 38; Recall@10 0.659). Per-source field weighting
(``index_text``) further promotes the field that carries each source's entry
semantics (WikEM anchor+wiki_links, Merck/NICE section_path, PMC anchor).

Buckets: wikem | merck | nice | pmc | society.

Output dir ``data/corpus/cpg_diff_index/``:
  - metadata.jsonl              global row list (KEEP_META + ``bucket``)
  - <bucket>_vec.pkl            TfidfVectorizer for the bucket
  - <bucket>_mat.npz            sparse doc-term matrix (rows = bucket order)
  - manifest.json               bucket -> [global_idx...] (row alignment), config

``DifferentiatedCPGRetriever`` loads this and exposes a RAGRetriever-compatible
``search`` / ``expand_ddx_siblings`` / ``is_ready`` surface.

    PYTHONPATH=src python scripts/build_differentiated_cpg_index.py
"""
from __future__ import annotations

import json
import pickle
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CPG_CHUNKS = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
INDEX_DIR = ROOT / "data" / "corpus" / "cpg_diff_index"

USEFUL = {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
NOISE = re.compile(
    r"checking your browser|verifying you are human|just a moment|enable javascript|"
    r"please enable cookies|access denied|cloudflare|are you a robot|captcha",
    re.I,
)
SOCIETY = {
    "ACC/AHA", "IDSA", "ESC", "ASH", "ACOG", "ACR", "SSC/SCCM", "WHO", "GOLD",
    "GINA", "CDC", "CDC/MMWR", "EULAR", "USPSTF", "KDIGO", "AAN", "ATS", "RCOG",
    "IDSA/ATS", "IDSA/SHEA", "Endocrine Society", "ESMO",
}
KEEP_META = (
    "id", "title", "section_path", "content", "article_id", "source_id",
    "source", "url", "entry_type", "chunk_type", "syndrome_anchor",
    "wiki_links", "license_note", "clinical_area", "tokens",
)


def bucket_of(source: str) -> str:
    if source == "WikEM":
        return "wikem"
    if source == "Merck-Manual-19e":
        return "merck"
    if source == "NICE":
        return "nice"
    if source == "PMC-OA":
        return "pmc"
    return "society"


def index_text(d: dict, mode: str) -> str:
    """Source-appropriate field weighting (repetition = weight in TF-IDF)."""
    sp = d.get("section_path") or d.get("title") or ""
    content = d.get("content") or ""
    anchor = d.get("syndrome_anchor") or ""
    wl = d.get("wiki_links") or []
    wl_txt = " ".join(wl) if isinstance(wl, list) else str(wl)
    if mode == "wikem":
        return f"{sp} {sp} {sp} {anchor} {anchor} {wl_txt} {wl_txt} {wl_txt} {content}"
    if mode == "merck":
        return f"{sp} {sp} {content}"
    if mode == "nice":
        return f"{sp} {sp} {content}"
    if mode == "pmc":
        return f"{anchor} {anchor} {content}"
    return content  # society


def load_rows() -> list[dict]:
    rows: list[dict] = []
    seen_sha: set[str] = set()
    stats = Counter()
    with CPG_CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["total"] += 1
            d = json.loads(line)
            ct = d.get("chunk_type")
            if ct not in USEFUL and d.get("entry_type") != "syndrome_entry":
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
            row = {k: d.get(k) for k in KEEP_META if k in d}
            row["bucket"] = bucket_of(d.get("source", ""))
            rows.append(row)
    print(f"  scanned={stats['total']} kept={len(rows)} "
          f"(type={stats['type']} short={stats['short']} "
          f"noise={stats['noise']} dup={stats['dup']})", flush=True)
    return rows


def main() -> int:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from scipy import sparse

    print("Loading CPG rows ...", flush=True)
    rows = load_rows()
    if not rows:
        print("ERROR: no rows")
        return 1
    by_bucket: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_bucket[r["bucket"]].append(i)
    print("  buckets:", {k: len(v) for k, v in by_bucket.items()}, flush=True)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with (INDEX_DIR / "metadata.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifest: dict = {"buckets": {}, "config": {
        "ngram_range": [1, 2], "max_features": 60000, "min_df": 2, "max_df": 0.95,
        "n_rows": len(rows), "source": "cpg_chunks", "useful_only": True}}
    for b, idxs in by_bucket.items():
        if not idxs:
            continue
        t0 = time.time()
        texts = [index_text(rows[i], b) for i in idxs]
        vec = TfidfVectorizer(max_features=60000, ngram_range=(1, 2),
                              stop_words="english", sublinear_tf=True,
                              min_df=2, max_df=0.95)
        try:
            mat = vec.fit_transform(texts)
        except ValueError as e:
            print(f"  [{b}] skipped: {e}", flush=True)
            continue
        with (INDEX_DIR / f"{b}_vec.pkl").open("wb") as f:
            pickle.dump(vec, f)
        sparse.save_npz(INDEX_DIR / f"{b}_mat.npz", mat)
        manifest["buckets"][b] = idxs
        print(f"  [{b}] {mat.shape} in {time.time()-t0:.1f}s", flush=True)

    with (INDEX_DIR / "manifest.json").open("w", encoding="utf-8") as f:
        json.dump(manifest, f)
    print(f"\nDifferentiated CPG index saved to {INDEX_DIR} "
          f"({len(rows)} rows, {len(manifest['buckets'])} buckets)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
