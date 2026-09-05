#!/usr/bin/env python3
"""Build a retrieval index over the exact corpus used by the ceiling audit.

The shipped indices under ``data/corpus/*_index`` cover a different snapshot
(3.3k of the 9.6k Merck chunks, an older PMC slice), so a retrieval miss on
them would be indistinguishable from an indexing gap.  This builds one index
over the same 861k chunks the audit scanned, so any miss in the trial is a
ranking failure and nothing else.

Text is not copied: each chunk is addressed by (source, byte offset) into its
original jsonl, and read back on demand.

Outputs to ``data/corpus/ceiling_trial_index/``:
    meta.jsonl          one row per chunk: gid, source, offset, title, section
    tfidf_vec.pkl       fitted TfidfVectorizer
    tfidf_mat.npz       csr matrix, L2-normalised
    dense.npy           float16 [N, 384] MiniLM embeddings, L2-normalised
    config.json
"""

from __future__ import annotations

import argparse
import json
import pickle
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data/corpus/ceiling_trial_index"

SOURCES = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
    "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
    "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
}

# the same corpus after the ingestion repairs of report S29: StatPearls with
# its <list>/<table-wrap> elements restored, pmc_oa with tables re-rendered
# from their JATS source and announced enumerations rejoined to their members,
# textbooks with OCR noise normalised.  Built side by side so the two indices
# can be compared on identical tasks.
SOURCES_V2 = dict(SOURCES)
SOURCES_V2.update({
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks_v2.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks_v2.jsonl",
    "textbooks": (ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
                  / "textbooks_chunks_normalised.jsonl"),
})
OUT_V2 = ROOT / "data/corpus/ceiling_trial_index_v2"

MODEL_DIR = "/data2/wanghongyi/models/all-MiniLM-L6-v2"


def chunk_text(row: dict) -> str:
    return row.get("text") or row.get("content") or ""


def iter_corpus(with_text: bool = True):
    """Yield (gid, source, offset, row) in a fixed order."""
    gid = 0
    for source, path in SOURCES.items():
        with path.open("rb") as handle:
            offset = handle.tell()
            for raw in handle:
                row = json.loads(raw)
                yield gid, source, offset, row
                offset += len(raw)
                gid += 1


def build_meta() -> list[dict]:
    meta = []
    t0 = time.time()
    for gid, source, offset, row in iter_corpus():
        # StatPearls encodes the section in the title suffix; keep it, the
        # extractor uses it to tell a Differential-Diagnosis list apart from a
        # definition paragraph.
        meta.append({
            "gid": gid,
            "source": source,
            "offset": offset,
            "native_id": str(row.get("id", "")),
            "article_id": str(row.get("article_id") or row.get("source_id") or ""),
            "title": str(row.get("title") or row.get("entry_title") or "")[:300],
            "section_path": str(row.get("section_path") or "")[:300],
            "tokens": row.get("tokens"),
        })
        if gid % 200000 == 0 and gid:
            print(f"  meta {gid} ({time.time()-t0:.0f}s)", flush=True)
    print(f"  meta done: {len(meta)} chunks ({time.time()-t0:.0f}s)", flush=True)
    return meta


def text_stream():
    for _gid, _source, _offset, row in iter_corpus():
        yield chunk_text(row)


def build_tfidf(n: int) -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer

    t0 = time.time()
    vec = TfidfVectorizer(
        lowercase=True,
        sublinear_tf=True,
        min_df=3,
        max_df=0.4,
        stop_words="english",
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]{1,}\b",
        dtype=np.float32,
    )
    mat = vec.fit_transform(text_stream())
    print(f"  tfidf {mat.shape} nnz={mat.nnz} ({time.time()-t0:.0f}s)", flush=True)
    assert mat.shape[0] == n, (mat.shape, n)
    sp.save_npz(OUT / "tfidf_mat.npz", mat.tocsr())
    with (OUT / "tfidf_vec.pkl").open("wb") as fh:
        pickle.dump(vec, fh)


def build_dense(n: int, batch: int, device: str) -> None:
    import torch
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_DIR, device=device)
    model.max_seq_length = 256
    model.half()

    out = np.zeros((n, model.get_sentence_embedding_dimension()), dtype=np.float16)
    buf: list[str] = []
    start = 0
    t0 = time.time()
    for _gid, _source, _offset, row in iter_corpus():
        buf.append(chunk_text(row)[:2000])
        if len(buf) == batch:
            emb = model.encode(buf, batch_size=batch, convert_to_numpy=True,
                               normalize_embeddings=True, show_progress_bar=False)
            out[start:start + len(buf)] = emb.astype(np.float16)
            start += len(buf)
            buf = []
            if start % (batch * 100) == 0:
                rate = start / max(time.time() - t0, 1e-9)
                print(f"  dense {start}/{n} ({rate:.0f}/s, eta {(n-start)/max(rate,1e-9)/60:.1f}m)",
                      flush=True)
    if buf:
        emb = model.encode(buf, batch_size=batch, convert_to_numpy=True,
                           normalize_embeddings=True, show_progress_bar=False)
        out[start:start + len(buf)] = emb.astype(np.float16)
        start += len(buf)
    assert start == n, (start, n)
    np.save(OUT / "dense.npy", out)
    print(f"  dense done {out.shape} ({time.time()-t0:.0f}s)", flush=True)
    del model
    torch.cuda.empty_cache()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-dense", action="store_true")
    ap.add_argument("--skip-tfidf", action="store_true")
    ap.add_argument("--batch", type=int, default=512)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--v2", action="store_true",
                    help="index the repaired corpus into ceiling_trial_index_v2")
    args = ap.parse_args()

    global OUT, SOURCES
    if args.v2:
        OUT, SOURCES = OUT_V2, SOURCES_V2
    for name, path in SOURCES.items():
        if not path.exists():
            raise SystemExit(f"missing source {name}: {path}")

    OUT.mkdir(parents=True, exist_ok=True)

    meta_path = OUT / "meta.jsonl"
    if meta_path.exists():
        n = sum(1 for _ in meta_path.open("rb"))
        print(f"meta.jsonl exists: {n} chunks", flush=True)
    else:
        meta = build_meta()
        with meta_path.open("w", encoding="utf-8") as fh:
            for m in meta:
                fh.write(json.dumps(m, ensure_ascii=False) + "\n")
        n = len(meta)

    if not args.skip_tfidf:
        print("building tfidf", flush=True)
        build_tfidf(n)
    if not args.skip_dense:
        print("building dense", flush=True)
        build_dense(n, args.batch, args.device)

    (OUT / "config.json").write_text(json.dumps({
        "n_chunks": n,
        "sources": {k: str(v.relative_to(ROOT)) for k, v in SOURCES.items()},
        "dense_model": MODEL_DIR,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, indent=2), encoding="utf-8")
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
