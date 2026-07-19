"""Deterministic demonstrator for the parent-child aggregation operators
(QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH §4):

  rule-in  up-propagation = MAX over children  (OR: any child ruled-in ⇒ family in)
  rule-out up-propagation = MIN over children  (AND / commonality: a family is
           ruled-out only if EVERY child is ruled-out; a finding that rules-IN one
           child must NOT rule-out the family — the CML-blast trap).

No LLM / retrieval; this validates the algebra the qualitative injection pipeline
will use once L1 is expanded to L2 and per-child directional evidence is scored.

    PYTHONPATH=src python scripts/eval_aggregation_operators.py
"""
from __future__ import annotations


def rule_in_parent(child_rule_in: dict[str, float]) -> float:
    """P(parent) ≥ max child ⇒ rule-in bubbles up as MAX (not mean → no dilution)."""
    return max(child_rule_in.values()) if child_rule_in else 0.0


def rule_out_parent(child_rule_out: dict[str, float],
                    child_rule_in: dict[str, float]) -> float:
    """Rule-out only from evidence that argues against ALL children. A finding that
    rules-IN some child cannot contribute to ruling out the family, so we take MIN
    of the per-child rule-out scores AND zero out any child still supported."""
    if not child_rule_out:
        return 0.0
    eff = {c: (0.0 if child_rule_in.get(c, 0.0) > 0.5 else s)
           for c, s in child_rule_out.items()}
    return min(eff.values())


def check(name, got, want, tol=1e-9):
    ok = abs(got - want) < tol
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got:.2f} want={want:.2f}")
    return ok


def main() -> int:
    print("Aggregation operator demonstrator (rule-in=max, rule-out=min-commonality)\n")
    ok = True

    # ── Case 1: CML family {chronic phase, accelerated, blast phase}.
    # finding "many undifferentiated (blast) cells": rules-IN blast phase strongly,
    # rules-OUT chronic phase. Family CML must NOT be ruled out (a child is ruled IN).
    print("Case 1 — CML family, finding='excess blast cells'")
    child_in = {"CML chronic": 0.0, "CML accelerated": 0.3, "CML blast": 0.95}
    child_out = {"CML chronic": 0.9, "CML accelerated": 0.2, "CML blast": 0.0}
    ri = rule_in_parent(child_in)
    ro = rule_out_parent(child_out, child_in)
    ok &= check("family rule-in  = max(children)", ri, 0.95)
    ok &= check("family rule-out = min(commonality, supported children voided)", ro, 0.0)
    print("    → blast-cells RULES IN the CML family and does NOT rule it out. ✓\n")

    # ── Case 2: a finding that argues against every child ⇒ family ruled out.
    print("Case 2 — finding argues against ALL children ⇒ family out")
    child_in2 = {"A": 0.0, "B": 0.0, "C": 0.0}
    child_out2 = {"A": 0.8, "B": 0.7, "C": 0.9}
    ok &= check("family rule-out = min = weakest common refute", 
                rule_out_parent(child_out2, child_in2), 0.7)
    print("    → all children refuted ⇒ family refuted at the weakest-link strength. ✓\n")

    # ── Case 3: dilution guard — one strongly-supported child, others irrelevant.
    print("Case 3 — dilution guard (why MAX, not MEAN)")
    child_in3 = {"rare-but-right": 0.9, "irrelevant-1": 0.0, "irrelevant-2": 0.0}
    ri3 = rule_in_parent(child_in3)
    mean3 = sum(child_in3.values()) / len(child_in3)
    ok &= check("family rule-in (max) preserves the hit", ri3, 0.9)
    print(f"    → mean would collapse it to {mean3:.2f} (the 'evidence collapse' bug); "
          f"max keeps {ri3:.2f}. ✓\n")

    print("=" * 60)
    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
