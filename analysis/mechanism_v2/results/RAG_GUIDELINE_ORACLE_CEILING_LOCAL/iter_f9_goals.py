#!/usr/bin/env python3
"""Round-n measurement for the G-A / G1 / G2 / G3 quote-gate iteration.

Does not change engine layers.  Prints whether each delivery target is met
and the C1-level 11-case ranking vs the recorded C1 baseline (2/11, MRR 0.415).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))

import gate_assertions as ga  # noqa: E402
import sweep_fixes as sw  # noqa: E402
from check_fixes import f7_mechanism_checks  # noqa: E402

BASELINE_C1 = {"top1": 2, "mrr": 0.415, "gold_eliminated": 1}


def uniq(rows):
    seen, out = set(), []
    for a in rows:
        k = (str(a.get("subject") or "").lower(),
             str(a.get("relation") or "").lower(),
             str(a.get("polarity") or "").lower(),
             str(a.get("modality") or "").lower(),
             str(a.get("predicate") or "").lower(),
             str(a.get("quote") or "")[:80].lower())
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out


def main() -> int:
    tasks = {t["case_key"]: t
             for t in json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    print("=== self-test ===", flush=True)
    ga._self_test()

    s6 = sw.stacks()["S6_+F4b"]
    print("\n=== mechanism checks ===", flush=True)
    rows = f7_mechanism_checks(tasks, old, s6)
    mech_pass = True
    for row in rows:
        flag = "PASS" if row["pass"] else "FAIL"
        if not row["pass"]:
            mech_pass = False
        print(f"  {flag}  {row['id']}", flush=True)

    print("\n=== ranking C1-level (B1+S6+quote_gate) ===", flush=True)
    sw.configure({**sw.BASELINES["B1"], **s6}, {"quote_gate": True})
    res = [sw.eng.run_case(tasks[k], old[k]) for k in tasks]
    m = sw.metrics(res)
    print(f"  top1={m['top1']}/11 top3={m['top3']}/11 MRR={m['mrr']:.3f} "
          f"elim_gold={m['gold_eliminated']}  "
          f"(C1 was {BASELINE_C1['top1']}/11 MRR {BASELINE_C1['mrr']})", flush=True)
    for r in res:
        suf = r["case_key"].split("/")[-1]
        if suf in {"74", "326", "119", "475"}:
            print(f"  {suf:>4} rank={r['gold_rank']} elim={r['gold_eliminated']} "
                  f"top1={str(r['top1'])[:48]}", flush=True)

    rank_ok = (m["top1"] >= BASELINE_C1["top1"]
               and m["mrr"] + 1e-9 >= BASELINE_C1["mrr"]
               and m["gold_eliminated"] <= BASELINE_C1["gold_eliminated"])

    ck74 = next(k for k in tasks if k.endswith("/74"))
    r74 = next(r for r in res if r["case_key"] == ck74)
    lqts_rows = [v for v in r74["ranking"] if re.search(r"long qt", v["label"], re.I)]
    print("\n=== 74 LQTS L1 (all labels) ===", flush=True)
    any_elim = False
    for v in lqts_rows:
        elims = v.get("eliminated") or []
        print(f"  {v['label'][:48]} score={v.get('score')} n_elim={len(elims)}", flush=True)
        for e in elims[:6]:
            any_elim = True
            print(f"    {e.get('rule')} pred={e.get('predicate')} cmp={e.get('comparison')}",
                  flush=True)
    if not any_elim:
        print("  (no Long-QT candidate eliminated)", flush=True)

    report = {
        "mechanism": rows,
        "ranking": m,
        "rank_not_worse_than_c1": rank_ok,
        "mechanism_all_pass": mech_pass,
        "lqts_eliminated": any_elim,
        "lqts_rules": [
            e.get("rule")
            for v in lqts_rows for e in (v.get("eliminated") or [])
        ],
    }
    out = LEDGER / "f9_goal_iteration.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out}", flush=True)
    return 0 if mech_pass and rank_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
