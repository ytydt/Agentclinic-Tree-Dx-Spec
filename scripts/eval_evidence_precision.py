"""Step 4 of the TALP eval expansion: BEYOND COVERAGE — precision / noise +
a filter-step study.

Coverage (Block 2) asks "can a source SUPPLY a discriminating signal for a key
finding?". It says nothing about the OPPOSITE failure: how much of the evidence
that actually reaches the annotator is irrelevant NOISE that dilutes the
posterior (the "evidence collapse" mechanism in RESIDUAL_MISS_ROOTCAUSE §13b).
This harness measures the complement:

  build_fused_discriminator_hints(kb, case)  — the reusable best-knowledge
      fusion (LR-grounded + CPG-mined + case_report-mined) that Step 2's LLM+KB
      arm injects. For each key finding x candidate it exposes the RAW grounded
      signal (LR / mention counts) and the KB-implied favored candidate, WITHOUT
      leaking the dataset label.

  PRECISION metric — take the finding pool that WOULD reach the annotator
      (approx: findings that get a non-null LR/hint or corpus mention for the
      candidate set), classify each as DISCRIMINATING (a dataset key finding:
      rule_in_gold / rule_out_distractor / decisive) vs NOISE (shared_non-
      discriminating / parent_child_trap-used-as-ruleout), and report the
      signal/noise ratio per case.

  FILTER-STEP study — the four candidate filter points on the path
      vignette → _gather_atomic_findings (top-8) → TALP select → bundler
      min_marginal_ig gate → annotator LR injection. For each, estimate noise
      REMOVED vs signal LOST, to recommend WHERE irrelevant evidence should be
      dropped.

    PYTHONPATH=src python scripts/eval_evidence_precision.py [--rag] [--top-k 6]
Requires the gnn-llm env (no LLM / no VPN — deterministic KB probe).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
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


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_lrcov = _load("lrcov", "scripts/eval_lr_coverage_isolated.py")
_cov = _load("dcov", "scripts/eval_discriminator_coverage.py")

# Minimum favored/second-strongest MENTION ratio required to call a direction
# from corpus mention counts ALONE (i.e. when no grounded directional signal
# exists). Equal mention counts (ratio ~1) are treated as non-directional.
_MENTION_RATIO_MIN = 1.5
# Qualifiers that NEGATE / normalise a finding: the finding then argues AGAINST
# the disease that its bare marker would rule IN (e.g. "normal serum lipase"
# must not rule IN acute pancreatitis). Sign-blind retrieval loses this.
_NEG_QUALIFIER_RE = re.compile(
    r"\b(normal|negative|absent|unremarkable|"
    r"within normal limits|wnl|no evidence of|not elevated|non[- ]?elevated|"
    r"ruled out|negative for|without)\b", re.I)


def _finding_polarity(finding: str) -> int:
    """+1 = finding present / abnormal (default); -1 = negated or normalised.

    A -1 finding must never be turned into a rule-IN for the disease its bare
    marker points to; sign/qualifier-blind fuzzy retrieval is exactly the
    "normal serum lipase -> pancreatitis LR+=100" bug (A2/A4/A8)."""
    return -1 if _NEG_QUALIFIER_RE.search(finding or "") else 1


# ─────────────────────────────────────────────────────────────────────────────
# Fused best-knowledge block (LR-grounded + CPG-mined + case_report-mined).
# ─────────────────────────────────────────────────────────────────────────────
class FusedKB:
    """Loads the three knowledge sources once and exposes per-(finding,candidate)
    grounded signals. Heavy to build (indices); reuse a single instance."""

    def __init__(self, rag: bool = False, top_k: int = 6,
                 mention_fallback: bool = False):
        self.top_k = top_k
        # When True, direction may be decided by a comparative MENTION ratio if
        # no grounded directional signal exists. Default OFF: mention counts are
        # a coverage/popularity signal, and letting them drive direction is the
        # very bug being fixed (e.g. low-LAP has NO LR, and leukemoid reaction
        # is merely written about more -> would wrongly out-point CML). With the
        # fallback OFF a data-gap finding honestly returns "no clear signal".
        self.mention_fallback = mention_fallback
        print("[FusedKB] Layer-A LIRICAL ...", flush=True)
        self.A = _lrcov.LiricalPhenotypeLR(KR / "phenotype.hpoa", KR / "hp.obo")
        print("[FusedKB] Layer-B anchor retriever ...", flush=True)
        self.kr = _lrcov.build_retriever(rag)
        self._rag = rag
        print("[FusedKB] CPG + case_report corpora ...", flush=True)
        self.cpg = _cov.build_rag(DATA / "corpus" / "cpg_index")
        self.crep = _cov.build_rag(DATA / "corpus" / "case_report_index")
        self._cache: dict = {}

    def signal(self, finding: str, candidate: str, hpo_hint: str = "") -> dict:
        """Raw grounded signal of `finding` for `candidate` (no dataset label)."""
        key = (finding, candidate, hpo_hint)
        if key in self._cache:
            return self._cache[key]
        ids = self.A.resolve_disease(candidate)
        hpo = hpo_hint or self.A.resolve_hpo(finding)
        a = self.A.lr(hpo, ids)
        b = _lrcov.layer_b(self.kr, finding, candidate, fast=not self._rag)
        cpg = _cov.mine_corpus(self.cpg, candidate, finding, self.top_k)
        cr = _cov.mine_corpus(self.crep, candidate, finding, self.top_k)
        lr_val = None
        if a:
            lr_val = a["lr_positive"]
        elif b["grounded"] and isinstance(b["lr"], (int, float)):
            lr_val = float(b["lr"])
        # ── DIRECTIONAL strength: ONLY grounded, sign-bearing signals ──────────
        # (likelihood ratio + grounded layer-B). These actually point AT a
        # candidate. Corpus mention counts are DELIBERATELY excluded here —
        # they are a coverage/popularity signal, not a direction (fixing the
        # "fused KB points the wrong way" bug: mb57 LR~26 vs CPG5+CR6, etc.).
        dir_strength = 0.0
        if lr_val:
            dir_strength += min(4.0, math.log10(max(lr_val, 1.0)) + 1.0)
        if b["grounded"]:
            dir_strength += 2.0
        # ── NON-directional MENTION mass: kept SEPARATE, used only as a
        #    comparative tie-breaker when NO directional signal exists ─────────
        mention = int(cpg) + int(cr)
        out = {"lr": lr_val, "b_grounded": b["grounded"], "b_tier": b["tier"],
               "cpg": cpg, "cr": cr,
               "dir_strength": round(dir_strength, 2), "mention": mention,
               "polarity": _finding_polarity(finding),
               # legacy scalar (retained for back-compat; NOT used for direction)
               "strength": round(dir_strength + min(2.0, 0.5 * cpg)
                                  + min(2.0, 0.5 * cr), 2)}
        self._cache[key] = out
        return out

    def favored(self, finding: str, candidates: list[str],
                hpo_hint: str = "") -> tuple[str, dict]:
        """The candidate the KB points to, + per-candidate signal map.

        Direction is decided by GROUNDED DIRECTIONAL signal (LR / layer-B) with
        a minimal separation. Corpus mention counts only break a tie when NO
        directional signal exists AND the favoured candidate is mentioned
        meaningfully more than the runner-up (ratio >= _MENTION_RATIO_MIN);
        equal mentions -> "no clear signal". A negated/normal finding is never
        turned into a rule-IN (polarity guard)."""
        sigs = {c: self.signal(finding, c, hpo_hint) for c in candidates}
        polarity = sigs[candidates[0]]["polarity"] if candidates else 1

        # 1) direction from grounded directional signal
        dir_best, dir_val = "", 0.0
        for c, s in sigs.items():
            if s["dir_strength"] > dir_val:
                dir_best, dir_val = c, s["dir_strength"]
        dscores = sorted((s["dir_strength"] for s in sigs.values()), reverse=True)
        dgap = (dscores[0] - dscores[1]) if len(dscores) > 1 else dscores[0]
        fav = dir_best if (dir_val >= 1.0 and dgap >= 0.5) else ""

        # 2) mention only as a comparative fallback when direction is absent
        #    AND explicitly enabled (default OFF — see mention_fallback docstring)
        if not fav and self.mention_fallback:
            m_best, m_val = "", 0
            for c, s in sigs.items():
                if s["mention"] > m_val:
                    m_best, m_val = c, s["mention"]
            mscores = sorted((s["mention"] for s in sigs.values()), reverse=True)
            second = mscores[1] if len(mscores) > 1 else 0
            ratio = (m_val / second) if second > 0 else (m_val and float("inf"))
            if m_val >= 2 and ratio >= _MENTION_RATIO_MIN:
                fav = m_best

        # 3) polarity guard: a negated / normal finding must not rule IN
        if fav and polarity < 0:
            fav = ""
        return fav, sigs


def build_fused_discriminator_hints(kb: FusedKB, case: dict,
                                    max_findings: int = 8) -> dict:
    """Fuse the three sources into ONE injectable block for a case.

    Returns {"block": <str for prompt injection>, "lines": [...structured...]}.
    Exposes per-candidate grounded numbers + a KB-implied favored candidate; the
    dataset `role`/`favors` labels are NEVER injected (that would leak the test).
    """
    cand_names = [c["name"] for c in case["candidates"]]
    lines = []
    for f in case["findings"][:max_findings]:
        fav, sigs = kb.favored(f["finding"], cand_names, f.get("hpo") or "")
        per = []
        for c in cand_names:
            s = sigs[c]
            bits = []
            if s["lr"]:
                bits.append(f"LR~{s['lr']:.0f}")
            if s["cpg"]:
                bits.append(f"CPG{s['cpg']}")
            if s["cr"]:
                bits.append(f"CR{s['cr']}")
            if bits:
                per.append(f"{c}: {' '.join(bits)}")
        lines.append({"finding": f["finding"], "kb_favored": fav,
                      "per_candidate": per,
                      "signals": {c: sigs[c] for c in cand_names}})
    block_rows = []
    for ln in lines:
        if not ln["per_candidate"]:
            continue
        tail = f" -> KB points to {ln['kb_favored']}" if ln["kb_favored"] \
            else " -> no clear KB signal"
        block_rows.append(f"- {ln['finding']}: "
                          f"{'; '.join(ln['per_candidate'])}{tail}")
    block = ("GROUNDED KNOWLEDGE-BASE SIGNALS (from likelihood-ratio tables + "
             "guideline/case-report mining; may be incomplete or noisy):\n"
             + ("\n".join(block_rows) if block_rows
                else "  (no grounded signal found for these candidates)"))
    return {"block": block, "lines": lines}


# ─────────────────────────────────────────────────────────────────────────────
# Precision / noise classification of the annotator-bound finding pool.
# ─────────────────────────────────────────────────────────────────────────────
_SIGNAL_ROLES = {"rule_in_gold", "rule_out_distractor"}
_NOISE_ROLES = {"shared_nondiscriminating", "parent_child_trap"}


def _has_lr_hint(kb: FusedKB, finding: str, cand_names: list[str],
                 hpo_hint: str) -> bool:
    """Approximate the annotator top-8 LR-injection gate: does ANY candidate get
    a non-null LR/hint or corpus mention for this finding?"""
    for c in cand_names:
        s = kb.signal(finding, c, hpo_hint)
        if s["lr"] or s["b_grounded"] or s["cpg"] or s["cr"]:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag", action="store_true")
    ap.add_argument("--top-k", type=int, default=6)
    ap.add_argument("--tag", default="precision")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "talp_discrimination_cases.json").read_text())
    kb = FusedKB(rag=args.rag, top_k=args.top_k)
    print()

    rows = []
    # filter-step aggregate: for each step, noise removed vs signal lost
    steps = ["atomic_top8", "talp_select", "bundler_ig_gate", "annotator_lr"]
    fagg = {s: {"noise_removed": 0, "signal_lost": 0} for s in steps}
    prec_agg = {"signal": 0, "noise": 0, "reach_signal": 0, "reach_noise": 0}

    for case in ds["cases"]:
        cand_names = [c["name"] for c in case["candidates"]]
        fused = build_fused_discriminator_hints(kb, case)
        case_signal = case_noise = 0
        reach_signal = reach_noise = 0
        finding_reports = []
        for f in case["findings"]:
            role = f.get("role", "")
            is_signal = role in _SIGNAL_ROLES or bool(f.get("decisive"))
            is_noise = role in _NOISE_ROLES and not f.get("decisive")
            in_vig = bool(f.get("in_vignette"))
            has_kb = _has_lr_hint(kb, f["finding"], cand_names, f.get("hpo") or "")
            # KB discriminates = a single candidate is favored with separation
            fav, _ = kb.favored(f["finding"], cand_names, f.get("hpo") or "")
            kb_discriminates = bool(fav)

            if is_signal:
                case_signal += 1
            if is_noise:
                case_noise += 1

            # ---- FILTER-STEP simulation --------------------------------------
            # 1) atomic top-8 extraction keeps only vignette-present findings.
            if not in_vig:
                if is_noise:
                    fagg["atomic_top8"]["noise_removed"] += 1
                if is_signal:
                    fagg["atomic_top8"]["signal_lost"] += 1
                # dropped here -> does not reach later steps
                finding_reports.append({"finding": f["finding"], "role": role,
                                        "dropped_at": "atomic_top8",
                                        "is_signal": is_signal,
                                        "is_noise": is_noise, "has_kb": has_kb})
                continue
            # 2) TALP select: SHARED-trap 0/9 => it does NOT drop shared/trap noise.
            #    (models the empirical finding; nothing removed here)
            # 3) bundler min_marginal_ig gate: drops findings with NO discriminating
            #    KB signal (low information gain proxy).
            if not kb_discriminates:
                if is_noise:
                    fagg["bundler_ig_gate"]["noise_removed"] += 1
                if is_signal:
                    fagg["bundler_ig_gate"]["signal_lost"] += 1
            # 4) annotator LR injection: keeps findings that get a non-null LR/hint.
            if not has_kb:
                if is_noise:
                    fagg["annotator_lr"]["noise_removed"] += 1
                if is_signal:
                    fagg["annotator_lr"]["signal_lost"] += 1

            # ---- PRECISION: what reaches the annotator (has a LR/hint) ---------
            if has_kb:
                if is_signal:
                    reach_signal += 1
                if is_noise:
                    reach_noise += 1
            finding_reports.append({"finding": f["finding"], "role": role,
                                    "in_vignette": in_vig, "has_kb": has_kb,
                                    "kb_discriminates": kb_discriminates,
                                    "is_signal": is_signal, "is_noise": is_noise})

        prec_agg["signal"] += case_signal
        prec_agg["noise"] += case_noise
        prec_agg["reach_signal"] += reach_signal
        prec_agg["reach_noise"] += reach_noise
        reach_tot = reach_signal + reach_noise
        precision = reach_signal / reach_tot if reach_tot else 0.0
        rows.append({"case": case["id"],
                     "n_signal": case_signal, "n_noise": case_noise,
                     "reach_signal": reach_signal, "reach_noise": reach_noise,
                     "annotator_precision": round(precision, 3),
                     "fused_block": fused["block"],
                     "findings": finding_reports})
        print(f"[{case['id']:<16}] signal={case_signal} noise={case_noise} | "
              f"reach S/N={reach_signal}/{reach_noise} "
              f"precision={precision:.0%}", flush=True)

    rt = prec_agg["reach_signal"] + prec_agg["reach_noise"]
    print("\n" + "=" * 74)
    print("EVIDENCE PRECISION (finding pool that reaches the annotator)")
    print(f"  key SIGNAL findings total : {prec_agg['signal']}")
    print(f"  NOISE findings total      : {prec_agg['noise']}")
    print(f"  reach annotator  signal   : {prec_agg['reach_signal']}")
    print(f"  reach annotator  noise    : {prec_agg['reach_noise']}")
    print(f"  ANNOTATOR PRECISION       : {prec_agg['reach_signal']}/{rt} "
          f"({(100*prec_agg['reach_signal']//rt) if rt else 0}%)")
    print("\nFILTER-STEP STUDY (noise removed vs signal lost, summed over cases)")
    print(f"  {'step':<20} {'noise_removed':>14} {'signal_lost':>12}")
    for s in steps:
        print(f"  {s:<20} {fagg[s]['noise_removed']:>14} "
              f"{fagg[s]['signal_lost']:>12}")

    out = PROJECT_ROOT / "logs" / f"evidence_{args.tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        {"precision": prec_agg, "filter_steps": fagg, "rows": rows},
        ensure_ascii=False, indent=2, default=str))
    print(f"\n  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
