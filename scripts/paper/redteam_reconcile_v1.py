#!/usr/bin/env python3
"""Numerical reconciliation for the main-paper contrasts, plus M3b.

Every load-bearing contrast in the main paper is reported either as a marginal
score over the arm's own scored cases or as a paired difference over the cases
both arms scored.  The two calibres do not coincide, which makes some pairs of
reported numbers look arithmetically incompatible.  This script emits, for each
contrast, the full two-by-two agreement table, both calibres of the marginal,
and the exact conditional interval, so that every published figure can be
recomputed from counts.

It also emits
  * the reciprocal-rank reconciliation for DiagnosisArena,
  * the deployed system's paired difference against the strongest baseline,
  * M3b, the propagation footprint of posterior write-back, and
  * the exposure-stratified margin used by the contamination audit.

Outputs analysis/redteam_metrics_v2/reconciliation.json
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import Counter
from math import comb, exp, lgamma, log
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

OUT_DIR = ROOT / "analysis" / "redteam_metrics_v2"

ARM_NAMES = {
    "B00-direct-cot": "Direct CoT",
    "B01-cot-rag": "CoT+RAG",
    "B02-flat-matched-rerank": "Flat rerank",
    "B03-flat-beam": "Flat beam search",
    "B04-dual-inf": "Dual-Inf",
    "B05-mdagents": "MDAgents",
    "B06-mac-single-vendor": "MAC",
    "B07-meddxagent-complete": "MEDDxAgent",
    "B11a-official-diagnosisgpt": "DiagnosisGPT-6B",
    "B11b-cod-prompt-shared-kb": "Chain-of-Diagnosis",
    "B12-sc-cot-5": "Self-consistent CoT",
    "B13-self-refine-1": "Self-refine",
    "B15-medprompt-style": "Medprompt-style",
    "B16-medrag-kg": "MedRAG+KG",
    "B17-imedrag": "i-MedRAG",
}

CELL_NAMES = {
    "M00": "both sites on",
    "AB05": "build-time only",
    "AB06": "decision-time only",
    "AB04": "neither site",
}


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------


def exact_mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Bisection inverse of the regularised incomplete beta, good to 1e-9."""
    if a <= 0:
        return 0.0
    if b <= 0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _betainc(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta by series expansion."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = lgamma(a) + lgamma(b) - lgamma(a + b)
    front = exp(a * log(x) + b * log(1 - x) - lbeta)
    # Lentz continued fraction
    f, c_, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c_ = 1.0 + num / c_
        if abs(c_) < 1e-30:
            c_ = 1e-30
        f *= c_ * d
        if abs(1.0 - c_ * d) < 1e-12:
            break
    return front * (f - 1.0) / a


def mcnemar_ci(b: int, c: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Exact conditional interval on the paired difference (b - c) / n."""
    d = b + c
    if d == 0:
        return (0.0, 0.0)
    alpha = 1 - conf
    lo_p = 0.0 if b == 0 else _beta_ppf(alpha / 2, b, d - b + 1)
    hi_p = 1.0 if b == d else _beta_ppf(1 - alpha / 2, b + 1, d - b)
    return (
        round((2 * lo_p - 1) * d / n, 4),
        round((2 * hi_p - 1) * d / n, 4),
    )


def four_cell(a: list[float], b: list[float]) -> dict:
    n11 = sum(1 for x, y in zip(a, b) if x > 0.5 and y > 0.5)
    n10 = sum(1 for x, y in zip(a, b) if x > 0.5 >= y)
    n01 = sum(1 for x, y in zip(a, b) if y > 0.5 >= x)
    n00 = sum(1 for x, y in zip(a, b) if x <= 0.5 and y <= 0.5)
    n = n11 + n10 + n01 + n00
    lo, hi = mcnemar_ci(n10, n01, n) if n else (0.0, 0.0)
    return {
        "n": n,
        "both_correct": n11,
        "a_only": n10,
        "b_only": n01,
        "both_wrong": n00,
        "acc_a": round((n11 + n10) / n, 4) if n else None,
        "acc_b": round((n11 + n01) / n, 4) if n else None,
        "paired_delta": round((n10 - n01) / n, 4) if n else None,
        "ci95": [lo, hi],
        "p_exact": round(exact_mcnemar(n10, n01), 4),
    }


def read_tsv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


TRUTHY = {"1", "true", "True"}


# --------------------------------------------------------------------------
# A1. MedCaseReasoning equivalence two-by-two
# --------------------------------------------------------------------------


def mcr_equivalence() -> dict:
    import pre_compat_joint as pcj
    from transfer_eval import io_gold
    from transfer_eval.judges import JUDGE_MODEL_SLUG, JudgeCache, LLMJudge

    mcr = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1"
    main = mcr / "compat_synonym_v1"
    ann = pcj.resolve_annotate_dir(main)
    cache = JudgeCache(ann / "judge_cache_llm_rank_metrics.json")
    judge = LLMJudge(client=None, cache=cache)
    parquet = (
        ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
    )

    cells = (
        ("M00", main, "eval_projection_compat"),
        ("AB05", main, "eval_projection_c1_mcr_ab05_precompat"),
        ("AB06", mcr / "c3_ab06_v1", "eval_projection_compat"),
        ("AB04", mcr / "c3_ab04_v1", "eval_projection_compat"),
    )
    ids = sorted(
        p.stem
        for p in (pcj.resolve_annotate_dir(main) / "eval_projection_compat").glob("*.json")
    )
    gold = io_gold.load_gold("medcasereasoning", parquet, case_ids=ids)

    def labels(run_dir: Path, subdir: str, cid: str) -> list[str]:
        fp = pcj.resolve_annotate_dir(run_dir) / subdir / f"{cid}.json"
        if not fp.is_file():
            return []
        doc = json.loads(fp.read_text(encoding="utf-8"))
        return [
            str(r.get("label") or "").strip()
            for r in (doc.get("pred_ddx") or [])
            if str(r.get("label") or "").strip()
        ]

    per_case: dict[str, dict[str, float]] = {}
    for arm, run_dir, subdir in cells:
        per_case[arm] = {}
        for cid in ids:
            gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
            labs = labels(run_dir, subdir, cid)[:5]
            if not gdx or not labs:
                continue
            per_case[arm][cid] = float(bool(judge.mcr_diagnosis_correct(labs[0], gdx)))

    common = sorted(set.intersection(*[set(per_case[a]) for a, *_ in cells]))
    arms = {}
    for arm, *_ in cells:
        own = list(per_case[arm].values())
        sub = [per_case[arm][c] for c in common]
        arms[arm] = {
            "site_configuration": CELL_NAMES[arm],
            "n_own": len(own),
            "acc_own_denominator": round(st.fmean(own), 4),
            "n_common": len(sub),
            "acc_common_denominator": round(st.fmean(sub), 4),
            "n_correct_common": int(sum(sub)),
        }
    contrasts = []
    for a, b, label in (
        ("M00", "AB05", "decision-time routing removed, build-time retained"),
        ("AB06", "AB04", "decision-time routing removed, build-time absent"),
        ("M00", "AB06", "build-time de-duplication removed, routing retained"),
        ("AB05", "AB04", "build-time de-duplication removed, routing absent"),
        ("M00", "AB04", "both sites removed"),
    ):
        cell = four_cell(
            [per_case[a][c] for c in common], [per_case[b][c] for c in common]
        )
        cell["contrast"] = label
        cell["a"], cell["b"] = CELL_NAMES[a], CELL_NAMES[b]
        contrasts.append(cell)
    marg = {a: arms[a]["acc_common_denominator"] for a, *_ in cells}
    return {
        "arms": arms,
        "contrasts": contrasts,
        "n_common": len(common),
        "interaction_on_common": round(
            (marg["M00"] - marg["AB04"])
            - ((marg["M00"] - marg["AB05"]) + (marg["M00"] - marg["AB06"])),
            4,
        ),
        "per_case_top1": {a: per_case[a] for a, *_ in cells},
    }


# --------------------------------------------------------------------------
# A2. DiagnosisArena axis contrasts, four-cell form
# --------------------------------------------------------------------------


def da_axis() -> dict:
    src = json.loads(
        (ROOT / "runs/paper_v1/ablations_block1_axis_cascade.json").read_text()
    )
    rows = []
    for arm, blk in (src.get("arms") or {}).items():
        for caliber in ("full_sample", "nonempty_conditional"):
            d = blk.get(caliber)
            if not isinstance(d, dict) or "b_m00_only" not in d:
                continue
            n = int(d["n_paired"])
            b = int(d["b_m00_only"])
            c = int(d["c_arm_only"])
            ref = round(float(d["m00_opt1"]) * n)
            n11 = ref - b
            lo, hi = mcnemar_ci(b, c, n)
            rows.append(
                {
                    "arm": arm,
                    "caliber": caliber,
                    "n": n,
                    "both_correct": n11,
                    "reference_only": b,
                    "variant_only": c,
                    "both_wrong": n - n11 - b - c,
                    "acc_reference": round(float(d["m00_opt1"]), 4),
                    "acc_variant": round(float(d["arm_opt1"]), 4),
                    "paired_delta": round((b - c) / n, 4),
                    "ci95": [lo, hi],
                    "p_exact": round(exact_mcnemar(b, c), 4),
                    "consistency_check": abs(
                        (n11 + c) / n - float(d["arm_opt1"])
                    )
                    < 0.011,
                }
            )
    return {"rows": rows}


# --------------------------------------------------------------------------
# A3. reciprocal rank reconciliation on DiagnosisArena
# --------------------------------------------------------------------------


def da_reciprocal_rank() -> dict:
    rows = [
        r
        for r in read_tsv(
            ROOT / "analysis/l1_recall_failure_v1/smoke_synonym_bind_live/metrics_all100.tsv"
        )
        if r.get("arm") == "R_compat_live"
    ]
    rr = [float(r.get("option_rr") or 0.0) for r in rows]
    n = len(rr)
    dist = Counter(round(1 / v) if v > 0 else 0 for v in rr)
    untruncated = st.fmean(rr)
    truncated = st.fmean(v if v >= 0.5 else 0.0 for v in rr)

    baselines = []
    for r in read_tsv(
        ROOT / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv"
    ):
        pred = Path((r.get("pred_dir") or "").strip())
        fp = pred / "mapper" / "records.json"
        if not str(pred) or not fp.is_file():
            continue
        vals = [
            float(x.get("option_rr") or 0.0)
            for x in json.loads(fp.read_text()).get("records", [])
        ]
        if not vals:
            continue
        baselines.append(
            {
                "arm": r.get("arm"),
                "name": ARM_NAMES.get((r.get("arm") or "").strip(), r.get("arm")),
                "mrr_untruncated": round(st.fmean(vals), 4),
                "mrr_truncated_at_2": round(
                    st.fmean(v if v >= 0.5 else 0.0 for v in vals), 4
                ),
                "n_credited_beyond_rank_2": sum(1 for v in vals if 0 < v < 0.5),
            }
        )
    return {
        "n": n,
        "credited_rank_distribution": {str(k): v for k, v in sorted(dist.items())},
        "top1": round(sum(1 for v in rr if v >= 1.0) / n, 4),
        "top2": round(sum(1 for v in rr if v >= 0.5) / n, 4),
        "mrr_untruncated": round(untruncated, 4),
        "mrr_truncated_at_2": round(truncated, 4),
        "difference": round(untruncated - truncated, 4),
        "n_cases_credited_beyond_rank_2": sum(1 for v in rr if 0 < v < 0.5),
        "baselines": baselines,
        "n_baselines_with_rank3_credit": sum(
            1 for b in baselines if b["n_credited_beyond_rank_2"]
        ),
    }


# --------------------------------------------------------------------------
# A4. deployed system against the strongest baseline, paired
# --------------------------------------------------------------------------


def _baseline_case_rows(pred_dir: Path) -> dict[str, bool]:
    nat = pred_dir / "mapper" / "records.json"
    if not nat.is_file():
        return {}
    return {
        str(r.get("source_id")): bool(r.get("option_top1"))
        for r in json.loads(nat.read_text()).get("records", [])
    }


def da_vs_baselines() -> dict:
    ours_rows = [
        r
        for r in read_tsv(
            ROOT / "analysis/l1_recall_failure_v1/smoke_synonym_bind_live/metrics_all100.tsv"
        )
        if r.get("arm") == "R_compat_live"
    ]
    ours = {str(r["case_id"]): r.get("option_top1") in TRUTHY for r in ours_rows}
    summary = read_tsv(
        ROOT / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv"
    )
    out = []
    for r in summary:
        arm = (r.get("arm") or "").strip()
        pred_dir = Path((r.get("pred_dir") or "").strip())
        base = _baseline_case_rows(pred_dir) if str(pred_dir) else {}
        common = sorted(set(ours) & set(base))
        if len(common) < 50:
            continue
        cell = four_cell(
            [float(ours[c]) for c in common], [float(base[c]) for c in common]
        )
        cell["arm"] = arm
        cell["name"] = ARM_NAMES.get(arm, arm)
        out.append(cell)
    order = sorted(range(len(out)), key=lambda i: out[i]["p_exact"])
    running = 0.0
    for rank, i in enumerate(order):
        adj = max(running, min(1.0, (len(out) - rank) * out[i]["p_exact"]))
        running = adj
        out[i]["p_holm"] = round(adj, 4)
        out[i]["survives_holm_05"] = bool(adj < 0.05)
    out.sort(key=lambda x: -(x["acc_b"] or 0))
    return {
        "rows": out,
        "reference": "APHHM",
        "n_comparisons": len(out),
        "n_unadjusted_below_05": sum(1 for r in out if r["p_exact"] < 0.05),
        "n_holm_below_05": sum(1 for r in out if r["survives_holm_05"]),
    }


# --------------------------------------------------------------------------
# A5. M3b propagation footprint of posterior write-back
# --------------------------------------------------------------------------


def m3b_propagation() -> dict:
    """How much of the emitted output moves when write-back is switched off."""
    ox = ROOT / "logs/open_xddx_ox_seq100_v1"
    hot = ox / "compat_synonym_noemit_fopt_live_v1/annotate/eval_projection_closed_live_mac"
    cold = ox / "c2_ab13_v1/annotate/eval_projection_c2_ab13"

    def emitted(d: Path) -> dict[str, list[str]]:
        if not d.is_dir():
            return {}
        out = {}
        for fp in sorted(d.glob("*.json")):
            doc = json.loads(fp.read_text(encoding="utf-8"))
            out[fp.stem] = [
                str(x.get("label") or "").strip().lower()
                for x in (doc.get("pred_ddx") or [])
            ]
        return out

    a, b = emitted(hot), emitted(cold)
    common = sorted(set(a) & set(b))
    if not common:
        return {"error": "no common emitted projections", "n": 0}
    changed_set = sum(1 for c in common if set(a[c]) != set(b[c]))
    changed_order = sum(1 for c in common if a[c] != b[c])
    changed_top1 = sum(
        1 for c in common if (a[c][:1] or [""]) != (b[c][:1] or [""])
    )
    jac = [
        len(set(a[c]) & set(b[c])) / len(set(a[c]) | set(b[c]))
        if (set(a[c]) | set(b[c]))
        else 1.0
        for c in common
    ]
    factorial = json.loads(
        (ROOT / "runs/paper_v1/ablations_block3_state_factorial.json").read_text()
    )
    paired = (factorial.get("factorial_2x2") or {}).get("paired_case_f1", {})
    return {
        "n": len(common),
        "frac_emitted_set_changed": round(changed_set / len(common), 4),
        "frac_emitted_order_changed": round(changed_order / len(common), 4),
        "frac_first_label_changed": round(changed_top1 / len(common), 4),
        "mean_jaccard_hot_vs_cold": round(st.fmean(jac), 4),
        "scored_movement": paired.get("writeback_locked_m00_vs_ab13"),
    }


# --------------------------------------------------------------------------
# A6. exposure-stratified margin on MedCaseReasoning
# --------------------------------------------------------------------------


def exposure_stratified(mcr_per_case: dict[str, dict[str, float]]) -> dict:
    expo_doc = json.loads((OUT_DIR / "metrics_m7m8.json").read_text())
    expo = set(
        (expo_doc.get("m8_realised_exposure", {}).get("MedCaseReasoning", {}) or {}).get(
            "exposed_case_ids", []
        )
    )
    ours = mcr_per_case.get("M00", {})
    base_root = ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1"
    rows = []
    for arm_dir in sorted(base_root.iterdir()) if base_root.is_dir() else []:
        cs = arm_dir / "replicate_01" / "annotate" / "official_eval_llm" / "case_scores"
        if not cs.is_dir():
            continue
        hits = {}
        for fp in sorted(cs.glob("*.json")):
            try:
                doc = json.loads(fp.read_text())
            except Exception:
                continue
            h = doc.get("diagnostic_hit")
            if h is not None:
                hits[fp.stem] = float(bool(h))
        if not hits:
            continue
        rows.append((arm_dir.name, hits))
    if not rows:
        return {"error": "no baseline per-case scores"}
    rows.sort(key=lambda kv: -st.fmean(kv[1].values()))
    best_arm, best = rows[0]
    common = sorted(set(ours) & set(best))
    strata = {}
    for name, sel in (
        ("exposed", [c for c in common if c in expo]),
        ("unexposed", [c for c in common if c not in expo]),
    ):
        if not sel:
            continue
        strata[name] = {
            "n": len(sel),
            "aphhm": round(st.fmean(ours[c] for c in sel), 4),
            "baseline": round(st.fmean(best[c] for c in sel), 4),
            "margin": round(
                st.fmean(ours[c] for c in sel) - st.fmean(best[c] for c in sel), 4
            ),
        }
    return {
        "benchmark": "MedCaseReasoning",
        "strongest_baseline": ARM_NAMES.get(best_arm, best_arm),
        "n_common": len(common),
        "n_exposed": sum(1 for c in common if c in expo),
        "strata": strata,
        "margin_difference_exposed_minus_unexposed": (
            round(
                strata["exposed"]["margin"] - strata["unexposed"]["margin"], 4
            )
            if {"exposed", "unexposed"} <= set(strata)
            else None
        ),
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    eq = mcr_equivalence()
    per_case = eq.pop("per_case_top1")
    doc = {
        "mcr_equivalence_two_by_two": eq,
        "da_axis_four_cell": da_axis(),
        "da_reciprocal_rank": da_reciprocal_rank(),
        "da_vs_baselines_paired": da_vs_baselines(),
        "m3b_propagation_footprint": m3b_propagation(),
        "exposure_stratified_margin": exposure_stratified(per_case),
    }
    (OUT_DIR / "reconciliation.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(doc, indent=2, ensure_ascii=False)[:9000])
    print("WROTE", OUT_DIR / "reconciliation.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
