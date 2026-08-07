#!/usr/bin/env python3
"""Block-3 OX state factorial audit (budget × writeback + nested cap).

Corrects the factor-confounded draft reading in ablations_c2_results.md:
AB14 changes BOTH budget and writeback; the clean budget single-factor arm is AB16.

Writes runs/paper_v1/ablations_block3_state_factorial.json.
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "scripts" / "paper",):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

from block2_equivalence_bounds import paired_bounds  # noqa: E402

OX = ROOT / "logs/open_xddx_ox_seq100_v1"
OUT = ROOT / "runs/paper_v1/ablations_block3_state_factorial.json"

SCORE_DIRS = {
    "m00": OX
    / "compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_closed_live_mac/case_scores",
    "ab13": OX / "c2_ab13_v1/annotate/official_eval_llm_c2_ab13/case_scores",
    "ab14": OX / "c2_ab14_v1/annotate/official_eval_llm_c2_ab14/case_scores",
    "ab16": OX
    / "compat_synonym_v1/annotate/official_eval_llm_closed_live_mac/case_scores",
    "ab17": OX / "c2_ab17_v1/annotate/official_eval_llm_c2_ab17/case_scores",
    "ab19": OX / "c2_ab19_v1/annotate/official_eval_llm_c2_ab19/case_scores",
    "ab15_posterior": OX
    / "compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_c1_ab15_posterior/case_scores",
    "ab15_post_n_mcr": OX
    / "compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_c1_ab15_post_n_mcr/case_scores",
}

# Factorial grid (cap fixed at 6 for the 2x2)
FACTOR_CELLS = {
    "ab13": {"budget": "locked_L1=4", "writeback": False, "cap": 6},
    "ab16": {"budget": "default_L1=6", "writeback": False, "cap": 6},
    "m00": {"budget": "locked_L1=4", "writeback": True, "cap": 6},
    "ab14": {"budget": "default_L1=6", "writeback": True, "cap": 6},
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _binom_two_sided(k: int, n: int) -> float:
    if n == 0:
        return 1.0
    lo = min(k, n - k)
    total = sum(math.comb(n, i) for i in range(0, lo + 1))
    return min(1.0, 2.0 * total / (2**n))


def _bootstrap_mean_ci(
    values: list[float], *, n_boot: int = 2000, seed: int = 0
) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot)
    )
    return {
        "mean": round(sum(values) / n, 6),
        "lo": round(means[int(0.025 * (n_boot - 1))], 6),
        "hi": round(means[int(0.975 * (n_boot - 1))], 6),
        "n": n,
    }


def _load_scores(path: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for p in sorted(path.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        diag = d.get("diagnostic") or {}
        interp = d.get("interpretation") or {}
        n_tot = float(interp.get("n_total_interpretations") or 0)
        n_ok = float(interp.get("n_correct_interpretations") or 0)
        out[p.stem] = {
            "f1": float(diag.get("f1") or 0.0),
            "tp": float(diag.get("tp") or 0.0),
            "n_pred": float(diag.get("n_pred") or 0.0),
            "n_gold": float(diag.get("n_gold") or 0.0),
            "iacc": (n_ok / n_tot) if n_tot else 0.0,
            "iacc_n_ok": n_ok,
            "iacc_n_tot": n_tot,
        }
    return out


def _micro_f1(scores: dict[str, dict[str, float]], cids: list[str]) -> float:
    tp = sum(scores[c]["tp"] for c in cids)
    n_pred = sum(scores[c]["n_pred"] for c in cids)
    n_gold = sum(scores[c]["n_gold"] for c in cids)
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    return (2 * p * r / (p + r)) if (p + r) else 0.0


def _paired_continuous(
    a: dict[str, dict[str, float]],
    b: dict[str, dict[str, float]],
    cids: list[str],
    key: str,
    *,
    seed: int,
) -> dict[str, Any]:
    deltas = [a[c][key] - b[c][key] for c in cids]
    n_a_better = sum(1 for d in deltas if d > 1e-12)
    n_b_better = sum(1 for d in deltas if d < -1e-12)
    n_tie = len(deltas) - n_a_better - n_b_better
    boot = _bootstrap_mean_ci(deltas, seed=seed)
    return {
        "n": len(cids),
        "mean_delta": round(sum(deltas) / len(deltas), 6) if deltas else None,
        "n_a_better": n_a_better,
        "n_b_better": n_b_better,
        "n_tie": n_tie,
        "sign_p_two_sided": round(
            _binom_two_sided(min(n_a_better, n_b_better), n_a_better + n_b_better), 6
        ),
        "bootstrap_ci95": boot,
    }


def _paired_micro_bootstrap(
    a: dict[str, dict[str, float]],
    b: dict[str, dict[str, float]],
    cids: list[str],
    *,
    n_boot: int = 5000,
    seed: int = 20260729,
) -> dict[str, Any]:
    """Paired case-bootstrap of micro-F1(a) − micro-F1(b)."""
    n = len(cids)
    point = _micro_f1(a, cids) - _micro_f1(b, cids)
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        samp = [cids[rng.randrange(n)] for _ in range(n)]
        deltas.append(_micro_f1(a, samp) - _micro_f1(b, samp))
    deltas.sort()
    n_le0 = sum(1 for d in deltas if d <= 0.0)
    p_one = (n_le0 + 1) / (n_boot + 1)
    return {
        "n": n,
        "delta_micro_f1": round(point, 6),
        "bootstrap_ci95": {
            "lo": round(deltas[int(0.025 * (n_boot - 1))], 6),
            "hi": round(deltas[int(0.975 * (n_boot - 1))], 6),
            "n_boot": n_boot,
            "seed": seed,
        },
        "p_one_sided_addone": round(p_one, 6),
        "p_two_sided_addone": round(min(1.0, 2.0 * p_one), 6),
        "n_boot_delta_le_0": n_le0,
    }


def _arm_summary(
    scores: dict[str, dict[str, float]], cids: list[str]
) -> dict[str, Any]:
    iacc_ok = sum(scores[c]["iacc_n_ok"] for c in cids)
    iacc_tot = sum(scores[c]["iacc_n_tot"] for c in cids)
    return {
        "n": len(cids),
        "micro_f1": round(_micro_f1(scores, cids), 6),
        "mean_case_f1": round(sum(scores[c]["f1"] for c in cids) / len(cids), 6),
        "interpretation_accuracy": round(iacc_ok / iacc_tot, 6) if iacc_tot else None,
    }


def main() -> int:
    loaded = {k: _load_scores(p) for k, p in SCORE_DIRS.items()}
    # common cases across the factorial 2x2 + nested
    core = ["m00", "ab13", "ab14", "ab16", "ab17", "ab19"]
    cids = sorted(set.intersection(*(set(loaded[k]) for k in core)))

    arms: dict[str, Any] = {}
    for k in core + ["ab15_posterior", "ab15_post_n_mcr"]:
        sc = loaded[k]
        use = [c for c in cids if c in sc] if k.startswith("ab15") else cids
        meta = FACTOR_CELLS.get(k, {})
        if k == "ab17":
            meta = {"budget": "locked_L1=4", "writeback": True, "cap": 1}
        elif k == "ab19":
            meta = {"budget": "locked_L1=4", "writeback": True, "cap": 999}
        elif k.startswith("ab15"):
            meta = {
                "budget": "locked_L1=4",
                "writeback": True,
                "cap": 6,
                "decode": k.replace("ab15_", ""),
            }
        arms[k] = {**meta, **_arm_summary(sc, use)}

    # Clean 2x2 effects on micro-F1 (aggregate) and paired case-F1
    f = {k: arms[k]["micro_f1"] for k in ("ab13", "ab16", "m00", "ab14")}
    factorial = {
        "cells_micro_f1": f,
        "writeback_effect_at_locked": round(f["m00"] - f["ab13"], 6),
        "writeback_effect_at_default": round(f["ab14"] - f["ab16"], 6),
        "budget_effect_at_cold": round(f["ab16"] - f["ab13"], 6),
        "budget_effect_at_hot": round(f["ab14"] - f["m00"], 6),
        "interaction": round(
            (f["ab14"] - f["ab16"]) - (f["m00"] - f["ab13"]), 6
        ),
        "paired_case_f1": {
            "writeback_locked_m00_vs_ab13": _paired_continuous(
                loaded["m00"], loaded["ab13"], cids, "f1", seed=31
            ),
            "writeback_default_ab14_vs_ab16": _paired_continuous(
                loaded["ab14"], loaded["ab16"], cids, "f1", seed=32
            ),
            "budget_cold_ab16_vs_ab13": _paired_continuous(
                loaded["ab16"], loaded["ab13"], cids, "f1", seed=33
            ),
            "budget_hot_ab14_vs_m00": _paired_continuous(
                loaded["ab14"], loaded["m00"], cids, "f1", seed=34
            ),
        },
        "paired_micro_f1_bootstrap": _paired_micro_bootstrap(
            loaded["m00"], loaded["ab13"], cids, seed=20260729
        ),
        "paired_iacc": {
            "writeback_locked_m00_vs_ab13": _paired_continuous(
                loaded["m00"], loaded["ab13"], cids, "iacc", seed=41
            ),
        },
        "confounded_reading_retracted": {
            "was": "M00−AB13 ≈ AB14−AB13 ⇒ prefer budget over writeback",
            "why_wrong": (
                "AB14 changes budget AND writeback; the clean budget arm is AB16. "
                "Writeback effects (~0.075) dwarf budget effects (~0.008)."
            ),
        },
    }

    # Nested cap arms vs M00 — use paired case-F1 sign + treat as continuous;
    # also report micro-F1 deltas and an equivalence-style bound via dichotomized
    # "case F1 strictly better" counts mapped through paired_bounds for a
    # coarse accuracy-like bound (documented as exploratory for continuous F1).
    def _cap_row(arm: str) -> dict[str, Any]:
        paired = _paired_continuous(loaded["m00"], loaded[arm], cids, "f1", seed=50)
        # dichotomize: case where M00 F1 > arm F1 etc.
        b = paired["n_a_better"]
        c = paired["n_b_better"]
        return {
            "arm_micro_f1": arms[arm]["micro_f1"],
            "m00_micro_f1": arms["m00"]["micro_f1"],
            "delta_micro_f1": round(arms["m00"]["micro_f1"] - arms[arm]["micro_f1"], 6),
            "paired_case_f1": paired,
            "dichotomized_sign_bounds": paired_bounds(b, c, len(cids), margin=0.05),
            "note": (
                "dichotomized_sign_bounds maps case-F1 wins to a McNemar CI; "
                "primary continuous evidence is paired_case_f1.bootstrap_ci95"
            ),
        }

    nested = {
        "ab17_single_champion_cap1": _cap_row("ab17"),
        "ab19_uncapped_cap999": _cap_row("ab19"),
    }

    # AB15 decode contrast (same hot tree, different decode)
    ab15_cids = sorted(
        set(loaded["m00"])
        & set(loaded["ab15_posterior"])
        & set(loaded["ab15_post_n_mcr"])
    )
    decode = {
        "n": len(ab15_cids),
        "closed_live_mac": _arm_summary(loaded["m00"], ab15_cids),
        "posterior": _arm_summary(loaded["ab15_posterior"], ab15_cids),
        "post_n_mcr": _arm_summary(loaded["ab15_post_n_mcr"], ab15_cids),
        "paired_case_f1_closed_vs_posterior": _paired_continuous(
            loaded["m00"], loaded["ab15_posterior"], ab15_cids, "f1", seed=61
        ),
        "paired_case_f1_closed_vs_post_n_mcr": _paired_continuous(
            loaded["m00"], loaded["ab15_post_n_mcr"], ab15_cids, "f1", seed=62
        ),
    }

    # Pre-registered falsification reads
    wb_locked = factorial["writeback_effect_at_locked"]
    budg_locked_side = factorial["budget_effect_at_hot"]  # budget alone can't explain
    # "If M00−AB13 gain can be explained by AB14 (budget) alone" — compare
    # writeback effect to budget effect magnitude.
    budget_alone_explains = abs(budg_locked_side) >= 0.9 * abs(wb_locked)
    ab19_harms = nested["ab19_uncapped_cap999"]["delta_micro_f1"] >= 0.01
    ab13_null = abs(wb_locked) < 0.01

    verdict = {
        "ab13_writeback_falsification_triggered": ab13_null,
        "budget_explains_gain_falsification_triggered": budget_alone_explains,
        "ab19_cap_falsification_triggered": not ab19_harms,
        "ab17_single_champion_null": abs(
            nested["ab17_single_champion_cap1"]["delta_micro_f1"]
        )
        < 0.02,
        "reading": (
            "Writeback is the load-bearing factor (~+0.075 F1 at both budget levels); "
            "budget is ~+0.008. Cap is bidirectional-null (AB17 cap=1 and AB19 cap=999 "
            "both within noise of M00) ⇒ remove cap from mechanism claim. "
            "AB15 shows closed-panel decode beats posterior Top-K on the same hot tree."
        ),
    }

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "slice": "OX ox_seq100_v1, n=100",
        "n_common_core": len(cids),
        "arms": arms,
        "factorial_2x2": factorial,
        "nested_cap": nested,
        "decode_ab15": decode,
        "verdict": verdict,
        "ab18_unrun": True,
        "ab20_not_on_ox_by_design": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(
        f"2x2 F1: AB13={f['ab13']:.4f} AB16={f['ab16']:.4f} "
        f"M00={f['m00']:.4f} AB14={f['ab14']:.4f}"
    )
    print(
        f"WB locked={factorial['writeback_effect_at_locked']:+.4f} "
        f"budget cold={factorial['budget_effect_at_cold']:+.4f} "
        f"interaction={factorial['interaction']:+.4f}"
    )
    print(
        f"AB17 ΔF1={nested['ab17_single_champion_cap1']['delta_micro_f1']:+.4f} "
        f"AB19 ΔF1={nested['ab19_uncapped_cap999']['delta_micro_f1']:+.4f}"
    )
    print("verdict:", json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
