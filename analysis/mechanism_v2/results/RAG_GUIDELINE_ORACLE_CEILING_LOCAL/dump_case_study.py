#!/usr/bin/env python3
"""Dump per-case materials for the mechanical-vs-manual case study."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

CASES = [
    "522", "773", "119", "257", "326", "475",
    "49", "56", "74", "91", "179",
]


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11_all4.json").read_text())}
    ext = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text())}
    stack_rows = json.loads((LEDGER / "fix_stack_all4.json").read_text())
    b1s6 = next(r for r in stack_rows if r["baseline"] == "B1" and r["fix"] == "S6_+F4b")
    b0s6 = next(r for r in stack_rows if r["baseline"] == "B0" and r["fix"] == "S6_+F4b")
    b1s0 = next(r for r in stack_rows if r["baseline"] == "B1" and r["fix"] == "S0_baseline")
    b0s0 = next(r for r in stack_rows if r["baseline"] == "B0" and r["fix"] == "S0_baseline")

    st = sw.stacks()["S6_+F4b"]
    sw.configure(sw.BASELINES["B1"], st)

    for cid in CASES:
        key = next(k for k in tasks if k.endswith("/" + cid))
        t = tasks[key]
        e = ext[key]
        r = eng.run_case(t, e)
        gold = r["gold_labels_in_set"]
        print("\n" + "=" * 88)
        print(f"{key}")
        print(f"gold={t['gold']!r}")
        print(f"gold_in_set={gold}")
        print(f"ncand={len(t['candidates'])} n_findings={r['n_findings']} "
              f"bound={r['n_assertions_bound']} join={r['join_stats']}")
        print(f"ranks  B0S0={b0s0['per_case'][key]}  B0S6={b0s6['per_case'][key]}  "
              f"B1S0={b1s0['per_case'][key]}  B1S6={b1s6['per_case'][key]}")
        print(f"B1S6 top1={b1s6['top1_labels'][key]!r}  gold_elim={r['gold_eliminated']}")
        print("FINDINGS:")
        for f in e.get("findings") or []:
            if not isinstance(f, dict):
                continue
            print(f"  [{f.get('polarity'):8s}] {str(f.get('label'))[:60]:60s} "
                  f"val={f.get('value')} {f.get('unit') or ''}")
        print("RANKING (B1+S6 live):")
        for i, c in enumerate(r["ranking"][:8], 1):
            mark = "<<" if c["label"] in gold else (" ELIM" if c.get("eliminated") else "")
            print(f"  {i:2d} {c['score']:8.3f} n_joined={c.get('n_joined',0):3d} "
                  f"{c['label'][:42]:42s}{mark}")
            if c.get("eliminated"):
                for el in c["eliminated"][:2]:
                    print(f"       ELIM {el.get('rule')}: {str(el.get('predicate'))[:80]}")
        # competitor eliminations that the manual tree would have used
        elim_comp = [c for c in r["ranking"] if c.get("eliminated") and c["label"] not in gold]
        print(f"competitors eliminated: {len(elim_comp)}")
        for c in elim_comp[:6]:
            el = c["eliminated"][0]
            print(f"  {c['label'][:36]:36s} {el.get('rule')} {str(el.get('predicate'))[:50]}")
        # gold contributions (top deltas)
        gold_c = next((c for c in r["ranking"] if c["label"] in gold), None)
        if gold_c:
            print("GOLD contributions:")
            for x in sorted(gold_c.get("contributions") or [],
                            key=lambda z: -abs(z.get("delta", 0)))[:8]:
                print(f"  {x.get('delta',0):+6.3f} {x.get('why','')} "
                      f"{str(x.get('finding') or x.get('predicate'))[:50]}")
        winner = r["ranking"][0]
        if winner["label"] not in gold:
            print("WINNER contributions:")
            for x in sorted(winner.get("contributions") or [],
                            key=lambda z: -abs(z.get("delta", 0)))[:8]:
                print(f"  {x.get('delta',0):+6.3f} {x.get('why','')} "
                      f"{str(x.get('finding') or x.get('predicate'))[:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
