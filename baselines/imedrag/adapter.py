"""i-MedRAG adapter on shared project KB + RobustLLMClient.

Upstream: Teddy-XiongGZ/MedRAG (i-MedRAG / PSB 2025)
  https://github.com/Teddy-XiongGZ/MedRAG
  arXiv:2408.00727

This module reuses the official iterative control flow and prompt *roles*
(follow-up ask → per-query RAG answer → accumulate context → final answer)
from ``baselines/imedrag/upstream/src/medrag.py`` / ``template.py``, but:

- Retrieval uses only ``data/corpus/rag_index`` + ``data/corpus/cpg_index``
  (via ``retrieve_live_bundle``), never MedRAG Textbooks/PubMed corpora.
- LLM calls go through the paper baseline ``SimpleCachedLLM`` / shared model.
- Output contract is open-vignette ordered Top-2 (no MCQ letters).

JSON wrappers below preserve official Analysis/Queries/Answer semantics while
matching the project's ``call_module`` JSON-only client.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = Path(__file__).resolve().parent / "upstream"
UPSTREAM_COMMIT = "7599a728a28789fd601728c08d313b1148051f41"
UPSTREAM_URL = "https://github.com/Teddy-XiongGZ/MedRAG"

# Official template strings (src/template.py) — kept verbatim where possible.
I_MEDRAG_SYSTEM = (
    "You are a helpful medical assistant, and your task is to answer the given "
    "question following the instructions given by the user. "
)
SIMPLE_MEDRAG_SYSTEM = (
    "You are a helpful medical expert, and your task is to answer a medical "
    "question using the relevant documents."
)
FOLLOW_UP_ASK = (
    "Please first analyze all the information in a section named Analysis "
    "(## Analysis). Then, use key terms from previous answers to form specific "
    "and direct questions. Generate {n_queries} concise, context-specific queries "
    "to search for additional information in an external knowledge base, in a "
    "section named Queries (## Queries). Each query should be simple and focused, "
    "directly relating to the key terms used in the answers. Wait for responses "
    "from the user before proceeding."
)
FOLLOW_UP_ANSWER = (
    "Please first think step-by-step to analyze all the information in a section "
    "named Analysis (## Analysis). Then, please provide your answer in a section "
    "named Answer (## Answer)."
)

ASK_PROMPT = f"""{I_MEDRAG_SYSTEM}

You are running i-MedRAG follow-up query generation (official loop).
Return JSON only:
{{"analysis":"...", "queries":["query 1", "query 2", ...]}}
Exactly the requested number of queries. Do not answer the main diagnosis yet.
"""

INNER_RAG_PROMPT = f"""{SIMPLE_MEDRAG_SYSTEM}

Answer the follow-up query using ONLY the supplied knowledge excerpts.
Return JSON only:
{{"answer":"concise factual answer from documents", "reasoning_summary":"brief"}}
"""

FINAL_PROMPT = f"""{I_MEDRAG_SYSTEM}

{FOLLOW_UP_ANSWER}

This is an open differential-diagnosis case (no multiple-choice letters).
Using the accumulated query-answer context and the vignette, produce an ordered
Top-2 of concrete diseases (best first).
Return JSON only:
{{"analysis":"...",
 "answer":"brief final answer prose",
 "top2_diagnoses":[{{"diagnosis":"...","reasoning_summary":"..."}},
 {{"diagnosis":"...","reasoning_summary":"..."}}]}}
