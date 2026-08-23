#!/usr/bin/env python3
"""Protocol-conformant online resume of C0 reviewer A's never-called cards.

The 2026-08-15 credit exhaustion left reviewer A with 364 failed cards: 7 held a
validator-invalid cache record and 357 were finalized in ``--cache-only`` mode
without any provider call, so no cache record exists for them.

``run-reviewer`` refuses to act once a reviewer summary exists, and
``recover-reviewer`` requires every failed card to carry active or quarantined
cache provenance, which the 357 never-called cards cannot. This script closes
only that gap: it calls the never-called cards through the official
``OnlineJSONCaller`` under the frozen model, module, prompt, payload and
temperature, so each new record lands on the same immutable cache identity the
original run would have produced.

It deliberately does not touch the 7 validator-invalid cards; those remain the
responsibility of ``recover-reviewer``, which quarantines their raw caches
first. It never deletes, imputes or rewrites an existing cache record.
"""
from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.ceiling_pool_census import (  # noqa: E402
    CLINICAL_PROMPT,
    SCHEMA_VERSION,
    _clinical_payload,
    _review_cache_key,
    _validate_relation_response,
)
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

CENSUS = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
REVIEWER_ID = "reviewer_a"
FROZEN_MODEL = "google/gemini-2.5-flash"
MAX_WORKERS = 24


def _frozen_identity(card: dict) -> tuple[dict, set[str], str, str, str]:
    payload = _clinical_payload(card)
    allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
    cache_key, prompt_sha, payload_sha = _review_cache_key(
        REVIEWER_ID, FROZEN_MODEL, payload
    )
    return payload, allowed, cache_key, prompt_sha, payload_sha


def resume(workers: int = MAX_WORKERS) -> dict:
    if not 1 <= workers <= 50:
        raise ValueError("workers must stay within the frozen 1..50 band")
    directory = CENSUS / "reviewers" / REVIEWER_ID
    summary = json.loads((directory / "review_summary.json").read_text(encoding="utf-8"))
    if str(summary.get("model")) != FROZEN_MODEL:
        raise RuntimeError(f"reviewer model drift: {summary.get('model')}")
    cards_path = CENSUS / "design/blinded_relation_cards.jsonl"
    if str(summary.get("cards_sha256")) != file_sha256(cards_path):
        raise RuntimeError("card freeze drift before resume")

    cards = read_jsonl(cards_path)
    prior = {
        str(row["blind_card_id"]): dict(row)
        for row in read_jsonl(directory / "reviews.jsonl")
    }
    cache_dir = directory / "cache"

    pending: list[dict] = []
    for card in cards:
        card_id = str(card["blind_card_id"])
        row = prior[card_id]
        if bool(row.get("success")):
            continue
        _, _, cache_key, _, _ = _frozen_identity(card)
        if (cache_dir / f"{cache_key}.json").is_file():
            # Validator-invalid card: owned by recover-reviewer, not this script.
            continue
        pending.append(card)

    caller = OnlineJSONCaller(
        out_dir=directory,
        model=FROZEN_MODEL,
        telemetry_path=directory / "telemetry.jsonl",
        temperature=0.0,
        call_timeout=240,
        max_retries=3,
    )

    def one(card: dict) -> dict:
        card_id = str(card["blind_card_id"])
        payload, allowed, cache_key, prompt_sha, payload_sha = _frozen_identity(card)
        try:
            outcome = caller.call(
                module=f"CeilingPoolCensus_{REVIEWER_ID}",
                prompt=CLINICAL_PROMPT,
                payload=payload,
                validator=lambda response: _validate_relation_response(response, allowed),
            )
            return {
                "blind_card_id": card_id,
                "success": bool(outcome.success),
                "error": str(outcome.error or ""),
                "cache_key": cache_key,
            }
        except Exception as exc:  # provider/transport failure stays a failure
            return {
                "blind_card_id": card_id,
                "success": False,
                "error": f"{type(exc).__name__}: {exc}",
                "cache_key": cache_key,
                "prompt_sha256": prompt_sha,
                "payload_sha256": payload_sha,
            }

    results: list[dict] = []
    if pending:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(one, card) for card in pending]
            for future in as_completed(futures):
                results.append(future.result())
    results.sort(key=lambda row: row["blind_card_id"])

    manifest = {
        "schema": f"{SCHEMA_VERSION}-reviewer-online-resume-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": REVIEWER_ID,
        "model": FROZEN_MODEL,
        "gateway": "same repository RobustLLMClient path as the original run",
        "scope": "never-called cards only; validator-invalid caches left to recover-reviewer",
        "n_never_called_before": len(pending),
        "n_now_valid": sum(bool(row["success"]) for row in results),
        "n_still_failed": sum(not bool(row["success"]) for row in results),
        "policy": "no deletion, imputation, model substitution or threshold change",
    }
    atomic_json(directory / "online_resume_manifest.json", manifest)
    write_jsonl(directory / "online_resume_results.jsonl", results)
    return manifest


