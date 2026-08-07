#!/usr/bin/env python3
"""Turn block-2's nulls into equivalence statements with explicit bounds.

A reviewer reading "twelve ablations, nearly all null" will suspect the
mechanism does nothing. That reading confuses two different quantities:

  how often the operator *acts*        -> gate fires on 82% of cases, mean
                                          candidates 4.64 -> 2.02 (-56%)
  how often *changing the policy*
  changes the delivered answer         -> 2-8 of 98 cases

The second being small is what makes the first safe, and in a paired design it
also makes the null *informative* rather than underpowered: the accuracy
difference is bounded by m/n where m is the discordant count, so

    |delta| <= m / n   holds deterministically on the sample,

and the exact conditional-McNemar CI is correspondingly narrow. That is an
equivalence result, not a failed difference test.

This script emits, for every block-2 contrast:
  - discordant count m, deterministic bound m/n
  - exact conditional-McNemar 95% CI on the paired accuracy difference
  - a non-inferiority verdict against a pre-declared margin

CI construction: condition on the m discordant pairs, put a Clopper-Pearson
interval on p = P(a-better | discordant), then map back via
delta = (2p - 1) * m / n. Standard exact conditional interval; degenerate
m = 0 gives the point interval [0, 0].
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

OUT_JSON = ROOT / "runs/paper_v1/ablations_block2_equivalence_bounds.json"
OPERATOR = ROOT / "runs/paper_v1/ablations_block2_operator_channel.json"
SITE = ROOT / "runs/paper_v1/ablations_block2_site_rank_metrics.json"
# Pre-declared non-inferiority margin on accuracy, in proportion units.
# 0.05 = half of the >=0.10 threshold the plan uses for a "real" effect.
MARGIN = 0.05


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _betaincinv(a: float, b: float, y: float) -> float:
    """Inverse regularised incomplete beta via bisection (no scipy dependency)."""
    from math import lgamma, log, exp

    def betainc(x: float) -> float:
        if x <= 0.0:
            return 0.0
        if x >= 1.0:
            return 1.0
        # continued fraction (Lentz) for the regularised incomplete beta
        lbeta = lgamma(a) + lgamma(b) - lgamma(a + b)
        front = exp(a * log(x) + b * log(1.0 - x) - lbeta) / a
        f, c, d = 1.0, 1.0, 0.0
        for i in range(0, 300):
            m = i // 2
            if i == 0:
                num = 1.0
            elif i % 2 == 0:
                num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
            else:
                num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
            d = 1.0 + num * d
            d = 1e-30 if abs(d) < 1e-30 else d
            d = 1.0 / d
            c = 1.0 + num / (c if abs(c) > 1e-30 else 1e-30)
            f *= c * d
            if abs(1.0 - c * d) < 1e-12:
                break
        res = front * (f - 1.0)
        return min(1.0, max(0.0, res if x < (a + 1) / (a + b + 2) else 1.0 - _sym(x)))

    def _sym(x: float) -> float:
        # betainc(b, a, 1-x) computed by swapping roles; used for the upper branch
        from math import lgamma as lg, log as ln, exp as ex

        aa, bb, xx = b, a, 1.0 - x
        lbeta = lg(aa) + lg(bb) - lg(aa + bb)
        front = ex(aa * ln(xx) + bb * ln(1.0 - xx) - lbeta) / aa
        f, c, d = 1.0, 1.0, 0.0
        for i in range(0, 300):
            m = i // 2
            if i == 0:
                num = 1.0
            elif i % 2 == 0:
                num = (m * (bb - m) * xx) / ((aa + 2 * m - 1) * (aa + 2 * m))
            else:
                num = -((aa + m) * (aa + bb + m) * xx) / ((aa + 2 * m) * (aa + 2 * m + 1))
            d = 1.0 + num * d
            d = 1e-30 if abs(d) < 1e-30 else d
            d = 1.0 / d
            c = 1.0 + num / (c if abs(c) > 1e-30 else 1e-30)
            f *= c * d
            if abs(1.0 - c * d) < 1e-12:
                break
        return min(1.0, max(0.0, front * (f - 1.0)))

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betainc(mid) < y:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else _betaincinv(k, n - k + 1, alpha / 2)
    hi = 1.0 if k == n else _betaincinv(k + 1, n - k, 1 - alpha / 2)
    return (lo, hi)


def paired_bounds(b: int, c: int, n: int, *, margin: float = MARGIN) -> dict[str, Any]:
    """b = a-better count, c = b-better count, n = paired cases."""
    m = b + c
    det = round(m / n, 4) if n else None
    if m == 0:
        lo = hi = 0.0
    else:
        p_lo, p_hi = clopper_pearson(b, m)
        lo = (2 * p_lo - 1) * m / n
        hi = (2 * p_hi - 1) * m / n
    return {
        "n_paired": n,
        "n_discordant": m,
        "delta_point": round((b - c) / n, 4) if n else None,
        "deterministic_abs_bound": det,
        "ci95_low": round(lo, 4),
        "ci95_high": round(hi, 4),
        "margin": margin,
        # Equivalence holds when the whole CI sits inside +/- margin.
        "equivalent_within_margin": bool(abs(lo) < margin and abs(hi) < margin),
        "max_possible_loss_pp": round(max(0.0, -lo) * 100, 2),
        "max_possible_gain_pp": round(max(0.0, hi) * 100, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--margin", type=float, default=MARGIN)
    args = ap.parse_args()

    op = json.loads(OPERATOR.read_text(encoding="utf-8"))
    site = json.loads(SITE.read_text(encoding="utf-8"))

    rows: list[dict[str, Any]] = []

    # operator factor: M00 vs each arm, full sample, per endpoint
    for r in op["arms"]:
        full = r.get("full") or {}
        n = full.get("n") or 0
        for ep in ("acc1", "any_hit", "mrr"):
            e = full.get(ep)
            if not e:
                continue
            rows.append(
                {
                    "factor": "operator",
                    "contrast": f"M00 vs {r['arm']}",
                    "endpoint": ep,
                    "n_output_discordant": r.get("n_discordant"),
                    **paired_bounds(
                        int(e["n_m00_better"]), int(e["n_arm_better"]), int(n),
                        margin=args.margin,
                    ),
                }
            )

    # site factor: every edge of the 2x2
    ep_map = {"top1": "acc1", "any_hit": "any_hit", "rr": "mrr"}
    for t in site["paired_tests"]:
        for ep_src, ep in ep_map.items():
            e = t.get(ep_src)
            if not e:
                continue
            b = e.get("b_a_only", e.get("n_a_better"))
            c = e.get("c_b_only", e.get("n_b_better"))
            rows.append(
                {
                    "factor": "site",
                    "contrast": f"{t['a']} vs {t['b']} ({t['contrast']})",
                    "endpoint": ep,
                    "n_output_discordant": None,
                    **paired_bounds(int(b), int(c), int(t["n"]), margin=args.margin),
                }
            )

    # how pervasive is the operator, i.e. the quantity a reviewer should see first
    arms = site["arms"]
    pervasiveness = {
        "gate_firing_rate": op["power"]["gate_firing_rate"],
        "mean_candidates_no_compression_AB05": arms["AB05"]["mean_surviving_candidates"],
        "mean_candidates_main_M00": arms["M00"]["mean_surviving_candidates"],
        "candidate_reduction_fraction": round(
            1
            - float(arms["M00"]["mean_surviving_candidates"])
            / float(arms["AB05"]["mean_surviving_candidates"]),
            4,
        ),
        "note": (
            "The operator acts on 82% of cases and removes ~56% of surviving "
            "candidates. What is rare is disagreement *between compression "
            "policies*, not compression itself."
        ),
    }

    eq = [r for r in rows if r["equivalent_within_margin"]]
    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "purpose": (
            "Report block-2 nulls as equivalence results with explicit bounds, so "
            "that 'mostly null' is not read as 'mechanism ineffective'."
        ),
        "margin": args.margin,
        "method": (
            "Paired design: |delta| <= n_discordant/n holds deterministically; "
            "CI is the exact conditional-McNemar interval (Clopper-Pearson on the "
            "discordant pairs, mapped back to the difference scale)."
        ),
        "pervasiveness": pervasiveness,
        "n_contrasts": len(rows),
        "n_equivalent_within_margin": len(eq),
        "contrasts": rows,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"pervasiveness: {json.dumps(pervasiveness, ensure_ascii=False)}\n")
    hdr = f"{'factor':9s} {'contrast':34s} {'ep':8s} {'m':>3s} {'Δ':>8s} {'CI95':>18s} {'≤±margin':>9s}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        ci = f"[{r['ci95_low']:+.4f},{r['ci95_high']:+.4f}]"
        print(
            f"{r['factor']:9s} {r['contrast'][:34]:34s} {r['endpoint']:8s} "
            f"{r['n_discordant']:3d} {r['delta_point']:+8.4f} {ci:>18s} "
            f"{'YES' if r['equivalent_within_margin'] else 'no':>9s}"
        )
    print(f"\nequivalent within +/-{args.margin}: {len(eq)}/{len(rows)}")
    print("WROTE", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
