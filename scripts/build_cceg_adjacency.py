#!/usr/bin/env python3
"""Build a deterministic candidate adjacency artifact from a CCEG claim index."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.cceg_claim_index import (  # noqa: E402
    CCEGClaimIndex,
    candidate_key,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_adjacency(
    index_path: Path,
    output_dir: Path,
    *,
    research: bool = False,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite adjacency: {output_dir}")
    index = CCEGClaimIndex.from_path(
        index_path, allow_research_unary=research)
    if index.rejected:
        raise ValueError("claim index contains rejected claims")
    adjacency: dict[str, list[dict[str, str]]] = defaultdict(list)
    edges = 0
    for claim in index.claims:
        if not claim.get("candidate_b"):
            continue
        left, right = candidate_key(claim["candidate_a"]), candidate_key(
            claim["candidate_b"])
        edge = {
            "neighbor": right,
            "claim_id": str(claim["claim_id"]),
            "relation": str(claim["relation"]),
        }
        adjacency[left].append(edge)
        adjacency[right].append({
            "neighbor": left,
            "claim_id": str(claim["claim_id"]),
            "relation": str(claim["relation"]),
        })
        edges += 1
    for rows in adjacency.values():
        rows.sort(key=lambda row: (row["neighbor"], row["claim_id"]))
    unary_edges = [
        {key: value for key, value in row.items() if key != "position"}
        for row in index.unary_edges()
    ]
    candidate_to_findings: dict[str, list[dict[str, str]]] = defaultdict(list)
    finding_to_candidates: dict[str, list[dict[str, str]]] = defaultdict(list)
    for edge in unary_edges:
        candidate_to_findings[edge["candidate_key"]].append({
            "finding_key": edge["finding_key"],
            "claim_id": edge["claim_id"],
            "effect": edge["effect"],
        })
        finding_to_candidates[edge["finding_key"]].append({
            "candidate_key": edge["candidate_key"],
            "claim_id": edge["claim_id"],
            "effect": edge["effect"],
        })
    for mapping in (candidate_to_findings, finding_to_candidates):
        for rows in mapping.values():
            rows.sort(key=lambda row: (
                next(iter(row.values())), row["claim_id"]))
    output_dir.mkdir(parents=True)
    artifact = output_dir / "adjacency.json"
    artifact.write_text(json.dumps(
        {
            "adjacency": dict(sorted(adjacency.items())),
            "bipartite": {
                "edges": unary_edges,
                "candidate_to_findings": dict(
                    sorted(candidate_to_findings.items())),
                "finding_to_candidates": dict(
                    sorted(finding_to_candidates.items())),
            },
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    source_file = index_path / "claims.jsonl" if index_path.is_dir() else index_path
    manifest = {
        "artifact": "cceg_candidate_finding_bipartite_adjacency",
        "index_version": 2,
        "inputs": [{"path": str(source_file), "sha256": _sha256(source_file)}],
        "outputs": [{
            "path": "adjacency.json",
            "sha256": _sha256(artifact),
            "nodes": len(adjacency),
            "edges": edges,
            "bipartite_edges": len(unary_edges),
            "candidate_nodes": len(candidate_to_findings),
            "finding_nodes": len(finding_to_candidates),
        }],
        "limits": {"supported_hops": [1, 2], "runtime_degree_cap_required": True},
        "lane": "research" if research else "clinical",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("claim_index", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--research", action="store_true")
    args = parser.parse_args()
    try:
        report = build_adjacency(
            args.claim_index, args.output, research=args.research)
    except (FileExistsError, ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
