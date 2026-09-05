#!/usr/bin/env python3
"""Cut two label-free annotation batches (§16.8).

- ``batch_train_200.tsv``: the stratified first 200 rows of the ten-case kit.
  These become training labels.
- ``batch_qc_case74.tsv``: 60 diagnostic-slot rows of case 74, whose human
  census labels we already hold.  Annotating them blind gives an agreement rate,
  i.e. how much the new labels can be trusted before anything is trained on them.

Neither file carries the gold label or the F7 prediction.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"
COLS = ["idx", "case", "relation", "subject", "predicate", "quote", "context",
        "licensed"]


def write(path: Path, rows: list[list[str]]) -> None:
    body = ["\t".join(COLS)]
    body += ["\t".join(c.replace("\t", " ").replace("\n", " ") for c in r)
             for r in rows]
    path.write_text("\n".join(body), encoding="utf-8")


def main() -> int:
    kit = (DATA / "annotate_diagnostic_slots.tsv").read_text("utf-8").splitlines()
    write(DATA / "batch_train_200.tsv",
          [l.split("\t")[:7] + [""] for l in kit[1:201]])

    test = [json.loads(l) for l in
            (DATA / "test_case74.jsonl").read_text("utf-8").splitlines() if l.strip()]
    diag = [r for r in test if r["relation"] != "excludes"]
    buckets = defaultdict(list)
    for i, r in enumerate(diag):
        buckets[r["relation"]].append((i, r))
    rng = random.Random(7)
    picked = []
    for rel, rows in buckets.items():
        rng.shuffle(rows)
        picked += rows[:{"required_for": 38, "pathognomonic_for": 16,
                         "sufficient_for": 6}.get(rel, 0)]
    rng.shuffle(picked)
    write(DATA / "batch_qc_case74.tsv", [
        [f"qc{i}", "74", r["relation"], str(r["subject"]), str(r["predicate"]),
         r["quote"], (r.get("evidence_sentence") or r["evidence"])[:400], ""]
        for i, r in picked])
    (DATA / "batch_qc_case74_key.json").write_text(json.dumps(
        {f"qc{i}": r["label"] for i, r in picked}, indent=2), encoding="utf-8")

    print(f"batch_train_200.tsv: {len(kit[1:201])} rows")
    print(f"batch_qc_case74.tsv: {len(picked)} rows "
          f"(key held out in batch_qc_case74_key.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
