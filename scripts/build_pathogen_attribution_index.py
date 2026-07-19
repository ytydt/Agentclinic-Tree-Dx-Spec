#!/usr/bin/env python3
"""Build a provenance-bearing pathogen edge cache from structured sources."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge_raw"
ALLOWED = {"causative_agent", "culture_confirms", "host_factor_shifts_prior"}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _load_edges(path: Path, source: str) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    rows = payload.get("edges", payload if isinstance(payload, list) else [])
    out = []
    for row in rows:
        if row.get("relation") not in ALLOWED:
            continue
        if not all(row.get(k) for k in (
            "syndrome", "organism_id", "organism", "provenance"
        )):
            continue
        item = {k: row.get(k) for k in (
            "syndrome", "organism_id", "organism", "relation",
            "provenance", "strength"
        )}
        item["source"] = source
        item["strength"] = item.get("strength") or (
            "decisive" if item["relation"] == "culture_confirms" else "weak")
        out.append(item)
    return out


def _snomed_edges(concepts_path: Path, relations_path: Path) -> list[dict]:
    if not concepts_path.exists() or not relations_path.exists():
        return []
    concepts = json.loads(concepts_path.read_text())
    relations = json.loads(relations_path.read_text())
    out = []
    for rel in relations:
        if rel.get("type") != "causative_agent":
            continue
        src, dst = str(rel.get("src", "")), str(rel.get("dst", ""))
        syndrome, organism = concepts.get(src, {}), concepts.get(dst, {})
        if not syndrome or not organism:
            continue
        out.append({
            "syndrome": syndrome.get("preferred") or syndrome.get("fsn"),
            "organism_id": f"SNOMED:{dst}",
            "organism": organism.get("preferred") or organism.get("fsn"),
            "relation": "causative_agent", "source": "SNOMED_CT",
            "provenance": f"{relations_path}#{src}->{dst}",
            "strength": "weak",
        })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snomed-bundle", type=Path,
                        help="expanded evaluation bundle from "
                             "build_snomed_knowledge.py --typed-eval-out")
    parser.add_argument("--taxonomy-aliases", type=Path,
                        help="NCBI Taxonomy alias cache for automatic organism "
                             "identity normalization")
    parser.add_argument("--open-kb", action="append", type=Path, default=[])
    parser.add_argument("--corpus", action="append", type=Path, default=[])
    parser.add_argument("--out", type=Path,
                        default=RAW / "pathogen_attribution_eval_index.json")
    args = parser.parse_args()
    if args.snomed_bundle and args.snomed_bundle.exists():
        bundle = json.loads(args.snomed_bundle.read_text())
        tmp_concepts = args.out.with_suffix(".snomed_concepts.tmp.json")
        tmp_relations = args.out.with_suffix(".snomed_relations.tmp.json")
        tmp_concepts.write_text(json.dumps(bundle.get("concepts", {})))
        tmp_relations.write_text(json.dumps(bundle.get("relations", [])))
        try:
            edges = _snomed_edges(tmp_concepts, tmp_relations)
        finally:
            tmp_concepts.unlink(missing_ok=True)
            tmp_relations.unlink(missing_ok=True)
    else:
        edges = _snomed_edges(
            RAW / "snomed_concepts.json", RAW / "snomed_relations.json")
    for path in args.open_kb:
        edges.extend(_load_edges(path, "OPEN_KB"))
    for path in args.corpus:
        edges.extend(_load_edges(path, "CORPUS_ASSERTION"))
    # Canonicalize SNOMED organism identities to NCBI Taxonomy when an open-KB
    # edge provides an exact normalized organism label. This is an automatic
    # crosswalk, not a hand-maintained production map.
    ncbi_by_label = {
        _norm(e["organism"]): e["organism_id"]
        for e in edges if str(e.get("organism_id", "")).startswith("NCBITaxon:")
    }
    if args.taxonomy_aliases and args.taxonomy_aliases.exists():
        ncbi_by_label.update(
            json.loads(args.taxonomy_aliases.read_text()).get("aliases", {}))
    for edge in edges:
        canonical = ncbi_by_label.get(_norm(edge["organism"]))
        if canonical:
            edge["organism_id"] = canonical
    dedup = {
        (e["syndrome"], e["organism_id"], e["relation"], e["provenance"]): e
        for e in edges
    }
    payload = {
        "_provenance": {
            "evaluation_only": True,
            "sources": [str(p) for p in args.open_kb + args.corpus],
            "note": "mention counts were not converted to LR or direction",
        },
        "edges": list(dedup.values()),
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"edges={len(dedup)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
