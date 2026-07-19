"""STARVATION-aware discrimination test on the improved matrix set
(data/eval/lr_discrimination_matrix.json, independent of lr_coverage_cases.json).

Unlike the coverage test (which only checked gold-favoring findings), this scores
the full (finding × candidate-branch) EXPECTED-EFFECT matrix and counts the error
modes that STARVE the correct branch under softmax renormalization:

  FALSE_HIGH_ON_DISTRACTOR : distractor expected ≤neutral but machinery gives a
                             strong FOR LR (LR≥3) → inflates a wrong branch.
  FALSE_RULEOUT_OF_GOLD    : gold expected ≥neutral but machinery gives against/
                             rule_out (LR≤0.33) → kills the correct branch.
  MISSED_RULEOUT_DISTRACTOR: distractor expected against/rule_out but machinery
                             leaves it ≥0.5 → distractor keeps competing.
  MISSED_SUPPORT_GOLD      : gold expected FOR (LR≥3) but machinery gives <1.5 →
                             correct branch under-fed.

Two engines compared per cell:
  prod_today : production get_lr_reference(fast) lr_positive AS-IS (incl pseudo-freq
               & misses) — what the annotator does now.
  stack      : 3-layer landing candidate = grounded Layer-B ∪ LIRICAL Layer-A
               (with is_a propagation) — miss → neutral.
Results are stratified by tree depth (L1 family-routing vs leaf) and trap type.

    PYTHONPATH=src python scripts/eval_lr_discrimination_matrix.py [--rag]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

DATA = PROJECT_ROOT / "data"
KR = DATA / "knowledge_raw"

# reuse Layer-A LIRICAL + Layer-B retriever from the coverage harness
_cov = importlib.util.spec_from_file_location(
    "cov", PROJECT_ROOT / "scripts" / "eval_lr_coverage_isolated.py")
_covm = importlib.util.module_from_spec(_cov)
_cov.loader.exec_module(_covm)


# expected-label → (sign, is_strong)  ; sign +1 for/against -1, 0 neutral
_EXP = {
    "pathognomonic": (+1, True), "strong_for": (+1, True), "for": (+1, True),
    "weak_for": (+1, False), "neutral": (0, False),
    "weak_against": (-1, False), "against": (-1, True), "rule_out": (-1, True),
}


def band(p):
    if not isinstance(p, (int, float)):
        return "neutral", 0, False        # miss → neutral
    if p >= 50:
        return "pathognomonic", +1, True
    if p >= 10:
        return "strong_for", +1, True
    if p >= 3:
        return "for", +1, True
    if p >= 1.5:
        return "weak_for", +1, False
    if p > 0.67:
        return "neutral", 0, False
    if p > 0.33:
        return "weak_against", -1, False
    if p > 0.1:
        return "against", -1, True
    return "rule_out", -1, True


def observed_prod(kr, finding, disease, fast):
    b = _covm.layer_b(kr, finding, disease, fast=fast)
    return b["lr"] if b["any_numeric"] else None


def observed_stack(kr, A, finding, disease, fast):
    b = _covm.layer_b(kr, finding, disease, fast=fast)
    if b["grounded"]:
        return b["lr"]
    a = A.lr(A.resolve_hpo(finding), A.resolve_disease(disease))
    if a is not None:
        return a["lr_positive"]
    return None


def classify(is_gold, exp_label, obs_p):
    """Return one of: OK, FALSE_HIGH_ON_DISTRACTOR, FALSE_RULEOUT_OF_GOLD,
    MISSED_RULEOUT_DISTRACTOR, MISSED_SUPPORT_GOLD, MINOR."""
    exp_sign, exp_strong = _EXP[exp_label]
    _, obs_sign, obs_strong = band(obs_p)
    p = obs_p if isinstance(obs_p, (int, float)) else 1.0

    if not is_gold and exp_sign <= 0 and p >= 3.0:
        return "FALSE_HIGH_ON_DISTRACTOR"
    if is_gold and exp_sign >= 0 and p <= 0.33:
        return "FALSE_RULEOUT_OF_GOLD"
    if not is_gold and exp_sign < 0 and exp_strong and p > 0.5:
        return "MISSED_RULEOUT_DISTRACTOR"
    if is_gold and exp_sign > 0 and exp_strong and p < 1.5:
        return "MISSED_SUPPORT_GOLD"
    # concordance check for the rest
    if obs_sign == exp_sign:
        return "OK"
    if obs_sign == 0 or exp_sign == 0:
        return "MINOR"          # one side neutral, not a starvation error
    return "MINOR"


_STARVE = {"FALSE_HIGH_ON_DISTRACTOR", "FALSE_RULEOUT_OF_GOLD",
           "MISSED_RULEOUT_DISTRACTOR", "MISSED_SUPPORT_GOLD"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag", action="store_true")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_discrimination_matrix.json").read_text())
    print("Loading Layer-A LIRICAL ...")
    A = _covm.LiricalPhenotypeLR(KR / "phenotype.hpoa", KR / "hp.obo")
    print(f"Loading Layer-B retriever (rag={args.rag}) ...")
    kr = _covm.build_retriever(args.rag)
    fast = not args.rag
    print()

    # counters: engine → metric
    tot = {e: defaultdict(int) for e in ("prod_today", "stack")}
    by_depth = {e: defaultdict(lambda: defaultdict(int)) for e in ("prod_today", "stack")}
    by_trap = {e: defaultdict(lambda: defaultdict(int)) for e in ("prod_today", "stack")}
    rows = []

    for case in ds["cases"]:
        print(f"══ {case['id']}  gold={case['gold']}")
        for ev in case["evidence"]:
            finding, depth, trap = ev["finding"], ev["depth"], ev["trap"]
            gold_name = case["gold"]
            for disease, exp_label in ev["effects"].items():
                is_gold = (disease == gold_name)
                op = observed_prod(kr, finding, disease, fast)
                osk = observed_stack(kr, A, finding, disease, fast)
                cp = classify(is_gold, exp_label, op)
                cs = classify(is_gold, exp_label, osk)
                for eng, obs, cls in (("prod_today", op, cp), ("stack", osk, cs)):
                    tot[eng]["n"] += 1
                    tot[eng][cls] += 1
                    tot[eng]["starve" if cls in _STARVE else "nostarve"] += 1
                    by_depth[eng][depth][cls] += 1
                    by_depth[eng][depth]["n"] += 1
                    by_trap[eng][trap][cls] += 1
                    by_trap[eng][trap]["n"] += 1
                rows.append({"case": case["id"], "finding": finding, "branch": disease,
                             "is_gold": is_gold, "depth": depth, "trap": trap,
                             "expected": exp_label, "prod_lr": op, "stack_lr": osk,
                             "prod_class": cp, "stack_class": cs})
            # compact per-finding print (gold cell + worst distractor error)
            gold_cell = next((r for r in rows if r["finding"] == finding and r["is_gold"]), None)
            gp = f"{gold_cell['prod_lr']:.2g}" if gold_cell and isinstance(gold_cell["prod_lr"], (int, float)) else "-"
            gs = f"{gold_cell['stack_lr']:.2g}" if gold_cell and isinstance(gold_cell["stack_lr"], (int, float)) else "-"
            print(f"  [{depth:<4}|{trap:<18}] {finding[:44]:<44} gold LR prod={gp:>6} stack={gs:>6}")
        print()

    def report(title, counters):
        print(f"\n{title}")
        for eng in ("prod_today", "stack"):
            m = counters[eng]
            n = max(1, m["n"])
            print(f"  [{eng}] n={m['n']}  STARVATION errors: {m['starve']} "
                  f"({100*m['starve']//n}%)  OK={m.get('OK',0)} MINOR={m.get('MINOR',0)}")
            for k in ("FALSE_HIGH_ON_DISTRACTOR", "FALSE_RULEOUT_OF_GOLD",
                      "MISSED_RULEOUT_DISTRACTOR", "MISSED_SUPPORT_GOLD"):
                print(f"      {k:<28}: {m.get(k,0)}")

    print("=" * 78)
    report("OVERALL (131 finding×branch cells)", tot)

    print("\n" + "=" * 78)
    print("BY TREE DEPTH")
    for eng in ("prod_today", "stack"):
        print(f"  [{eng}]")
        for depth in ("L1", "leaf"):
            m = by_depth[eng][depth]
            n = max(1, m["n"])
            st = sum(m.get(k, 0) for k in _STARVE)
            print(f"    {depth:<5} n={m['n']:<3} starvation={st} ({100*st//n}%)  "
                  f"OK={m.get('OK',0)}")

    print("\nBY TRAP TYPE (stack engine)")
    for trap in ("pathognomonic", "discriminator", "ruleout_distractor",
                 "shared_high", "confounder_correct", "constitutional"):
        m = by_trap["stack"][trap]
        if not m:
            continue
        n = max(1, m["n"])
        st = sum(m.get(k, 0) for k in _STARVE)
        detail = " ".join(f"{k.split('_')[0][:4]}{k.split('_')[-1][:3]}={m.get(k,0)}"
                          for k in _STARVE if m.get(k, 0))
        print(f"  {trap:<20} n={m['n']:<3} starvation={st} ({100*st//n}%)  {detail}")

    out = PROJECT_ROOT / "logs" / "lr_discrimination_matrix.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"\ndetail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
