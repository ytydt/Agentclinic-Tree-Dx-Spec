#!/usr/bin/env python3
"""IMP-53 — MedCPT dense encoding of the CPG corpus (for the BM25/TF-IDF + MedCPT
hybrid retriever, CPG §17 B2/L1/L2 lexical-gap fix).

The §19 substrate (``data/corpus/cpg_index``) is TF-IDF-only, so a query that
shares no surface tokens with the gold DDx chunk (mechanism/eponym phrasing, B2)
cannot retrieve it. MedCPT (PubMedBERT bi-encoder, NCBI) gives a *dense* tower
trained on PubMed click logs; fusing it with the sparse tower (RRF) recovers the
lexical-gap misses without losing the sparse tower's exact-term precision.

This script ENCODES the corpus (the long pole — run in the background):

  1. read ``cpg_index/metadata.jsonl`` (id, title, content) — same chunk set as
     the sparse index, so the two towers are row-aligned by ``id``.
  2. encode [title, content] with ``ncbi/MedCPT-Article-Encoder`` (CLS, 768-d,
     dot-product space) in batches on the least-busy visible GPU.
  3. shard-checkpoint embeddings to ``cpg_medcpt_index/shards/`` so an interrupted
     run RESUMES instead of restarting.
  4. on completion, concatenate shards → ``embeddings.npy`` + a FAISS
     ``IndexFlatIP`` (``index.faiss``) + ``config.json`` + ``ids.json``.

    PYTHONPATH=src python scripts/build_medcpt_cpg_index.py            # full corpus
    PYTHONPATH=src python scripts/build_medcpt_cpg_index.py --limit 2000   # smoke
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SRC_INDEX = ROOT / "data" / "corpus" / "cpg_index"
OUT = ROOT / "data" / "corpus" / "cpg_medcpt_index"
SHARDS = OUT / "shards"
MODEL = "ncbi/MedCPT-Article-Encoder"
SHARD_ROWS = 5000          # embeddings per checkpoint shard
MAX_LEN = 512


def pick_gpu() -> int:
    """Least-used visible CUDA device by free memory (falls back to 0)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return -1
        best, best_free = 0, -1
        for i in range(torch.cuda.device_count()):
            free, _ = torch.cuda.mem_get_info(i)
            if free > best_free:
                best_free, best = free, i
        return best
    except Exception:
        return -1


def load_rows(limit: int | None) -> tuple[list[str], list[str], list[str]]:
    """Return (ids, titles, contents) from the sparse index metadata (row-aligned)."""
    ids, titles, contents = [], [], []
    with open(SRC_INDEX / "metadata.jsonl", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            d = json.loads(line)
            ids.append(str(d.get("id", i)))
            titles.append(str(d.get("title", "") or "")[:512])
            contents.append(str(d.get("content", "") or "")[:4000])
    return ids, titles, contents


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="encode only first N rows (smoke)")
    ap.add_argument("--batch", type=int, default=64)
    args = ap.parse_args()
    limit = args.limit or None

    import torch
    from transformers import AutoModel, AutoTokenizer

    gpu = pick_gpu()
    device = f"cuda:{gpu}" if gpu >= 0 else "cpu"
    print(f"[medcpt] device={device}  model={MODEL}", flush=True)

    ids, titles, contents = load_rows(limit)
    n = len(ids)
    print(f"[medcpt] corpus rows={n}", flush=True)
    SHARDS.mkdir(parents=True, exist_ok=True)
    (OUT / "ids.json").write_text(json.dumps(ids), encoding="utf-8")

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).to(device).eval()

    t0 = time.time()
    done_shards = {int(p.stem.split("_")[1]) for p in SHARDS.glob("shard_*.npy")}
    for s0 in range(0, n, SHARD_ROWS):
        sidx = s0 // SHARD_ROWS
        if sidx in done_shards:
            continue
        s1 = min(s0 + SHARD_ROWS, n)
        embs = []
        with torch.no_grad():
            for b in range(s0, s1, args.batch):
                e = min(b + args.batch, s1)
                pairs = [[titles[j], contents[j]] for j in range(b, e)]
                enc = tok(pairs, truncation=True, padding=True,
                          max_length=MAX_LEN, return_tensors="pt").to(device)
                out = model(**enc).last_hidden_state[:, 0, :]  # CLS (dot-product space)
                embs.append(out.cpu().to(torch.float32).numpy())
        arr = np.concatenate(embs, axis=0)
        np.save(SHARDS / f"shard_{sidx:05d}.npy", arr)
        el = time.time() - t0
        rate = (s1) / max(1e-6, el)
        eta = (n - s1) / max(1e-6, rate)
        print(f"[medcpt] shard {sidx} rows {s0}-{s1} | {s1}/{n} "
              f"({rate:.0f} rows/s, eta {eta/60:.1f} min)", flush=True)

    # ---- assemble: concat shards (in order) → embeddings.npy + FAISS IndexFlatIP
    shard_files = sorted(SHARDS.glob("shard_*.npy"), key=lambda p: int(p.stem.split("_")[1]))
    mats = [np.load(p) for p in shard_files]
    full = np.concatenate(mats, axis=0).astype("float32")
    assert full.shape[0] == n, f"row mismatch {full.shape[0]} != {n}"
    np.save(OUT / "embeddings.npy", full)

    import faiss
    index = faiss.IndexFlatIP(full.shape[1])
    index.add(full)
    faiss.write_index(index, str(OUT / "index.faiss"))
    (OUT / "config.json").write_text(json.dumps({
        "model": MODEL, "dim": int(full.shape[1]), "ntotal": int(n),
        "index_type": "IndexFlatIP", "space": "dot",
        "row_aligned_with": "data/corpus/cpg_index/metadata.jsonl",
        "max_len": MAX_LEN,
    }, indent=2), encoding="utf-8")
    print(f"[medcpt] DONE n={n} dim={full.shape[1]} -> {OUT}  ({(time.time()-t0)/60:.1f} min)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
