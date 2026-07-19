#!/usr/bin/env python3
"""Extract unary candidate effects with lexical reranking and resumable caching."""
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
sys.path.insert(0, str(ROOT / "scripts"))

from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402
from extract_cceg_claims import document_split, hydrate_quote, load_jsonl  # noqa: E402

DEFAULT_SCOPE = ROOT / "data/cceg/unary_v1/scope_queries.jsonl"
DEFAULT_CHUNKS = ROOT / "data/cpg/processed/cpg_chunks.jsonl"
DEFAULT_OUT = ROOT / "data/cceg/unary_v1/claims.raw.jsonl"
DEFAULT_CACHE = ROOT / "data/cceg/unary_v1/extraction_cache"

EXTRACTION_PROMPT = """You extract unary candidate effects from clinical sources.
The payload contains one candidate, one typed finding, and one source chunk.
Return a claim only when one unique, exact verbatim substring of chunk.content
states that the finding is typical/supportive of the candidate (rule_in), or
atypical/contradictory for the candidate (rule_out). Do not require or invent a
comparison candidate or contrast excerpt. Lists and mere co-mentions are not
candidate effects. Preserve negation and value scope. Return strict JSON:
{"claims":[{"effect":"rule_in|rule_out","quote":"exact substring",
"strength":"explicit|qualified|anecdotal","confidence":0.0,
"event_type":"laboratory|symptom|sign|imaging|history|other",
"value_state":"elevated|suppressed|present|absent|normal|unknown",
"polarity":1,"value":null,"unit":null,"specimen":null,
"normalization":{"system":null,"code":null,"display":null,
"provenance":null,"confidence":null},"negation_scope_ok":true,
"value_scope_ok":true}]}
Return {"claims":[]} when the chunk does not explicitly entail a unary effect."""
PROMPT_SHA256 = hashlib.sha256(EXTRACTION_PROMPT.encode("utf-8")).hexdigest()
_TOKEN = re.compile(r"[a-z0-9]+")
_DIAGNOSIS_SECTION = re.compile(
    r"\b(diagnos(?:is|tic|tics)|clinical (?:features|presentation)|"
    r"signs? and symptoms?|evaluation|workup|differential)\b", re.I)
_WRITE_LOCK = threading.Lock()


def _terms(text: str) -> set[str]:
    return {term for term in _TOKEN.findall(text.casefold()) if len(term) > 2}


def _strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip())
        elif isinstance(value, Mapping):
            for key in ("display", "code", "name", "surface"):
                text = str(value.get(key) or "").strip()
                if text:
                    result.append(text)
    return result


