#!/usr/bin/env python3
"""Fold the annotated batch into the training set (§16.8).

Rows that were labelled by hand override the F7 teacher label; ``?`` rows are
dropped rather than guessed.  Also reports how often the annotator agreed with
the teacher, which is a second read on how much of F7 is actually right.

``--k`` truncates to the first k annotated rows, so the caller can trace a
learning curve without re-annotating.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATA = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL" / "relation_verifier"


def key(case: str, rel: str, subj: str, pred: str, quote: str) -> tuple:
    return (str(case), str(rel).lower(), str(subj).lower().strip(),
            str(pred).lower().strip(), str(quote)[:80].lower().strip())


def load_annotations(k: int | None) -> dict[tuple, str]:
    kit = (DATA / "annotate_diagnostic_slots.tsv").read_text("utf-8").splitlines()
    by_idx = {}
    for line in kit[1:]:
        f = line.split("\t")
        if len(f) < 7:
            continue
        by_idx[f[0]] = key(f[1], f[2], f[3], f[4], f[5])

    labels = (DATA / "labels_train_200.tsv").read_text("utf-8").splitlines()
    out: dict[tuple, str] = {}
    rows = [l.split("\t") for l in labels[1:] if l.strip()]
    rows = [r for r in rows if len(r) >= 2]
    rows.sort(key=lambda r: int(r[0]))
    if k is not None:
        rows = rows[:k]
    for idx, lab in rows:
        if idx in by_idx:
            out[by_idx[idx]] = lab.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--out", type=str, default="train_other10_human.jsonl")
    args = ap.parse_args()

    ann = load_annotations(args.k)
    rows = [json.loads(l) for l in
            (DATA / "train_other10.jsonl").read_text("utf-8").splitlines() if l.strip()]

    stats = Counter()
    out_rows = []
    for r in rows:
        if r["source"] == "perturbation":
            out_rows.append(r)
            continue
        kk = key(r["case"], r["relation"], r["subject"], r["predicate"], r["quote"])
        lab = ann.get(kk)
        if lab is None:
            out_rows.append(r)
            continue
        stats["matched"] += 1
        if lab == "?":
            stats["dropped_unjudgeable"] += 1
            continue
        human = int(lab)
        stats["agree_with_teacher" if human == r["label"] else "differ"] += 1
        stats[f"human_{human}"] += 1
        r = dict(r, label=human, source="human")
        out_rows.append(r)

    (DATA / args.out).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows),
        encoding="utf-8")

    n_used = stats["matched"] - stats["dropped_unjudgeable"]
    agree = stats["agree_with_teacher"] / max(1, n_used)
    print(f"annotations loaded: {len(ann)}  matched to train rows: {stats['matched']}")
    print(f"  unjudgeable dropped : {stats['dropped_unjudgeable']}")
    print(f"  human licensed / not: {stats['human_1']} / {stats['human_0']}")
    print(f"  agreement with F7 teacher: {stats['agree_with_teacher']}/{n_used} "
          f"= {agree:.3f}")
    print(f"wrote {DATA / args.out} ({len(out_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
