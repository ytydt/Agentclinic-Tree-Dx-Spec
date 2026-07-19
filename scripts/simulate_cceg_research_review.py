#!/usr/bin/env python3
"""Run an auditable synthetic CCEG review for research analysis only."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402

ARTIFACT_VERSION = 1
LABELS = frozenset({"accept", "reject", "uncertain"})
FORBIDDEN_OUTPUT_FIELDS = frozenset({
    "allowed_consumers",
    "claim_status",
    "clinical_status",
    "validated",
})

REVIEWER_A_PROMPT = """You are synthetic research reviewer A. Independently
assess whether the verbatim quote supports the proposed structured CCEG claim.
Use only the supplied claim and quote. Focus first on exact pair binding,
direction, value scope, and negation. This is research simulation, not clinical
validation and not human attestation. Return strict JSON:
{"label":"accept|reject|uncertain","reason":"brief evidence-bound reason"}."""

REVIEWER_B_PROMPT = """You are synthetic research reviewer B. Perform an
independent adversarial audit of a proposed CCEG claim using only its quoted
source. Look first for alternative readings, enumeration, missing comparator,
negation errors, or unsupported value specificity. This is research simulation,
not clinical validation and not human attestation. Return strict JSON:
{"label":"accept|reject|uncertain","reason":"brief evidence-bound reason"}."""

ADJUDICATOR_PROMPT = """You are a third synthetic research adjudicator. The two
independent research reviewers disagreed. Resolve only that disagreement from
the supplied claim, quote, and both reasons. Do not treat either reviewer as a
human or clinician. Return strict JSON:
{"label":"accept|reject|uncertain","reason":"brief evidence-bound resolution"}."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def object_sha256(value: Any) -> str:
    return _sha256_bytes(canonical_json(value).encode("utf-8"))


def _research_safe_copy(value: Any) -> Any:
    """Deep-copy input evidence while stripping clinical lifecycle keys."""
    if isinstance(value, Mapping):
        return {
            str(key): _research_safe_copy(nested)
            for key, nested in value.items()
            if str(key) not in FORBIDDEN_OUTPUT_FIELDS
        }
    if isinstance(value, list):
        return [_research_safe_copy(item) for item in value]
    if isinstance(value, tuple):
        return [_research_safe_copy(item) for item in value]
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    role: str
    model: str
    seed: int
    prompt: str

    @property
    def prompt_sha256(self) -> str:
        return _sha256_bytes(self.prompt.encode("utf-8"))

    def manifest_record(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "model": self.model,
            "seed": self.seed,
            "prompt_sha256": self.prompt_sha256,
        }


def default_specs(
    reviewer_a_model: str,
    reviewer_b_model: str,
    adjudicator_model: str,
    reviewer_a_seed: int,
    reviewer_b_seed: int,
    adjudicator_seed: int,
) -> tuple[AgentSpec, AgentSpec, AgentSpec]:
    return (
        AgentSpec(
            "synthetic-reviewer-a",
            "reviewer",
            reviewer_a_model,
            reviewer_a_seed,
            REVIEWER_A_PROMPT,
        ),
        AgentSpec(
            "synthetic-reviewer-b",
            "reviewer",
            reviewer_b_model,
            reviewer_b_seed,
            REVIEWER_B_PROMPT,
        ),
        AgentSpec(
            "synthetic-adjudicator",
            "adjudicator",
            adjudicator_model,
            adjudicator_seed,
            ADJUDICATOR_PROMPT,
        ),
    )