"""


def _ensure_two(names: Sequence[str]) -> list[str]:
    cleaned = [str(n).strip() for n in names if str(n).strip()]
    while len(cleaned) < 2:
        cleaned.append(cleaned[-1] if cleaned else "undetermined")
    return cleaned[:2]


def _text_field(raw: Any, *keys: str) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, Mapping):
        return str(raw or "").strip()
    for key in keys:
        val = raw.get(key)
        if val:
            return str(val).strip()
    return str(raw.get("raw_text") or "").strip()


def _parse_queries(raw: Any, *, n_queries: int) -> list[str]:
    queries: list[str] = []
    if isinstance(raw, Mapping):
        rows = raw.get("queries") or raw.get("output") or []
        if isinstance(rows, str):
            rows = [rows]
        for item in rows:
            q = re.sub(r"^\d+\.\s*", "", str(item).strip())
            if q and q.casefold() not in {x.casefold() for x in queries}:
                queries.append(q[:300])
            if len(queries) >= n_queries:
                break
        if queries:
            return queries
        blob = _text_field(raw, "text", "content", "raw_text")
    else:
        blob = str(raw or "")
    if "## Queries" in blob:
        blob = blob.split("## Queries", 1)[-1]
    for line in blob.splitlines():
        line = re.sub(r"^\d+\.\s*", "", line.strip(" -*\t"))
        if len(line) < 4:
            continue
        if line.casefold().startswith(("analysis", "answer", "query")):
            continue
        if line.casefold() not in {x.casefold() for x in queries}:
            queries.append(line[:300])
        if len(queries) >= n_queries:
            break
    return queries


def _format_docs(chunks: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for idx, chunk in enumerate(chunks):
        title = str(chunk.get("title") or "")
        text = str(chunk.get("text") or chunk.get("content") or "")
        parts.append(f"Document [{idx}] (Title: {title}) {text}")
    return "\n".join(parts) if parts else ""


def _retrieve_shared(
    query: str,
    retrievers: Mapping[str, Any] | None,
    *,
    max_chunks: int = 8,
    per_query_per_index: int = 4,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not retrievers or not str(query).strip():
        return [], {}
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    from eval_naive_cot_rag_ablation import retrieve_live_bundle

    chunks, audit = retrieve_live_bundle(
        [str(query).strip()[:300]],
        retrievers,
        per_query_per_index=per_query_per_index,
        max_chunks=max_chunks,
    )
    return chunks, audit


def diagnose_case(
    vignette: str,
    cache: Any,
    *,
    retrievers: Mapping[str, Any] | None = None,
    dry_run: bool = False,
    n_rounds: int = 3,
    n_queries: int = 2,
    max_chunks: int = 8,
    question: str | None = None,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Run i-MedRAG iterative follow-up RAG → ordered Top-2 diagnoses."""
    cost = {
        "llm_calls": 0,
        "input_tokens_est": 0,
        "output_tokens_est": 0,
        "retrieval_calls": 0,
        "retrieval_snippets": 0,
        "snippet_chars": 0,
        "latency_s": 0.0,
    }
    t0 = time.time()
    main_q = question or (
        f"{vignette.strip()}\n\nWhat is the most likely diagnosis? "
        "List the top two concrete disease names, best first."
    )
    if dry_run and getattr(cache, "client", None) is None:
        top2 = ["i-MedRAG-dx-a", "i-MedRAG-dx-b"]
        cost["latency_s"] = time.time() - t0
        return top2, {
            "dry_run": True,
            "method": "imedrag",
            "upstream": UPSTREAM_URL,
            "upstream_commit": UPSTREAM_COMMIT,
        }, cost

    context = ""
    history: list[dict[str, Any]] = []
    qa_pairs: list[dict[str, Any]] = []
    n_rounds = max(1, int(n_rounds))
    n_queries = max(1, int(n_queries))

    for round_idx in range(n_rounds):
        ask_user = FOLLOW_UP_ASK.format(n_queries=n_queries)
        ask_payload = {
            "question": main_q,
            "context": context,
            "instruction": ask_user,
            "round": round_idx,
            "n_queries": n_queries,
        }
        ask_raw = cache.call(
            f"PaperB17IMedRAGAsk_{round_idx}",
            ASK_PROMPT,
            ask_payload,
        )
        cost["llm_calls"] += 1
        queries = _parse_queries(ask_raw, n_queries=n_queries)
        if not queries:
            # Official code continues on parse failure; seed with vignette head.
            queries = [
                " ".join(vignette.split())[:180],
                f"differential diagnosis {' '.join(vignette.split())[:120]}",
            ][:n_queries]
        history.append({"round": round_idx, "ask": ask_raw, "queries": queries})

        for q_idx, query in enumerate(queries):
            chunks, audit = _retrieve_shared(
                query, retrievers, max_chunks=max_chunks,
            )
            cost["retrieval_calls"] += len(audit.get("requests") or [])
            cost["retrieval_snippets"] += len(chunks)
            cost["snippet_chars"] += sum(len(c.get("text") or "") for c in chunks)
            docs = _format_docs(chunks)
            rag_raw = cache.call(
                f"PaperB17IMedRAGInner_{round_idx}_{q_idx}",
                INNER_RAG_PROMPT,
                {
                    "query": query,
                    "context": docs,
                    "question": query,
                },
            )
            cost["llm_calls"] += 1
            answer = _text_field(rag_raw, "answer", "text", "content") or str(rag_raw)
            block = f"Query: {query}\nAnswer: {answer}"
            context = f"{context}\n\n{block}".strip() if context else block
            qa_pairs.append({
                "round": round_idx,
                "query": query,
                "answer": answer,
                "n_chunks": len(chunks),
                "retrieval": audit,
            })

    final_raw = cache.call(
        "PaperB17IMedRAGFinal",
        FINAL_PROMPT,
        {
            "question": main_q,
            "context": context,
            "vignette": vignette,
            "instruction": FOLLOW_UP_ANSWER,
        },
    )
    cost["llm_calls"] += 1

    # Prefer structured top2; else parse answer prose.
    top2: list[str] = []
    if isinstance(final_raw, Mapping):
        rows = final_raw.get("top2_diagnoses") or []
        for row in rows:
            if isinstance(row, Mapping):
                name = str(
                    row.get("diagnosis") or row.get("name") or row.get("disease") or ""
                ).strip()
            else:
                name = str(row).strip()
            if name and name.casefold() not in {n.casefold() for n in top2}:
                top2.append(name)
            if len(top2) >= 2:
                break
    if len(top2) < 2:
        # Late import to avoid circular deps when adapter used standalone.
        sys.path.insert(0, str(ROOT / "scripts" / "paper"))
        import baseline_common as bc  # noqa: WPS433

        top2 = bc.clean_top2_from_response(final_raw)
        if not any(top2):
            ans = _text_field(final_raw, "answer", "text", "content")
            top2 = bc.parse_numbered_diagnoses(ans, k=2)

    cost["latency_s"] = time.time() - t0
    return _ensure_two(top2), {
        "method": "imedrag",
        "upstream": UPSTREAM_URL,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_present": UPSTREAM.is_dir(),
        "n_rounds": n_rounds,
        "n_queries": n_queries,
        "max_chunks": max_chunks,
        "kb": "shared_rag_index+cpg_index",
        "context": context,
        "history": history,
        "qa_pairs": qa_pairs,
        "final": final_raw,
    }, cost
