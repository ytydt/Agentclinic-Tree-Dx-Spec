#!/usr/bin/env python3
"""Build an immutable case-report membership/phenotype claim index."""
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

from agentclinic_tree_dx.knowledge.case_report_membership_index import (  # noqa: E402
    CaseReportMembershipIndex,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> list[dict[str, Any]]:
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


def build_membership(input_path: Path, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(
            f"refusing to overwrite membership index: {output_dir}")
    index = CaseReportMembershipIndex(_load(input_path))
    if index.rejected:
        raise ValueError(
            f"{len(index.rejected)} non-serving claims rejected: "
            f"{json.dumps(index.rejected[:10], ensure_ascii=False)}")
    if not index.claims:
        raise ValueError("no grounded case-report membership claims")
    output_dir.mkdir(parents=True)
    artifact = output_dir / "claims.jsonl"
    with artifact.open("x", encoding="utf-8") as stream:
        for claim in index.claims:
            stream.write(json.dumps(
                claim, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            stream.write("\n")
    types = Counter(str(row["claim_type"]) for row in index.claims)
    manifest = {
        "artifact": "case_report_membership_index",
        "index_version": 1,
        "inputs": [{"path": str(input_path), "sha256": _sha256(input_path)}],
        "outputs": [{
            "path": "claims.jsonl",
            "sha256": _sha256(artifact),
            "rows": len(index.claims),
        }],
        "counts": {"claims": len(index.claims), "claim_types": dict(sorted(types.items()))},
        "policy": {
            "grounded_only": True,
            "allowed_claim_types": ["membership", "phenotype_assertion"],
            "emits_direction": False,
        },
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
    args = parser.parse_args()
    try:
        report = build_membership(args.claims, args.output)
    except (FileExistsError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
