#!/usr/bin/env python3
"""Independent organism-attribution coverage and safety probe."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.pathogen_attribution_index import (
    PathogenAttributionIndex, PathogenEdge)


def _load_edges(path: Path, source: str | None = None) -> list[PathogenEdge]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    return [
        PathogenEdge(**row) for row in payload.get("edges", [])
        if source is None or row.get("source", "").lower() == source
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pathogen-source", default="fused",
                        choices=["none", "snomed", "open_kb", "corpus", "fused"])
    parser.add_argument("--open-kb", type=Path)
    args = parser.parse_args()
    edges: list[PathogenEdge] = []
    built = ROOT / "data/knowledge_raw/pathogen_attribution_eval_index.json"
    corpus = ROOT / "data/eval/talp_pathogen_probe_edges.json"
    if args.pathogen_source in {"snomed", "fused"}:
        edges.extend(_load_edges(built, "snomed_ct"))
    if args.pathogen_source in {"open_kb", "fused"} and args.open_kb:
        edges.extend(_load_edges(args.open_kb))
    if args.pathogen_source in {"corpus", "fused"}:
        edges.extend(_load_edges(corpus))
    index = PathogenAttributionIndex(edges)
    probes = json.loads(
        (ROOT / "data/eval/talp_pathogen_attribution_probes.json").read_text())
    rows = []
    for case in probes["cases"]:
        result = index.attribute(
            case["syndrome"], culture_result=case.get("culture_result"),
            vignette_only=not bool(case.get("culture_result")))
        expected = case["expected"]
        rows.append({
            "id": case["id"], "expected": expected,
            "got": result.organism_id, "decision": result.decision,
            "reason": result.reason, "evidence_n": len(result.evidence),
            "ok": result.organism_id == expected,
            "false_attribution": expected is None and result.organism_id is not None,
        })
    culture = [r for r in rows if r["expected"]]
    vignette = [r for r in rows if not r["expected"]]
    report = {
        "source": args.pathogen_source,
        "edge_coverage": len(edges),
        "composite_resolve": sum(r["ok"] for r in rows) / len(rows),
        "culture_resolution": sum(r["ok"] for r in culture) / len(culture),
        "vignette_only_abstain": sum(r["ok"] for r in vignette) / len(vignette),
        "false_organism_attribution": sum(r["false_attribution"] for r in rows),
        "syndrome_vs_organism_gap": len(vignette),
        "rows": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
