#!/usr/bin/env python3
"""Independently validate CCEG quote hydration and clinical entailment."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402
from extract_cceg_claims import hydrate_quote, load_jsonl  # noqa: E402

VALIDATION_PROMPT = """You are an independent clinical entailment validator.
Judge only whether the exact source quote entails the structured claim for the
specified candidate(s) and finding value state. Do not use outside knowledge to
repair missing evidence. Explicit contradiction is conflict; missing,
enumerative, or merely related text is not_entailed. Check candidate binding,
negation scope, and value scope. For pair-scoped direction/common/test claims,
require both support and contrast excerpts. Unary phenotype_assertion claims
must bind the finding to candidate_a but do not require any contrast excerpt.
Return strict JSON:
{"verdict":"entailed|not_entailed|conflict|uncertain",
"pair_binding_ok":true,"negation_scope_ok":true,"value_scope_ok":true,
"has_support_excerpt":true,"has_contrast_excerpt":true,
"rationale":"brief quote-grounded reason"}."""
PROMPT_SHA256 = hashlib.sha256(VALIDATION_PROMPT.encode("utf-8")).hexdigest()


def hydrate_claim(
    claim: Mapping[str, Any], chunk: Mapping[str, Any],
) -> list[str]:
    """L0: verify source identity, exact substring, and exact stored span."""
    errors: list[str] = []
    provenance = claim.get("provenance") or {}
    if str(provenance.get("chunk_id")) != str(chunk.get("id")):
        errors.append("chunk_id does not match hydrated chunk")
        return errors
    content = str(chunk.get("content") or chunk.get("text") or "")
    quote = provenance.get("quote")
    try:
        expected = list(hydrate_quote(content, quote))
    except ValueError as exc:
        errors.append(str(exc))
        return errors
    if provenance.get("quote_span") != expected:
        errors.append(f"quote_span must be exact {expected}")
    elif content[expected[0]:expected[1]] != quote:
        errors.append("quote_span does not slice to quote")
    return errors


def deterministic_conflict(claim: Mapping[str, Any]) -> str | None:
    """Detect high-precision negation/value contradictions before any LLM call."""
    quote = str((claim.get("provenance") or {}).get("quote") or "").casefold()
    finding = claim.get("finding") or {}
    state = str(finding.get("value_state") or "")
    surface = str(finding.get("surface") or "").casefold()
    if state == "present" and any(
        marker in quote for marker in (f"absence of {surface}", f"absent {surface}", f"no {surface}")
    ):
        return "finding is marked present but quote explicitly negates it"
    opposite = {
        "elevated": ("low ", "lower ", "suppressed ", "decreased "),
        "suppressed": ("high ", "higher ", "elevated ", "increased "),
        "absent": ("present ", "positive ", "detected "),
        "normal": ("abnormal ", "elevated ", "suppressed "),
    }.get(state, ())
    if surface and any(marker + surface in quote for marker in opposite):
        return f"quote value contradicts value_state={state}"
    relation = str(claim.get("relation") or "")
    a = str((claim.get("candidate_a") or {}).get("name") or "").casefold()
    b = str((claim.get("candidate_b") or {}).get("name") or "").casefold()
    if relation == "supports_a" and a and f"against {a}" in quote:
        return "quote argues against candidate_a"
    if relation == "supports_b" and b and f"against {b}" in quote:
        return "quote argues against candidate_b"
    return None


def apply_verdict(
    claim: Mapping[str, Any], response: Mapping[str, Any], l0_errors: list[str],
) -> dict[str, Any]:
    """Return a new claim; automatic validation never fabricates human review."""
    updated = json.loads(json.dumps(claim))
    extraction = updated["extraction"]
    audit = updated["audit"]
    comparator = updated["comparator"]
    conflict = deterministic_conflict(updated)
    verdict = "conflict" if conflict else str(response.get("verdict") or "uncertain")
    checks = (
        response.get("pair_binding_ok") is True,
        response.get("negation_scope_ok") is True,
        response.get("value_scope_ok") is True,
    )
    pair_scoped = updated.get("claim_type") in {
        "direction", "common", "test_recommendation",
    }
    comparator_ok = not pair_scoped or (
        response.get("has_support_excerpt") is True
        and response.get("has_contrast_excerpt") is True
    )
    entailed = not l0_errors and not conflict and verdict == "entailed" and all(checks) and comparator_ok
    if entailed:
        extraction["entailment_status"] = "grounded"
        updated["claim_status"] = "pending_review"
        audit.update({
            "pair_binding_ok": True,
            "negation_scope_ok": True,
            "value_scope_ok": True,
        })
        if pair_scoped:
            comparator["has_support_excerpt"] = True
            comparator["has_contrast_excerpt"] = True
    elif l0_errors or verdict in {"not_entailed", "conflict"}:
        extraction["entailment_status"] = "conflict" if (
            conflict or verdict == "conflict") else "rejected"
        updated["claim_status"] = "rejected"
    else:
        extraction["entailment_status"] = "unvalidated"
        updated["claim_status"] = "pending_review"
    # Deliberately preserve unreviewed status and empty reviewer IDs.
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("--chunks", type=Path, default=ROOT / "data/cpg/processed/cpg_chunks.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument(
        "--cache-dir", type=Path,
        default=ROOT / "data/cceg/pilot/entailment_cache")
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.out.exists() or args.report.exists():
        parser.error("refusing to overwrite output or report")
    if not 1 <= args.max_concurrency <= 100:
        parser.error("--max-concurrency must be between 1 and 100")
    claims = load_jsonl(args.claims)
    chunks = {str(row.get("id")): row for row in load_jsonl(args.chunks)}
    if args.dry_run:
        print(json.dumps({
            "claims": len(claims), "chunks": len(chunks),
            "prompt_sha256": PROMPT_SHA256,
            "max_concurrency": args.max_concurrency,
        }, indent=2))
        return 0
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(
        model=args.model, call_timeout=180, max_retries=4,
        timeout_retry_cap=2, temperature=0.0)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    def validate_one(claim: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        chunk = chunks.get(str((claim.get("provenance") or {}).get("chunk_id")))
        l0_errors = ["chunk not found"] if chunk is None else hydrate_claim(claim, chunk)
        conflict = deterministic_conflict(claim)
        if l0_errors or conflict:
            response: dict[str, Any] = {
                "verdict": "conflict" if conflict else "not_entailed",
                "rationale": conflict or "; ".join(l0_errors),
            }
        else:
            payload = {
                    "candidate_a": claim.get("candidate_a"),
                    "candidate_b": claim.get("candidate_b"),
                    "finding": claim.get("finding"),
                    "relation": claim.get("relation"),
                    "claim_type": claim.get("claim_type"),
                    "quote": (claim.get("provenance") or {}).get("quote"),
            }
            identity = json.dumps(
                [PROMPT_SHA256, args.model, payload],
                ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            cache_path = args.cache_dir / (
                hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".json")
            if cache_path.exists():
                response = json.loads(cache_path.read_text(encoding="utf-8"))
            else:
                response = llm.call_module(
                    "CCEGIndependentEntailmentValidator",
                    VALIDATION_PROMPT,
                    payload,
                )
                try:
                    with cache_path.open("x", encoding="utf-8") as handle:
                        handle.write(
                            json.dumps(
                                response, ensure_ascii=False, sort_keys=True
                            ) + "\n")
                except FileExistsError:
                    response = json.loads(cache_path.read_text(encoding="utf-8"))
        updated = apply_verdict(claim, response, l0_errors)
        schema_errors = validate_claim(updated)
        if schema_errors:
            raise ValueError(
                f"{claim.get('claim_id')}: post-validation schema errors: {schema_errors}")
        report_row = {
            "claim_id": claim.get("claim_id"),
            "l0_errors": l0_errors,
            "deterministic_conflict": conflict,
            "verdict": response.get("verdict"),
            "rationale": response.get("rationale"),
            "entailment_status": updated["extraction"]["entailment_status"],
            "claim_status": updated["claim_status"],
        }
        return updated, report_row

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_concurrency
    ) as pool:
        validated = list(pool.map(validate_one, claims))
    results = [row[0] for row in validated]
    report_rows = [row[1] for row in validated]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        for claim in results:
            handle.write(json.dumps(claim, ensure_ascii=False) + "\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({
        "validator": "independent_entailment_v1",
        "model": args.model,
        "prompt_sha256": PROMPT_SHA256,
        "claims": len(results),
        "grounded_entailment": sum(
            row["entailment_status"] == "grounded" for row in report_rows),
        "rows": report_rows,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
