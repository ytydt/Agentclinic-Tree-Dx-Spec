#!/usr/bin/env python3
"""E11: B07 retrieval condition x generic-refine factorial.

The experiment reuses the historical B07 orchestrator decisions and queries so
that query sampling cannot masquerade as a retrieval effect.  Four diagnosis
conditions receive an identical prompt and clean vignette; only the served
knowledge bundle changes (off, relevant, random, or lexical hard-negative).
Each frozen draft is then either returned directly or passed through one
identical generic-refine call.

Gold labels and answer options are never included in an online payload.  The
historical retrieval gate is retained only as a pre-treatment moderator; the
factorial treatments themselves are forced for every case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import tarfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import (  # noqa: E402
    DEVELOPMENT_SLICES,
    ROOT,
    FrozenExactSynonymBridge,
    clean_vignette,
    combined_file_sha256,
    file_sha256,
    load_normalized_cases,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    RunManifest,
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


EXPERIMENT_ID = "E11"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_OUT = ROOT / "analysis/mechanism_v2/results/E11_b07_factorial"
E4_PREREG = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/preregistration.json"
BRIDGE_PATH = ROOT / "data/knowledge_raw/disease_name_bridge.json"
MERCK_PATH = ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl"
PRODUCTION_RAG_INDEX = ROOT / "data/corpus/rag_index"

RETRIEVALS = ("off", "relevant", "random", "hard_negative")
REFINES = ("off", "on")
ARMS = tuple(f"{retrieval}_refine_{refine}" for retrieval in RETRIEVALS for refine in REFINES)
MAX_CHUNKS = 6
MAX_CHUNK_CHARS = 1400

HISTORICAL_RUNS: dict[str, Path] = {
    "DA_d2_seq100": ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01/trace.jsonl",
    "DA_d2_heldout100": ROOT / "runs/paper_v1/diagnosisarena_heldout_v1/B07-meddxagent-complete/replicate_01/trace.jsonl",
    "DA_d2_heldout200b": ROOT / "runs/paper_v1/diagnosisarena_heldout200b_v1/B07-meddxagent-complete/replicate_01/trace.jsonl",
    "MCR_v1_seq100": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/B07-meddxagent-complete/replicate_01/trace.jsonl",
    "MCR_v2_seq100": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v2/B07-meddxagent-complete/replicate_01/trace.jsonl",
    "MCR_seq200b": ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq200b_v1/B07-meddxagent-complete/replicate_01/trace.jsonl",
}

DIAGNOSE_PROMPT = """You are MEDDxAgent diagnosis-strategy agent (complete-profile static mode).
Use the full vignette and the supplied knowledge excerpts, if any. Treat excerpts
as fallible reference material: diagnosis must remain grounded in the vignette.
Produce exactly two distinct, concrete diagnoses in best-first order. Do not use
answer-option letters. Return JSON only:
{"top2_diagnoses":[
 {"diagnosis":"disease 1","explanation":"brief case-grounded contrast"},
 {"diagnosis":"disease 2","explanation":"brief case-grounded contrast"}
]}
"""

REFINE_PROMPT = """You are MEDDxAgent iterative refine (complete-profile, one extra turn).
Given the full vignette, the same fallible knowledge excerpts, and the frozen
draft Top-2, revise only if case evidence warrants. You may reorder, replace, or
retain diagnoses; do not change merely to appear active. Return exactly two
distinct concrete diagnoses in best-first order and no answer-option letters.
Return JSON only:
{"top2_diagnoses":["disease 1","disease 2"],
 "change_rationale":"brief evidence-grounded reason, or retained"}