def _query_lexicon(query: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    candidate = query.get("candidate") or {}
    finding = query.get("finding") or {}
    candidate_terms = [str(candidate.get("name") or "")]
    candidate_terms.extend(_strings(candidate.get("aliases")))
    candidate_terms.extend(_strings(candidate.get("concepts")))
    finding_terms = [str(finding.get("surface") or "")]
    finding_terms.extend(_strings(finding.get("aliases")))
    finding_terms.extend(_strings(finding.get("concepts")))
    return candidate_terms, finding_terms


def lexical_score(query: Mapping[str, Any], chunk: Mapping[str, Any]) -> float:
    """Score aliases/concepts and prioritize diagnostic source sections."""
    content = str(chunk.get("content") or chunk.get("text") or "")
    section = " ".join(str(chunk.get(key) or "") for key in ("section_path", "title"))
    metadata = " ".join(str(chunk.get(key) or "") for key in (
        "source", "article_id", "chunk_type"))
    haystack = f"{section} {metadata} {content}".casefold()
    candidate_terms, finding_terms = _query_lexicon(query)
    candidate_hits = sum(
        1 for term in candidate_terms if term and term.casefold() in haystack)
    finding_hits = sum(
        1 for term in finding_terms if term and term.casefold() in haystack)
    query_tokens = _terms(" ".join(candidate_terms + finding_terms))
    score = float(len(query_tokens & _terms(haystack)))
    score += 5.0 * candidate_hits + 3.0 * finding_hits
    if _DIAGNOSIS_SECTION.search(section):
        score += 8.0
    return score


class UnaryChunkRetriever:
    """Restricted inverted index followed by deterministic lexical reranking."""

    def __init__(
        self, chunks: list[dict[str, Any]], queries: Iterable[Mapping[str, Any]],
    ) -> None:
        self.chunks = chunks
        vocabulary: set[str] = set()
        for query in queries:
            candidate_terms, finding_terms = _query_lexicon(query)
            vocabulary.update(_terms(" ".join(candidate_terms + finding_terms)))
        self.postings: dict[str, list[int]] = defaultdict(list)
        for position, chunk in enumerate(chunks):
            content = " ".join(str(chunk.get(key) or "") for key in (
                "title", "section_path", "source", "article_id", "chunk_type",
                "content", "text"))
            # Avoid constructing a set containing every token in the 600+ MB
            # corpus. Only retain the small frozen query vocabulary.
            matched: set[str] = set()
            for token_match in _TOKEN.finditer(content.casefold()):
                term = token_match.group()
                if len(term) > 2 and term in vocabulary:
                    matched.add(term)
            for term in matched:
                self.postings[term].append(position)

    def retrieve(self, query: Mapping[str, Any], top_k: int) -> list[dict[str, Any]]:
        candidate_terms, finding_terms = _query_lexicon(query)
        positions: set[int] = set()
        candidate_tokens = _terms(" ".join(candidate_terms))
        seed_tokens = sorted(
            (term for term in candidate_tokens if self.postings.get(term)),
            key=lambda term: (len(self.postings[term]), term))
        if not seed_tokens:
            seed_tokens = sorted(
                (term for term in _terms(" ".join(finding_terms))
                 if self.postings.get(term)),
                key=lambda term: (len(self.postings[term]), term))
        # Rare candidate/alias/concept terms are a high-recall lexical first
        # stage; aliases and finding concepts then participate in full rerank.
        for term in seed_tokens[:3]:
            positions.update(self.postings.get(term, ()))
        ranked = [
            (lexical_score(query, self.chunks[position]),
             str(self.chunks[position].get("id") or ""), self.chunks[position])
            for position in positions
        ]
        ranked = [item for item in ranked if item[0] > 0]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:top_k]]


def _candidate(name: str) -> dict[str, Any]:
    return {"name": name, "id": None, "id_provenance": None, "l1_parent": None}


def _source_class(chunk: Mapping[str, Any]) -> str:
    corpus = str(chunk.get("corpus") or chunk.get("source_tier") or "").casefold()
    if "case" in corpus:
        return "case_report_prose"
    if str(chunk.get("chunk_type") or "").casefold() == "enumeration":
        return "cpg_enumeration"
    return "cpg_prose"


