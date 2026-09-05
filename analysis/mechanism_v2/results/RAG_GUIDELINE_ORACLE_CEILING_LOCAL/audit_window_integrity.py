#!/usr/bin/env python3
"""Does the +-1 retrieval window deliver what it promises, old index vs v2?

TrialRetriever.passage() glues the hit chunk to its same-document neighbours and
run_trial_retrieval.py calls it with the default window=1, so extraction sees
three chunks, not one.  Two things can silently break that:

  document guard   the neighbour test is doc_key = "source|article_id".  An
                   empty article_id makes every chunk of a source look like one
                   document, so the window runs across article boundaries.
  truncation       run_trial_extraction.py cuts the passage at
                   --max-passage-chars (6000).  Merging lists back into their
                   lead-in makes chunks longer, so the three-chunk window can
                   now cross that line and lose its tail.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
MAX_PASSAGE_CHARS = 6000

INDEXES = {
    "old": (ROOT / "data/corpus/ceiling_trial_index", {
        "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
        "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
        "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
        "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
        "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
        "textbooks": ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl",
    }),
    "v2": (ROOT / "data/corpus/ceiling_trial_index_v2", {
        "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
        "manifest_cpg": ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl",
        "wikem": ROOT / "data/cpg/processed/wikem_ddx_chunks.jsonl",
        "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks_v2.jsonl",
        "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks_v2.jsonl",
        "textbooks": (ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
                      / "textbooks_chunks_normalised.jsonl"),
    }),
}


def run(tag: str, index: Path, sources: dict) -> None:
    meta = [json.loads(l) for l in (index / "meta.jsonl").open(encoding="utf-8")]
    n = len(meta)
    doc_key = [f"{m['source']}|{m['article_id']}" for m in meta]

    # True article identity, independent of the doc_key the retriever computes.
    # In the old build every StatPearls native_id is "_p0", "_p1", ... with the
    # counter restarting at each article and the prefix empty, so the only way
    # to see the article boundaries is to watch that counter wrap.
    def suffix_num(nid: str) -> int | None:
        tail = nid.rsplit("_p", 1)[-1] if "_p" in nid else nid.rsplit("_", 1)[-1]
        return int(tail) if tail.isdigit() else None

    true_key: list[str] = []
    doc_seq = 0
    prev_num: int | None = None
    prev_src = None
    for m in meta:
        s = m["source"]
        num = suffix_num(m["native_id"])
        prefix = (m["native_id"].rsplit("_p", 1)[0] if "_p" in m["native_id"]
                  else m["native_id"].rsplit("_", 1)[0])
        if s != prev_src or num is None or prev_num is None or num <= prev_num:
            doc_seq += 1
        prev_num, prev_src = num, s
        # prefer a real identifier when there is one; fall back to the counter
        ident = (prefix or m["article_id"] or f"seq{doc_seq}")
        true_key.append(f"{s}|{ident}" if prefix or m["article_id"]
                        else f"{s}|seq{doc_seq}")

    # how often the guard admits a neighbour from another document
    leak = Counter()
    tot = Counter()
    for g in range(n):
        s = meta[g]["source"]
        for h in (g - 1, g + 1):
            if not (0 <= h < n):
                continue
            tot[s] += 1
            if doc_key[h] == doc_key[g] and true_key[h] != true_key[g]:
                leak[s] += 1

    # length of the window that extraction actually receives
    handles: dict[str, object] = {}

    def text2(g: int) -> str:
        m = meta[g]
        h = handles.get(m["source"])
        if h is None:
            h = sources[m["source"]].open("rb")
            handles[m["source"]] = h
        h.seek(m["offset"])
        row = json.loads(h.readline())
        return row.get("text") or row.get("content") or ""

    step = max(1, n // 40000)
    lens: list[int] = []
    trunc = Counter()
    seen = Counter()
    for g in range(0, n, step):
        lo = g
        while lo - 1 >= 0 and g - (lo - 1) <= 1 and doc_key[lo - 1] == doc_key[g]:
            lo -= 1
        hi = g
        while hi + 1 < n and (hi + 1) - g <= 1 and doc_key[hi + 1] == doc_key[g]:
            hi += 1
        L = len("\n".join(text2(x) for x in range(lo, hi + 1)))
        lens.append(L)
        s = meta[g]["source"]
        seen[s] += 1
        if L > MAX_PASSAGE_CHARS:
            trunc[s] += 1
    for h in handles.values():
        h.close()

    lens.sort()
    print(f"\n=== {tag}  ({n} chunks) ===")
    print("  +-1 window admits a neighbour from a DIFFERENT document:")
    for s in sorted(tot):
        v = leak[s]
        print(f"    {s:<14}{v:>8} / {tot[s]:<8} {v/tot[s]:6.2%}")
    print(f"  3-chunk window length: median {lens[len(lens)//2]}, "
          f"p90 {lens[int(len(lens)*0.9)]}, p99 {lens[int(len(lens)*0.99)]}, "
          f"max {lens[-1]}")
    over = sum(trunc.values())
    print(f"  exceeds --max-passage-chars={MAX_PASSAGE_CHARS}: "
          f"{over}/{len(lens)} ({over/len(lens):.2%}) of sampled windows")
    for s in sorted(trunc, key=lambda x: -trunc[x]):
        print(f"    {s:<14}{trunc[s]:>7} / {seen[s]:<7} {trunc[s]/seen[s]:6.2%}")


def main() -> int:
    for tag in (sys.argv[1:] or ["old", "v2"]):
        index, sources = INDEXES[tag]
        run(tag, index, sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