def _claim_projection(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only evidence fields; omit every clinical lifecycle field."""
    provenance = claim.get("provenance") or {}
    return {
        "source_claim_id": str(claim.get("claim_id") or ""),
        "claim_type": claim.get("claim_type"),
        "candidate_a": _research_safe_copy(claim.get("candidate_a")),
        "candidate_b": _research_safe_copy(claim.get("candidate_b")),
        "finding": _research_safe_copy(claim.get("finding")),
        "relation": claim.get("relation"),
        "recommended_test": claim.get("recommended_test"),
        "source_class": claim.get("source_class"),
        "evidence": {
            "source_id": provenance.get("source_id"),
            "chunk_id": provenance.get("chunk_id"),
            "article_id": provenance.get("article_id"),
            "url": provenance.get("url"),
            "quote": provenance.get("quote"),
            "quote_span": provenance.get("quote_span"),
        },
    }


def _validate_response(response: Mapping[str, Any], agent_id: str) -> dict[str, str]:
    label = str(response.get("label") or "").casefold()
    reason = str(response.get("reason") or "").strip()
    if label not in LABELS:
        raise ValueError(f"{agent_id}: invalid research label {label!r}")
    if not reason:
        raise ValueError(f"{agent_id}: non-empty reason required")
    return {"label": label, "reason": reason}


def _cache_key(spec: AgentSpec, payload: Mapping[str, Any]) -> str:
    return object_sha256({
        "artifact_version": ARTIFACT_VERSION,
        "agent": spec.manifest_record(),
        "payload": payload,
    })


def cached_call(
    spec: AgentSpec,
    payload: Mapping[str, Any],
    cache_dir: Path,
    call: Callable[[AgentSpec, Mapping[str, Any]], Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Call one synthetic agent with content-addressed, race-safe caching."""
    key = _cache_key(spec, payload)
    path = cache_dir / spec.agent_id / f"{key}.json"
    cache_hit = path.exists()
    if cache_hit:
        raw = json.loads(path.read_text(encoding="utf-8"))
        try:
            response = _validate_response(raw, spec.agent_id)
        except ValueError:
            path.unlink()
            cache_hit = False
    if not cache_hit:
        seeded_payload = {
            **payload,
            "research_reproducibility_seed": spec.seed,
        }
        last_error: ValueError | None = None
        for _attempt in range(3):
            raw = dict(call(spec, seeded_payload))
            try:
                response = _validate_response(raw, spec.agent_id)
                break
            except ValueError as exc:
                last_error = exc
        else:
            raise last_error or ValueError(
                f"{spec.agent_id}: no valid response")
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = canonical_json(response) + "\n"
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        except FileExistsError:
            response = _validate_response(
                json.loads(path.read_text(encoding="utf-8")), spec.agent_id)
    return response, {
        "agent_id": spec.agent_id,
        "cache_key": key,
        "cache_hit": cache_hit,
        "response_sha256": object_sha256(response),
    }


def _research_claim(
    source_claim: Mapping[str, Any],
    projection: Mapping[str, Any],
    decision: str,
    review_trace_sha256: str,
    reviews: list[Mapping[str, Any]],
    adjudication: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Materialize accepted research evidence as schema-v2, never clinical."""
    if (
        decision != "accept"
        or (source_claim.get("extraction") or {}).get("entailment_status")
        != "grounded"
    ):
        return None
    record = deepcopy(dict(source_claim))
    record["schema_version"] = 2
    record["claim_status"] = "research_validated"
    claim_type = str(record.get("claim_type") or "")
    record["allowed_consumers"] = (
        ["audit", "research_p3_soft", "research_p4_soft"]
        if claim_type == "candidate_effect"
        else ["audit", "research_p5_soft"]
    )
    reviewer_rows = [*reviews]
    if adjudication is not None:
        reviewer_rows.append(adjudication)
    record["review"] = {
        "status": "accepted",
        "reviewer_ids": [str(row["agent_id"]) for row in reviewer_rows],
        "adjudication": (
            f"{adjudication['agent_id']}: {adjudication['reason']}"
            if adjudication is not None else None
        ),
        "mode": "synthetic_dual_llm",
        "reviewer_runs": [
            {
                "reviewer_id": str(row["agent_id"]),
                "model": str(row["model"]),
                "prompt": str(row["prompt"]),
                "prompt_sha256": str(row["prompt_sha256"]),
                "seed": int(row["seed"]),
            }
            for row in reviewer_rows
        ],
    }
    record.setdefault("provenance_bundle", [])
    record.setdefault("derivation", None)
    record["research_review"] = {
        "source_claim_id": str(projection["source_claim_id"]),
        "review_trace_sha256": review_trace_sha256,
        "research_only": True,
        "clinical_use_prohibited": True,
    }
    # The frozen schema is intentionally closed; audit lineage is already
    # preserved in the packet/manifest, not injected as an unknown claim field.
    record.pop("research_review")
    errors = validate_claim(record)
    if errors:
        raise ValueError(
            f"{projection['source_claim_id']}: research promotion failed: {errors}")
    return record


def simulate_review(
    claims: list[Mapping[str, Any]],
    specs: tuple[AgentSpec, AgentSpec, AgentSpec],
    cache_dir: Path,
    max_concurrency: int,
    call: Callable[[AgentSpec, Mapping[str, Any]], Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Review claims concurrently while preserving deterministic output order."""
    reviewer_a, reviewer_b, adjudicator = specs
    if reviewer_a.prompt_sha256 == reviewer_b.prompt_sha256:
        raise ValueError("reviewer prompts must be independent")
    if reviewer_a.seed == reviewer_b.seed:
        raise ValueError("reviewer seeds must be independent")
    if reviewer_a.model == reviewer_b.model:
        raise ValueError("reviewer models must be independent")
    input_claims = len(claims)
    claims = [
        claim for claim in claims
        if (claim.get("extraction") or {}).get("entailment_status") == "grounded"
        and claim.get("claim_status") in {"pending_review", "grounded"}
    ]
    projections = [_claim_projection(claim) for claim in claims]
    source_ids = [str(row["source_claim_id"]) for row in projections]
    if any(not source_id for source_id in source_ids):
        raise ValueError("every source claim requires claim_id")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("source claim_id values must be unique")
    source_by_id = {
        str(claim["claim_id"]): claim for claim in claims
    }

    def review_one(projection: Mapping[str, Any]) -> tuple[
        dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        payload = {"claim": projection}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(cached_call, reviewer_a, payload, cache_dir, call)
            future_b = pool.submit(cached_call, reviewer_b, payload, cache_dir, call)
            result_a, cache_a = future_a.result()
            result_b, cache_b = future_b.result()
        reviews = [
            {
                **reviewer_a.manifest_record(),
                "prompt": reviewer_a.prompt,
                **result_a,
            },
            {
                **reviewer_b.manifest_record(),
                "prompt": reviewer_b.prompt,
                **result_b,
            },
        ]
        cache_events = [cache_a, cache_b]
        adjudication = None
        if result_a["label"] != result_b["label"]:
            adjudication_payload = {
                "claim": projection,
                "reviewer_outputs": reviews,
            }
            resolved, cache_adjudicator = cached_call(
                adjudicator,
                adjudication_payload,
                cache_dir,
                call,
            )
            adjudication = {
                **adjudicator.manifest_record(),
                "prompt": adjudicator.prompt,
                **resolved,
            }
            cache_events.append(cache_adjudicator)
            decision = resolved["label"]
        else:
            decision = result_a["label"]
        trace = {
            "source_claim_id": projection["source_claim_id"],
            "reviews": reviews,
            "adjudication": adjudication,
            "research_decision": decision,
        }
        trace_hash = object_sha256(trace)
        item = {
            "research_review_id": "research_review_" + object_sha256(
                projection
            )[:16],
            "source_claim_id": projection["source_claim_id"],
            "claim": projection,
            "reviews": reviews,
            "adjudication": adjudication,
            "research_decision": decision,
            "review_trace_sha256": trace_hash,
        }
        source_claim = source_by_id[str(projection["source_claim_id"])]
        return item, _research_claim(
            source_claim, projection, decision, trace_hash, reviews, adjudication
        ), {
            "source_claim_id": projection["source_claim_id"],
            "calls": cache_events,
        }

    workers = min(max_concurrency, max(1, len(projections)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        reviewed = list(pool.map(review_one, projections))
    reviewed.sort(key=lambda row: str(row[0]["source_claim_id"]))
    items = [row[0] for row in reviewed]
    research_claims = [row[1] for row in reviewed if row[1] is not None]
    cache_audit = [row[2] for row in reviewed]
    packet = {
        "artifact_kind": "cceg_research_review_packet",
        "artifact_version": ARTIFACT_VERSION,
        "research_only": True,
        "clinical_use_prohibited": True,
        "notice": (
            "Synthetic model review only; not human attestation and not eligible "
            "for clinical scoring, validation, or serving."
        ),
        "agents": [spec.manifest_record() for spec in specs],
        "items": items,
    }
    counts = {label: 0 for label in sorted(LABELS)}
    for item in items:
        counts[item["research_decision"]] += 1
    report = {
        "artifact_kind": "cceg_research_review_report",
        "artifact_version": ARTIFACT_VERSION,
        "research_only": True,
        "clinical_use_prohibited": True,
        "reviewed_claims": len(items),
        "input_claims": input_claims,
        "excluded_by_l1": input_claims - len(items),
        "input_claims": input_claims,
        "excluded_by_l1": input_claims - len(items),
        "disagreements": sum(item["adjudication"] is not None for item in items),
        "research_decision_counts": counts,
        "packet_sha256": object_sha256(packet),
    }
    return packet, report, research_claims, cache_audit


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{number}: expected object")
        rows.append(row)
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        stream.write("\n")


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(canonical_json(row))
            stream.write("\n")


def _llm_caller() -> Callable[[AgentSpec, Mapping[str, Any]], Mapping[str, Any]]:
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    clients: dict[str, RobustLLMClient] = {}

    def call(spec: AgentSpec, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        client = clients.get(spec.agent_id)
        if client is None:
            client = RobustLLMClient(
                model=spec.model,
                call_timeout=180,
                max_retries=4,
                timeout_retry_cap=2,
                temperature=0.0,
            )
            clients[spec.agent_id] = client
        seeded_prompt = (
            f"{spec.prompt}\nReproducibility seed: {spec.seed}. "
            "Use this seed only to fix your rubric tie-breaking order."
        )
        return client.call_module(spec.agent_id, seeded_prompt, payload)

    return call


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("--packet-out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--claims-out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--reviewer-a-model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--reviewer-b-model", default="qwen/qwen3-32b")
    parser.add_argument("--adjudicator-model", default="google/gemini-2.5-pro")
    parser.add_argument("--reviewer-a-seed", type=int, default=17011)
    parser.add_argument("--reviewer-b-seed", type=int, default=29021)
    parser.add_argument("--adjudicator-seed", type=int, default=43003)
    parser.add_argument("--max-concurrency", type=int, default=8)
    parser.add_argument(
        "--claim-types",
        help="comma-separated claim types admitted to this review run",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    outputs = [
        args.packet_out,
        args.report_out,
        args.claims_out,
        args.manifest_out,
    ]
    if not 1 <= args.max_concurrency <= 100:
        parser.error("--max-concurrency must be between 1 and 100")
    if any(path.exists() for path in outputs):
        parser.error("refusing to overwrite research artifacts")
    specs = default_specs(
        args.reviewer_a_model,
        args.reviewer_b_model,
        args.adjudicator_model,
        args.reviewer_a_seed,
        args.reviewer_b_seed,
        args.adjudicator_seed,
    )
    claims = _load_jsonl(args.claims)
    claim_types = {
        value.strip() for value in (args.claim_types or "").split(",")
        if value.strip()
    }
    if claim_types:
        claims = [
            claim for claim in claims
            if str(claim.get("claim_type") or "") in claim_types
        ]
    if args.dry_run:
        print(json.dumps({
            "artifact_kind": "cceg_research_review_dry_run",
            "research_only": True,
            "claims": len(claims),
            "agents": [spec.manifest_record() for spec in specs],
            "max_concurrency": args.max_concurrency,
        }, indent=2))
        return 0
    packet, report, research_claims, cache_audit = simulate_review(
        claims,
        specs,
        args.cache_dir,
        args.max_concurrency,
        _llm_caller(),
    )
    _write_json(args.packet_out, packet)
    _write_json(args.report_out, report)
    _write_jsonl(args.claims_out, research_claims)
    manifest = {
        "artifact_kind": "cceg_research_review_manifest",
        "artifact_version": ARTIFACT_VERSION,
        "research_only": True,
        "clinical_use_prohibited": True,
        "input": {
            "path": str(args.claims),
            "sha256": file_sha256(args.claims),
            "rows": len(claims),
        },
        "agents": [spec.manifest_record() for spec in specs],
        "max_concurrency": args.max_concurrency,
        "claim_types": sorted(claim_types),
        "cache_dir": str(args.cache_dir),
        "cache_audit": cache_audit,
        "outputs": [
            {
                "artifact_kind": kind,
                "path": str(path),
                "sha256": file_sha256(path),
            }
            for kind, path in (
                ("cceg_research_review_packet", args.packet_out),
                ("cceg_research_review_report", args.report_out),
                ("cceg_research_claims", args.claims_out),
            )
        ],
        "environment": {
            "python": sys.version.split()[0],
            "pid": os.getpid(),
        },
    }
    _write_json(args.manifest_out, manifest)
    print(json.dumps({
        "research_only": True,
        "reviewed_claims": len(research_claims),
        "disagreements": report["disagreements"],
        "manifest": str(args.manifest_out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
