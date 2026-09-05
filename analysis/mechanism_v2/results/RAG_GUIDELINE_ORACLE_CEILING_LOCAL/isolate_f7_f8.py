#!/usr/bin/env python3
"""Four-cell isolation for F7/F8 on B1+S6 (section 16 of the trial report).

Cells (all on B1 + cumulative stack through S6_+F4b):
  C0  old extraction, no quote gate / NLI
  C1  old extraction + F7
  C2  old extraction + F7 + F8
  C3  grounded re-extract + F7 + F8

Also counts F7 gate reason codes over the old extraction.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0, str(Path(__file__).parent))

import gate_assertions as ga  # noqa: E402
import sweep_fixes as sw  # noqa: E402


FOCUS = ("/74", "/326", "/119", "/475")


def load_ext(name: str) -> dict[str, dict]:
    path = LEDGER / name
    return {e["case_key"]: e for e in json.loads(path.read_text("utf-8"))}


def gate_hit_census(ext: dict[str, dict]) -> dict:
    before = []
    for case in ext.values():
        before.extend(a for a in case["assertions"] if isinstance(a, dict))
    after = ga.gate_assertions(before, apply_nli=False)
    stats = ga.gate_stats(before, after)
    # per-E tallies already in stats via _gate codes
    return stats


def run_cell(tasks, ext, extra_fix: dict) -> dict:
    s6 = sw.stacks()["S6_+F4b"]
    sw.configure({**sw.BASELINES["B1"], **s6}, extra_fix)
    res = [sw.eng.run_case(tasks[k], ext[k]) for k in tasks]
    m = sw.metrics(res)
    focus = {}
    for r in res:
        suf = "/" + r["case_key"].split("/")[-1]
        if any(r["case_key"].endswith(f) for f in FOCUS):
            focus[r["case_key"]] = {
                "gold_rank": r["gold_rank"],
                "top1": r["top1"],
                "gold_eliminated": r["gold_eliminated"],
                "n_confirmed": sum(len(v.get("confirmed") or []) for v in r["ranking"]),
            }
    m["focus"] = focus
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--old", default="trial_extraction_k30all4clean_groups.json")
    ap.add_argument("--grounded", default="trial_extraction_k30clean_groups_grounded.json")
    ap.add_argument("--out", default="f7_f8_isolation.json")
    args = ap.parse_args()

    tasks = {t["case_key"]: t for t in json.loads((LEDGER / args.tasks).read_text("utf-8"))}
    old = load_ext(args.old)
    report: dict = {"gate_census_old": gate_hit_census(old)}

    cells = [
        ("C0_old", old, {}),
        ("C1_old_F7", old, {"quote_gate": True}),
        ("C2_old_F7_F8", old, {"quote_gate": True, "nli": True}),
    ]
    gpath = LEDGER / args.grounded
    if gpath.exists():
        grounded = load_ext(args.grounded)
        cells.append(("C3_grounded_F7_F8", grounded, {"quote_gate": True, "nli": True}))
        report["gate_census_grounded"] = gate_hit_census(grounded)
    else:
        report["grounded_missing"] = str(gpath)

    report["cells"] = {}
    for name, ext, fix in cells:
        print(f"=== {name} ===", flush=True)
        m = run_cell(tasks, ext, fix)
        report["cells"][name] = m
        print(f"  top1={m['top1']}/11 top3={m['top3']}/11 MRR={m['mrr']:.3f} "
              f"elim_gold={m['gold_eliminated']}", flush=True)
        for k, v in m["focus"].items():
            print(f"  {k.split('/')[-1]:>4} rank={v['gold_rank']} "
                  f"elim={v['gold_eliminated']} top1={str(v['top1'])[:48]}", flush=True)

    out = LEDGER / args.out
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
