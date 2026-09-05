#!/usr/bin/env python3
"""F1: corpus-side discriminativeness for every (candidate, finding) pair.

Section 6 of the trial report showed the engine degenerates into a coverage
count because a well-documented competitor accumulates many true but
non-separating features.  The weight that fixes this has to say how much more
often a finding is stated about *this* disease than about the other candidates
in the same case, and that is a corpus statistic, not something the extraction
can supply.

P(f|h) is measured over the documents the corpus considers to be *about* h --
those whose title names h -- rather than every document that happens to mention
h, because a disease mentioned in passing in a 300-page textbook would otherwise
dilute to zero.  Token presence is read off the TF-IDF matrix of the trial
index, so the count is over the same 861,131 chunks the audit scanned.

Output: ``corpus_lift_table.json``, {"norm(candidate)||norm(finding)": log lift}.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
INDEX = ROOT / "data/corpus/ceiling_trial_index"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

ALPHA = 0.5          # Laplace smoothing on the topic proportion
MIN_TOPIC_CHUNKS = 8  # below this the proportion has no resolution

# The engine's tokeniser drops tokens shorter than three characters and a list
# of generic clinical nouns, which is right for joining a predicate to a finding
# and wrong for deciding what a document is about: it turns "Long QT Syndrome"
# into {long} and so makes every title containing the word "long" a topic
# document for it.  Titles get their own tokeniser that keeps everything.
TITLE_STOP = {"the", "of", "and", "a", "an", "in", "for", "to", "with", "its"}


def title_tokens(s: str) -> set[str]:
    return {w for w in eng.norm(s).split() if w and w not in TITLE_STOP}


def load_index():
    meta = [json.loads(l) for l in (INDEX / "meta.jsonl").open(encoding="utf-8")]
    with (INDEX / "tfidf_vec.pkl").open("rb") as fh:
        vec = pickle.load(fh)
    mat = sp.load_npz(INDEX / "tfidf_mat.npz").tocsc()
    return meta, vec, mat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11.json")
    ap.add_argument("--arm", default="k30oracleclean")
    ap.add_argument("--out", default="corpus_lift_table.json")
    ap.add_argument("--anchor", choices=["mention", "title"], default="mention")
    args = ap.parse_args()

    print("loading index", flush=True)
    meta, vec, mat = load_index()
    n = len(meta)

    # gid -> document, and a normalised title per document
    doc_of_gid = np.zeros(n, dtype=np.int32)
    doc_title: list[str] = []
    doc_ids: dict[str, int] = {}
    for gid, m in enumerate(meta):
        key = f"{m['source']}|{m['article_id']}|{m['title'][:80]}"
        d = doc_ids.get(key)
        if d is None:
            d = len(doc_title)
            doc_ids[key] = d
            doc_title.append(eng.norm(m["title"]))
        doc_of_gid[gid] = d
    n_docs = len(doc_title)
    print(f"  {n} chunks in {n_docs} documents", flush=True)

    # documents whose title contains a given token, for the topic lookup
    title_tok_docs: dict[str, set[int]] = defaultdict(set)
    for d, t in enumerate(doc_title):
        for w in title_tokens(t):
            title_tok_docs[w].add(d)

    chunks_of_doc: dict[int, list[int]] = defaultdict(list)
    for gid in range(n):
        chunks_of_doc[int(doc_of_gid[gid])].append(gid)

    vocab = vec.vocabulary_
    tok_chunk_cache: dict[str, np.ndarray] = {}

    def chunks_with_token(tok: str) -> np.ndarray:
        if tok in tok_chunk_cache:
            return tok_chunk_cache[tok]
        col = vocab.get(tok)
        out = (np.empty(0, dtype=np.int32) if col is None
               else mat.indices[mat.indptr[col]:mat.indptr[col + 1]].astype(np.int32))
        tok_chunk_cache[tok] = out
        return out

    def topic_docs(label: str, aliases: list[str]) -> set[int]:
        best: set[int] = set()
        for name in [label, *aliases]:
            toks = title_tokens(name)
            if not toks:
                continue
            sets = [title_tok_docs.get(t, set()) for t in toks]
            best |= set.intersection(*sets) if all(sets) else set()
        return best

    def mention_chunks(label: str, aliases: list[str]) -> np.ndarray:
        """Chunks that name the candidate.  Title anchoring is unusable on the
        StatPearls slice -- a third of its entries carry a title taken from
        their own reference list, and `article_id` is empty for all 367,799
        chunks, so there are no document boundaries either (see
        statpearls_title_audit.json).  A chunk is 36-154 tokens, short enough
        that naming a disease means being about it."""
        acc: np.ndarray | None = None
        for name in [label, *aliases]:
            toks = [t for t in title_tokens(name) if t in vocab]
            if not toks:
                continue
            hit = chunks_with_token(toks[0])
            for t in toks[1:]:
                hit = np.intersect1d(hit, chunks_with_token(t))
                if hit.size == 0:
                    break
            acc = hit if acc is None else np.union1d(acc, hit)
        return acc if acc is not None else np.empty(0, dtype=np.int32)

    def chunks_with_all(phrase: str) -> np.ndarray | None:
        toks = [t for t in eng.tokens(phrase) if t in vocab]
        if not toks:
            return None
        acc = chunks_with_token(toks[0])
        for t in toks[1:]:
            acc = np.intersect1d(acc, chunks_with_token(t))
            if acc.size == 0:
                break
        return acc

    tasks = json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))
    extraction = {e["case_key"]: e for e in
                  json.loads((LEDGER / f"trial_extraction_{args.arm}.json").read_text("utf-8"))}

    table: dict[str, float] = {}
    stats = []
    for task in tasks:
        key = task["case_key"]
        cands = task["candidates"]
        # Counting at chunk level instead of document level removes the length
        # confound: a candidate whose topic article is a 200-chunk textbook
        # section would otherwise "contain" every finding and score positive on
        # all of them, which is what put wall thickness and QTc on the same
        # candidate in the first build.
        if args.anchor == "title":
            topics = {c["label"]: topic_docs(c["label"], c.get("aliases") or []) for c in cands}
            topic_chunks = {k: np.array(sorted(g for d in v for g in chunks_of_doc[d]),
                                        dtype=np.int32) for k, v in topics.items()}
        else:
            topics = {}
            topic_chunks = {c["label"]: mention_chunks(c["label"], c.get("aliases") or [])
                            for c in cands}
        usable = {k: v for k, v in topic_chunks.items() if len(v) >= MIN_TOPIC_CHUNKS}
        findings = {(f.get("label") or "").strip()
                    for f in extraction[key]["findings"] if isinstance(f, dict)}
        findings |= {(f.get("canonical") or "").strip()
                     for f in extraction[key]["findings"] if isinstance(f, dict)}
        findings = {f for f in findings if len(f) >= 3}

        n_pairs = 0
        for fnd in findings:
            hits = chunks_with_all(fnd)
            if hits is None:
                continue
            probs = {}
            for label, tchunks in usable.items():
                k = np.intersect1d(tchunks, hits).size
                probs[label] = (k + ALPHA) / (len(tchunks) + 2 * ALPHA)
            if len(probs) < 2:
                continue
            mean_p = sum(probs.values()) / len(probs)
            for label, p in probs.items():
                table[f"{eng.norm(label)}||{eng.norm(fnd)}"] = round(math.log(p / mean_p), 4)
                n_pairs += 1
        stats.append({"case": key, "n_candidates": len(cands), "n_usable": len(usable),
                      "n_findings": len(findings), "n_pairs": n_pairs, "anchor": args.anchor,
                      "topic_docs": {k: len(v) for k, v in sorted(topics.items())},
                      "topic_chunks": {k: int(len(v)) for k, v in sorted(topic_chunks.items())}})
        print(f"  {key:24s} usable {len(usable)}/{len(cands)} candidates, "
              f"{n_pairs} pairs", flush=True)

    (LEDGER / args.out).write_text(json.dumps(table, indent=0, ensure_ascii=False), encoding="utf-8")
    (LEDGER / args.out.replace(".json", "_stats.json")).write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / args.out}  ({len(table)} pairs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
