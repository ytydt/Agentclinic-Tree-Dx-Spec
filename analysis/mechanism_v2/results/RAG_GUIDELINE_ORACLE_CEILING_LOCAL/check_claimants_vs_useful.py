#!/usr/bin/env python3
"""Is the idf discount measuring the thing the auditor called uselessness?

Layer 3 already divides a finding's weight by how many candidates claim it, so
in principle a symptom every candidate shares is already cheap.  The audit found
83 faithful-but-useless rows scoring anyway.  This checks whether the claimant
count separates the rows a clinician called useless from the ones they did not.
If it does not, the discount is measuring retrieval coverage rather than
clinical specificity, and no tuning of it will help.

    python check_claimants_vs_useful.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_mechanical_engine as eng  # noqa: E402
import sweep_fixes as sw  # noqa: E402

LEDGER = Path(__file__).resolve().parents[4] / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
OUT = LEDGER / "relation_verifier"


def claimants_for_case(task: dict, extraction: dict) -> dict[str, int]:
    """How many candidates carry an assertion that joins to each finding."""
    from gate_assertions import gate_assertions

    assertions = gate_assertions(
        [eng.clamp_relation(a) for a in extraction["assertions"]
         if isinstance(a, dict)], apply_nli=False)
    findings = [f for f in extraction["findings"]
                if isinstance(f, dict) and f.get("label")]

    claim: dict[str, set[str]] = defaultdict(set)
    for a in assertions:
        hit = None
        for cand in task["candidates"]:
            for name in [cand["label"], *(cand.get("aliases") or [])]:
                if eng.subject_match(a["subject"], name):
                    hit = cand["label"]
                    break
            if hit:
                break
        if not hit:
            continue
        for f in findings:
            for side in (f.get("canonical"), f.get("label")):
                if eng.predicate_match(a["predicate"], side or ""):
                    claim[eng.norm(f["label"])].add(hit)
                    break
            else:
                continue
            break
    return {k: len(v) for k, v in claim.items()}


def main() -> int:
    lab = {}
    for line in (OUT / "labels_defect_reaudit.tsv").read_text("utf-8").splitlines()[1:]:
        if line.strip():
            f = line.split("\t")
            lab[int(f[0])] = (f[1].strip(), f[2].strip())
    key = {r["idx"]: r for r in
           json.loads((OUT / "batch_defect_reaudit_key.json").read_text("utf-8"))}
    tasks = {t["case_key"]: t for t in
             json.loads((LEDGER / "trial_tasks_11_all4.json").read_text("utf-8"))}
    old = {e["case_key"]: e for e in json.loads(
        (LEDGER / "trial_extraction_k30all4clean_groups.json").read_text("utf-8"))}
    sw.configure({**sw.BASELINES["B1"], **sw.stacks()["S6_+F4b"]},
                 {"quote_gate": True})

    cases = sorted({key[i]["case"] for i in lab})
    claim = {c: claimants_for_case(tasks[c], old[c]) for c in cases}
    ncand = {c: len(tasks[c]["candidates"]) for c in cases}

    rows = []
    for i, (defect, useful) in lab.items():
        r = key[i]
        n = claim[r["case"]].get(eng.norm(r["finding"]))
        if n is None:
            continue
        rows.append({"useful": useful, "n_claim": n,
                     "spec": eng.specificity(n, ncand[r["case"]]),
                     "finding": r["finding"], "case": r["case"]})

    u1 = [r for r in rows if r["useful"] == "1"]
    u0 = [r for r in rows if r["useful"] == "0"]
    print(f"rows with a resolvable claimant count: {len(rows)}  "
          f"(useful=1 {len(u1)}, useful=0 {len(u0)})\n")

    def mean(xs):
        return sum(xs) / len(xs) if xs else float("nan")

    print(f"{'':<14}{'n_claimants':>13}{'idf weight':>13}")
    print(f"{'useful=1':<14}{mean([r['n_claim'] for r in u1]):>13.2f}"
          f"{mean([r['spec'] for r in u1]):>13.3f}")
    print(f"{'useful=0':<14}{mean([r['n_claim'] for r in u0]):>13.2f}"
          f"{mean([r['spec'] for r in u0]):>13.3f}")
    print("\nif the discount tracked usefulness, useful=0 would sit at a higher"
          "\nclaimant count and therefore a lower weight.\n")

    print("share of rows that are the sole claimant (full idf weight):")
    for name, grp in (("useful=1", u1), ("useful=0", u0)):
        s = sum(1 for r in grp if r["n_claim"] == 1)
        print(f"  {name:<10}{s:>4}/{len(grp):<4} = {s / len(grp):.1%}")

    print("\nmost-claimed findings among useful=0 rows:")
    for k, v in Counter(r["finding"] for r in u0).most_common(8):
        ns = {r["n_claim"] for r in u0 if r["finding"] == k}
        print(f"  {k[:44]:<46}rows={v}  n_claimants={sorted(ns)}")

    json.dump({"n": len(rows),
               "mean_claimants": {"useful_1": mean([r["n_claim"] for r in u1]),
                                  "useful_0": mean([r["n_claim"] for r in u0])},
               "mean_idf_weight": {"useful_1": mean([r["spec"] for r in u1]),
                                   "useful_0": mean([r["spec"] for r in u0])},
               "sole_claimant_share": {
                   "useful_1": sum(1 for r in u1 if r["n_claim"] == 1) / len(u1),
                   "useful_0": sum(1 for r in u0 if r["n_claim"] == 1) / len(u0)}},
              (LEDGER / "claimants_vs_useful.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'claimants_vs_useful.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
