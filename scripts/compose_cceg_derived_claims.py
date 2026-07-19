#!/usr/bin/env python3
"""Materialize all allowlisted same-article CCEG derived contrasts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_claim_index import (  # noqa: E402
    CCEGClaimIndex,
    candidate_key,
)
from agentclinic_tree_dx.knowledge.cceg_compose import CCEGComposer  # noqa: E402
from agentclinic_tree_dx.knowledge.cceg_schema import validate_claim  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("claims", []) if isinstance(payload, dict) else payload


def compose_all(claims: list[dict[str, Any]]) -> tuple[
    list[dict[str, Any]], dict[str, int]
]:
    index = CCEGClaimIndex(claims, allow_research_unary=True)
    if index.rejected:
        raise ValueError(f"input rejected: {index.rejected[:10]}")
    groups: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list))
    for edge in index.unary_edges():
        groups[(edge["finding_key"], edge["article_id"])][
            edge["effect"]].append(edge)
    composer = CCEGComposer(index)
    emitted: dict[str, dict[str, Any]] = {}
    attempted = 0
    for effects in groups.values():
        for support, against in product(
            effects.get("supports", ()), effects.get("argues_against", ())
        ):
            attempted += 1
            support_claim = index.claims[support["position"]]
            against_claim = index.claims[against["position"]]
            rows = composer.compose(
                support_claim["candidate_a"],
                against_claim["candidate_a"],
                support_claim["finding"],
            )
            for row in rows:
                premise_ids = set(row["derivation"]["premise_claim_ids"])
                if premise_ids != {
                    support["claim_id"], against["claim_id"]
                }:
                    continue
                errors = validate_claim(row)
                if errors:
                    raise ValueError(
                        f"invalid derived claim {row['claim_id']}: {errors}")
                emitted[row["claim_id"]] = row
    rows = sorted(emitted.values(), key=lambda row: row["claim_id"])
    return rows, {
        "input_claims": len(claims),
        "finding_article_groups": len(groups),
        "candidate_pairs_attempted": attempted,
        "derived_claims": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path)
    parser.add_argument("--claims-out", type=Path, required=True)
    parser.add_argument("--manifest-out", type=Path, required=True)
    args = parser.parse_args()
    if args.claims_out.exists() or args.manifest_out.exists():
        parser.error("refusing to overwrite composed artifacts")
    rows, counts = compose_all(_load(args.claims))
    args.claims_out.parent.mkdir(parents=True, exist_ok=True)
    with args.claims_out.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(
                row, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")) + "\n")
    manifest = {
        "artifact": "cceg_derived_contrasts",
        "schema_version": 2,
        "lane": "research",
        "composition_policy": (
            "same-article+same-finding-state+supports/argues-against"),
        "inputs": [{"path": str(args.claims), "sha256": _sha256(args.claims)}],
        "outputs": [{
            "path": str(args.claims_out),
            "sha256": _sha256(args.claims_out),
            "rows": len(rows),
        }],
        "counts": counts,
    }
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
