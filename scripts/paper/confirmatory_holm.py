#!/usr/bin/env python3
"""§7 five confirmatory contrasts with Holm correction.

Contrasts (paper_ablation_plan.md §7):
  C1  M00 vs AB03   (DA option @1, full sample — default block-1 caliber)
  C2  M00 vs AB10b  (MCR LLM any-hit@5 permutation on perturbable subset)
  C3  M00 vs AB13   (OX micro-F1 paired case-bootstrap)
  C4  M00 vs AB28   (DA option @1 true paired from metrics_typed_all100.tsv)
  C5  M00 vs AB21   (DA option @1 selector exclusion; null allowed)

Endpoint heterogeneity is intentional and registered. Writes
runs/paper_v1/confirmatory_holm_five.json.
"""
from __future__ import annotations

import csv
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runs/paper_v1/confirmatory_holm_five.json"
B1 = ROOT / "runs/paper_v1/ablations_block1_axis_cascade.json"
B3 = ROOT / "runs/paper_v1/ablations_block3_state_factorial.json"
B4 = ROOT / "runs/paper_v1/ablations_block4_selector_exclusion.json"
AB10B = ROOT / "runs/paper_v1/ablations_c1_ab10b_llm_permutation.json"
AB28_TSV = (
    ROOT
    / "analysis/l1_gold_recall_v1/smoke_typed_remap/metrics_typed_all100.tsv"
)
OX = ROOT / "logs/open_xddx_ox_seq100_v1"
M00_SCORES = (
    OX
    / "compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_closed_live_mac/case_scores"
)
AB13_SCORES = OX / "c2_ab13_v1/annotate/official_eval_llm_c2_ab13/case_scores"

N_BOOT = 5000
BOOT_SEED = 20260729


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    lo = min(k, n - k)
    total = sum(math.comb(n, i) for i in range(0, lo + 1))
    return min(1.0, 2.0 * total / (2**n))


def _holm(rows: list[dict[str, Any]], alpha: float = 0.05) -> list[dict[str, Any]]:
    ordered = sorted(enumerate(rows), key=lambda iv: iv[1]["p_raw"])
    m = len(rows)
    adjusted: list[float | None] = [None] * m
    running_max = 0.0
    for rank, (idx, row) in enumerate(ordered):
        adj = min(1.0, float(row["p_raw"]) * (m - rank))
        running_max = max(running_max, adj)
        adjusted[idx] = running_max
    out = []
    for i, row in enumerate(rows):
        out.append(
            {
                **row,
                "p_holm": round(float(adjusted[i]), 6),
                "survives_holm_0.05": float(adjusted[i]) < alpha,
            }
        )
    return out


