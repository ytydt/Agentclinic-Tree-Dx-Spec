#!/usr/bin/env python3
"""Does reopening layers 1 and 2 help, now that the relation labels are better.

The scope restrictions on those layers were put in when the labels could not be
trusted.  Each variant here lifts one of them; the interesting column is not
top-1 but `elim_gold`, because a rigid veto that fires on the gold costs more
than the ranking it fixes.

    python sweep_rigidity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

FLAGS = ("RIGID_REQUIRED_ANY_MODALITY", "RIGID_SUFFICIENT_CONFIRMS",
         "RIGID_PATHO_READS_THRESHOLD", "RIGID_REQUIRED_CLOSED_WORLD")

VARIANTS = {
    "V0_current":            (),
    "V1_required_any_mod":   ("RIGID_REQUIRED_ANY_MODALITY",),
    "V2_sufficient_confirms": ("RIGID_SUFFICIENT_CONFIRMS",),
    "V3_patho_reads_cutoff": ("RIGID_PATHO_READS_THRESHOLD",),
    "V4_required_closed_world": ("RIGID_REQUIRED_CLOSED_WORLD",),
    "V5_all_rigid":          FLAGS,
    "V1+V2":                 ("RIGID_REQUIRED_ANY_MODALITY", "RIGID_SUFFICIENT_CONFIRMS"),
}


def main() -> int:
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}

    out = {}
    print(f"{'variant':<26}{'top1':>6}{'top3':>6}{'MRR':>8}{'elim_gold':>11}"
          f"{'vetoes':>8}{'confirms':>10}")
    for name, on in VARIANTS.items():
        for fl in FLAGS:
            setattr(eng, fl, fl in on)
        sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                     {"quote_gate": True})
        res = [sw.eng.run_case(tasks[k], old[k]) for k in tasks]
        m = sw.metrics(res)
        vet = sum(len(c["eliminated"]) for r in res for c in r["ranking"])
        con = sum(len(c["confirmed"]) for r in res for c in r["ranking"])
        killed = [r["case_key"].split("/")[-1] for r in res if r["gold_eliminated"]]
        print(f"{name:<26}{m['top1']:>6}{m['top3']:>6}{m['mrr']:>8.3f}"
              f"{m['gold_eliminated']:>11}{vet:>8}{con:>10}"
              f"   gold killed in: {killed}")
        out[name] = {"flags": list(on), "top1": m["top1"], "top3": m["top3"],
                     "mrr": round(m["mrr"], 4),
                     "gold_eliminated": m["gold_eliminated"],
                     "total_vetoes": vet, "total_confirms": con,
                     "gold_killed_cases": killed}
    for fl in FLAGS:
        setattr(eng, fl, False)
    (LEDGER / "rigidity_sweep.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {LEDGER / 'rigidity_sweep.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
