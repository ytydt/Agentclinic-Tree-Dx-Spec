#!/usr/bin/env python3
"""Audit CCEG JSON/JSONL claims against the frozen v1 contract."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_schema import (  # noqa: E402
    SCHEMA_VERSION,
    claim_json_schema,
    validate_claim,
)


def load_claims(path: Path) -> list[dict]:
    """Load either a JSON array/object or newline-delimited JSON claims."""
    if path.suffix.lower() == ".jsonl":
        claims = []
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                claim = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(claim, dict):
                raise ValueError(
                    f"{path}:{line_number}: claim must be an object")
            claims.append(claim)
        return claims
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        claims = payload
    elif isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        claims = payload["claims"]
    elif isinstance(payload, dict):
        claims = [payload]
    else:
        raise ValueError(f"{path}: expected claim object, list, or claims array")
    if any(not isinstance(claim, dict) for claim in claims):
        raise ValueError(f"{path}: every claim must be an object")
    return claims


def audit(claims: Iterable[dict]) -> dict:
    """Return a deterministic batch-level quality report."""
    rows = []
    claim_types: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    for index, claim in enumerate(claims):
        claim_id = claim.get("claim_id", f"<row:{index}>")
        errors = validate_claim(claim)
        if claim_id in seen_ids:
            errors.append("claim_id: duplicate within batch")
            duplicate_ids.append(str(claim_id))
        seen_ids.add(str(claim_id))
        claim_types[str(claim.get("claim_type", "<missing>"))] += 1
        sources[str(claim.get("source_class", "<missing>"))] += 1
        statuses[str(claim.get("claim_status", "<missing>"))] += 1
        rows.append({
            "index": index,
            "claim_id": claim_id,
            "errors": errors,
            "valid": not errors,
        })
    invalid = [row for row in rows if not row["valid"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "claims": len(rows),
        "valid_claims": len(rows) - len(invalid),
        "invalid_claims": len(invalid),
        "claim_types": dict(claim_types),
        "source_classes": dict(sources),
        "claim_statuses": dict(statuses),
        "duplicate_ids": sorted(set(duplicate_ids)),
        "errors": invalid,
        "publishable": bool(rows) and not invalid,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claims", nargs="?", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--schema-out", type=Path,
        help="write the canonical v1 JSON Schema; refuses overwrite")
    args = parser.parse_args()
    if args.schema_out:
        if args.schema_out.exists():
            parser.error(f"refusing to overwrite schema: {args.schema_out}")
        args.schema_out.parent.mkdir(parents=True, exist_ok=True)
        args.schema_out.write_text(json.dumps(
            claim_json_schema(), ensure_ascii=False, indent=2) + "\n")
        print(f"created CCEG v{SCHEMA_VERSION} schema: {args.schema_out}")
        if args.claims is None:
            return 0
    if args.claims is None:
        parser.error("claims path is required unless --schema-out is supplied")
    report = audit(load_claims(args.claims))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n")
    print(text)
    return 1 if report["invalid_claims"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
