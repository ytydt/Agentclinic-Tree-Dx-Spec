"""Direction-fix assertion for the fused knowledge-base signal (Workstream 1).

Demonstrates the "fused KB points the wrong way" fix on the four documented
cases. For each target finding it prints:
  * OLD  = argmax of the legacy additive `strength` (LR term + mention term) —
           the buggy behaviour that let corpus mention counts out-vote a strong
           likelihood ratio, or decide direction with no LR at all.
  * NEW  = `FusedKB.favored` after the fix (directional signal only; mention is
           a default-OFF comparative fallback; negated/normal findings never
           rule IN).

Asserts the NEW direction is either the gold candidate or "no clear signal",
and never the wrong distractor.

    PYTHONPATH=src python scripts/assert_fused_direction.py
Requires the gnn-llm env (no LLM / no VPN — deterministic KB probe, heavy load).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


evp = _load("evp", "scripts/eval_evidence_precision.py")


# (case, finding, candidates, gold, wrong_distractor_that_must_not_win)
CHECKS = [
    ("mb57_kartagener", "situs inversus",
     ["primary ciliary dyskinesia", "cystic fibrosis",
      "common variable immunodeficiency", "chronic aspiration"],
     "primary ciliary dyskinesia", "chronic aspiration"),
    ("mb55_glucagonoma", "necrolytic migratory erythema",
     ["glucagonoma", "insulinoma", "type 1 diabetes mellitus",
      "type 2 diabetes mellitus", "hypercortisolism"],
     "glucagonoma", "hypercortisolism"),
    ("mb65_cml", "low leukocyte alkaline phosphatase",
     ["chronic myeloid leukemia", "acute myeloid leukemia",
      "acute lymphoblastic leukemia", "chronic lymphocytic leukemia",
      "leukemoid reaction"],
     "chronic myeloid leukemia", "leukemoid reaction"),
    ("mb66_peliosis", "normal serum lipase",
     ["peliosis hepatis", "Budd-Chiari syndrome", "choledocholithiasis",
      "acute pancreatitis", "ectopic pregnancy"],
     "peliosis hepatis", "acute pancreatitis"),
]


def _old_argmax_strength(sigs: dict) -> str:
    """Reproduce the legacy behaviour: argmax additive strength, gap>=0.5."""
    best, best_s = "", 0.0
    for c, s in sigs.items():
        if s["strength"] > best_s:
            best, best_s = c, s["strength"]
    ordered = sorted((s["strength"] for s in sigs.values()), reverse=True)
    gap = (ordered[0] - ordered[1]) if len(ordered) > 1 else ordered[0]
    return best if (best_s >= 1.0 and gap >= 0.5) else ""


# Polarity two-way control (deterministic, no KB load): the negation guard must
# flag normal/absent qualifiers WITHOUT suppressing legitimate ABNORMAL findings.
_POLARITY_CONTROLS = [
    ("normal serum lipase", -1),
    ("lipase within normal limits", -1),
    ("negative pregnancy test", -1),
    ("absent Philadelphia chromosome", -1),
    ("no evidence of malignancy", -1),
    ("PTH not elevated", -1),
    # legitimate abnormal findings must stay +1 (rule-IN allowed)
    ("elevated serum lipase", 1),
    ("low leukocyte alkaline phosphatase", 1),
    ("elevated parathyroid hormone", 1),
    ("basophilia", 1),
    ("situs inversus", 1),
    ("necrolytic migratory erythema", 1),
]


def _check_polarity() -> list[str]:
    print("POLARITY TWO-WAY CONTROL (negated must be -1, abnormal must be +1)")
    fails = []
    for finding, want in _POLARITY_CONTROLS:
        got = evp._finding_polarity(finding)
        ok = got == want
        print(f"    {'OK' if ok else 'FAIL'}  polarity({finding!r}) = "
              f"{got:+d} (want {want:+d})")
        if not ok:
            fails.append(finding)
    print()
    return fails


def main() -> int:
    pol_fail = _check_polarity()
    kb = evp.FusedKB(rag=False)
    print()
    failures = list(pol_fail)
    for case, finding, cands, gold, wrong in CHECKS:
        _, sigs = kb.favored(finding, cands)          # populates cache/signals
        old = _old_argmax_strength(sigs)
        new, _ = kb.favored(finding, cands)
        # mention-fallback-ON variant, to show popularity bias is what we avoid
        kb.mention_fallback = True
        new_fb, _ = kb.favored(finding, cands)
        kb.mention_fallback = False
        ok = (new in ("", gold)) and (new != wrong)
        pol = sigs[cands[0]]["polarity"]
        print(f"[{case}] '{finding}' (polarity={pol:+d})")
        print(f"    OLD strength-argmax : {old or '(none)'}")
        print(f"    NEW favored         : {new or '(no clear signal)'}"
              f"   {'OK' if ok else 'FAIL'}")
        print(f"    NEW (+mention_fb)   : {new_fb or '(no clear signal)'}"
              f"   <- popularity fallback, default OFF")
        per = {c: (f"dir={sigs[c]['dir_strength']}", f"mention={sigs[c]['mention']}",
                   f"lr={sigs[c]['lr']}") for c in cands}
        print(f"    signals             : {per}")
        print()
        if not ok:
            failures.append(case)
    if failures:
        print(f"ASSERTION FAILED for: {failures}")
        return 1
    print("ALL 4 DIRECTION CHECKS PASSED "
          "(new favored is gold or 'no clear signal', never the distractor).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
