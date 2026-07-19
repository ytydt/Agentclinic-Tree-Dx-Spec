#!/usr/bin/env python3
"""Build a separate evaluation SNOMED slice; never overwrites legacy assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/knowledge_raw"
DEFAULT_TAGS = {
    "organism", "specimen", "observable entity", "procedure", "product",
    "substance", "clinical finding", "disorder", "body structure",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concepts", type=Path, default=RAW / "snomed_concepts.json")
    parser.add_argument("--term-index", type=Path,
                        default=RAW / "snomed_term_index.json")
    parser.add_argument("--out", type=Path,
                        default=RAW / "snomed_typed_eval_slice.json")
    parser.add_argument("--tags", default=",".join(sorted(DEFAULT_TAGS)))
    args = parser.parse_args()
    tags = {x.strip().lower() for x in args.tags.split(",") if x.strip()}
    concepts = json.loads(args.concepts.read_text())
    terms = json.loads(args.term_index.read_text())
    selected = {
        cid: concept for cid, concept in concepts.items()
        if str(concept.get("tag", "")).lower() in tags
    }
    selected_ids = set(selected)
    selected_terms = {
        term: [cid for cid in ids if cid in selected_ids]
        for term, ids in terms.items()
        if any(cid in selected_ids for cid in ids)
    }
    payload = {
        "_provenance": {
            "source_concepts": str(args.concepts),
            "source_term_index": str(args.term_index),
            "tags": sorted(tags),
            "evaluation_only": True,
        },
        "concepts": selected,
        "term_index": selected_terms,
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False))
    print(f"concepts={len(selected)} terms={len(selected_terms)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
