#!/usr/bin/env python3
"""Rebuild reviewer reviews.jsonl/summary from disk cache without API calls."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.ceiling_pool_census import (  # noqa: E402
    SCHEMA_VERSION,
    _clinical_payload,
    _review_cache_key,
    _validate_relation_response,
)
from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

CENSUS = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
FROZEN_MODELS = {
    "reviewer_b": "anthropic/claude-sonnet-4.6",
    "reviewer_c": "openai/gpt-5.6-sol",
}


def rebuild(reviewer_id: str) -> dict:
    model = FROZEN_MODELS[reviewer_id]
    cards = read_jsonl(CENSUS / "design/blinded_relation_cards.jsonl")
    directory = CENSUS / "reviewers" / reviewer_id
    cache_dir = directory / "cache"
    results = []
    for card in cards:
        payload = _clinical_payload(card)
        allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
        cache_key, prompt_sha, payload_sha = _review_cache_key(reviewer_id, model, payload)
        cache_path = cache_dir / f"{cache_key}.json"
        if cache_path.is_file():
            record = json.loads(cache_path.read_text(encoding="utf-8"))
            response = dict(record.get("response") or {})
            error = _validate_relation_response(response, allowed) or ""
            success = not bool(error)
            results.append(
                {
                    "blind_card_id": str(card["blind_card_id"]),
                    "reviewer_id": reviewer_id,
                    "model": model,
                    "success": success,
                    "error": error,
                    "review": response,
                    "cache_hit": True,
                    "cache_key": cache_key,
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                }
            )
        else:
            results.append(
                {
                    "blind_card_id": str(card["blind_card_id"]),
                    "reviewer_id": reviewer_id,
                    "model": model,
                    "success": False,
                    "error": f"FileNotFoundError: required immutable cache record missing: {cache_key}",
                    "review": {},
                    "cache_hit": False,
                    "cache_key": "",
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                }
            )
    results.sort(key=lambda row: row["blind_card_id"])
    reviews_path = directory / "reviews.jsonl"
    write_jsonl(reviews_path, results)
    summary = {
        "schema_version": f"{SCHEMA_VERSION}-reviewer-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer_id": reviewer_id,
        "model": model,
        "cards_path": "design/blinded_relation_cards.jsonl",
        "cards_sha256": file_sha256(CENSUS / "design/blinded_relation_cards.jsonl"),
        "n_cards": len(results),
        "n_success": sum(bool(row["success"]) for row in results),
        "n_failure": sum(not bool(row["success"]) for row in results),
        "artifact_sha256": {"reviews.jsonl": file_sha256(reviews_path)},
        "manual_resume": True,
    }
    atomic_json(directory / "review_summary.json", summary)
    return summary


if __name__ == "__main__":
    reviewers = sys.argv[1:] or ["reviewer_b", "reviewer_c"]
    for reviewer_id in reviewers:
        summary = rebuild(reviewer_id)
        print(json.dumps({k: summary[k] for k in ("reviewer_id", "n_cards", "n_success", "n_failure")}, ensure_ascii=False))