def rebuild() -> dict:
    """Rebuild reviews.jsonl/summary from disk cache without any provider call."""
    directory = CENSUS / "reviewers" / REVIEWER_ID
    prior_summary = json.loads(
        (directory / "review_summary.json").read_text(encoding="utf-8")
    )
    cards_path = CENSUS / "design/blinded_relation_cards.jsonl"
    cards = read_jsonl(cards_path)
    cache_dir = directory / "cache"
    rows: list[dict] = []
    for card in cards:
        card_id = str(card["blind_card_id"])
        payload, allowed, cache_key, prompt_sha, payload_sha = _frozen_identity(card)
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.is_file():
            record = json.loads(cache_path.read_text(encoding="utf-8"))
            response = dict(record.get("response") or {})
            error = _validate_relation_response(response, allowed) or ""
            rows.append(
                {
                    "blind_card_id": card_id,
                    "reviewer_id": REVIEWER_ID,
                    "model": FROZEN_MODEL,
                    "success": not bool(error),
                    "error": error,
                    "review": response,
                    "cache_hit": True,
                    "cache_key": cache_key,
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                }
            )
        else:
            rows.append(
                {
                    "blind_card_id": card_id,
                    "reviewer_id": REVIEWER_ID,
                    "model": FROZEN_MODEL,
                    "success": False,
                    "error": (
                        "FileNotFoundError: required immutable cache record missing: "
                        f"{cache_key}"
                    ),
                    "review": {},
                    "cache_hit": False,
                    "cache_key": "",
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                }
            )
    rows.sort(key=lambda row: row["blind_card_id"])
    reviews_path = directory / "reviews.jsonl"
    write_jsonl(reviews_path, rows)
    summary = {
        **prior_summary,
        "schema_version": f"{SCHEMA_VERSION}-reviewer-v1",
        "rebuilt_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": REVIEWER_ID,
        "model": FROZEN_MODEL,
        "cards_path": "design/blinded_relation_cards.jsonl",
        "cards_sha256": file_sha256(cards_path),
        "n_cards": len(rows),
        "n_success": sum(bool(row["success"]) for row in rows),
        "n_failure": sum(not bool(row["success"]) for row in rows),
        "artifact_sha256": {"reviews.jsonl": file_sha256(reviews_path)},
        "online_resume": True,
    }
    atomic_json(directory / "review_summary.json", summary)
    return summary


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "resume"
    if command == "resume":
        print(json.dumps(resume(), ensure_ascii=False, indent=2, sort_keys=True))
    elif command == "rebuild":
        value = rebuild()
        print(
            json.dumps(
                {k: value[k] for k in ("reviewer_id", "model", "n_cards", "n_success", "n_failure")},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        raise SystemExit(f"unknown command: {command}")
