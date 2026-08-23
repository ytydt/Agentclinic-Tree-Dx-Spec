#!/usr/bin/env python3
"""Validate manual B/C reviews and write frozen-identity cache records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from analysis.mechanism_v2.ceiling_pool_census import (  # noqa: E402
    CLINICAL_PROMPT,
    _clinical_payload,
    _review_cache_key,
    _validate_relation_response,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402

CENSUS = ROOT / "analysis/mechanism_v2/results/CEILING_POOL_CENSUS"
MANUAL = CENSUS / "manual_resume"
CARDS = CENSUS / "design/blinded_relation_cards.jsonl"
FROZEN_MODELS = {
    "reviewer_b": "anthropic/claude-sonnet-4.6",
    "reviewer_c": "openai/gpt-5.6-sol",
}
EXECUTORS = {
    "reviewer_b": "cursor-grok-4.6-manual-reviewer-b",
    "reviewer_c": "gpt-5.6-sol-subagent-manual-reviewer-c",
}


def load_reviews(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return rows
    if text.startswith("["):
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError(f"{path} JSON is not a list")
        iterable = items
    else:
        iterable = [json.loads(line) for line in text.splitlines() if line.strip()]
    for item in iterable:
        if not isinstance(item, dict):
            continue
        card_id = str(item.get("blind_card_id") or "")
        relations = item.get("candidate_relations")
        if relations is None and isinstance(item.get("review"), dict):
            relations = item["review"].get("candidate_relations")
            flags = item["review"].get("case_quality_flags")
        else:
            flags = item.get("case_quality_flags")
        rows[card_id] = {
            "blind_card_id": card_id,
            "candidate_relations": relations,
            "case_quality_flags": [] if flags is None else flags,
        }
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer", required=True, choices=sorted(FROZEN_MODELS))
    parser.add_argument("--inputs", nargs="+", required=True)
    args = parser.parse_args()
    reviewer_id = args.reviewer
    model = FROZEN_MODELS[reviewer_id]
    cards = {str(row["blind_card_id"]): row for row in read_jsonl(CARDS)}
    merged: dict[str, dict] = {}
    for raw in args.inputs:
        merged.update(load_reviews(Path(raw)))

    directory = CENSUS / "reviewers" / reviewer_id
    cache_dir = directory / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    ledger: list[dict] = []
    ok = 0
    bad: list[str] = []
    for card_id, review in sorted(merged.items()):
        card = cards.get(card_id)
        if card is None:
            bad.append(f"{card_id}: unknown card")
            continue
        payload = _clinical_payload(card)
        allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
        response = {
            "candidate_relations": review.get("candidate_relations") or [],
            "case_quality_flags": review.get("case_quality_flags") or [],
        }
        error = _validate_relation_response(response, allowed)
        cache_key, prompt_sha, payload_sha = _review_cache_key(reviewer_id, model, payload)
        if error:
            bad.append(f"{card_id}: {error}")
            continue
        record = {
            "schema": "mechanism_v2_online_call_v1",
            "model": model,
            "module": f"CeilingPoolCensus_{reviewer_id}",
            "prompt_sha256": prompt_sha,
            "payload_sha256": payload_sha,
            "temperature": 0.0,
            "success": True,
            "error": "",
            "response": response,
            "manual_resume": {
                "bypassed_openrouter": True,
                "executor": EXECUTORS[reviewer_id],
                "frozen_model_identity_preserved": True,
            },
        }
        atomic_json(cache_dir / f"{cache_key}.json", record)
        ledger.append(
            {
                "blind_card_id": card_id,
                "cache_key": cache_key,
                "reviewer_id": reviewer_id,
                "model": model,
                "executor": EXECUTORS[reviewer_id],
            }
        )
        ok += 1
    write_jsonl(MANUAL / f"{reviewer_id}_accepted.jsonl", ledger)
    (MANUAL / f"{reviewer_id}_rejected.txt").write_text("\n".join(bad) + ("\n" if bad else ""), encoding="utf-8")
    print(f"{reviewer_id}: accepted={ok} rejected={len(bad)} input_rows={len(merged)}")
    return 0 if not bad else 2


if __name__ == "__main__":
    raise SystemExit(main())