def _concepts(raw: Mapping[str, Any], query: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalization = raw.get("normalization") or {}
    seeds: list[Mapping[str, Any]] = []
    if isinstance(normalization, Mapping):
        seeds.append(normalization)
    seeds.extend(
        concept for concept in (query.get("finding") or {}).get("concepts", [])
        if isinstance(concept, Mapping))
    for concept in seeds:
        if all(concept.get(key) for key in ("system", "code", "display", "provenance")):
            return [{
                "system": str(concept["system"]),
                "code": str(concept["code"]),
                "display": str(concept["display"]),
                "provenance": str(concept["provenance"]),
                "confidence": float(concept.get("confidence", 1.0)),
            }]
    return []


def materialize_claim(
    raw: Mapping[str, Any],
    query: Mapping[str, Any],
    chunk: Mapping[str, Any],
    model: str,
) -> dict[str, Any]:
    effect = str(raw.get("effect") or "")
    if effect not in {"rule_in", "rule_out"}:
        raise ValueError("effect must be rule_in or rule_out")
    quote = str(raw.get("quote") or "")
    content = str(chunk.get("content") or chunk.get("text") or "")
    start, end = hydrate_quote(content, quote)
    source_class = _source_class(chunk)
    if source_class != "cpg_prose":
        raise ValueError("only CPG prose can emit unary candidate effects")
    finding_seed = query.get("finding") or {}
    concepts = _concepts(raw, query)
    identity = json.dumps(
        [query["query_id"], chunk.get("id"), raw],
        ensure_ascii=False, sort_keys=True, default=str)
    claim = {
        "schema_version": 2,
        "claim_id": "cceg_" + hashlib.sha256(
            identity.encode("utf-8")).hexdigest()[:16],
        "claim_type": "candidate_effect",
        "candidate_a": _candidate(str((query.get("candidate") or {}).get("name") or "")),
        "candidate_b": None,
        "finding": {
            "surface": str(finding_seed.get("surface") or ""),
            "event_type": str(raw.get("event_type") or finding_seed.get("event_type") or "other"),
            "concepts": concepts,
            "polarity": int(raw.get("polarity", finding_seed.get("polarity", 0))),
            "value_state": str(
                raw.get("value_state") or finding_seed.get("value_state") or "unknown"),
            "value": raw.get("value", finding_seed.get("value") or None),
            "unit": raw.get("unit"),
            "specimen": raw.get("specimen"),
            "temporal": {
                "onset": None, "duration": None, "relation": None, "anchor": None,
            },
            "context": {},
            "abstained": not concepts,
        },
        "relation": (
            "supports_candidate"
            if effect == "rule_in" else "argues_against_candidate"),
        "recommended_test": None,
        "strength": (
            "anecdotal" if source_class.startswith("case_report")
            else str(raw.get("strength") or "qualified")
        ),
        "source_class": source_class,
        "allowed_consumers": ["audit"],
        "comparator": {
            "required": False,
            "has_support_excerpt": True,
            "has_contrast_excerpt": False,
            "contrast_candidates": [],
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
            "pipeline": "extract_cceg_unary_claims_v2",
            "model": model,
            "prompt_sha256": PROMPT_SHA256,
            "confidence": float(raw.get("confidence", 0.0)),
            "entailment_status": "unvalidated",
            "normalization_abstained": not concepts,
            "normalization_reason": None if concepts else "no complete concept mapping",
        },
        "audit": {
            "enumeration_only": False,
            "pair_binding_ok": True,
            "negation_scope_ok": bool(raw.get("negation_scope_ok")),
            "value_scope_ok": bool(raw.get("value_scope_ok")),
        },
        "review": {
            "status": "unreviewed",
            "reviewer_ids": [],
            "adjudication": None,
            "mode": "human",
            "reviewer_runs": [],
        },
        "split": {
            "document_family": str(query.get("document_family") or "unary"),
            "document_split": document_split(chunk),
            "family_held_out": bool(query.get("family_held_out")),
            "pilot_scope": True,
        },
        "claim_status": "raw",
        "provenance_bundle": [],
        "derivation": None,
    }
    errors = validate_claim(claim)
    if errors:
        raise ValueError("invalid unary claim: " + "; ".join(errors))
    return claim


def _cache_key(query: Mapping[str, Any], chunk: Mapping[str, Any], model: str) -> str:
    payload = json.dumps(
        [PROMPT_SHA256, model, query, chunk], ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_one(
    llm: Any,
    query: Mapping[str, Any],
    chunk: Mapping[str, Any],
    model: str,
    cache_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    key = _cache_key(query, chunk, model)
    cache_path = cache_dir / f"{key}.json"
    if cache_path.exists():
        response = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        response = llm.call_module(
            "CCEGUnaryCandidateEffectExtractor",
            EXTRACTION_PROMPT,
            {
                "candidate": query["candidate"],
                "finding": query["finding"],
                "chunk": {
                    "id": chunk.get("id"),
                    "source": chunk.get("source"),
                    "article_id": chunk.get("article_id"),
                    "section_path": chunk.get("section_path") or chunk.get("title"),
                    "chunk_type": chunk.get("chunk_type"),
                    "content": chunk.get("content") or chunk.get("text"),
                },
            },
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            with cache_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
        except FileExistsError:
            response = json.loads(cache_path.read_text(encoding="utf-8"))
    raw_claims = response.get("claims", []) if isinstance(response, Mapping) else []
    if not isinstance(raw_claims, list):
        return [], ["extractor response claims must be an array"]
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    for index, raw in enumerate(raw_claims):
        if not isinstance(raw, Mapping):
            rejected.append(f"claim[{index}]: expected object")
            continue
        try:
            accepted.append(materialize_claim(raw, query, chunk, model))
        except (TypeError, ValueError) as exc:
            rejected.append(f"claim[{index}]: {exc}")
    return accepted, rejected


def _completed_queries(manifest: Path) -> set[str]:
    if not manifest.exists():
        return set()
    return {
        str(row.get("query_id")) for row in load_jsonl(manifest)
        if row.get("event") == "query_complete"
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", type=Path, default=DEFAULT_SCOPE)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_concurrency <= 100:
        parser.error("--max-concurrency must be between 1 and 100")
    manifest = args.manifest or args.out.with_suffix(args.out.suffix + ".manifest.jsonl")
    if not args.resume and (args.out.exists() or manifest.exists()):
        parser.error("refusing to overwrite unary output/manifest; use --resume")
    if args.resume and not (args.out.exists() and manifest.exists()):
        parser.error("--resume requires existing unary output and manifest")
    queries = load_jsonl(args.scope)
    chunks = load_jsonl(args.chunks)
    retriever = UnaryChunkRetriever(chunks, queries)
    completed = _completed_queries(manifest) if args.resume else set()
    grouped = {
        str(query["query_id"]): (
            query, retriever.retrieve(query, args.top_k)
        )
        for query in queries if query["query_id"] not in completed
    }
    retrieved = sum(bool(items[1]) for items in grouped.values())
    empty = sum(not items[1] for items in grouped.values())
    if args.dry_run:
        print(json.dumps({
            "queries": len(queries),
            "pending_queries": len(grouped),
            "retrieved": retrieved,
            "empty": empty,
            "pending_jobs": sum(len(items[1]) for items in grouped.values()),
            "prompt_sha256": PROMPT_SHA256,
            "would_write": str(args.out),
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
            "scope_sha256": _file_sha256(args.scope),
            "chunks_sha256": _file_sha256(args.chunks),
            "model": args.model,
            "prompt_sha256": PROMPT_SHA256,
            "top_k": args.top_k,
            "max_concurrency": args.max_concurrency,
            "retrieved": retrieved,
            "empty": empty,
        }, ensure_ascii=False) + "\n")

    def run_query(
        query_id: str, query: Mapping[str, Any], selected: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], list[str]]:
        accepted: list[dict[str, Any]] = []
        rejected: list[str] = []
        for chunk in selected:
            try:
                claims, failures = extract_one(
                    llm, query, chunk, args.model, args.cache_dir)
                accepted.extend(claims)
                rejected.extend(f"{chunk.get('id')}: {failure}" for failure in failures)
            except Exception as exc:
                rejected.append(f"{chunk.get('id')}: {exc}")
        return query_id, accepted, rejected

    accepted_count = 0
    rejected_count = 0
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_concurrency
    ) as pool:
        futures = [
            pool.submit(run_query, query_id, query, selected)
            for query_id, (query, selected) in grouped.items()
        ]
        for future in concurrent.futures.as_completed(futures):
            query_id, claims, failures = future.result()
            event = {
                "event": "query_complete",
                "query_id": query_id,
                "retrieved": len(grouped[query_id][1]),
                "empty": not grouped[query_id][1],
                "l0_rejected": len(failures),
                "accepted": len(claims),
                "errors": failures,
                "prompt_sha256": PROMPT_SHA256,
                "model": args.model,
            }
            with _WRITE_LOCK:
                with args.out.open("a", encoding="utf-8") as handle:
                    for claim in claims:
                        handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
                with manifest.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            accepted_count += len(claims)
            rejected_count += len(failures)
    print(json.dumps({
        "retrieved": retrieved,
        "empty": empty,
        "l0_rejected": rejected_count,
        "accepted": accepted_count,
        "output": str(args.out),
        "manifest": str(manifest),
        "prompt_sha256": PROMPT_SHA256,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
