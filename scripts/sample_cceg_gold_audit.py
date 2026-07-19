#!/usr/bin/env python3
"""Create a deterministic, unsigned CCEG dual-review audit packet."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def deterministic_sample(claims: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Include every direction/common claim, then sample remaining strata."""
    mandatory_types = {"direction", "common"}
    mandatory = sorted(
        (claim for claim in claims if claim.get("claim_type") in mandatory_types),
        key=lambda row: hashlib.sha256(
            str(row.get("claim_id")).encode("utf-8")).hexdigest(),
    )
    selected = list(mandatory)
    selected_ids = {str(row.get("claim_id")) for row in selected}
    strata: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for claim in claims:
        if str(claim.get("claim_id")) in selected_ids:
            continue
        key = (
            str(claim.get("claim_type")),
            str((claim.get("split") or {}).get("document_family")),
        )
        strata.setdefault(key, []).append(claim)
    for rows in strata.values():
        rows.sort(key=lambda row: hashlib.sha256(
            str(row.get("claim_id")).encode("utf-8")).hexdigest())
    keys = sorted(strata)
    target = min(max(size, len(mandatory)), len(claims))
    while len(selected) < target:
        advanced = False
        for key in keys:
            if strata[key] and len(selected) < size:
                selected.append(strata[key].pop(0))
                advanced = True
        if not advanced:
            break
    return selected


def make_packet(claims: list[dict[str, Any]], size: int) -> dict[str, Any]:
    selected = deterministic_sample(claims, size)
    items = []
    for claim in selected:
        items.append({
            "audit_id": "audit_" + hashlib.sha256(
                str(claim["claim_id"]).encode("utf-8")).hexdigest()[:12],
            "claim_id": claim["claim_id"],
            "claim": {
                "claim_type": claim.get("claim_type"),
                "candidate_a": claim.get("candidate_a"),
                "candidate_b": claim.get("candidate_b"),
                "finding": claim.get("finding"),
                "relation": claim.get("relation"),
                "quote": (claim.get("provenance") or {}).get("quote"),
                "source_class": claim.get("source_class"),
            },
            "automated_label": (
                "accept"
                if (claim.get("extraction") or {}).get("entailment_status") == "grounded"
                else "reject"
            ),
            "reviews": [
                {"reviewer_id": "", "label": "", "reason": ""},
                {"reviewer_id": "", "label": "", "reason": ""},
            ],
            "adjudication": {"label": "", "adjudicator_id": "", "reason": ""},
        })
    return {
        "packet_version": 1,
        "status": "UNSIGNED",
        "instructions": (
            "Two independent clinical reviewers must label every item accept/reject. "
            "They must not copy IDs or timestamps from examples. Disagreements require "
            "a separately identified adjudicator."
        ),
        "thresholds": {"minimum_kappa": 0.8, "minimum_precision": 0.9},
        "coverage_policy": {
            "mandatory_claim_types": ["direction", "common"],
            "mandatory_claims": sum(
                claim.get("claim_type") in {"direction", "common"}
                for claim in claims
            ),
            "all_mandatory_included": all(
                claim.get("claim_type") not in {"direction", "common"}
                or any(
                    item["claim_id"] == claim.get("claim_id")
                    for item in items
                )
                for claim in claims
            ),
        },
        "batch_signoffs": [
            {"reviewer_id": "", "signed_at": "", "attestation": ""},
            {"reviewer_id": "", "signed_at": "", "attestation": ""},
        ],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=100)
    args = parser.parse_args()
    if args.size < 1:
        parser.error("--size must be positive")
    if args.out.exists():
        parser.error("refusing to overwrite audit packet")
    packet = make_packet(load_jsonl(args.claims), args.size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "items": len(packet["items"]),
        "status": "UNSIGNED",
        "output": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
