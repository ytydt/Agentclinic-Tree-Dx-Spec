#!/usr/bin/env python3
"""Build an immutable, manifest-described CCEG direct-claim index."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_claim_index import (  # noqa: E402
    CCEGClaimIndex,
    INDEX_VERSION,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_claims(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return [
            json.loads(line) for line in path.read_text(
                encoding="utf-8").splitlines() if line.strip()
        ]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
        return payload["claims"]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError("claims input must be an object, array, or JSONL")


def build_index(
    input_path: Path,
    output_dir: Path,
    *,
    research: bool = False,
) -> dict[str, Any]:
    """Build once; any existing output path is an explicit error."""
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite index: {output_dir}")
    rows = load_claims(input_path)
    index = CCEGClaimIndex(rows, allow_research_unary=research)
    if index.rejected:
        detail = json.dumps(index.rejected[:10], ensure_ascii=False)
        raise ValueError(
            f"{len(index.rejected)} claims rejected; index not written: {detail}")
    if not index.claims:
        raise ValueError("no grounded validated claims to index")

    output_dir.mkdir(parents=True)
    claims_path = output_dir / "claims.jsonl"
    with claims_path.open("x", encoding="utf-8") as stream:
        for claim in index.claims:
            stream.write(json.dumps(
                claim, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            stream.write("\n")
    unary_path = output_dir / "unary_index.json"
    unary_path.write_text(
        json.dumps(
            index.unary_index_artifact(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
    claim_types = Counter(str(row["claim_type"]) for row in index.claims)
    source_classes = Counter(str(row["source_class"]) for row in index.claims)
    schema_versions = Counter(
        str(row["schema_version"]) for row in index.claims)
    manifest = {
        "artifact": "cceg_claim_index",
        "index_version": INDEX_VERSION,
        "schema_version": max(
            int(version) for version in schema_versions),
        "schema_versions": dict(sorted(schema_versions.items())),
        "inputs": [{
            "path": str(input_path),
            "sha256": _sha256(input_path),
        }],
        "outputs": [{
            "path": "claims.jsonl",
            "sha256": _sha256(claims_path),
            "rows": len(index.claims),
        }, {
            "path": "unary_index.json",
            "sha256": _sha256(unary_path),
            "rows": len(index.unary_edges()),
        }],
        "counts": {
            "claims": len(index.claims),
            "unary_edges": len(index.unary_edges()),
            "claim_types": dict(sorted(claim_types.items())),
            "source_classes": dict(sorted(source_classes.items())),
        },
        "policy": "schema-valid-and-grounded-only",
        "lane_policy": (
            "research-v2-candidate-effect" if research else "clinical-grounded"),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claims", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--research", action="store_true")
    args = parser.parse_args()
    try:
        manifest = build_index(args.claims, args.output, research=args.research)
    except (FileExistsError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
