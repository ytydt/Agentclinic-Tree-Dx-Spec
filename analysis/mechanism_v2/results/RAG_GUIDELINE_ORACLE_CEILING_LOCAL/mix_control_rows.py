#!/usr/bin/env python3
"""Interleave known-answer control rows into a fresh annotation batch.

The pool batch comes from cases outside the frozen 11, so nothing there can be
checked against a human key.  Mixing in rows from the case-74 blind QC batch --
whose human census labels are known -- makes the delivery self-validating: the
same pass yields both the new labels and this annotator's agreement with the
census, with no way to tell the two kinds of row apart.

    python mix_control_rows.py --batch pool6 --controls 30
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = [l for l in path.read_text("utf-8").splitlines() if l.strip()]
    head = lines[0].split("\t")
    return head, [l.split("\t") for l in lines[1:]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="pool6")
    ap.add_argument("--controls", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    head, rows = read_tsv(OUT / f"batch_{args.batch}.tsv")
    c_head, c_rows = read_tsv(OUT / "batch_qc_case74.tsv")
    answers = json.loads((OUT / "batch_qc_case74_key.json").read_text("utf-8"))

    # the control sheet carries its own idx labels (qc*); keep them only in the
    # private key, never in the sheet the annotator sees
    ci, cc, cr, cs, cp, cq, cx = (c_head.index(x) for x in
                                  ("idx", "case", "relation", "subject",
                                   "predicate", "quote", "context"))
    rng = random.Random(args.seed)
    picked = rng.sample([r for r in c_rows if r[ci] in answers],
                        min(args.controls, len(c_rows)))

    merged = []
    for r in rows:
        merged.append({"src": "pool", "orig": r[0], "cells": r[1:7],
                       "answer": None})
    for r in picked:
        merged.append({"src": "control", "orig": r[ci],
                       "cells": [r[cc], r[cr], r[cs], r[cp], r[cq], r[cx]],
                       "answer": answers[r[ci]]})
    rng.shuffle(merged)

    tsv = ["\t".join(["idx", "case", "relation", "subject", "predicate",
                      "quote", "context", "licensed"])]
    key = []
    for i, m in enumerate(merged):
        tsv.append("\t".join([str(i)]
                             + [" ".join(str(c).split()) for c in m["cells"]]
                             + [""]))
        key.append({"idx": i, "src": m["src"], "orig_idx": m["orig"],
                    "answer": m["answer"]})

    (OUT / f"batch_{args.batch}_mixed.tsv").write_text("\n".join(tsv),
                                                       encoding="utf-8")
    (OUT / f"batch_{args.batch}_mixed_key.json").write_text(
        json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")
    n_ctl = sum(1 for m in merged if m["src"] == "control")
    print(f"wrote {OUT / f'batch_{args.batch}_mixed.tsv'}: {len(merged)} rows "
          f"({len(merged) - n_ctl} pool + {n_ctl}控制行, shuffled)")
    print(f"wrote {OUT / f'batch_{args.batch}_mixed_key.json'} (answers withheld)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
