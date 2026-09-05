#!/usr/bin/env python3
"""Embed every string the join layer ever compares, once.

The trial's concept join is pure token-set matching, and section 4.3 of the
trial report showed it fails on pairs that are clinically the same phrase:
"p63 positivity" vs "p63 staining" (Jaccard 0.33), "unpasteurized milk" vs
"exposure to unpasteurized sheep stomach" (0.20).  A hand-written synonym
table would fix exactly those and nothing else, so the join fix is done with
the same sentence encoder the retriever already uses.

Output: ``join_embeddings.npz`` with a string list and an L2-normalised matrix.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
MODEL_DIR = "/data2/wanghongyi/models/all-MiniLM-L6-v2"

ARMS = [
    "trial_extraction_k30clean.json",
    "trial_extraction_k30oracleclean.json",
    "trial_extraction_k30oracleclean_groups.json",
]


def collect() -> list[str]:
    strings: set[str] = set()
    for name in ARMS:
        path = LEDGER / name
        if not path.exists():
            continue
        for case in json.loads(path.read_text(encoding="utf-8")):
            for a in case["assertions"]:
                if isinstance(a, dict):
                    for key in ("predicate", "subject", "comparator"):
                        v = (a.get(key) or "").strip()
                        if v:
                            strings.add(v)
            for f in case["findings"]:
                if isinstance(f, dict):
                    for key in ("label", "canonical"):
                        v = (f.get(key) or "").strip()
                        if v:
                            strings.add(v)
    for task in json.loads((LEDGER / "trial_tasks_11.json").read_text(encoding="utf-8")):
        for c in task["candidates"]:
            strings.add(c["label"])
            strings.update(x for x in (c.get("aliases") or []) if x)
    return sorted(s for s in strings if len(s) >= 2)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda:1")
    ap.add_argument("--batch", type=int, default=512)
    args = ap.parse_args()

    from sentence_transformers import SentenceTransformer

    strings = collect()
    print(f"{len(strings)} unique strings", flush=True)
    model = SentenceTransformer(MODEL_DIR, device=args.device)
    model.max_seq_length = 64
    emb = model.encode(strings, batch_size=args.batch, convert_to_numpy=True,
                       normalize_embeddings=True, show_progress_bar=False)
    out = LEDGER / "join_embeddings.npz"
    np.savez_compressed(out, strings=np.array(strings, dtype=object), emb=emb.astype(np.float32))
    print(f"wrote {out}  shape={emb.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
