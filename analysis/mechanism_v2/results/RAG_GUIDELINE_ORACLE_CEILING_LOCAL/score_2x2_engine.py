#!/usr/bin/env python3
"""Settle the S34 2x2 downstream: does any of it reach the ranking.

S34 stopped at the extraction side -- more groups reach across lines, the logic
mix moves toward what the text writes.  Whether that changes top-1 is a
separate question, because a group only affects the score if its members bind
to a candidate and join to a patient finding.  This runs all four arms through
the delivered stack (B1 + S7) and also reports how often a group actually fired,
which is the mechanism link between the two.

    python score_2x2_engine.py
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

ARMS = [
    ("old prompt / old index", "trial_extraction_x2_oldidxclean_groups.json"),
    ("new prompt / old index", "trial_extraction_x2_oldidxclean_groups_free.json"),
    ("old prompt / v2 index", "trial_extraction_x2_v2idxclean_groups.json"),
    ("new prompt / v2 index", "trial_extraction_x2_v2idxclean_groups_free.json"),
]


def group_activity(results: list[dict]) -> Counter:
    """How often criterion groups actually reached the score.

    Contributions carry `why` = "group:<logic>/<n>" and live in
    `contributions`, which run_case truncates to 25 per candidate.  Group
    contributions are appended before the per-assertion ones, so the cap only
    bites on a candidate with more than 25 groups; treat the count as a lower
    bound.
    """
    c: Counter = Counter()
    for r in results:
        for v in r["ranking"]:
            for e in v.get("eliminated") or []:
                if e.get("rule") == "criterion_group_violated":
                    c["eliminations"] += 1
            for s in v.get("contributions") or []:
                why = str(s.get("why") or "")
                if why.startswith("group:"):
                    c["contributions"] += 1
                    c["logic:" + why.split(":", 1)[1].split("/")[0]] += 1
                    if s.get("delta", 0) > 0:
                        c["delta_sum"] += s["delta"]
    return c


def gold_elim_why(results: list[dict], tasks: dict) -> dict[str, list[str]]:
    """Which rule killed the gold, for the cases where it was eliminated."""
    out: dict[str, list[str]] = {}
    for r in results:
        if not r["gold_eliminated"]:
            continue
        # run_case reports gold_eliminated as the list of gold labels that were
        # vetoed, matched against task["gold_labels_in_set"], not task["gold"]
        killed = set(r["gold_eliminated"])
        why = []
        for v in r["ranking"]:
            if v["label"] not in killed:
                continue
            for e in v.get("eliminated") or []:
                why.append(f"{e.get('rule')}: {str(e.get('predicate') or '')[:60]}")
        out[r["case_key"].split("/")[-1]] = why
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="S7_+F7")
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--drop-excludes", action="store_true",
                    help="ablate the excludes/argues_against layer-1 path")
    ap.add_argument("--ablate-f4b", action="store_true",
                    help="also run each arm with group_all_required off")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))}
    fix = sw.stacks()[args.stack]
    print(f"stack {args.stack}: {fix}\n")

    table = []
    for name, fn in ARMS:
        path = LEDGER / fn
        if not path.exists():
            print(f"[missing] {name}")
            continue
        ext = {e["case_key"]: e for e in
               json.loads(path.read_text(encoding="utf-8"))}
        if args.drop_excludes:
            # every gold elimination in this 2x2 is exclusion_triggered, so
            # removing the relation that feeds it says how much of the ranking
            # difference between the arms rides on that one layer-1 path
            for e in ext.values():
                e["assertions"] = [a for a in e["assertions"]
                                   if (a.get("relation") or "").lower()
                                   not in {"excludes", "argues_against"}]
        sw.configure(sw.BASELINES["B1"], fix)
        results = [eng.run_case(tasks[k], ext[k]) for k in tasks]
        m = sw.metrics(results)
        g = group_activity(results)
        m["gold_elim_why"] = gold_elim_why(results, tasks)
        table.append((name, m, g))

        if args.ablate_f4b:
            # F4b turns an "all" group into a veto; with more groups extracted
            # more vetoes fire, so test whether the regression rides on it
            sw.configure(sw.BASELINES["B1"], {**fix, "group_all_required": False})
            r2 = [eng.run_case(tasks[k], ext[k]) for k in tasks]
            m2 = sw.metrics(r2)
            print(f"  [-F4b] {name:<24} top1 {m['top1']}->{m2['top1']}  "
                  f"MRR {m['mrr']:.3f}->{m2['mrr']:.3f}  "
                  f"gold_elim {m['gold_eliminated']}->{m2['gold_eliminated']}")

    print(f"{'arm':<24}{'top1':>6}{'top3':>6}{'MRR':>8}{'MRR 95% CI':>18}"
          f"{'gold elim':>11}{'grp contrib':>13}{'grp elim':>10}")
    for name, m, g in table:
        ci = f"[{m['mrr_ci'][0]:.3f}, {m['mrr_ci'][1]:.3f}]"
        print(f"{name:<24}{m['top1']:>4}/11{m['top3']:>4}/11{m['mrr']:>8.3f}{ci:>18}"
              f"{m['gold_eliminated']:>11}{g['contributions']:>13}{g['eliminations']:>10}")

    print(f"\n{'arm':<24}{'grp all':>9}{'grp any':>9}{'grp at_least_n':>15}{'sum delta':>11}")
    for name, _, g in table:
        print(f"{name:<24}{g['logic:all']:>9}{g['logic:any']:>9}"
              f"{g['logic:at_least_n']:>15}{g['delta_sum']:>11.2f}")

    print(f"\n{'arm':<24}per-case gold rank")
    for name, m, _ in table:
        ranks = " ".join(f"{k.split('/')[-1]}:{v if v else '-'}"
                         for k, v in m["per_case"].items())
        print(f"{name:<24}{ranks}")

    print("\ngold eliminated, and by what")
    for name, m, _ in table:
        for case, why in m["gold_elim_why"].items():
            print(f"  {name:<24}{case:>5}  " + ("; ".join(why) or "(no rule recorded)"))

    tag = "_noexcl" if args.drop_excludes else ""
    out = LEDGER / f"trial_engine_x2{tag}.json"
    out.write_text(json.dumps(
        [{"arm": n, **m, "group_activity": dict(g)} for n, m, g in table],
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