def _load_case_tp(path: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for p in sorted(path.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        diag = d.get("diagnostic") or {}
        out[p.stem] = {
            "tp": float(diag.get("tp") or 0.0),
            "n_pred": float(diag.get("n_pred") or 0.0),
            "n_gold": float(diag.get("n_gold") or 0.0),
        }
    return out


def _micro_f1(scores: dict[str, dict[str, float]], cids: list[str]) -> float:
    tp = sum(scores[c]["tp"] for c in cids)
    n_pred = sum(scores[c]["n_pred"] for c in cids)
    n_gold = sum(scores[c]["n_gold"] for c in cids)
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return (2 * p * r / (p + r)) if (p + r) else 0.0


def _paired_micro_f1_bootstrap(
    a: dict[str, dict[str, float]],
    b: dict[str, dict[str, float]],
    *,
    n_boot: int = N_BOOT,
    seed: int = BOOT_SEED,
) -> dict[str, Any]:
    """Paired case-bootstrap of micro-F1(a) − micro-F1(b)."""
    cids = sorted(set(a) & set(b))
    n = len(cids)
    point = _micro_f1(a, cids) - _micro_f1(b, cids)
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(n_boot):
        samp = [cids[rng.randrange(n)] for _ in range(n)]
        deltas.append(_micro_f1(a, samp) - _micro_f1(b, samp))
    deltas.sort()
    # Add-one one-sided p for H1: Δ>0 (a better than b)
    n_le0 = sum(1 for d in deltas if d <= 0.0)
    p_one = (n_le0 + 1) / (n_boot + 1)
    p_two = min(1.0, 2.0 * p_one)
    return {
        "n": n,
        "micro_f1_a": round(_micro_f1(a, cids), 6),
        "micro_f1_b": round(_micro_f1(b, cids), 6),
        "delta_micro_f1": round(point, 6),
        "bootstrap_ci95": {
            "lo": round(deltas[int(0.025 * (n_boot - 1))], 6),
            "hi": round(deltas[int(0.975 * (n_boot - 1))], 6),
            "n_boot": n_boot,
            "seed": seed,
        },
        "p_one_sided_addone": round(p_one, 6),
        "p_two_sided_addone": round(p_two, 6),
        "n_boot_delta_le_0": n_le0,
    }


def _ab28_true_paired(tsv: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(tsv.open(encoding="utf-8"), delimiter="\t"))
    b = c = ties = 0
    for r in rows:
        ca = int(float(r["compat_opt1"] or 0))
        ty = int(float(r["typed_opt1"] or 0))
        if ca > ty:
            b += 1
        elif ty > ca:
            c += 1
        else:
            ties += 1
    n = len(rows)
    compat_rate = sum(int(float(r["compat_opt1"] or 0)) for r in rows) / n
    typed_rate = sum(int(float(r["typed_opt1"] or 0)) for r in rows) / n
    return {
        "n": n,
        "compat_opt1": round(compat_rate, 4),
        "typed_opt1": round(typed_rate, 4),
        "delta": round(compat_rate - typed_rate, 4),
        "b_compat_only": b,
        "c_typed_only": c,
        "n_ties": ties,
        "sign_p_two_sided": round(_binom_two_sided(min(b, c), b + c), 6),
        "source_tsv": str(tsv.relative_to(ROOT)),
    }


def main() -> int:
    b1 = json.loads(B1.read_text(encoding="utf-8"))
    b3 = json.loads(B3.read_text(encoding="utf-8"))
    b4 = json.loads(B4.read_text(encoding="utf-8"))
    ab10b = json.loads(AB10B.read_text(encoding="utf-8"))

    # C1: AB03 full-sample option @1
    ab03 = b1["arms"]["ab03"]["full_sample"]
    c1 = {
        "id": "C1",
        "contrast": "M00 vs AB03 (random axis)",
        "supports": "Contribution 1",
        "slice": "DA d2_seq100",
        "endpoint": "option @1 (full sample)",
        "effect": ab03["delta_opt1"],
        "effect_note": "Δ = M00 − arm (positive = M00 better)",
        "n": ab03["n_paired"],
        "discordant_bc": [ab03["b_m00_only"], ab03["c_arm_only"]],
        "p_raw": ab03["sign_p_two_sided"],
        "p_source": "exact binomial sign test on discordant pairs",
    }

    # C2: AB10b LLM any-hit permutation (one-sided as registered)
    hit = ab10b["arms"]["AB10b"]["llm_any_hit"]
    c2 = {
        "id": "C2",
        "contrast": "M00 vs AB10b (count-matched semantics-blind merge)",
        "supports": "Contribution 2",
        "slice": "MCR mcr_val_seq100 (perturbable n=42)",
        "endpoint": "Prompt7 LLM any-hit@5 (permutation)",
        "effect": round(hit["m00"] - hit["null_mean"], 4),
        "effect_note": "M00 − null_mean on perturbable subset",
        "n": hit["n_cases"],
        "p_raw": hit["p_one_sided"],
        "p_source": "one-sided permutation (200 seeds) as registered for C2",
    }

    # C3: paired case-bootstrap of micro-F1 (registered OX diagnostic endpoint)
    micro = _paired_micro_f1_bootstrap(
        _load_case_tp(M00_SCORES), _load_case_tp(AB13_SCORES)
    )
    case_f1 = b3["factorial_2x2"]["paired_case_f1"]["writeback_locked_m00_vs_ab13"]
    c3 = {
        "id": "C3",
        "contrast": "M00 vs AB13 (cold posterior / no writeback)",
        "supports": "Contribution 3",
        "slice": "OX ox_seq100",
        "endpoint": "micro-F1 (paired case-bootstrap)",
        "effect": micro["delta_micro_f1"],
        "effect_note": (
            f"micro-F1 {micro['micro_f1_a']} → {micro['micro_f1_b']}; "
            f"bootstrap 95% CI [{micro['bootstrap_ci95']['lo']}, "
            f"{micro['bootstrap_ci95']['hi']}]"
        ),
        "n": micro["n"],
        "bootstrap": micro,
        "case_f1_auxiliary": {
            "mean_delta": case_f1["mean_delta"],
            "discordant_bc": [case_f1["n_a_better"], case_f1["n_b_better"]],
            "sign_p_two_sided": case_f1["sign_p_two_sided"],
            "bootstrap_ci95": case_f1["bootstrap_ci95"],
        },
        "p_raw": micro["p_two_sided_addone"],
        "p_source": (
            f"two-sided add-one paired case-bootstrap of micro-F1 "
            f"({N_BOOT} resamples, seed={BOOT_SEED}); "
            "case-F1 sign test retained as auxiliary"
        ),
    }

    # C4: true paired option @1 from smoke_typed_remap metrics TSV
    ab28 = _ab28_true_paired(AB28_TSV)
    c4 = {
        "id": "C4",
        "contrast": "M00 vs AB28 (full-leaf inject + typed remap)",
        "supports": "Contribution 4",
        "slice": "DA (historical smoke_typed_remap all100; reused)",
        "endpoint": "option @1 (true paired)",
        "effect": ab28["delta"],
        "effect_note": (
            f"{ab28['compat_opt1']} → {ab28['typed_opt1']}; "
            f"b/c={ab28['b_compat_only']}/{ab28['c_typed_only']}"
        ),
        "n": ab28["n"],
        "discordant_bc": [ab28["b_compat_only"], ab28["c_typed_only"]],
        "n_ties": ab28["n_ties"],
        "p_raw": ab28["sign_p_two_sided"],
        "p_source": (
            "exact binomial sign test on per-case compat_opt1 vs typed_opt1 "
            f"({ab28['source_tsv']})"
        ),
        "reused_not_reverified": True,
        "paired": ab28,
    }

    # C5: AB21
    ab21 = b4["arms"]["ab21"]["opt1"]
    c5 = {
        "id": "C5",
        "contrast": "M00 vs AB21 (salience selector)",
        "supports": "R2 exclusion (null allowed)",
        "slice": "DA d2_seq100",
        "endpoint": "option @1",
        "effect": -ab21["delta_arm_minus_m00"],  # M00 − arm
        "effect_note": "Δ = M00 − arm; exclusion control expects null",
        "n": b4["arms"]["ab21"]["n"],
        "discordant_bc": [ab21["b_m00_only"], ab21["c_arm_only"]],
        "p_raw": ab21["sign_p_two_sided"],
        "p_source": "exact binomial sign test on discordant pairs",
    }

    rows = _holm([c1, c2, c3, c4, c5])
    doc = {
        "schema_version": 2,
        "created_at": _utc(),
        "alpha": 0.05,
        "method": "Holm step-down on the five pre-registered confirmatory contrasts",
        "revision": (
            "C3 uses paired micro-F1 case-bootstrap (not case-F1 sign alone); "
            "C4 uses true paired b/c from metrics_typed_all100.tsv "
            "(not aggregate-derived c=0 construction)."
        ),
        "endpoint_heterogeneity_declared": (
            "Endpoints differ by block as registered in paper_ablation_plan.md §7 "
            "(DA @1 / MCR permutation any-hit / OX micro-F1 bootstrap). Holm is "
            "applied to the five confirmatory p-values as registered, not to a "
            "common endpoint."
        ),
        "contrasts": rows,
        "surviving": [r["id"] for r in rows if r["survives_holm_0.05"]],
        "notes": [
            "C5 is an exclusion control: surviving null is the intended outcome.",
            "C4 is historical reuse; §8 re-verification under frozen judge remains open.",
            "C1 uses full-sample AB03 (default caliber); conditional nonempty is reported elsewhere.",
            "C3 case-F1 sign test is auxiliary and agrees in direction with micro-F1 bootstrap.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for r in rows:
        print(
            f"{r['id']}: effect={r['effect']} p_raw={r['p_raw']:.4g} "
            f"p_holm={r['p_holm']:.4g} survive={r['survives_holm_0.05']} "
            f"| {r.get('endpoint')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
