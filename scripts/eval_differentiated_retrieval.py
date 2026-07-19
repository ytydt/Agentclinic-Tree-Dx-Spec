#!/usr/bin/env python3
"""Experiment: does a UNIFIED retrieval method hurt syndrome-entry recall when
each data source has its own best organisation? And does a DIFFERENTIATED
(source-stratified) retriever fix it?  (CPG §16)

Two query sets (clean syndrome entry points):
  - WikEM   : syndrome_anchor (chief complaint) → gold = that page's chunks;
              gold DDx entities = union of wiki_links on the page.
  - Merck   : "Approach to ..." chapter complaint → gold = that chapter's chunks.

Arms:
  A. unified      : single TF-IDF over all useful chunks, one query template
                    "approach to {S} differential diagnosis evaluation".
  B. differentiated: per-source sub-index + source-specific query form + field
                    weighting, fused by Reciprocal Rank Fusion (k=60) with a
                    syndrome_entry / anchor-match boost.

Metrics (per arm, per query set, at k):
  - entry Recall@k         : >=1 gold chunk in top-k
  - median first-gold rank : where the entry surfaces (lower = better)
  - DDx entity coverage@k  : (WikEM) fraction of gold wiki_links covered by any
                             retrieved chunk text
Diagnostics (defect evidence):
  - top-k source composition for failed unified queries (PMC flooding)
  - IDF pollution: syndrome-term IDF in unified vs WikEM-only corpus
  - length skew  : median content length by source

Outputs: data/cpg/eval/differentiated_retrieval_report.json

    PYTHONPATH=src python scripts/eval_differentiated_retrieval.py
    python scripts/eval_differentiated_retrieval.py --k 10 --pmc-cap 0
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
OUT = ROOT / "data" / "cpg" / "eval" / "differentiated_retrieval_report.json"

USEFUL = {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
NOISE = re.compile(
    r"checking your browser|verifying you are human|just a moment|enable javascript|"
    r"please enable cookies|access denied|cloudflare|are you a robot|captcha",
    re.I,
)

# Society guideline sources share a structure (long disease-management prose).
SOCIETY = {
    "ACC/AHA", "IDSA", "ESC", "ASH", "ACOG", "ACR", "SSC/SCCM", "WHO", "GOLD",
    "GINA", "CDC", "CDC/MMWR", "EULAR", "USPSTF", "KDIGO", "AAN", "ATS", "RCOG",
    "IDSA/ATS", "IDSA/SHEA", "Endocrine Society", "ESMO",
}


def norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)          # drop "(geriatrics)" etc.
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


def toks(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(t) > 2}


def load_chunks(pmc_cap: int) -> list[dict]:
    rows: list[dict] = []
    pmc = 0
    seen_sha: set[str] = set()
    for line in CHUNKS.open(encoding="utf-8"):
        d = json.loads(line)
        ct = d.get("chunk_type")
        if ct not in USEFUL and d.get("entry_type") != "syndrome_entry":
            continue
        content = (d.get("content") or "").strip()
        if len(content) < 120:
            continue
        if NOISE.search(content[:200]):
            continue
        sha = d.get("sha256")
        if sha and sha in seen_sha:
            continue
        if sha:
            seen_sha.add(sha)
        if d.get("source") == "PMC-OA":
            if pmc_cap and pmc >= pmc_cap:
                continue
            pmc += 1
        rows.append(d)
    return rows


def index_text(d: dict, *, mode: str) -> str:
    """Source-appropriate field weighting (repetition = weight in TF-IDF)."""
    sp = d.get("section_path") or d.get("title") or ""
    content = d.get("content") or ""
    anchor = d.get("syndrome_anchor") or ""
    wl = d.get("wiki_links") or []
    wl_txt = " ".join(wl) if isinstance(wl, list) else ""
    if mode == "wikem":
        return f"{sp} {sp} {sp} {anchor} {anchor} {wl_txt} {wl_txt} {wl_txt} {content}"
    if mode == "merck":
        return f"{sp} {sp} {content}"
    if mode == "nice":
        return f"{sp} {sp} {content}"
    if mode == "pmc":
        return f"{anchor} {anchor} {content}"
    if mode == "society":
        return content
    # unified
    return f"{sp} {content} {wl_txt}"


def build_tfidf(texts: list[str], *, max_features: int = 80000):
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(max_features=max_features, ngram_range=(1, 2),
                          stop_words="english", sublinear_tf=True,
                          min_df=2, max_df=0.95)
    mat = vec.fit_transform(texts)
    return vec, mat


def search(vec, mat, rows, query: str, k: int) -> list[tuple[int, float]]:
    qv = vec.transform([query])
    scores = (mat @ qv.T).toarray().ravel()
    order = scores.argsort()[::-1][:k]
    return [(int(i), float(scores[i])) for i in order if scores[i] > 0]


def build_queries(rows: list[dict]):
    """Gold = entry chunks per clean syndrome. Returns wikem & merck query sets."""
    wikem_pages: dict[str, dict] = {}   # norm-anchor -> {S, gold_idx, entities}
    merck_ch: dict[str, dict] = {}
    for i, d in enumerate(rows):
        src = d.get("source")
        if src == "WikEM" and d.get("syndrome_anchor"):
            key = norm(d["syndrome_anchor"])
            if not key:
                continue
            p = wikem_pages.setdefault(key, {"S": key, "gold_idx": set(), "entities": set()})
            p["gold_idx"].add(i)
            for e in (d.get("wiki_links") or []):
                ne = norm(e)
                if ne and ne != key and len(ne) > 2:
                    p["entities"].add(ne)
        elif src == "Merck-Manual-19e" and d.get("entry_type") == "syndrome_entry":
            sp = d.get("section_path") or ""
            m = re.search(r"approach to (?:the patient with )?(.+?)(?: >|$)", sp, re.I)
            if not m:
                continue
            key = norm(m.group(1))
            if not key:
                continue
            c = merck_ch.setdefault(key, {"S": key, "gold_idx": set()})
            c["gold_idx"].add(i)
    wikem_q = [p for p in wikem_pages.values() if p["entities"]]  # need gold entities
    merck_q = [c for c in merck_ch.values() if len(c["gold_idx"]) >= 1]
    return wikem_q, merck_q


def rrf_fuse(ranklists: list[list[int]], k_const: int = 60) -> list[int]:
    score: dict[int, float] = defaultdict(float)
    for rl in ranklists:
        for rank, idx in enumerate(rl, start=1):
            score[idx] += 1.0 / (k_const + rank)
    return [i for i, _ in sorted(score.items(), key=lambda kv: -kv[1])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--pmc-cap", type=int, default=0, help="cap PMC chunks (0=all); domination is the point")
    ap.add_argument("--limit-q", type=int, default=0)
    args = ap.parse_args()
    K = args.k

    print(f"Loading useful chunks (pmc_cap={args.pmc_cap}) ...", flush=True)
    rows = load_chunks(args.pmc_cap)
    by_src = Counter(d.get("source") for d in rows)
    print(f"  rows={len(rows)}  sources={dict(by_src.most_common(8))}", flush=True)

    # group row indices by source bucket
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, d in enumerate(rows):
        s = d.get("source")
        if s == "WikEM":
            buckets["wikem"].append(i)
        elif s == "Merck-Manual-19e":
            buckets["merck"].append(i)
        elif s == "NICE":
            buckets["nice"].append(i)
        elif s == "PMC-OA":
            buckets["pmc"].append(i)
        elif s in SOCIETY:
            buckets["society"].append(i)
        else:
            buckets["society"].append(i)
    print("  buckets:", {k: len(v) for k, v in buckets.items()}, flush=True)

    wikem_q, merck_q = build_queries(rows)
    if args.limit_q:
        wikem_q = wikem_q[:args.limit_q]
        merck_q = merck_q[:args.limit_q]
    print(f"  queries: wikem={len(wikem_q)} merck={len(merck_q)}", flush=True)

    # ---- Arm A: unified index ------------------------------------------------
    print("Building UNIFIED index ...", flush=True)
    t0 = time.time()
    uni_texts = [index_text(d, mode="unified") for d in rows]
    uvec, umat = build_tfidf(uni_texts)
    print(f"  unified shape={umat.shape} in {time.time()-t0:.1f}s", flush=True)

    # ---- Arm B: per-source indices ------------------------------------------
    print("Building PER-SOURCE indices ...", flush=True)
    sub = {}  # bucket -> (vec, mat, [global_idx])
    for b, idxs in buckets.items():
        if not idxs:
            continue
        t0 = time.time()
        texts = [index_text(rows[i], mode=b) for i in idxs]
        try:
            v, m = build_tfidf(texts, max_features=60000)
        except ValueError:
            continue
        sub[b] = (v, m, idxs)
        print(f"  [{b}] {m.shape} in {time.time()-t0:.1f}s", flush=True)

    def diff_search(S: str, k: int) -> list[int]:
        """Differentiated retrieval: per-source query form → top-k each → RRF + boost."""
        qforms = {
            "wikem": S,
            "merck": f"approach to {S}",
            "nice": f"{S} assessment diagnosis recommendations",
            "society": f"{S} diagnosis evaluation",
            "pmc": f"differential diagnosis of {S} causes evaluation",
        }
        ranklists = []
        cand: set[int] = set()
        for b, (v, m, idxs) in sub.items():
            q = qforms.get(b, S)
            hits = search(v, m, None, q, k)
            rl = [idxs[i] for i, _ in hits]
            ranklists.append(rl)
            cand.update(rl)
        fused = rrf_fuse(ranklists)
        # syndrome_entry / anchor-token boost (re-rank within fused head)
        S_toks = toks(S)
        def boost(idx: int) -> float:
            d = rows[idx]
            b = 0.0
            if d.get("entry_type") == "syndrome_entry":
                b += 0.5
            anchor = norm(d.get("syndrome_anchor") or "")
            if anchor and S_toks & toks(anchor):
                b += 1.0
            sp = d.get("section_path") or ""
            if S_toks and S_toks <= toks(sp):
                b += 0.5
            return b
        base = {idx: 1.0 / (60 + r) for r, idx in enumerate(fused, 1)}
        reranked = sorted(base, key=lambda i: -(base[i] + 0.002 * boost(i)))
        return reranked[:k]

    def uni_search(S: str, k: int) -> list[int]:
        q = f"approach to {S} differential diagnosis evaluation causes"
        return [i for i, _ in search(uvec, umat, None, q, k)]

    # ---- evaluate ------------------------------------------------------------
    def eval_set(qset, name):
        res = {"n": len(qset)}
        for arm, fn in (("unified", uni_search), ("differentiated", diff_search)):
            hits = 0
            ranks = []
            cover = []
            pmc_flood = []
            for q in qset:
                topk = fn(q["S"], K)
                gold = q["gold_idx"]
                first = None
                for r, idx in enumerate(topk, 1):
                    if idx in gold:
                        first = r
                        break
                if first:
                    hits += 1
                    ranks.append(first)
                # DDx entity coverage (wikem only)
                if q.get("entities"):
                    blob = " ".join((rows[i].get("content") or "") + " " +
                                    " ".join(rows[i].get("wiki_links") or [])
                                    for i in topk).lower()
                    covered = sum(1 for e in q["entities"] if e in blob)
                    cover.append(covered / max(1, len(q["entities"])))
                # source composition diagnostic
                comp = Counter(rows[i].get("source") for i in topk)
                pmc_flood.append(comp.get("PMC-OA", 0) / max(1, len(topk)))
            ranks_sorted = sorted(ranks)
            res[arm] = {
                "recall_at_k": round(hits / len(qset), 4),
                "hits": hits,
                "median_first_gold_rank": ranks_sorted[len(ranks_sorted)//2] if ranks_sorted else None,
                "ddx_entity_coverage_at_k": round(sum(cover)/len(cover), 4) if cover else None,
                "mean_pmc_share_of_topk": round(sum(pmc_flood)/len(pmc_flood), 4) if pmc_flood else None,
            }
        return res

    report = {
        "k": K, "pmc_cap": args.pmc_cap,
        "corpus_rows": len(rows),
        "source_distribution": dict(by_src.most_common()),
        "bucket_sizes": {k: len(v) for k, v in buckets.items()},
        "wikem_entry_recall": eval_set(wikem_q, "wikem"),
        "merck_entry_recall": eval_set(merck_q, "merck"),
    }

    # ---- defect diagnostics --------------------------------------------------
    # (1) Candidate flooding: document-frequency FRACTION of syndrome terms in
    #     PMC vs WikEM (comparable across corpora), plus the ABSOLUTE number of
    #     PMC chunks containing the term = competing candidates that bury entries.
    def df_map(texts):
        df = Counter()
        for t in texts:
            for w in set(re.findall(r"[a-z]{3,}", t.lower())):
                df[w] += 1
        return df, len(texts)
    wikem_texts = [rows[i].get("content") or "" for i in buckets["wikem"]]
    pmc_texts = [rows[i].get("content") or "" for i in buckets.get("pmc", [])]
    pmc_df, pmcN = df_map(pmc_texts)
    wk_df, wkN = df_map(wikem_texts)
    sample_terms = []
    for q in wikem_q[:60]:
        for w in q["S"].split():
            if len(w) > 3:
                sample_terms.append(w)
    sample_terms = list(dict.fromkeys(sample_terms))[:25]
    flood = []
    for w in sample_terms:
        flood.append({
            "term": w,
            "wikem_df_frac": round(wk_df.get(w, 0) / max(1, wkN), 4),
            "pmc_df_frac": round(pmc_df.get(w, 0) / max(1, pmcN), 4),
            "pmc_competing_chunks": pmc_df.get(w, 0),
        })
    report["defect_candidate_flooding"] = {
        "note": "even small pmc_df_frac => thousands of PMC prose chunks contain the syndrome term and compete with the single terse entry chunk",
        "pmc_N": pmcN, "wikem_N": wkN,
        "terms": flood,
    }

    # (2) Burial depth: for unified FAILS (gold not in top-k), how deep is the
    #     entry chunk really, and how many PMC chunks sit above it?
    burial = []
    DEEP = 200
    for q in wikem_q:
        topk = uni_search(q["S"], K)
        if any(i in q["gold_idx"] for i in topk):
            continue
        deep = [i for i, _ in search(uvec, umat, None,
                f"approach to {q['S']} differential diagnosis evaluation causes", DEEP)]
        best = None
        for r, idx in enumerate(deep, 1):
            if idx in q["gold_idx"]:
                best = r
                break
        pmc_above = sum(1 for idx in deep[: (best or DEEP)] if rows[idx].get("source") == "PMC-OA")
        burial.append({"S": q["S"], "best_gold_rank_in_unified": best,
                       "pmc_chunks_above": pmc_above})
    burial_ranks = [b["best_gold_rank_in_unified"] for b in burial if b["best_gold_rank_in_unified"]]
    report["defect_entry_burial"] = {
        "note": "unified fails: entry chunk exists but is ranked far below PMC prose",
        "n_unified_fails": len(burial),
        "median_true_rank_of_entry": (sorted(burial_ranks)[len(burial_ranks)//2] if burial_ranks else None),
        "not_in_top200": sum(1 for b in burial if b["best_gold_rank_in_unified"] is None),
        "examples": burial[:15],
    }
    report["defect_length_skew_median_content_len"] = {
        s: sorted(len(rows[i].get("content") or "") for i in
                  [j for j, d in enumerate(rows) if d.get("source") == s])[
            max(0, sum(1 for d in rows if d.get("source") == s)//2 - 1)]
        for s in ["WikEM", "NICE", "Merck-Manual-19e", "PMC-OA", "ESC", "IDSA"]
        if any(d.get("source") == s for d in rows)
    }
    report["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n==== SUMMARY ====")
    print(json.dumps({k: report[k] for k in
                      ("wikem_entry_recall", "merck_entry_recall")}, ensure_ascii=False, indent=2))
    print(f"\nReport: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
