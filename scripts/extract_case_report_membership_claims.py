#!/usr/bin/env python3
"""Extract pilot-scoped, enumeration-only membership claims from case records."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agentclinic_tree_dx.knowledge.cceg_claim_index import normalize_term  # noqa: E402
from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402
from extract_cceg_claims import document_split, hydrate_quote, load_jsonl  # noqa: E402

PIPELINE = "extract_case_report_membership_v1"
PIPELINE_SHA256 = hashlib.sha256(PIPELINE.encode("utf-8")).hexdigest()


def extract_claims(
    chunks: list[dict[str, Any]],
    scope: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = {
        normalize_term(name): str(name)
        for query in scope
        for name in (query.get("candidate_a"), query.get("candidate_b"))
        if normalize_term(name)
    }
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        content = str(chunk.get("content") or chunk.get("text") or "")
        marker = "Differential diagnosis includes:"
        marker_start = content.find(marker)
        if marker_start < 0:
            continue
        quote = content[marker_start:].strip()
        start, end = hydrate_quote(content, quote)
        links = chunk.get("wiki_links") or []
        for link in links:
            normalized = normalize_term(link)
            if normalized not in candidates:
                continue
            candidate = candidates[normalized]
            identity = (str(chunk.get("id")), normalized)
            if identity in seen:
                continue
            seen.add(identity)
            claim = {
                "schema_version": 1,
                "claim_id": "cceg_" + hashlib.sha256(
                    json.dumps(identity).encode("utf-8")).hexdigest()[:16],
                "claim_type": "membership",
                "candidate_a": {
                    "name": candidate, "id": None, "id_provenance": None,
                    "l1_parent": None,
                },
                "candidate_b": None,
                "finding": {
                    "surface": str(
                        chunk.get("syndrome_anchor") or chunk.get("title")
                        or "case presentation"),
                    "event_type": "other",
                    "concepts": [],
                    "polarity": 1,
                    "value_state": "present",
                    "value": None,
                    "unit": None,
                    "specimen": None,
                    "temporal": {
                        "onset": None, "duration": None,
                        "relation": None, "anchor": None,
                    },
                    "context": {},
                    "abstained": True,
                },
                "relation": "member_of",
                "recommended_test": None,
                "strength": "anecdotal",
                "source_class": "case_report_list",
                "allowed_consumers": ["audit"],
                "comparator": {
                    "required": False,
                    "has_support_excerpt": False,
                    "has_contrast_excerpt": False,
                    "contrast_candidates": [],
                },
                "provenance": {
                    "source_id": str(
                        chunk.get("source_id") or chunk.get("id")),
                    "chunk_id": str(chunk.get("id")),
                    "article_id": str(
                        chunk.get("article_id") or chunk.get("source_id")
                        or chunk.get("id")),
                    "section": str(
                        chunk.get("section_path") or chunk.get("title")
                        or "Differential Diagnosis"),
                    "chunk_type": str(chunk.get("chunk_type") or "enumeration"),
                    "quote": quote,
                    "quote_span": [start, end],
                    "url": str(chunk.get("url") or "urn:cceg:case-record"),
                    "evidence_grade": None,
                },
                "extraction": {
                    "pipeline": PIPELINE,
                    "model": "deterministic-enumeration",
                    "prompt_sha256": PIPELINE_SHA256,
                    "confidence": 1.0,
                    "entailment_status": "unvalidated",
                    "normalization_abstained": True,
                    "normalization_reason": "candidate display-name match only",
                },
                "audit": {
                    "enumeration_only": True,
                    "pair_binding_ok": True,
                    "negation_scope_ok": True,
                    "value_scope_ok": True,
                },
                "review": {
                    "status": "unreviewed",
                    "reviewer_ids": [],
                    "adjudication": None,
                },
                "split": {
                    "document_family": str(
                        chunk.get("source") or "case_report"),
                    "document_split": document_split(chunk),
                    "family_held_out": False,
                    "pilot_scope": True,
                },
                "claim_status": "raw",
            }
            errors = validate_claim(claim)
            if errors:
                raise ValueError(
                    f"{claim['claim_id']}: schema errors: {errors}")
            claims.append(claim)
    return sorted(claims, key=lambda row: row["claim_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunks", type=Path,
        default=ROOT / "data/cpg/processed/case_report_chunks.jsonl")
    parser.add_argument(
        "--scope", type=Path,
        default=ROOT / "data/cceg/pilot/scope_queries.jsonl")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "data/cceg/pilot/case_membership.raw.jsonl")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("refusing to overwrite output")
    claims = extract_claims(load_jsonl(args.chunks), load_jsonl(args.scope))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        for claim in claims:
            handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
    print(json.dumps({
        "claims": len(claims),
        "pipeline_sha256": PIPELINE_SHA256,
        "output": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
