#!/usr/bin/env python3
"""What is still costing top-1 on the 11, now that the gates are better.

The question this answers is not "how many cases fail" but "what kind of thing
fails", split three ways, because the three call for different work:

  LOGIC   the relation label itself is wrong in a way the engine then acts on --
          a real necessity that no longer vetoes, a false sufficiency that
          confirms.  Fixing this is gate work.
  EXEC    the label is right and the engine mishandles it -- unit strings that
          do not compare, a threshold that never evaluates, a finding that
          never joins.  Fixing this is engine work.
  BIND    nothing to do with logic: the assertion is hung on the wrong subject,
          an alias fails, the guideline for the gold was never retrieved.

    python audit_top1_errors.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
HIGH = ("required_for", "pathognomonic_for", "sufficient_for", "excludes")


def drivers(cand: dict, k: int = 6) -> list[dict]:
    rows = sorted((cand.get("contributions") or []),
                  key=lambda c: -abs(float(c.get("delta") or 0)))[:k]
    return [{"delta": round(float(c.get("delta") or 0), 3),
             "why": c.get("why", ""), "predicate": c.get("predicate", ""),
             "relation": c.get("relation", ""), "quote": (c.get("quote") or "")[:110]}
            for c in rows]


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})

    out = []
    for key in tasks:
        r = sw.eng.run_case(tasks[key], old[key])
        rank = r["ranking"]
        top1 = rank[0] if rank else {}
        gold = next((c for c in rank if c.get("gold_match") == "strong"), None)
        rec = {
            "case": key,
            "gold": r["gold"],
            "gold_rank": r["gold_rank"],
            "gold_eliminated": r["gold_eliminated"],
            "gold_in_set": bool(gold),
            "top1": top1.get("label", ""),
            "top1_is_gold": r["top1_is_gold"],
            "top1_score": round(float(top1.get("score") or 0), 2),
            "top1_confirmed": [
                {"predicate": c.get("predicate", ""),
                 "quote": (c.get("quote") or "")[:110]}
                for c in (top1.get("confirmed") or [])],
            "top1_drivers": drivers(top1),
            "gold_score": round(float(gold.get("score") or 0), 2) if gold else None,
            "gold_confirmed_n": len(gold.get("confirmed") or []) if gold else None,
            "gold_elim_reasons": [
                {"rule": e.get("rule", ""), "predicate": e.get("predicate", ""),
                 "quote": (e.get("quote") or "")[:110]}
                for e in (gold.get("eliminated") or [])] if gold else [],
            "gold_drivers": drivers(gold) if gold else [],
            "n_candidates": len(rank),
        }
        out.append(rec)

    out.sort(key=lambda x: (x["top1_is_gold"], x["gold_rank"] or 99))
    (LEDGER / "top1_error_audit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(1 for r in out if r["top1_is_gold"])
    print(f"top1 correct: {n_ok}/{len(out)}\n")
    for r in out:
        mark = "OK  " if r["top1_is_gold"] else "MISS"
        print(f"{mark} {r['case']:24s} goldrank={str(r['gold_rank']):>4} "
              f"elim={r['gold_eliminated']} nc={r['n_candidates']:>3}")
        print(f"      gold: {r['gold'][:60]}  score={r['gold_score']} "
              f"conf={r['gold_confirmed_n']}")
        if not r["top1_is_gold"]:
            print(f"      top1: {r['top1'][:60]}  score={r['top1_score']} "
                  f"conf={len(r['top1_confirmed'])}")
            for c in r["top1_confirmed"][:3]:
                print(f"        CONFIRM {c['predicate'][:40]} | {c['quote'][:80]}")
            for d in r["top1_drivers"][:3]:
                print(f"        +{d['delta']:<7} {d['why'][:22]} "
                      f"{d['predicate'][:34]} | {d['quote'][:60]}")
        for e in r["gold_elim_reasons"]:
            print(f"        KILLED {e['rule']} {e['predicate'][:40]} | {e['quote'][:70]}")
    print(f"\nwrote {LEDGER / 'top1_error_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