"""

ENDPOINT_CONTRACT = (
    "frozen-exact-synonym pre-mapper Top-1/Top-2; paired retrieval and refine "
    "transitions; draft-to-final candidate addition/deletion/reordering; "
    "historical-gate moderation; chunk support and confirmation-bias audit"
)


def selected_case_keys() -> list[str]:
    document = json.loads(E4_PREREG.read_text(encoding="utf-8"))
    keys = [str(value) for value in document["selection"]["case_keys"]]
    if len(keys) != 400 or len(set(keys)) != 400:
        raise AssertionError("E11 requires E4's frozen 400-case development sample")
    return sorted(keys)


def _source_id_from_historical(case_id: str) -> str:
    suffix = str(case_id).rsplit("__", 1)[-1]
    if suffix.isdigit():
        return str(int(suffix))
    return suffix


def _fallback_queries(vignette: str) -> list[str]:
    text = " ".join(str(vignette or "").split())
    if not text:
        return ["differential diagnosis clinical findings"]
    return [
        text[:260],
        f"differential diagnosis {text[:210]}",
        f"diagnostic criteria {text[210:410] or text[:180]}",
    ]


def _clean_queries(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        query = " ".join(str(value or "").split()).strip()[:300]
        key = query.casefold()
        if query and key not in seen:
            output.append(query)
            seen.add(key)
        if len(output) == 4:
            break
    return output


def load_jobs() -> tuple[list[dict[str, Any]], list[Path]]:
    selected = set(selected_case_keys())
    inputs: list[Path] = [E4_PREREG, BRIDGE_PATH, MERCK_PATH]
    jobs: list[dict[str, Any]] = []
    for spec in DEVELOPMENT_SLICES:
        trace_path = HISTORICAL_RUNS[spec.slice_id]
        if not trace_path.is_file():
            raise FileNotFoundError(f"historical B07 trace missing: {trace_path}")
        inputs.extend([spec.cases_json, trace_path])
        historical = {
            _source_id_from_historical(str(row["case_id"])): row
            for row in read_jsonl(trace_path)
        }
        cases = load_normalized_cases(spec.cases_json)
        for source_id, case in cases.items():
            case_key = f"{spec.slice_id}/{source_id}"
            if case_key not in selected:
                continue
            trace_row = historical.get(str(source_id))
            if trace_row is None:
                raise KeyError(f"historical B07 trace absent for {case_key}")
            trace = dict(trace_row.get("trace") or {})
            orchestrator = dict(trace.get("orchestrator") or {})
            queries = _clean_queries(orchestrator.get("retrieval_queries"))
            query_source = "historical_orchestrator"
            if not queries:
                queries = _clean_queries(trace.get("queries"))
                query_source = "historical_runtime_fallback"
            if not queries:
                queries = _fallback_queries(str(case.get("case_text") or ""))
                query_source = "frozen_local_fallback"
            jobs.append(
                {
                    "case_key": case_key,
                    "slice_id": spec.slice_id,
                    "family": spec.family,
                    "case_id": str(source_id),
                    "vignette": clean_vignette(str(case["case_text"])),
                    "gold": str(case["gold"]),
                    "historical_trace_case_id": str(trace_row["case_id"]),
                    "historical_need_retrieval": bool(orchestrator.get("need_retrieval", True)),
                    "historical_queries": queries,
                    "query_source": query_source,
                    "historical_strategy_notes": str(orchestrator.get("strategy_notes") or "")[:3000],
                    "historical_draft": [str(value) for value in (trace.get("draft") or [])][:2],
                    "historical_final": _extract_top2(dict(trace.get("refine") or {})),
                }
            )
    jobs.sort(key=lambda row: row["case_key"])
    found = {row["case_key"] for row in jobs}
    if found != selected:
        raise AssertionError(
            f"E11 join mismatch missing={sorted(selected-found)[:5]} extra={sorted(found-selected)[:5]}"
        )
    return jobs, inputs


def _load_merck_chunks(path: Path = MERCK_PATH) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            content = " ".join(str(row.get("content") or "").split())
            if not content:
                continue
            chunks.append(
                {
                    "id": str(row.get("id") or f"merck_{len(chunks)}"),
                    "title": " ".join(str(row.get("title") or row.get("section_path") or "").split())[:500],
                    "content": content,
                    "article_id": str(row.get("article_id") or row.get("source_id") or ""),
                    "source": str(row.get("source") or "Merck-Manual-19e"),
                }
            )
    if not chunks:
        raise ValueError(f"no usable Merck chunks in {path}")
    return chunks


def _is_lfs_pointer(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as stream:
        return stream.read(80).startswith(b"version https://git-lfs.github.com/spec/v1")


class MerckLexicalIndex:
    """Environment-adaptive TF-IDF index with a pure-Python BM25 fallback."""

    def __init__(self, chunks: Sequence[Mapping[str, Any]]) -> None:
        self.chunks = [dict(row) for row in chunks]
        self.backend = "merck_bm25"
        self._matrix = None
        self._vectorizer = None
        self._postings: dict[str, list[tuple[int, int]]] = {}
        self._doc_lengths: list[int] = []
        self._avgdl = 0.0
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer

            corpus = [f"{row['title']} {row['content']}" for row in self.chunks]
            vectorizer = TfidfVectorizer(
                lowercase=True,
                stop_words="english",
                ngram_range=(1, 2),
                min_df=1 if len(corpus) < 100 else 2,
                max_features=80000,
                sublinear_tf=True,
                dtype=np.float32,
            )
            self._matrix = vectorizer.fit_transform(corpus)
            self._vectorizer = vectorizer
            self.backend = "merck_tfidf"
        except (ImportError, ValueError):
            self._build_bm25()

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9][a-z0-9-]+", str(text).lower())

    def _build_bm25(self) -> None:
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        lengths: list[int] = []
        for index, row in enumerate(self.chunks):
            counts = Counter(self._tokens(f"{row['title']} {row['content']}"))
            lengths.append(sum(counts.values()))
            for token, count in counts.items():
                postings[token].append((index, count))
        self._postings = dict(postings)
        self._doc_lengths = lengths
        self._avgdl = sum(lengths) / len(lengths)

    def search_scores(self, queries: Sequence[str]) -> list[tuple[int, float]]:
        queries = [str(value) for value in queries if str(value).strip()]
        if self._vectorizer is not None and self._matrix is not None:
            import numpy as np

            q_matrix = self._vectorizer.transform(queries or ["differential diagnosis"])
            product = self._matrix @ q_matrix.T
            scores = np.asarray(product.max(axis=1).toarray()).ravel()
            order = np.argsort(scores)[::-1]
            return [(int(index), float(scores[index])) for index in order if scores[index] > 0]
        query_counts = Counter(self._tokens(" ".join(queries)))
        n_docs = len(self.chunks)
        scores: dict[int, float] = defaultdict(float)
        k1, b = 1.5, 0.75
        for token, qtf in query_counts.items():
            postings = self._postings.get(token) or []
            if not postings:
                continue
            idf = math.log(1.0 + (n_docs - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, tf in postings:
                dl = self._doc_lengths[index]
                denom = tf + k1 * (1.0 - b + b * dl / max(self._avgdl, 1.0))
                scores[index] += qtf * idf * (tf * (k1 + 1.0) / denom)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class ProductionRAGIndex:
    """Adapter for the repository RAGRetriever when its original assets exist."""

    def __init__(self, index_dir: Path) -> None:
        meta = index_dir / "metadata.jsonl"
        if not meta.is_file() or _is_lfs_pointer(meta):
            raise FileNotFoundError("production RAG metadata is not materialized")
        from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever

        self._retriever = RAGRetriever(index_dir, device="cpu")
        if not self._retriever.is_ready:
            raise RuntimeError("production RAG backend could not be loaded")
        self.chunks = [
            {
                "id": str(row.get("id") or f"rag_{index}"),
                "title": str(row.get("title") or row.get("section_path") or ""),
                "content": " ".join(str(row.get("content") or "").split()),
                "article_id": str(row.get("article_id") or row.get("source_id") or ""),
                "source": str(row.get("source") or "repository-rag-index"),
            }
            for index, row in enumerate(self._retriever._metadata)  # noqa: SLF001 - frozen audit adapter
        ]
        self.backend = f"production_{self._retriever._backend}"  # noqa: SLF001

    def search_scores(self, queries: Sequence[str]) -> list[tuple[int, float]]:
        by_id = {str(row["id"]): index for index, row in enumerate(self.chunks)}
        scores: dict[int, float] = {}
        for query in queries:
            for hit in self._retriever.search(str(query), top_k=250, score_threshold=-1.0):
                index = by_id.get(str(hit.get("id")))
                if index is not None:
                    scores[index] = max(scores.get(index, float("-inf")), float(hit.get("score") or 0.0))
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def build_retriever(mode: str = "auto") -> MerckLexicalIndex | ProductionRAGIndex:
    requested = (mode or "auto").strip().lower()
    if requested not in {"auto", "production", "merck"}:
        raise ValueError("retriever must be auto, production, or merck")
    if requested in {"auto", "production"}:
        try:
            return ProductionRAGIndex(Path(os.environ.get("TREE_DX_RAG_INDEX", PRODUCTION_RAG_INDEX)))
        except (FileNotFoundError, RuntimeError, ImportError, ValueError):
            if requested == "production":
                raise
    return MerckLexicalIndex(_load_merck_chunks())


def _select_unique(
    ranked: Sequence[tuple[int, float]],
    chunks: Sequence[Mapping[str, Any]],
    *,
    exclude_ids: set[str] | None = None,
    exclude_articles: set[str] | None = None,
    start: int = 0,
    limit: int = MAX_CHUNKS,
) -> list[tuple[int, float]]:
    exclude_ids = exclude_ids or set()
    exclude_articles = exclude_articles or set()
    selected: list[tuple[int, float]] = []
    used_articles: set[str] = set()
    candidates = list(ranked[start:])
    for require_unique in (True, False):
        for index, score in candidates:
            row = chunks[index]
            chunk_id = str(row["id"])
            article = str(row.get("article_id") or "")
            if chunk_id in exclude_ids or (article and article in exclude_articles):
                continue
            if any(existing == index for existing, _ in selected):
                continue
            if require_unique and article and article in used_articles:
                continue
            selected.append((index, score))
            if article:
                used_articles.add(article)
            if len(selected) == limit:
                return selected
    return selected


def _select_length_matched(
    ranked: Sequence[tuple[int, float]],
    chunks: Sequence[Mapping[str, Any]],
    target_lengths: Sequence[int],
    *,
    exclude_ids: set[str] | None = None,
    exclude_articles: set[str] | None = None,
    start: int = 0,
) -> list[tuple[int, float]]:
    """Choose high-ranked, article-distinct chunks that meet character caps.

    Long targets are allocated first so a short early target cannot consume the
    only long, high-similarity excerpt.  The returned order is restored to the
    relevant bundle's positions, making truncation exactly character matched
    whenever the corpus contains eligible material.
    """
    exclude_ids = exclude_ids or set()
    exclude_articles = exclude_articles or set()
    candidates = list(ranked[start:])
    used_indices: set[int] = set()
    used_articles: set[str] = set()
    selected: dict[int, tuple[int, float]] = {}
    for position in sorted(range(len(target_lengths)), key=lambda value: (-target_lengths[value], value)):
        target = int(target_lengths[position])
        choice: tuple[int, float] | None = None
        for index, score in candidates:
            row = chunks[index]
            chunk_id = str(row["id"])
            article = str(row.get("article_id") or "")
            if index in used_indices or chunk_id in exclude_ids:
                continue
            if article and (article in exclude_articles or article in used_articles):
                continue
            if len(str(row.get("content") or "")) < target:
                continue
            choice = (index, score)
            break
        if choice is None:
            # Preserve article exclusion even in the fallback; choose the
            # longest available eligible chunk and record any residual mismatch.
            eligible = []
            for rank_position, (index, score) in enumerate(candidates):
                row = chunks[index]
                chunk_id = str(row["id"])
                article = str(row.get("article_id") or "")
                if index in used_indices or chunk_id in exclude_ids:
                    continue
                if article and (article in exclude_articles or article in used_articles):
                    continue
                eligible.append((len(str(row.get("content") or "")), -rank_position, index, score))
            if not eligible:
                raise AssertionError("no eligible length-matched retrieval chunk")
            _, _, index, score = max(eligible)
            choice = (index, score)
        selected[position] = choice
        used_indices.add(choice[0])
        article = str(chunks[choice[0]].get("article_id") or "")
        if article:
            used_articles.add(article)
    return [selected[position] for position in range(len(target_lengths))]


def _served_chunk(
    row: Mapping[str, Any],
    *,
    score: float | None,
    target_chars: int,
) -> dict[str, Any]:
    content = str(row.get("content") or "")[: min(MAX_CHUNK_CHARS, max(1, target_chars))]
    return {
        "chunk_id": str(row["id"]),
        "title": str(row.get("title") or "")[:500],
        "text": content,
        "article_id": str(row.get("article_id") or ""),
        "source": str(row.get("source") or ""),
        "retrieval_score": None if score is None else round(float(score), 8),
        "served_chars": len(content),
        "text_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def build_retrieval_plan(
    jobs: Sequence[Mapping[str, Any]],
    out: Path,
    *,
    retriever_mode: str = "auto",
) -> list[dict[str, Any]]:
    plan_path = out / "retrieval_plan.jsonl"
    manifest_path = out / "retrieval_manifest.json"
    if plan_path.is_file() and manifest_path.is_file():
        rows = read_jsonl(plan_path)
        if len(rows) != len(jobs):
            raise AssertionError(f"frozen retrieval plan incomplete: {len(rows)}/{len(jobs)}")
        return rows
    retriever = build_retriever(retriever_mode)
    corpus = retriever.chunks
    plan: list[dict[str, Any]] = []
    for job in jobs:
        ranked = retriever.search_scores(job["historical_queries"])
        relevant_pairs = _select_unique(ranked, corpus, limit=MAX_CHUNKS)
        if len(relevant_pairs) != MAX_CHUNKS:
            raise AssertionError(f"too few relevant chunks for {job['case_key']}")
        relevant_ids = {str(corpus[index]["id"]) for index, _ in relevant_pairs}
        relevant_articles = {
            str(corpus[index].get("article_id") or "") for index, _ in relevant_pairs
            if str(corpus[index].get("article_id") or "")
        }
        # "Hard-negative" is an operational lexical near-neighbour: skip the
        # top six and exclude every article represented in the relevant bundle.
        # Its clinical negativity is deliberately audited rather than assumed.
        target_lengths = [
            min(MAX_CHUNK_CHARS, len(str(corpus[index]["content"])))
            for index, _ in relevant_pairs
        ]
        hard_pairs = _select_length_matched(
            ranked,
            corpus,
            target_lengths,
            exclude_ids=relevant_ids,
            exclude_articles=relevant_articles,
            start=MAX_CHUNKS,
        )
        if len(hard_pairs) != MAX_CHUNKS:
            raise AssertionError(f"too few hard-negative chunks for {job['case_key']}")
        hard_ids = {str(corpus[index]["id"]) for index, _ in hard_pairs}
        hard_articles = {
            str(corpus[index].get("article_id") or "") for index, _ in hard_pairs
            if str(corpus[index].get("article_id") or "")
        }
        excluded = relevant_ids | hard_ids
        rng = random.Random(stable_seed(EXPERIMENT_ID, "random_retrieval", job["case_key"]))
        random_indices = list(range(len(corpus)))
        rng.shuffle(random_indices)
        random_pairs = _select_length_matched(
            [(index, 0.0) for index in random_indices],
            corpus,
            target_lengths,
            exclude_ids=excluded,
            exclude_articles=relevant_articles | hard_articles,
        )
        if len(random_pairs) != MAX_CHUNKS:
            raise AssertionError(f"too few random chunks for {job['case_key']}")
        bundles: dict[str, list[dict[str, Any]]] = {"off": []}
        for name, pairs in (
            ("relevant", relevant_pairs),
            ("random", random_pairs),
            ("hard_negative", hard_pairs),
        ):
            bundles[name] = [
                _served_chunk(corpus[index], score=score, target_chars=target_lengths[position])
                for position, (index, score) in enumerate(pairs)
            ]
        plan.append(
            {
                "case_key": str(job["case_key"]),
                "historical_need_retrieval": bool(job["historical_need_retrieval"]),
                "query_source": str(job["query_source"]),
                "queries": list(job["historical_queries"]),
                "retriever_backend": retriever.backend,
                "bundles": bundles,
            }
        )
    plan.sort(key=lambda row: row["case_key"])
    write_jsonl(plan_path, plan)
    atomic_json(
        manifest_path,
        {
            "schema": "e11_retrieval_plan_v1",
            "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
            "retriever_requested": retriever_mode,
            "retriever_backend": retriever.backend,
            "corpus_path": str(MERCK_PATH.relative_to(ROOT)) if retriever.backend.startswith("merck") else str(PRODUCTION_RAG_INDEX.relative_to(ROOT)),
            "corpus_sha256": file_sha256(MERCK_PATH) if retriever.backend.startswith("merck") else None,
            "corpus_chunks": len(corpus),
            "max_chunks": MAX_CHUNKS,
            "max_chunk_chars": MAX_CHUNK_CHARS,
            "relevant_definition": "top query-similar chunks with article diversity",
            "random_definition": "stable case-seeded corpus sample, disjoint from relevant/hard-negative chunks and articles",
            "hard_negative_definition": "highest remaining query-similar chunks after top-six and relevant-article exclusion; clinical negativity not presumed",
            "matching": "bundle count fixed at six; non-relevant chunks selected to meet and then truncated to each relevant excerpt's exact character count",
            "n_cases": len(plan),
            "historical_gate_true_n": sum(bool(row["historical_need_retrieval"]) for row in plan),
            "query_sources": dict(Counter(row["query_source"] for row in plan)),
            "plan_sha256": canonical_sha256(plan),
        },
    )
    return plan


def _diagnosis_values(response: Mapping[str, Any]) -> list[Any]:
    values = response.get("top2_diagnoses")
    if values is None:
        values = response.get("ordered_diagnoses")
    return list(values) if isinstance(values, list) else []


def _extract_top2(response: Mapping[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in _diagnosis_values(response):
        if isinstance(value, Mapping):
            value = value.get("diagnosis") or value.get("name") or ""
        label = " ".join(str(value or "").split()).strip()[:300]
        key = normalize_label(label)
        if label and key and key not in seen:
            output.append(label)
            seen.add(key)
        if len(output) == 2:
            break
    return output


def _top2_validator(response: Mapping[str, Any]) -> str | None:
    values = _diagnosis_values(response)
    if len(values) != 2:
        return "top2_diagnoses must contain exactly two items"
    labels = _extract_top2(response)
    if len(labels) != 2:
        return "top2 diagnoses must be non-empty and distinct"
    return None


def _online_chunks(chunks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    # Treatment labels and retrieval scores are intentionally withheld.  Every
    # non-empty condition has the same visible schema.
    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "title": str(row.get("title") or ""),
            "text": str(row.get("text") or ""),
            "source": str(row.get("source") or ""),
        }
        for row in chunks
    ]


def _orchestrator_payload(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "need_retrieval": bool(job["historical_need_retrieval"]),
        "retrieval_queries": list(job["historical_queries"]),
        "strategy_notes": str(job["historical_strategy_notes"]),
    }


def _score_top2(
    labels: Sequence[str], gold: str, bridge: FrozenExactSynonymBridge
) -> dict[str, Any]:
    keys = [bridge.canonical_key(str(label)) for label in labels]
    gold_key = bridge.canonical_key(gold)
    return {
        "top2_keys": keys,
        "gold_key": gold_key,
        "gold_top1": bool(keys and keys[0] == gold_key),
        "gold_top2": bool(gold_key and gold_key in keys[:2]),
    }


def _arm_summary(rows: Sequence[Mapping[str, Any]], telemetry_path: Path) -> dict[str, Any]:
    by_family: dict[str, Any] = {}
    for family in ("DA", "MCR"):
        subset = [row for row in rows if row["family"] == family]
        by_family[family] = {
            "n": len(subset),
            "success_n": sum(bool(row["success"]) for row in subset),
            "strict_top1_n": sum(bool(row["gold_top1"]) for row in subset),
            "strict_top2_n": sum(bool(row["gold_top2"]) for row in subset),
        }
    by_gate: dict[str, Any] = {}
    for gate in (False, True):
        subset = [row for row in rows if bool(row["historical_need_retrieval"]) is gate]
        by_gate[str(gate).lower()] = {
            "n": len(subset),
            "strict_top1_n": sum(bool(row["gold_top1"]) for row in subset),
            "strict_top2_n": sum(bool(row["gold_top2"]) for row in subset),
        }
    return {
        "experiment_id": EXPERIMENT_ID,
        "arm": str(rows[0]["arm"]) if rows else "",
        "n_cases": len(rows),
        "success_n": sum(bool(row["success"]) for row in rows),
        "strict_top1_n": sum(bool(row["gold_top1"]) for row in rows),
        "strict_top2_n": sum(bool(row["gold_top2"]) for row in rows),
        "changed_from_draft_n": sum(bool(row.get("changed_from_draft")) for row in rows),
        "introduced_candidate_n": sum(bool(row.get("introduced_candidate")) for row in rows),
        "fallback_to_draft_n": sum(bool(row.get("fallback_to_draft")) for row in rows),
        "by_family": by_family,
        "by_historical_gate": by_gate,
        "telemetry": aggregate_telemetry(read_jsonl(telemetry_path)),
    }


def _write_arm_manifest(
    arm_dir: Path,
    arm: str,
    prereg: Mapping[str, Any],
    *,
    model: str,
    workers: int,
) -> None:
    manifest = RunManifest(
        experiment_id=EXPERIMENT_ID,
        arm_id=arm,
        dataset="E4 frozen DA200+MCR200 development sample",
        model=model,
        workers=workers,
        rag=True,
        source_commit=source_commit(),
        prompt_hashes=dict(prereg["prompt_hashes"]),
        input_hash=str(prereg["input_hash"]),
        selection_freeze="E4 preregistration case keys + E11 retrieval_plan.jsonl",
        endpoint_contract=ENDPOINT_CONTRACT,
        excluded_variance_controls=list(prereg["excluded_variance_controls"]),
    )
    manifest.write(arm_dir / "run_manifest.json")


def run_diagnose(
    retrieval: str,
    jobs: Sequence[Mapping[str, Any]],
    plan: Sequence[Mapping[str, Any]],
    out: Path,
    prereg: Mapping[str, Any],
    *,
    model: str,
    workers: int,
) -> list[dict[str, Any]]:
    if retrieval not in RETRIEVALS:
        raise ValueError(retrieval)
    validate_workers(workers, rag=True)
    arm = f"{retrieval}_refine_off"
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    plan_by_key = {str(row["case_key"]): row for row in plan}
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)

    def worker(job: Mapping[str, Any]) -> dict[str, Any]:
        plan_row = plan_by_key[str(job["case_key"])]
        chunks = list(plan_row["bundles"][retrieval])
        payload = {
            "vignette": str(job["vignette"]),
            "knowledge_chunks": _online_chunks(chunks),
            "orchestrator": _orchestrator_payload(job),
        }
        outcome = caller.call(
            module="E11B07Diagnose",
            prompt=DIAGNOSE_PROMPT,
            payload=payload,
            validator=_top2_validator,
        )
        top2 = _extract_top2(outcome.response) if outcome.success else []
        score = _score_top2(top2, str(job["gold"]), bridge)
        return {
            "case_key": str(job["case_key"]),
            "slice_id": str(job["slice_id"]),
            "family": str(job["family"]),
            "case_id": str(job["case_id"]),
            "arm": arm,
            "retrieval": retrieval,
            "refine": "off",
            "success": outcome.success,
            "error": outcome.error,
            "gold": str(job["gold"]),
            "top2_labels": top2,
            **score,
            "historical_need_retrieval": bool(job["historical_need_retrieval"]),
            "query_source": str(job["query_source"]),
            "historical_queries": list(job["historical_queries"]),
            "historical_draft": list(job["historical_draft"]),
            "historical_final": list(job["historical_final"]),
            "served_chunk_ids": [str(row["chunk_id"]) for row in chunks],
            "served_bundle_sha256": canonical_sha256(_online_chunks(chunks)),
            "served_chars": sum(int(row.get("served_chars") or 0) for row in chunks),
            "raw_response": outcome.response,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "prompt_sha256": outcome.prompt_sha256,
            "payload_sha256": outcome.payload_sha256,
            "changed_from_draft": False,
            "introduced_candidate": False,
            "fallback_to_draft": False,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, job): str(job["case_key"]) for job in jobs}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    if len(rows) != len(jobs):
        raise AssertionError(f"{arm} incomplete: {len(rows)}/{len(jobs)}")
    write_jsonl(arm_dir / "case_results.jsonl", rows)
    atomic_json(arm_dir / "summary.json", _arm_summary(rows, telemetry_path))
    _write_arm_manifest(arm_dir, arm, prereg, model=model, workers=workers)
    return rows


def run_refine(
    retrieval: str,
    jobs: Sequence[Mapping[str, Any]],
    plan: Sequence[Mapping[str, Any]],
    out: Path,
    prereg: Mapping[str, Any],
    *,
    model: str,
    workers: int,
) -> list[dict[str, Any]]:
    if retrieval not in RETRIEVALS:
        raise ValueError(retrieval)
    validate_workers(workers, rag=True)
    source_arm = f"{retrieval}_refine_off"
    arm = f"{retrieval}_refine_on"
    draft_rows = read_jsonl(out / "arms" / source_arm / "case_results.jsonl")
    if len(draft_rows) != len(jobs):
        raise FileNotFoundError(f"complete {source_arm} output required")
    drafts = {str(row["case_key"]): row for row in draft_rows}
    plan_by_key = {str(row["case_key"]): row for row in plan}
    arm_dir = out / "arms" / arm
    arm_dir.mkdir(parents=True, exist_ok=True)
    telemetry_path = arm_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=arm_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)

    def worker(job: Mapping[str, Any]) -> dict[str, Any]:
        draft = drafts[str(job["case_key"])]
        chunks = list(plan_by_key[str(job["case_key"])]["bundles"][retrieval])
        draft_top2 = list(draft.get("top2_labels") or [])
        if not draft.get("success") or len(draft_top2) != 2:
            # A failed upstream diagnosis remains an ITA failure.  We do not
            # ask refine to manufacture a draft or use a gold-aware fallback.
            outcome = None
            top2: list[str] = []
            success = False
            error = "upstream diagnose invalid; refine not called"
            raw_response: dict[str, Any] = {}
        else:
            payload = {
                "vignette": str(job["vignette"]),
                "knowledge_chunks": _online_chunks(chunks),
                "draft_top2": draft_top2,
                "orchestrator": _orchestrator_payload(job),
            }
            outcome = caller.call(
                module="E11B07Refine",
                prompt=REFINE_PROMPT,
                payload=payload,
                validator=_top2_validator,
            )
            raw_response = outcome.response
            if outcome.success:
                top2 = _extract_top2(outcome.response)
                success = True
                error = ""
            else:
                # Mirrors the historical algorithm's explicit `or draft`
                # behavior while preserving the failure in provenance.
                top2 = draft_top2
                success = True
                error = f"refine invalid; frozen draft fallback: {outcome.error}"
        score = _score_top2(top2, str(job["gold"]), bridge)
        draft_keys = list(draft.get("top2_keys") or [])
        final_keys = list(score["top2_keys"])
        return {
            "case_key": str(job["case_key"]),
            "slice_id": str(job["slice_id"]),
            "family": str(job["family"]),
            "case_id": str(job["case_id"]),
            "arm": arm,
            "retrieval": retrieval,
            "refine": "on",
            "success": success,
            "refine_call_success": bool(outcome and outcome.success),
            "error": error,
            "gold": str(job["gold"]),
            "top2_labels": top2,
            **score,
            "draft_top2_labels": draft_top2,
            "draft_top2_keys": draft_keys,
            "draft_gold_top1": bool(draft.get("gold_top1")),
            "draft_gold_top2": bool(draft.get("gold_top2")),
            "historical_need_retrieval": bool(job["historical_need_retrieval"]),
            "query_source": str(job["query_source"]),
            "historical_queries": list(job["historical_queries"]),
            "historical_draft": list(job["historical_draft"]),
            "historical_final": list(job["historical_final"]),
            "served_chunk_ids": [str(row["chunk_id"]) for row in chunks],
            "served_bundle_sha256": canonical_sha256(_online_chunks(chunks)),
            "served_chars": sum(int(row.get("served_chars") or 0) for row in chunks),
            "raw_response": raw_response,
            "cache_hit": bool(outcome and outcome.cache_hit),
            "cache_key": str(outcome.cache_key if outcome else ""),
            "prompt_sha256": str(outcome.prompt_sha256 if outcome else sha256_text(REFINE_PROMPT)),
            "payload_sha256": str(outcome.payload_sha256 if outcome else ""),
            "changed_from_draft": final_keys != draft_keys,
            "introduced_candidate": bool(set(final_keys) - set(draft_keys)),
            "fallback_to_draft": bool(outcome and not outcome.success),
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, job): str(job["case_key"]) for job in jobs}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    if len(rows) != len(jobs):
        raise AssertionError(f"{arm} incomplete: {len(rows)}/{len(jobs)}")
    write_jsonl(arm_dir / "case_results.jsonl", rows)
    atomic_json(arm_dir / "summary.json", _arm_summary(rows, telemetry_path))
    _write_arm_manifest(arm_dir, arm, prereg, model=model, workers=workers)
    return rows


def freeze(
    out: Path,
    jobs: Sequence[Mapping[str, Any]],
    inputs: Sequence[Path],
    plan: Sequence[Mapping[str, Any]],
    *,
    model: str,
    workers: int,
) -> dict[str, Any]:
    validate_workers(workers, rag=True)
    out.mkdir(parents=True, exist_ok=True)
    retrieval_manifest = json.loads((out / "retrieval_manifest.json").read_text(encoding="utf-8"))
    expected = {
        "schema": "e11_b07_factorial_prereg_v1",
        "experiment_id": EXPERIMENT_ID,
        "development_not_confirmation": True,
        "created_before_online_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "workers": workers,
        "rag_worker_ceiling": 25,
        "arms": list(ARMS),
        "selection": {
            "source": str(E4_PREREG.relative_to(ROOT)),
            "n_cases": len(jobs),
            "family_counts": dict(Counter(row["family"] for row in jobs)),
            "slice_counts": dict(Counter(row["slice_id"] for row in jobs)),
            "case_keys_sha256": canonical_sha256([row["case_key"] for row in jobs]),
        },
        "input_hash": combined_file_sha256(inputs),
        "retrieval_plan_sha256": canonical_sha256(plan),
        "retriever_backend": retrieval_manifest["retriever_backend"],
        "prompt_hashes": {
            "diagnose": sha256_text(DIAGNOSE_PROMPT),
            "refine": sha256_text(REFINE_PROMPT),
        },
        "factor_isolation": {
            "orchestrator": "historical B07 decision, queries and strategy frozen per case across all eight arms",
            "diagnose": "same model, prompt, vignette and orchestrator; only knowledge_chunks differ",
            "refine": "same frozen diagnosis draft and same knowledge bundle; off is byte-level draft reuse, on is one generic refine call",
            "condition_masking": "retrieval condition labels and IR scores are withheld from model payloads",
            "forced_treatment": "all cases receive assigned bundle regardless of historical need_retrieval; historical gate is a moderator only",
        },
        "seven_falsifiable_primary_contrasts": [
            ["off_refine_off", "relevant_refine_off", "relevant retrieval vs no chunks"],
            ["random_refine_off", "relevant_refine_off", "relevant retrieval vs nonspecific context"],
            ["hard_negative_refine_off", "relevant_refine_off", "top-ranked retrieval vs topically plausible near-miss context"],
            ["off_refine_off", "off_refine_on", "generic refine without retrieval"],
            ["relevant_refine_off", "relevant_refine_on", "generic refine with relevant retrieval"],
            ["random_refine_off", "random_refine_on", "generic refine with random context"],
            ["hard_negative_refine_off", "hard_negative_refine_on", "generic refine under misleading-context pressure"],
        ],
        "primary_endpoint": "paired frozen-identity pre-mapper Top-1, Holm-adjusted across seven contrasts",
        "secondary_endpoints": [
            "paired frozen-identity pre-mapper Top-2",
            "clinical-complete/equivalent Top-1 and Top-2 after heterogeneous screen plus root audit",
            "draft change, candidate introduction/deletion, and correct-to-wrong/wrong-to-correct transitions",
            "family and historical retrieval-gate moderation",
            "chunk relevance, gold support, incumbent support and confirmation index",
        ],
        "hard_negative_caveat": "operational lexical near-neighbour, not assumed clinically false; contamination is a measured endpoint",
        "payload_transmitted": ["clean vignette", "historical target-blind queries/strategy", "condition-specific chunks", "frozen draft for refine-on"],
        "payload_withheld": ["gold", "answer options", "gold letter", "other-arm outputs", "treatment label", "retrieval score"],
        "failure_policy": "intention-to-analyse; invalid diagnose is incorrect and skips refine; invalid refine explicitly falls back to frozen draft as historical B07 did",
        "excluded_variance_controls": ["repeat runs", "new confirmation set", "provider/retry standardisation"],
        "endpoint_contract": ENDPOINT_CONTRACT,
    }
    path = out / "preregistration.json"
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in ("schema", "model", "workers", "arms", "input_hash", "retrieval_plan_sha256", "prompt_hashes"):
            if current.get(key) != expected.get(key):
                raise AssertionError(f"frozen E11 preregistration mismatch: {key}")
        return current
    atomic_json(path, expected)
    atomic_json(
        out / "environment.json",
        {
            "capabilities": dependency_capabilities(),
            "model": model,
            "workers": workers,
            "retriever_backend": retrieval_manifest["retriever_backend"],
            "llama_provider_policy_requested": os.environ.get("TREE_DX_LLAMA_PROVIDER_POLICY", "ordered"),
            "transport_requested": os.environ.get("TREE_DX_LLM_TRANSPORT", "auto"),
            "bridge_sha256": file_sha256(BRIDGE_PATH),
        },
    )
    return expected


def write_design_note(out: Path) -> None:
    path = out / "DESIGN.md"
    if path.is_file():
        return
    path.write_text(
        """# E11 B07 retrieval × refine factorial: frozen design

