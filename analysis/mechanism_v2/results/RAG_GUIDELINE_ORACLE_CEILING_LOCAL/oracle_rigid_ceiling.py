#!/usr/bin/env python3
"""If every genuinely-licensed high-stakes rule fired correctly, who wins?

Grants everything at once: the 40 rows a human judged genuinely licensed are
taken as correctly extracted, layers 1 and 2 are read rigidly (one vote, highest
priority: a pathognomonic or sufficient finding present confirms outright, a
violated necessity vetoes), and binding is assumed perfect.  The only thing not
granted is the answer itself.

The first question is not whether the rules execute but whether they are even
about the right disease, so this reports, per case, whether a licensed rule
lands on the gold, on a rival candidate, or on nothing in the candidate set.

    python oracle_rigid_ceiling.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


def licensed_rows() -> list[dict]:
    lab = {}
    for line in (OUT / "labels_pool6_mixed.tsv").read_text("utf-8").splitlines()[1:]:
        if line.strip():
            f = line.split("\t")
            lab[int(f[0])] = f[1].strip()
    mix = {r["idx"]: r for r in
           json.loads((OUT / "batch_pool6_mixed_key.json").read_text("utf-8"))}
    pk = {r["idx"]: r for r in
          json.loads((OUT / "batch_pool6_key.json").read_text("utf-8"))}
    return [pk[int(m["orig_idx"])] for i, v in lab.items()
            if (m := mix.get(i)) and v == "1" and m["src"] != "control"]


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_pool6.json").read_text("utf-8"))}
    rows = licensed_rows()

    per: dict[str, dict] = defaultdict(lambda: {"gold": [], "rival": [], "none": []})
    for r in rows:
        task = tasks[r["case"]]
        # gold_labels_in_set carries the alias, not the candidate label, so the
        # engine's own gold_match is the only reliable marker here
        golds = {c["label"] for c in task["candidates"]
                 if c.get("gold_match") == "strong"}
        hit = None
        for cand in task["candidates"]:
            names = [cand["label"], *(cand.get("aliases") or [])]
            if any(eng.subject_match(r["subject"], n) for n in names):
                hit = cand["label"]
                break
        slot = "none" if hit is None else ("gold" if hit in golds else "rival")
        per[r["case"]][slot].append({**r, "bound_to": hit})

    print("per case: where the licensed high-stakes rules land\n")
    print(f"{'case':>5}  {'gold':<42}{'in cand?':>9}"
          f"{'on gold':>9}{'on rival':>10}{'unbound':>9}")
    tot = Counter()
    for key in sorted(tasks, key=lambda k: int(k.split("/")[-1])):
        d = per[key]
        g = tasks[key]["gold"]
        in_set = any(c.get("gold_match") == "strong"
                     for c in tasks[key]["candidates"])
        tot["gold"] += len(d["gold"])
        tot["rival"] += len(d["rival"])
        tot["none"] += len(d["none"])
        tot["winnable"] += bool(in_set)
        print(f"{key.split('/')[-1]:>5}  {g[:40]:<42}{('yes' if in_set else 'NO'):>9}"
              f"{len(d['gold']):>9}{len(d['rival']):>10}{len(d['none']):>9}")
    print(f"\n  cases whose gold is even in the candidate set: "
          f"{tot['winnable']}/{len(tasks)}")
    n = sum(tot.values())
    print(f"{'ALL':>5}  {'':<44}{tot['gold']:>9}{tot['rival']:>10}{tot['none']:>9}"
          f"   (n={n})")

    print("\n\nthe rules that land on the gold -- the only ones that can win a case")
    for key in sorted(tasks, key=lambda k: int(k.split("/")[-1])):
        d = per[key]["gold"]
        if not d:
            continue
        print(f"\n  case {key.split('/')[-1]}  gold = {tasks[key]['gold']}")
        for r in d:
            print(f"    [{r['relation']}] {r['subject'][:40]} -> {r['bound_to'][:40]}")
            print(f"        predicate: {r['predicate'][:80]}")
            print(f"        quote    : {' '.join(r['quote'].split())[:150]}")

    print("\n\nrules that land on a RIVAL -- under one-vote confirmation these"
          "\nfire for the wrong disease whenever their finding is present")
    for key in sorted(tasks, key=lambda k: int(k.split("/")[-1])):
        d = per[key]["rival"]
        if not d:
            continue
        print(f"\n  case {key.split('/')[-1]}  gold = {tasks[key]['gold'][:50]}")
        for r in d:
            print(f"    [{r['relation']}] -> {r['bound_to'][:44]} | "
                  f"{r['predicate'][:52]}")

    json.dump({k: {s: [{"relation": r["relation"], "subject": r["subject"],
                        "predicate": r["predicate"], "quote": r["quote"],
                        "bound_to": r["bound_to"]} for r in v]
                   for s, v in d.items()} for k, d in per.items()},
              (LEDGER / "rigid_ceiling_binding.json").open("w"), indent=2,
              ensure_ascii=False)
    print(f"\n\nwrote {LEDGER / 'rigid_ceiling_binding.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
