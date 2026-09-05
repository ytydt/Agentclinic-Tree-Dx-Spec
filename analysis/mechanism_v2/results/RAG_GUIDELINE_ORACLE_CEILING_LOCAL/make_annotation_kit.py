#!/usr/bin/env python3
"""Annotation kit for the relation-slot verifier (§16.8).

Emits the 848 diagnostic-slot rows of the ten non-74 cases as a TSV with an
empty ``licensed`` column, plus the codebook.  The F7 prediction is deliberately
withheld from the sheet: showing it would make the labels agree with the gates
by suggestion, and the whole point is an independent signal.

Sampling is stratified by case and relation so a partial pass (the first N rows)
is still a usable, unbiased training set.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"

CODEBOOK = """# Relation-slot annotation codebook

One row = one extracted assertion.  Question: **does the cited guideline text
license this relation slot for this (disease, finding) pair?**

Write `1` (licensed) or `0` (not licensed) in the `licensed` column.  Use `?`
if the quote is too truncated to judge; `?` rows are dropped, not guessed.

Slot meanings (the closed schema the engine consumes):

| relation | reading |
|---|---|
| `required_for` | the finding must be present to make the diagnosis |
| `pathognomonic_for` | the finding on its own establishes the diagnosis |
| `sufficient_for` | the finding is enough to diagnose, others may also be |
| `excludes` | the finding being **present** rules the disease out |

Conventions fixed by earlier rounds (keep them, they define the target):

1. A workup statement is not a necessity.  "Evaluation includes echocardiography",
   "an ECG is required", "Holter monitoring" -> `0` for `required_for`.
2. A test may be required only when the text is exclusive about it: "the
   diagnosis can only be made after angiography", "cannot be diagnosed without",
   or when the requirement is the test's *result*.
3. Screening and risk stratification are not index diagnosis: "essential to
   identify at-risk relatives" -> `0`.
4. Treatment or administrative thresholds are not diagnostic criteria:
   "gradient of 50 mmHg or more" (treatment), "grounded for seven days" -> `0`.
5. Counting criteria are necessities: "at least 2 of the three precordial
   leads", "3 or more metabolic abnormalities" -> `1` for `required_for`.
6. A disease-name tautology is not pathognomonic: "a condition termed long QT
   syndrome" for predicate `prolonged QT` -> `0`.
7. Judge the *relation slot as written*, not whether some other slot would have
   been better.  A true necessity written as `pathognomonic_for` is `0` here.
"""


def main() -> int:
    rows = [json.loads(l) for l in
            (DATA / "train_other10.jsonl").read_text("utf-8").splitlines() if l.strip()]
    pool = [r for r in rows
            if r["source"] != "perturbation" and r["relation"] != "excludes"]

    buckets = defaultdict(list)
    for r in pool:
        buckets[(r["case"], r["relation"])].append(r)
    rng = random.Random(0)
    for v in buckets.values():
        rng.shuffle(v)

    # round-robin over (case, relation) so any prefix stays stratified
    order, keys = [], sorted(buckets)
    while any(buckets[k] for k in keys):
        for k in keys:
            if buckets[k]:
                order.append(buckets[k].pop())

    out = ["\t".join(["idx", "case", "relation", "subject", "predicate",
                      "quote", "context", "licensed"])]
    for i, r in enumerate(order):
        ctx = (r.get("evidence_sentence") or r["evidence"]).replace("\t", " ")
        out.append("\t".join([
            str(i), r["case"], r["relation"],
            str(r["subject"]).replace("\t", " "),
            str(r["predicate"]).replace("\t", " "),
            r["quote"].replace("\t", " "),
            ctx[:400], "",
        ]))
    (DATA / "annotate_diagnostic_slots.tsv").write_text(
        "\n".join(out), encoding="utf-8")
    (DATA / "ANNOTATION_CODEBOOK.md").write_text(CODEBOOK, encoding="utf-8")

    print(f"rows to label: {len(order)}")
    print("stratified round-robin over (case, relation); any prefix is usable")
    for rel in sorted({r['relation'] for r in order}):
        print(f"  {rel:<20}{sum(1 for r in order if r['relation'] == rel):>5}")
    print(f"\nwrote {DATA / 'annotate_diagnostic_slots.tsv'}")
    print(f"wrote {DATA / 'ANNOTATION_CODEBOOK.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
