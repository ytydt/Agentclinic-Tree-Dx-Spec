#!/usr/bin/env python3
"""Extract pair-scoped CCEG claims from CPG chunks with resumable caching."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import sys
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402

DEFAULT_SCOPE = ROOT / "data/cceg/pilot/scope_queries.jsonl"
DEFAULT_CHUNKS = ROOT / "data/cpg/processed/cpg_chunks.jsonl"
DEFAULT_OUT = ROOT / "data/cceg/pilot/claims.raw.jsonl"
DEFAULT_CACHE = ROOT / "data/cceg/pilot/extraction_cache"

EXTRACTION_PROMPT = """You extract contrastive clinical evidence claims.
The payload contains exactly one candidate pair, one typed finding surface/value,
and one source chunk. Extract only claims explicitly supported by an exact,
verbatim substring of chunk.content. Pair-scoped direction/common/test claims
must compare candidate_a with candidate_b in that same quote. A disease list is
enumeration, not direction. Case reports may emit membership or phenotype
claims only and never direction/common/test claims.
Return strict JSON:
{"claims":[{"claim_type":"direction|common|membership|phenotype_assertion|test_recommendation",
"relation":"supports_a|supports_b|argues_against_a|argues_against_b|common|member_of|typical_for|atypical_for|recommends_test",
"quote":"exact substring","strength":"explicit|qualified|anecdotal",
"confidence":0.0,"event_type":"laboratory|symptom|sign|imaging|history|other",
"value_state":"elevated|suppressed|present|absent|normal|unknown",
"polarity":1,"value":null,"unit":null,"specimen":null,
"normalization":{"system":null,"code":null,"display":null,"provenance":null,"confidence":null},
"enumeration_only":false,"pair_binding_ok":true,"negation_scope_ok":true,
"value_scope_ok":true,"has_support_excerpt":true,
"has_contrast_excerpt":true,"recommended_test":null}]}
Return {"claims":[]} when the chunk does not explicitly entail a claim."""
PROMPT_SHA256 = hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()
DOCUMENT_SPLIT_SALT = "cceg-v1-source-document-split"
_TOKEN = re.compile(r"[a-z0-9]+")
_WRITE_LOCK = threading.Lock()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{number}: expected object")
                rows.append(value)
    return rows


def hydrate_quote(content: str, quote: str) -> tuple[int, int]:
    """Return the exact quote span, rejecting absent or ambiguous text."""
    if not isinstance(content, str) or not isinstance(quote, str) or not quote:
        raise ValueError("quote and chunk content must be non-empty strings")
    start = content.find(quote)
    if start < 0:
        raise ValueError("quote is not an exact chunk.content substring")
    if content.find(quote, start + 1) >= 0:
        raise ValueError("quote is ambiguous within chunk.content")
    end = start + len(quote)
    if content[start:end] != quote:
        raise ValueError("hydrated quote span is not exact")
    return start, end


def _terms(text: str) -> set[str]:
    return {term for term in _TOKEN.findall(text.casefold()) if len(term) > 2}


def retrieve_pair_chunks(
    query: Mapping[str, Any], chunks: Iterable[Mapping[str, Any]], top_k: int,
) -> list[dict[str, Any]]:
    """Deterministic metadata retrieval scored for both candidates and finding."""
    a = str(query["candidate_a"]).casefold()
    b = str(query["candidate_b"]).casefold()
    finding = query.get("finding") or {}
    surface = str(finding.get("surface", ""))
    query_terms = _terms(f"{a} {b} {surface} {finding.get('value', '')}")
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for raw in chunks:
        content = str(raw.get("content") or raw.get("text") or "")
        metadata = " ".join(str(raw.get(key) or "") for key in (
            "title", "section_path", "source", "article_id", "chunk_type"))
        haystack = f"{metadata} {content}".casefold()
        overlap = len(query_terms & _terms(haystack))
        score = float(overlap)
        score += 4.0 if a in haystack else 0.0
        score += 4.0 if b in haystack else 0.0
        score += 2.0 if surface.casefold() in haystack else 0.0
        if score:
            ranked.append((score, str(raw.get("id") or ""), dict(raw)))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [row for _, _, row in ranked[:top_k]]


class PairChunkRetriever:
    """One-pass restricted inverted index for the frozen pilot query vocabulary."""

    def __init__(
        self,
        chunks: list[dict[str, Any]],
        queries: Iterable[Mapping[str, Any]],
    ) -> None:
        self.chunks = chunks
        vocabulary: set[str] = set()
        for query in queries:
            finding = query.get("finding") or {}
            vocabulary.update(_terms(
                f"{query['candidate_a']} {query['candidate_b']} "
                f"{finding.get('surface', '')} {finding.get('value', '')}"
            ))
        self.postings: dict[str, list[int]] = defaultdict(list)
        self.haystacks: list[str] = []
        for position, raw in enumerate(chunks):
            content = str(raw.get("content") or raw.get("text") or "")
            metadata = " ".join(str(raw.get(key) or "") for key in (
                "title", "section_path", "source", "article_id", "chunk_type"))
            haystack = f"{metadata} {content}".casefold()
            self.haystacks.append(haystack)
            for term in _terms(haystack) & vocabulary:
                self.postings[term].append(position)

    def retrieve(
        self,
        query: Mapping[str, Any],
        top_k: int,
    ) -> list[dict[str, Any]]:
        a = str(query["candidate_a"]).casefold()
        b = str(query["candidate_b"]).casefold()
        finding = query.get("finding") or {}
        surface = str(finding.get("surface", ""))
        query_terms = _terms(f"{a} {b} {surface} {finding.get('value', '')}")
        overlap_by_position: dict[int, int] = defaultdict(int)
        for term in query_terms:
            for position in self.postings.get(term, ()):
                overlap_by_position[position] += 1
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for position, overlap in overlap_by_position.items():
            raw = self.chunks[position]
            haystack = self.haystacks[position]
            score = float(overlap)
            score += 4.0 if a in haystack else 0.0
            score += 4.0 if b in haystack else 0.0
            score += 2.0 if surface.casefold() in haystack else 0.0
            ranked.append((score, str(raw.get("id") or ""), raw))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [row for _, _, row in ranked[:top_k]]


def _source_class(chunk: Mapping[str, Any]) -> str:
    corpus = str(chunk.get("corpus") or chunk.get("source_tier") or "").casefold()
    if "case" in corpus:
        return "case_report_prose"
    return "cpg_enumeration" if chunk.get("chunk_type") == "enumeration" else "cpg_prose"


def _candidate(name: str) -> dict[str, Any]:
    return {"name": name, "id": None, "id_provenance": None, "l1_parent": None}


def document_split(chunk: Mapping[str, Any]) -> str:
    """Assign an immutable source-document split, independent of case labels."""
    document_id = str(
        chunk.get("article_id") or chunk.get("source_id") or chunk.get("source")
        or chunk.get("id") or ""
    )
    if not document_id:
        raise ValueError("source document requires a stable identifier")
    bucket = int(hashlib.sha256(
        f"{DOCUMENT_SPLIT_SALT}:{document_id}".encode("utf-8")
    ).hexdigest()[:8], 16) % 100
    return "build" if bucket < 80 else ("audit" if bucket < 90 else "held_out")


def materialize_claim(
    raw: Mapping[str, Any],
    query: Mapping[str, Any],
    chunk: Mapping[str, Any],
    model: str,
) -> dict[str, Any]:
    quote = str(raw.get("quote") or "")
    content = str(chunk.get("content") or chunk.get("text") or "")
    start, end = hydrate_quote(content, quote)
    claim_type = str(raw.get("claim_type") or "")
    source_class = _source_class(chunk)
    if source_class.startswith("case_report") and claim_type in {
        "direction", "common", "test_recommendation",
    }:
        raise ValueError("case reports cannot emit directional pair claims")
    normalization = raw.get("normalization") or {}
    mapped = all(normalization.get(key) for key in (
        "system", "code", "display", "provenance"))
    concepts = [{
        "system": normalization["system"],
        "code": normalization["code"],
        "display": normalization["display"],
        "provenance": normalization["provenance"],
        "confidence": float(normalization.get("confidence", 0.0)),
    }] if mapped else []
    pair_scoped = claim_type in {"direction", "common", "test_recommendation"}
    finding_seed = query.get("finding") or {}
    identity = json.dumps(
        [query["query_id"], chunk.get("id"), raw],
        ensure_ascii=False, sort_keys=True, default=str)
    claim = {
        "schema_version": 1,
        "claim_id": "cceg_" + hashlib.sha256(
            identity.encode("utf-8")).hexdigest()[:16],
        "claim_type": claim_type,
        "candidate_a": _candidate(str(query["candidate_a"])),
        "candidate_b": _candidate(str(query["candidate_b"])) if pair_scoped else None,
        "finding": {
            "surface": str(finding_seed.get("surface") or ""),
            "event_type": str(raw.get("event_type") or "other"),
            "concepts": concepts,
            "polarity": int(raw.get("polarity", 0)),
            "value_state": str(raw.get("value_state") or "unknown"),
            "value": raw.get("value", finding_seed.get("value") or None),
            "unit": raw.get("unit"),
            "specimen": raw.get("specimen"),
            "temporal": {
                "onset": None, "duration": None, "relation": None, "anchor": None,
            },
            "context": {},
            "abstained": not mapped,
        },
        "relation": raw.get("relation"),
        "recommended_test": raw.get("recommended_test"),
        "strength": "anecdotal" if source_class.startswith("case_report") else raw.get("strength"),
        "source_class": source_class,
        "allowed_consumers": ["audit"],
        "comparator": {
            "required": pair_scoped,
            "has_support_excerpt": bool(raw.get("has_support_excerpt")) if pair_scoped else False,
            "has_contrast_excerpt": bool(raw.get("has_contrast_excerpt")) if pair_scoped else False,
            "contrast_candidates": [str(query["candidate_b"])] if pair_scoped else [],
        },
        "provenance": {
            "source_id": str(chunk.get("source_id") or chunk.get("source") or chunk.get("id")),
            "chunk_id": str(chunk.get("id")),
            "article_id": str(chunk.get("article_id") or chunk.get("source_id") or chunk.get("id")),
            "section": str(chunk.get("section_path") or chunk.get("title") or "unknown"),
            "chunk_type": str(chunk.get("chunk_type") or "other"),
            "quote": quote,
            "quote_span": [start, end],
            "url": str(chunk.get("url") or "urn:cceg:local"),
            "evidence_grade": chunk.get("evidence_grade"),
        },
        "extraction": {
            "pipeline": "extract_cceg_claims_v1",
            "model": model,
            "prompt_sha256": PROMPT_SHA256,
            "confidence": float(raw.get("confidence", 0.0)),
            "entailment_status": "unvalidated",
            "normalization_abstained": not mapped,
            "normalization_reason": None if mapped else "extractor did not provide a complete mapping",
        },
        "audit": {
            "enumeration_only": bool(raw.get("enumeration_only")),
            "pair_binding_ok": bool(raw.get("pair_binding_ok")),
            "negation_scope_ok": bool(raw.get("negation_scope_ok")),
            "value_scope_ok": bool(raw.get("value_scope_ok")),
        },
        "review": {"status": "unreviewed", "reviewer_ids": [], "adjudication": None},
        "split": {
            "document_family": query["document_family"],
            "document_split": document_split(chunk),
            "family_held_out": bool(query["family_held_out"]),
            "pilot_scope": True,
        },
        "claim_status": "raw",
    }
    errors = validate_claim(claim)
    if errors:
        raise ValueError("invalid extracted claim: " + "; ".join(errors))
    return claim


def _cache_key(query: Mapping[str, Any], chunk: Mapping[str, Any], model: str) -> str:
    payload = json.dumps([
        PROMPT_SHA256,
        model,
        query,
        chunk,
    ], ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_one(
    llm: Any,
    query: Mapping[str, Any],
    chunk: Mapping[str, Any],
    model: str,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    key = _cache_key(query, chunk, model)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        response = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "pair": {
                "candidate_a": query["candidate_a"],
                "candidate_b": query["candidate_b"],
            },
            "finding": query["finding"],
            "chunk": {
                "id": chunk.get("id"),
                "source": chunk.get("source"),
                "article_id": chunk.get("article_id"),
                "section_path": chunk.get("section_path") or chunk.get("title"),
                "chunk_type": chunk.get("chunk_type"),
                "content": chunk.get("content") or chunk.get("text"),
            },
        }
        response = llm.call_module("CCEGPairClaimExtractor", EXTRACTION_PROMPT, payload)
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            with cache_path.open("x", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        except FileExistsError:
            response = json.loads(cache_path.read_text(encoding="utf-8"))
    raw_claims = response.get("claims", []) if isinstance(response, Mapping) else []
    if not isinstance(raw_claims, list):
        raise ValueError("extractor response claims must be an array")
    return [
        materialize_claim(raw, query, chunk, model)
        for raw in raw_claims if isinstance(raw, Mapping)
    ]


def _completed_queries(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    return {
        str(row.get("query_id"))
        for row in load_jsonl(manifest)
        if row.get("event") == "query_complete"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_concurrency <= 100:
        parser.error("--max-concurrency must be between 1 and 100")
    manifest = args.manifest or args.out.with_suffix(args.out.suffix + ".manifest.jsonl")
    if not args.resume and (args.out.exists() or manifest.exists()):
        parser.error("refusing to overwrite output/manifest; use --resume")
    if args.resume and not (args.out.exists() and manifest.exists()):
        parser.error("--resume requires existing output and manifest")
    queries = load_jsonl(args.scope)
    chunks = load_jsonl(args.chunks)
    retriever = PairChunkRetriever(chunks, queries)
    completed = _completed_queries(manifest) if args.resume else set()
    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for query in queries:
        if query["query_id"] in completed:
            continue
        jobs.extend(
            (query, chunk)
            for chunk in retriever.retrieve(query, args.top_k)
        )
    if args.dry_run:
        print(json.dumps({
            "queries": len(queries), "pending_jobs": len(jobs),
            "prompt_sha256": PROMPT_SHA256, "would_write": str(args.out),
        }, indent=2))
        return 0
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(
        model=args.model, call_timeout=180, max_retries=4,
        timeout_retry_cap=2, temperature=0.0)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        args.out.touch(exist_ok=False)
        manifest.touch(exist_ok=False)
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "event": "run_resume" if args.resume else "run_start",
            "scope": str(args.scope),
            "chunks": str(args.chunks),
            "output": str(args.out),
            "model": args.model,
            "prompt_sha256": PROMPT_SHA256,
            "scope_sha256": _file_sha256(args.scope),
            "chunks_sha256": _file_sha256(args.chunks),
            "document_split_salt": DOCUMENT_SPLIT_SALT,
            "top_k": args.top_k,
            "max_concurrency": args.max_concurrency,
        }, ensure_ascii=False) + "\n")
    claims_written = 0
    errors = 0
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {
        str(query["query_id"]): []
        for query in queries
        if query["query_id"] not in completed
    }
    for query, chunk in jobs:
        grouped.setdefault(str(query["query_id"]), []).append((query, chunk))

    def run_query(
        query_id: str,
        items: list[tuple[dict[str, Any], dict[str, Any]]],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        claims: list[dict[str, Any]] = []
        failures: list[str] = []
        for query, chunk in items:
            try:
                claims.extend(extract_one(llm, query, chunk, args.model, args.cache_dir))
            except Exception as exc:  # preserve per-chunk failures in manifest
                failures.append(f"{chunk.get('id')}: {exc}")
        return query_id, claims, failures

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_concurrency) as pool:
        futures = [
            pool.submit(run_query, query_id, items)
            for query_id, items in grouped.items()
        ]
        for future in concurrent.futures.as_completed(futures):
            query_id, claims, failures = future.result()
            # L0 rejects malformed/unsupported claims individually. A bad claim
            # must not erase valid claims extracted from sibling source chunks.
            claims_to_write = claims
            event = {
                "event": "query_complete",
                "query_id": query_id,
                "claims": len(claims_to_write),
                "rejected_chunks": len(failures),
                "errors": failures,
                "prompt_sha256": PROMPT_SHA256,
                "model": args.model,
            }
            with _WRITE_LOCK:
                with args.out.open("a", encoding="utf-8") as handle:
                    for claim in claims_to_write:
                        handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
                with manifest.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            claims_written += len(claims_to_write)
            errors += len(failures)
    print(json.dumps({
        "claims_written": claims_written, "l0_rejections": errors,
        "output": str(args.out), "manifest": str(manifest),
        "prompt_sha256": PROMPT_SHA256,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
