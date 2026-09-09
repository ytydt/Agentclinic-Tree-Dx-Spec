#!/usr/bin/env python3
"""Every exclusion that fired, with the evidence needed to judge it by hand.

S35.3 found that all six gold eliminations in the 2x2 are exclusion_triggered,
and that layer 1 accepts an `excludes` at any modality while it demands
`obligatory` of `required_for`.  Before changing that asymmetry, this dumps the
assertions behind each firing -- quote, modality, source, and the finding they
joined to -- so the firings can be classified by reading them rather than by
whether they moved the ranking.

    python dump_exclusions.py --arm new/v2 --gold-only
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = {
    "old/old": "trial_extraction_x2_oldidxclean_groups.json",
    "new/old": "trial_extraction_x2_oldidxclean_groups_free.json",
    "old/v2": "trial_extraction_x2_v2idxclean_groups.json",
    "new/v2": "trial_extraction_x2_v2idxclean_groups_free.json",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="new/v2", choices=sorted(ARMS))
    ap.add_argument("--stack", default="S7_+F7")
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--gold-only", action="store_true",
                    help="only the firings that eliminated a gold label")
    ap.add_argument("--out", default="exclusion_census.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    ext = {e["case_key"]: e for e in
           json.loads((LEDGER / ARMS[args.arm]).read_text(encoding="utf-8"))}
    sw.configure(sw.BASELINES["B1"], sw.stacks()[args.stack])

    rows, stats = [], Counter()
    for key, task in tasks.items():
        r = eng.run_case(task, ext[key])
        gold = set(task["gold_labels_in_set"])
        # the elimination entry keeps only predicate/quote/finding, and the
        # verdict does not carry its assertions, so replay run_case's own
        # pre-processing and index the result to trace each firing back
        assertions = [a for a in ext[key]["assertions"] if isinstance(a, dict)]
        if eng.FIX_ENUM:
            assertions = [eng.clamp_relation(a) for a in assertions]
        if eng.FIX_QUOTE_GATE or eng.FIX_NLI:
            from gate_assertions import gate_assertions
            assertions = gate_assertions(assertions, apply_nli=eng.FIX_NLI)
        # (predicate, quote) is not unique -- the same sentence yields several
        # relations -- so keep only the ones that could have fired
        by_pq: dict[tuple, list] = {}
        for a in assertions:
            if (a.get("relation") or "").lower() in {"excludes", "argues_against"}:
                by_pq.setdefault((a.get("predicate"), a.get("quote")), []).append(a)

        for v in r["ranking"]:
            for e in v.get("eliminated") or []:
                if e.get("rule") != "exclusion_triggered":
                    continue
                is_gold = v["label"] in gold
                if args.gold_only and not is_gold:
                    continue
                cands = by_pq.get((e.get("predicate"), e.get("quote")), [])
                # prefer one whose subject binds to this candidate
                a = next((x for x in cands
                          if str(x.get("subject") or "").lower()[:12]
                          in v["label"].lower()), cands[0] if cands else {})
                if not cands:
                    stats["untraced"] += 1
                stats[f"gold={is_gold}"] += 1
                stats["modality:" + str(a.get("modality") or "none").lower()] += 1
                stats["relation:" + str(a.get("relation") or "?").lower()] += 1
                rows.append({
                    "case": key.split("/")[-1], "candidate": v["label"],
                    "is_gold": is_gold,
                    "relation": a.get("relation"), "modality": a.get("modality"),
                    "subject": a.get("subject"), "predicate": e.get("predicate"),
                    "joined_finding": e.get("finding"),
                    "source": a.get("_source"), "title": a.get("_title"),
                    "section": a.get("_section"),
                    "quote": e.get("quote"),
                })

    print(f"arm {args.arm}  stack {args.stack}  "
          f"{'gold firings only' if args.gold_only else 'all firings'}")
    print(f"firings: {len(rows)}   {dict(stats.most_common())}\n")
    for r in rows:
        print(f"[{r['case']}] {r['candidate']}"
              f"{'  <-- GOLD' if r['is_gold'] else ''}")
        print(f"    {r['relation']}/{r['modality']}  subject={str(r['subject'])[:50]}")
        print(f"    predicate: {r['predicate']}")
        print(f"    joined to finding: {r['joined_finding']}")
        print(f"    {r['source']} | {str(r['title'])[:70]}")
        print(f"    quote: {str(r['quote'])[:260]}\n")

    out = LEDGER / args.out
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
