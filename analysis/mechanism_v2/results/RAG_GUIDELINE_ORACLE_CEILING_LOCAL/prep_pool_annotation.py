#!/usr/bin/env python3
"""Label-free annotation batch from cases OUTSIDE the frozen 11.

Every gate rule so far was induced from the 11 cases, so measuring the gates on
them is contaminated.  This cuts the same kind of diagnostic-slot batch as
``prep_annotation_batches.py`` but from a different extraction arm, and freezes
the gate's own prediction into a key file that the annotator never sees.

    F7_EXTRA_RETRIEVAL=trial_retrieval_pool6k30all4.json \
    python prep_pool_annotation.py \
        --extraction trial_extraction_pool6k30all4clean_groups.json \
        --n 200 --tag pool6
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate_assertions as ga  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"
DIAGNOSTIC = ("required_for", "pathognomonic_for", "sufficient_for")


def flat(text: object) -> str:
    """One TSV cell: guideline passages carry newlines that would split rows."""
    return " ".join(str(text or "").split())


def rows_from(extraction: str) -> list[dict]:
    data = json.loads((LEDGER / extraction).read_text("utf-8"))
    seen: set[tuple] = set()
    rows: list[dict] = []
    for entry in data:
        case = entry.get("case_key") or ""
        for a in entry.get("assertions") or []:
            if not isinstance(a, dict):
                continue
            rel = (a.get("relation") or "").lower()
            if rel not in DIAGNOSTIC:
                continue
            quote = str(a.get("quote") or "")
            key = (case, rel, str(a.get("subject") or "").strip().lower(),
                   str(a.get("predicate") or "").strip().lower(),
                   quote.strip().lower()[:80])
            if key in seen:
                continue
            seen.add(key)
            gated = ga.gate_one(dict(a))
            kept = int(gated is not None
                       and (gated.get("relation") or "").lower() == rel)
            passage = ga.resolve_passage(a)
            span = ga.evidence_span(quote, passage) if passage else ""
            rows.append({
                "case": case, "relation": rel,
                "subject": a.get("subject") or "",
                "predicate": a.get("predicate") or "",
                "quote": quote,
                "context": flat(span or quote),
                "f7_pred": kept,
                "has_passage": int(bool(passage)),
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extraction",
                    default="trial_extraction_pool6k30all4clean_groups.json")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--tag", default="pool6")
    args = ap.parse_args()

    rows = rows_from(args.extraction)
    print(f"unique diagnostic-slot rows: {len(rows)}")
    by_case = defaultdict(int)
    for r in rows:
        by_case[r["case"]] += 1
    for c, n in sorted(by_case.items()):
        print(f"  {c:24s}{n:5d}")
    miss = sum(1 for r in rows if not r["has_passage"])
    print(f"rows whose passage could not be resolved: {miss}")

    # stratify by (case, relation) so the batch mirrors the pool
    buckets = defaultdict(list)
    for r in rows:
        buckets[(r["case"], r["relation"])].append(r)
    rng = random.Random(0)
    for v in buckets.values():
        rng.shuffle(v)
    order, keys = [], sorted(buckets)
    while any(buckets[k] for k in keys):
        for k in keys:
            if buckets[k]:
                order.append(buckets[k].pop())
    batch = order[:args.n]

    OUT.mkdir(parents=True, exist_ok=True)
    tsv = ["\t".join(["idx", "case", "relation", "subject", "predicate",
                      "quote", "context", "licensed"])]
    key_rows = []
    for i, r in enumerate(batch):
        tsv.append("\t".join([
            str(i), r["case"], r["relation"],
            flat(r["subject"]), flat(r["predicate"]), flat(r["quote"]),
            r["context"][:400], "",
        ]))
        key_rows.append({"idx": i, **r})

    (OUT / f"batch_{args.tag}.tsv").write_text("\n".join(tsv), encoding="utf-8")
    (OUT / f"batch_{args.tag}_key.json").write_text(
        json.dumps(key_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUT / f'batch_{args.tag}.tsv'} ({len(batch)} rows, no labels)")
    print(f"wrote {OUT / f'batch_{args.tag}_key.json'} (gate predictions withheld)")
    lic = sum(r["f7_pred"] for r in batch)
    print(f"gate would license {lic}/{len(batch)} = {lic / len(batch):.3f} "
          f"(annotator must not see this)")
    for rel in DIAGNOSTIC:
        n = sum(1 for r in batch if r["relation"] == rel)
        print(f"  {rel:<20}{n:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
