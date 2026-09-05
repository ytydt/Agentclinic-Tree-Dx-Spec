#!/usr/bin/env python3
"""Re-score oracle recall of a v2-index retrieval arm.

`trial_tasks_11_all4.json` stores oracle_gids as integers, and a gid is just a
row number in that index's meta.jsonl.  The v2 index has 907,371 rows against
the old index's 861,131, so the same integer names a different chunk and the
oracle counter reads 11/26 instead of 23/26 for reasons that have nothing to do
with retrieval.  This maps old gid -> (source, native_id) -> v2 gid and reports
recall on the mapped ids, plus how much of the oracle survived the remap at all.

  python remap_oracle_gids.py --arm x2_v2idx
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OLD = ROOT / "data/corpus/ceiling_trial_index"
NEW = ROOT / "data/corpus/ceiling_trial_index_v2"


def load_keys(index: Path) -> list[tuple[str, str]]:
    out = []
    with (index / "meta.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            m = json.loads(line)
            out.append((m["source"], m["native_id"]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="x2_v2idx")
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    args = ap.parse_args()

    old_keys = load_keys(OLD)
    new_index = {k: i for i, k in enumerate(load_keys(NEW))}
    print(f"old {len(old_keys)} chunks, v2 {len(new_index)} chunks")

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    arm = json.loads((LEDGER / f"trial_retrieval_{args.arm}.json").read_text(encoding="utf-8"))

    lost = Counter()
    n_ok = n_tot = 0
    per_case = []
    for rec in arm:
        task = tasks[rec["case_key"]]
        all_gids = {g for r in rec["retrieved"].values()
                    for p in r["passages"] for g in p["window_gids"]}
        ok = 0
        for a in task["assertions"]:
            mapped, dropped = set(), 0
            for g in a["oracle_gids"]:
                key = old_keys[g]
                v = new_index.get(key)
                if v is None:
                    dropped += 1
                    lost[key[0]] += 1
                else:
                    mapped.add(v)
            hit = bool(mapped & all_gids)
            ok += hit
            n_tot += 1
            n_ok += hit
            if dropped:
                per_case.append((a["id"], dropped, len(a["oracle_gids"]), hit))
        print(f"  {rec['case_key']:24s} oracle {ok}/{len(task['assertions'])}")

    print(f"\nremapped oracle recall: {n_ok}/{n_tot} ({n_ok / n_tot:.3f})")
    if lost:
        print(f"oracle chunks with no v2 counterpart, by source: {dict(lost)}")
        for aid, d, tot, hit in per_case:
            print(f"  {aid:8s} lost {d}/{tot} oracle chunks  hit={hit}")

    # The id remap still cannot see statpearls, whose native_ids were rewritten
    # by the article_id repair, so score the same arm with the index-independent
    # instrument the task file already carries: the oracle regex pair.
    print("\n--- regex-scored oracle recall (index-independent) ---")
    ok = tot = 0
    for rec in arm:
        task = tasks[rec["case_key"]]
        texts = [p["text"] + " " + p["title"]
                 for r in rec["retrieved"].values() for p in r["passages"]]
        hits = 0
        for a in task["assertions"]:
            srx = re.compile(a["subject_re"], re.I)
            prx = re.compile(a["predicate_re"], re.I)
            hit = any(srx.search(t) and prx.search(t) for t in texts)
            hits += hit
            ok += hit
            tot += 1
        print(f"  {rec['case_key']:24s} oracle {hits}/{len(task['assertions'])}")
    print(f"regex oracle recall: {ok}/{tot} ({ok / tot:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