This is a 400-case development/mechanism experiment, not a fresh confirmation.
It tests four forced knowledge conditions (`off`, query-top `relevant`, stable
`random`, and query-near but relevant-article-excluded `hard_negative`) crossed
with generic refine off/on. Historical B07 target-blind orchestrator outputs are
reused byte-for-byte at the semantic-field level; no new query-planner call can
confound a retrieval comparison.

The seven preregistered comparisons are three retrieval contrasts at refine-off
plus four within-retrieval refine contrasts. Frozen-identity Top-1 is primary;
clinical equivalence is adjudicated separately because the exact bridge is
conservative. Hard-negative is an operational IR treatment, not a declaration
that its chunks are false. Gold-support contamination and incumbent-confirming
evidence are audited before any causal interpretation.

The repository `RAGRetriever` remains available through
`TREE_DX_E11_RETRIEVER=production` when its metadata and dependencies are
materialized. `auto` uses it when viable and otherwise falls back to an audited
TF-IDF index over the committed Merck 19e corpus; a pure-Python BM25 fallback
remains available when scikit-learn is absent. LLM transport remains the shared
`RobustLLMClient`, whose official OpenAI SDK route is selected when installed.
""",
        encoding="utf-8",
    )


def archive_arm(out: Path, arm: str) -> tuple[Path, str]:
    arm_dir = out / "arms" / arm
    archive = arm_dir / "RUN_ARTIFACTS.tar.gz"
    members = [
        path for path in sorted(arm_dir.iterdir())
        if path.is_file() and path.name not in {archive.name, f"{archive.name}.sha256"}
    ]
    with tarfile.open(archive, "w:gz") as bundle:
        for path in members:
            bundle.add(path, arcname=path.name)
    digest = file_sha256(archive)
    (arm_dir / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return archive, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "diagnose", "refine"))
    parser.add_argument("--retrieval", choices=RETRIEVALS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument(
        "--retriever",
        default=os.environ.get("TREE_DX_E11_RETRIEVER", "auto"),
        choices=("auto", "production", "merck"),
    )
    args = parser.parse_args()
    jobs, inputs = load_jobs()
    args.out.mkdir(parents=True, exist_ok=True)
    plan = build_retrieval_plan(jobs, args.out, retriever_mode=args.retriever)
    prereg = freeze(args.out, jobs, inputs, plan, model=args.model, workers=args.workers)
    write_design_note(args.out)
    if args.command == "freeze":
        print(json.dumps({"experiment": EXPERIMENT_ID, "n": len(jobs), "backend": prereg["retriever_backend"]}, indent=2))
        return
    if not args.retrieval:
        parser.error("--retrieval is required for diagnose/refine")
    if args.command == "diagnose":
        rows = run_diagnose(
            args.retrieval, jobs, plan, args.out, prereg,
            model=args.model, workers=args.workers,
        )
        arm = f"{args.retrieval}_refine_off"
    else:
        rows = run_refine(
            args.retrieval, jobs, plan, args.out, prereg,
            model=args.model, workers=args.workers,
        )
        arm = f"{args.retrieval}_refine_on"
    archive, digest = archive_arm(args.out, arm)
    print(json.dumps({"arm": arm, "n": len(rows), "archive": str(archive), "sha256": digest}, indent=2))


if __name__ == "__main__":
    main()
