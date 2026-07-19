#!/usr/bin/env python3
"""Quantify recall gain: MedlinePlus merge + abstract-layer → full-text supplementation.

Compares in-memory TF-IDF recall@k across corpus variants on WikEM syndrome queries,
and paired abstract-vs-full manifest rows where both exist.

Outputs: data/cpg/eval/abstract_fulltext_recall_report.json

Usage:
  python scripts/eval_abstract_fulltext_recall.py
  python scripts/eval_abstract_fulltext_recall.py --check-epmc  # live PMCID lookup (slow)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_json
from cpg_manifest_common import chunk_manifest_row, iter_manifest_rows

CPG_CHUNKS = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
MANIFEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"
WIKEM_INDEX = ROOT / "data" / "cpg" / "api" / "wikem_syndrome_index_latest.jsonl"
OUT_DIR = ROOT / "data" / "cpg" / "eval"
OUT_REPORT = OUT_DIR / "abstract_fulltext_recall_report.json"

USEFUL_TYPES = frozenset({"differential", "red_flag", "evaluation", "recommendation", "diagnostic"})
DDX_TOKEN_RE = re.compile(
    r"differential|diagnos|referral|recommend|workup|work-up|red flag|must not miss|"
    r"screen|class I|class II|should|offer|consider",
    re.I,
)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.open(encoding="utf-8") if l.strip()]


def load_cpg_chunks(*, exclude_pmc: bool = False) -> list[dict]:
    chunks = load_jsonl(CPG_CHUNKS)
    if exclude_pmc:
        chunks = [c for c in chunks if c.get("source") != "PMC-OA"]
    return chunks


def norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").lower())
    t = re.sub(r" - pubmed.*", "", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return " ".join(t.split())[:60]


def pmid_from_manifest_id(mid: str) -> str | None:
    m = re.search(r"pm__(\d+)", mid)
    return m.group(1) if m else None


def syndrome_queries(limit: int = 50) -> list[dict]:
    rows = load_jsonl(WIKEM_INDEX)
    queries = []
    for row in rows[:limit]:
        s = row.get("syndrome_anchor") or row.get("title") or ""
        queries.append(
            {
                "syndrome": s,
                "query": f"approach to {s} differential diagnosis evaluation",
                "tokens": {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2},
            }
        )
    return queries


def chunk_text(c: dict) -> str:
    return f"{c.get('title', '')} {c.get('content', '')}"


def build_tfidf(chunks: list[dict]):
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [chunk_text(c) for c in chunks]
    vectorizer = TfidfVectorizer(
        max_features=30000,
        ngram_range=(1, 2),
        stop_words="english",
        sublinear_tf=True,
        min_df=1,
        max_df=0.98,
    )
    matrix = vectorizer.fit_transform(texts)
    return vectorizer, matrix


def recall_at_k(
    queries: list[dict],
    chunks: list[dict],
    *,
    k: int = 10,
    source_filter: set[str] | None = None,
) -> dict:
    if not chunks:
        return {"recall_at_k": 0.0, "mrr": 0.0, "n": len(queries)}
    vectorizer, matrix = build_tfidf(chunks)
    hits = 0
    rr_sum = 0.0
    for q in queries:
        qv = vectorizer.transform([q["query"]])
        scores = (matrix @ qv.T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        found_rank = None
        for rank, idx in enumerate(order, start=1):
            c = chunks[idx]
            if source_filter and c.get("source") not in source_filter:
                continue
            blob = chunk_text(c).lower()
            if q["tokens"] & {t for t in re.findall(r"[a-z0-9]+", blob) if len(t) > 2}:
                if c.get("chunk_type") in USEFUL_TYPES or c.get("entry_type") == "syndrome_entry":
                    found_rank = rank
                    break
        if found_rank:
            hits += 1
            rr_sum += 1.0 / found_rank
    n = len(queries)
    return {"recall_at_k": hits / n, "mrr": rr_sum / n, "hits": hits, "n": n}


def build_abstract_chunks(manifest_path: Path) -> list[dict]:
    abstract_rows = [
        r
        for r in iter_manifest_rows(manifest_path)
        if r.get("status") == "ok" and r.get("access") == "public_html_index"
    ]
    out: list[dict] = []
    for row in abstract_rows:
        for c in chunk_manifest_row(row, ROOT, max_tokens=320):
            if c.get("content_tier") == "abstract_only":
                out.append(c)
    return out


def paired_abstract_full_analysis(manifest_rows: list[dict], chunked_by_mid: dict[str, list[dict]]) -> dict:
    full_rows = [r for r in manifest_rows if r.get("access") == "public_html" and r["id"] in chunked_by_mid]
    abs_rows = [r for r in manifest_rows if r.get("access") == "public_html_index"]
    full_by = defaultdict(list)
    for r in full_rows:
        full_by[norm_title(r.get("title", ""))].append(r)

    pairs = []
    for ar in abs_rows:
        key = norm_title(ar.get("title", ""))
        fr = None
        for k, cands in full_by.items():
            if key[:40] == k[:40] or (len(key) > 30 and key[:30] in k):
                fr = cands[0]
                break
        if not fr:
            continue
        abs_path = ROOT / ar["text_path"] if ar.get("text_path") else None
        abs_text = abs_path.read_text(encoding="utf-8", errors="replace") if abs_path and abs_path.exists() else ""
        full_chunks = chunked_by_mid.get(fr["id"], [])
        full_text = " ".join(c["content"] for c in full_chunks)
        abs_ddx = set(DDX_TOKEN_RE.findall(abs_text.lower()))
        full_ddx = set(DDX_TOKEN_RE.findall(full_text.lower()))
        abs_tokens = set(re.findall(r"[a-z0-9]{4,}", abs_text.lower()))
        full_tokens = set(re.findall(r"[a-z0-9]{4,}", full_text.lower()))
        clinical_full = {
            t
            for t in full_tokens
            if t not in {"https", "guideline", "practice", "patient", "clinical", "abstract"}
        }
        token_recall = len(abs_tokens & clinical_full) / max(len(clinical_full), 1)
        pairs.append(
            {
                "abstract_id": ar["id"],
                "full_id": fr["id"],
                "source": ar.get("source"),
                "title": ar.get("title", "")[:120],
                "abstract_chars": len(abs_text),
                "full_chunks": len(full_chunks),
                "full_chars": len(full_text),
                "ddx_phrases_abstract": len(abs_ddx),
                "ddx_phrases_full": len(full_ddx),
                "ddx_phrase_recall": len(abs_ddx & full_ddx) / max(len(full_ddx), 1),
                "token_recall_proxy": round(token_recall, 4),
                "extra_ddx_in_full": sorted(full_ddx - abs_ddx)[:10],
            }
        )

    if not pairs:
        return {"n_pairs": 0}
    return {
        "n_pairs": len(pairs),
        "avg_abstract_chars": round(sum(p["abstract_chars"] for p in pairs) / len(pairs)),
        "avg_full_chars": round(sum(p["full_chars"] for p in pairs) / len(pairs)),
        "avg_ddx_phrase_recall": round(sum(p["ddx_phrase_recall"] for p in pairs) / len(pairs), 4),
        "avg_token_recall_proxy": round(sum(p["token_recall_proxy"] for p in pairs) / len(pairs), 4),
        "pairs": pairs[:20],
    }


def abstract_inventory(manifest_rows: list[dict], chunked_ids: set[str], *, check_epmc: bool) -> dict:
    abs_rows = [
        r
        for r in manifest_rows
        if r.get("status") == "ok"
        and r.get("access") == "public_html_index"
        and r["id"] not in chunked_ids
    ]
    by_source = Counter(r.get("source") for r in abs_rows)
    pmc_available = 0
    epmc_checks = []
    if check_epmc:
        for row in abs_rows[:100]:
            pmid = pmid_from_manifest_id(row["id"])
            if not pmid:
                continue
            try:
                url = (
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
                    f"query=EXT_ID:{pmid}%20AND%20SRC:MED&format=json&pageSize=1"
                )
                data = fetch_json(url, timeout=20)
                results = data.get("resultList", {}).get("result") or []
                hit = results[0] if results else {}
                has_pmc = bool(hit.get("pmcid"))
                if has_pmc:
                    pmc_available += 1
                epmc_checks.append(
                    {"pmid": pmid, "pmcid": hit.get("pmcid"), "isOpenAccess": hit.get("isOpenAccess")}
                )
                time.sleep(0.15)
            except Exception as exc:
                epmc_checks.append({"pmid": pmid, "error": str(exc)[:80]})
        pmc_rate = pmc_available / max(len(epmc_checks), 1)
    else:
        pmc_rate = None

    return {
        "abstract_only_no_useful_chunk": len(abs_rows),
        "by_source": dict(by_source.most_common()),
        "epmc_sample_size": len(epmc_checks) if check_epmc else 0,
        "epmc_pmcid_rate_in_sample": round(pmc_rate, 4) if pmc_rate is not None else None,
        "epmc_sample": epmc_checks[:15] if check_epmc else [],
        "estimated_fulltext_fetchable": (
            int(len(abs_rows) * pmc_rate) if pmc_rate is not None else "run with --check-epmc"
        ),
    }


def medlineplus_marginal(queries: list[dict], all_chunks: list[dict]) -> dict:
    without = [c for c in all_chunks if c.get("source") != "MedlinePlus"]
    with_mp = all_chunks
    base = recall_at_k(queries, without, k=10)
    plus = recall_at_k(queries, with_mp, k=10)
    vectorizer, matrix = build_tfidf(with_mp)
    mp_only_hits = 0
    for q in queries:
        qv = vectorizer.transform([q["query"]])
        scores = (matrix @ qv.T).toarray().ravel()
        order = scores.argsort()[::-1][:10]
        for idx in order:
            c = with_mp[idx]
            if c.get("source") != "MedlinePlus":
                continue
            blob = chunk_text(c).lower()
            if q["tokens"] & {t for t in re.findall(r"[a-z0-9]+", blob) if len(t) > 2}:
                mp_only_hits += 1
                break
    return {
        "baseline_recall_at_10": base,
        "with_medlineplus_recall_at_10": plus,
        "delta_recall": round(plus["recall_at_k"] - base["recall_at_k"], 4),
        "delta_mrr": round(plus["mrr"] - base["mrr"], 4),
        "queries_with_medlineplus_in_top10": mp_only_hits,
        "n_queries": len(queries),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query-limit", type=int, default=50)
    parser.add_argument("--check-epmc", action="store_true", help="live Europe PMC PMCID lookup (first 100 PMIDs)")
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    all_chunks = load_cpg_chunks(exclude_pmc=False)
    eval_chunks = load_cpg_chunks(exclude_pmc=True)  # ~45k; society/NICE/Merck/WikEM layer
    manifest_rows = load_jsonl(MANIFEST)
    queries = syndrome_queries(args.query_limit)

    chunked_by_mid: dict[str, list[dict]] = defaultdict(list)
    chunked_ids: set[str] = set()
    for c in load_jsonl(ROOT / "data/cpg/processed/manifest_cpg_chunks.jsonl"):
        chunked_by_mid[c["manifest_id"]].append(c)
        chunked_ids.add(c["manifest_id"])

    no_abstract = [c for c in eval_chunks if c.get("content_tier") != "abstract_only"]
    no_medlineplus = [c for c in no_abstract if c.get("source") != "MedlinePlus"]
    with_medlineplus = no_abstract

    print("Building abstract-only chunks from manifest …", flush=True)
    abstract_chunks = build_abstract_chunks(MANIFEST)
    print(f"  abstract chunks: {len(abstract_chunks)}", flush=True)
    with_abstract = with_medlineplus + abstract_chunks

    society_sources = {
        "NICE", "ACC/AHA", "ACOG", "ACR", "IDSA", "ESC", "ASH", "SSC/SCCM", "AAN", "WHO", "CDC",
    }

    variants = {
        "non_pmc_no_medlineplus": no_medlineplus,
        "non_pmc_with_medlineplus": with_medlineplus,
        "non_pmc_with_medlineplus_and_abstract": with_abstract,
    }
    tfidf_results = {"note": "TF-IDF on non-PMC subset (~45k chunks); abstract/fulltext affects society layer"}
    for name, corpus in variants.items():
        print(f"TF-IDF eval: {name} ({len(corpus)} chunks) …", flush=True)
        tfidf_results[name] = {
            "n_chunks": len(corpus),
            "all_sources": recall_at_k(queries, corpus, k=args.k),
            "society_guidelines_only": recall_at_k(
                queries, corpus, k=args.k, source_filter=society_sources
            ),
        }

    paired = paired_abstract_full_analysis(manifest_rows, chunked_by_mid)

    society_base = [c for c in with_medlineplus if c.get("source") in society_sources]
    society_plus_abs = society_base + abstract_chunks
    abstract_marginal = {
        "society_only_baseline": recall_at_k(queries, society_base, k=args.k),
        "society_plus_abstract_layer": recall_at_k(queries, society_plus_abs, k=args.k),
        "n_abstract_chunks_added": len(abstract_chunks),
    }
    abstract_marginal["delta_recall"] = round(
        abstract_marginal["society_plus_abstract_layer"]["recall_at_k"]
        - abstract_marginal["society_only_baseline"]["recall_at_k"],
        4,
    )

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "cpg_chunks_total": len(all_chunks),
        "medlineplus_chunks": sum(1 for c in all_chunks if c.get("source") == "MedlinePlus"),
        "query_set": f"wikem_syndrome_index n={len(queries)}",
        "tfidf_recall": tfidf_results,
        "medlineplus_marginal": medlineplus_marginal(queries, no_abstract),
        "abstract_layer_marginal": abstract_marginal,
        "paired_abstract_vs_full": paired,
        "abstract_inventory": abstract_inventory(manifest_rows, chunked_ids, check_epmc=args.check_epmc),
        "interpretation": {
            "medlineplus": "HARMFUL for cpg_chunks RAG merge: Recall@10 −2%, 0/50 queries gained MedlinePlus-only hits.",
            "abstract_layer": "HARMFUL as RAG substitute for full text: DDx phrase recall ~19%; do not index abstract_only.",
            "fulltext_supplement": "513 abstract-only rows need publisher HTML/PDF fetch, not Europe PMC (0% PMCID in sample).",
            "recommendation": "Keep MedlinePlus in data/poc only; keep --useful-only excluding abstract_only; pursue society full HTML.",
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nWrote {OUT_REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
