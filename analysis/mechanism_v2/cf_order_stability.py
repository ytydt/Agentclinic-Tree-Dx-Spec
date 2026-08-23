#!/usr/bin/env python3
"""Re-analysis of the archived R6 X4 order-permutation probe.  Zero new calls.

R6 already ran the order counterfactual on the Collapse3c pool with three seeds
(`logs/backbone_v1/*/r6_x4_c3c_s{0,1,2}`) and concluded **"顺序不敏感 ... 位置偏置
不是当前主矛盾"** on the strength of "三种子序 spread <= 0.01".

That conclusion rests on an accuracy spread, and accuracy is the one statistic
that cannot see the effect in question.  On the frozen 800, 77.9% of cases have no
complete object anywhere in the pool, so a champion can be replaced by a different
*wrong* candidate without moving accuracy at all.  Order-invariant accuracy is
therefore compatible with two very different worlds:

- **H2** evidence-driven: the champion itself is stable, order is irrelevant;
- **H1'** position-driven: the champion churns freely, but the churn is confined to
  candidates that are all equally wrong, so accuracy never notices.

The statistic that separates them is champion *identity* stability, which R6 never
reported and which these logs already contain:

    theta = 1 - P(permuted champion == baseline champion)

theta has two pre-computable poles: 0 under H2, and ~1 under pure position
anchoring.  It is reported overall and split by whether a complete object was even
available, because that split is exactly what makes the accuracy test blind.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "src", ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from agentclinic_tree_dx.aphhm_c import _norm  # noqa: E402
from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

OUT_DIR = ROOT / "analysis/mechanism_v2/results/ORDER_COUNTERFACTUAL"
BASE_ARM = "aphhm_c_collapse3c_v1"
SEEDS = ("s0", "s1", "s2")
# The X4 probe was run on the four dev slices only, not on the 200b holdouts.
DEV_SLICES = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
}


def _blank() -> dict[str, Any]:
    return {
        "cases": 0,
        "pairs": 0,
        "same_champion": 0,
        "baseline_champion_absent_from_probe_shortlist": 0,
        "probe_index0": 0,
        "baseline_index0_same_shortlist": 0,
        "probe_width": 0,
        "baseline_pool_width": 0,
        "baseline_frontier_width": 0,
        # strata: does a complete object exist in the probe's shortlist at all?
        "strat_pairs": Counter(),
        "strat_same": Counter(),
        # correctness movement
        "base_complete": 0,
        "probe_complete": 0,
        "moved_and_correctness_changed": 0,
        "moved_within_wrong": 0,
        "rescued": 0,
        "broken": 0,
        # per-seed, so the three permutations can be checked against each other
        "seed_pairs": Counter(),
        "seed_same": Counter(),
        "seed_index0": Counter(),
    }


def main() -> None:
    clinical = ClinicalEndpoint()
    clinical.drop_conflicts()
    per: dict[str, dict[str, Any]] = {}
    examples: list[dict[str, Any]] = []

    for dataset, (family, sl) in DEV_SLICES.items():
        agg = per.setdefault(family, _blank())
        base_dir = ROOT / "logs/backbone_v1" / dataset / BASE_ARM / "case_stages"
        for bpath in sorted(base_dir.glob("*.json")):
            bdoc = json.loads(bpath.read_text(encoding="utf-8"))
            bst = bdoc["stages"]
            case_id = str(bdoc.get("source_id") or bdoc.get("case_id") or bpath.stem)
            rows = {str(r["concept_id"]): r for r in bst.get("registry") or []}
            pool = [c for c in (bst.get("ledger_rank") or []) if c in rows]
            front = [c for c in (bst.get("frontier") or []) if c in rows]
            base_champ = str(
                (bst.get("frontier_selector") or {}).get("champion") or ""
            ).strip()
            if not base_champ or len(pool) < 2:
                continue
            agg["cases"] += 1
            agg["baseline_pool_width"] += len(pool)
            agg["baseline_frontier_width"] += len(front)
            base_ok = clinical.relation(family, sl, case_id, base_champ) == COMPLETE

            for seed in SEEDS:
                ppath = (
                    ROOT
                    / "logs/backbone_v1"
                    / dataset
                    / f"r6_x4_c3c_{seed}"
                    / "case_stages"
                    / bpath.name
                )
                if not ppath.is_file():
                    continue
                pdoc = json.loads(ppath.read_text(encoding="utf-8"))
                presented = [str(x) for x in (pdoc.get("shortlist") or [])]
                pchamp = str(pdoc.get("champion") or "").strip()
                if not presented or not pchamp:
                    continue
                agg["pairs"] += 1
                agg["probe_width"] += len(presented)

                norm_presented = [_norm(x) for x in presented]
                if _norm(base_champ) not in norm_presented:
                    # cannot be a fair identity comparison: the probe never
                    # offered the baseline answer.
                    agg["baseline_champion_absent_from_probe_shortlist"] += 1
                    continue

                same = _norm(pchamp) == _norm(base_champ)
                agg["same_champion"] += int(same)
                agg["seed_pairs"][seed] += 1
                agg["seed_same"][seed] += int(same)
                if norm_presented and _norm(pchamp) == norm_presented[0]:
                    agg["probe_index0"] += 1
                    agg["seed_index0"][seed] += 1
                # where did the baseline champion sit in *generation* order,
                # restricted to the same set the probe offered?
                gen_same_set = [
                    rows[c]["preferred_label"]
                    for c in pool
                    if _norm(str(rows[c]["preferred_label"])) in set(norm_presented)
                ]
                if gen_same_set and _norm(gen_same_set[0]) == _norm(base_champ):
                    agg["baseline_index0_same_shortlist"] += 1

                has_complete = any(
                    clinical.relation(family, sl, case_id, lab) == COMPLETE
                    for lab in presented
                )
                key = (
                    "complete_available_in_shortlist"
                    if has_complete
                    else "no_complete_in_shortlist"
                )
                agg["strat_pairs"][key] += 1
                agg["strat_same"][key] += int(same)

                probe_ok = clinical.relation(family, sl, case_id, pchamp) == COMPLETE
                agg["base_complete"] += int(base_ok)
                agg["probe_complete"] += int(probe_ok)
                if not same:
                    if base_ok != probe_ok:
                        agg["moved_and_correctness_changed"] += 1
                        agg["rescued"] += int(probe_ok and not base_ok)
                        agg["broken"] += int(base_ok and not probe_ok)
                    else:
                        agg["moved_within_wrong"] += int(not probe_ok)
                    if len(examples) < 18:
                        examples.append(
                            {
                                "family": family,
                                "case": bpath.stem,
                                "seed": seed,
                                "baseline": base_champ,
                                "probe": pchamp,
                                "base_complete": base_ok,
                                "probe_complete": probe_ok,
                                "complete_available": has_complete,
                            }
                        )

    def _r(n: int, d: int) -> Optional[float]:
        return round(n / d, 4) if d else None

    report: dict[str, Any] = {
        "schema_version": "cf-order-stability-v1",
        "model_calls": 0,
        "source": "archived r6_x4_c3c_s{0,1,2} vs aphhm_c_collapse3c_v1",
        "scope": "four dev slices (n=400/family); the 200b holdouts were never probed",
        "families": {},
        "examples": examples,
    }
    for fam, a in sorted(per.items()):
        n = a["pairs"]
        cmp_n = n - a["baseline_champion_absent_from_probe_shortlist"]
        stability = _r(a["same_champion"], cmp_n)
        report["families"][fam] = {
            "cases": a["cases"],
            "comparable_pairs": cmp_n,
            "mean_probe_shortlist_width": _r(a["probe_width"], n),
            "mean_baseline_pool_width": _r(a["baseline_pool_width"], a["cases"]),
            "mean_baseline_frontier_width": _r(
                a["baseline_frontier_width"], a["cases"]
            ),
            "baseline_champion_absent_from_probe_shortlist": a[
                "baseline_champion_absent_from_probe_shortlist"
            ],
            "champion_identity": {
                "stability": stability,
                "theta_position_driven_share": (
                    round(1 - stability, 4) if stability is not None else None
                ),
            },
            "index0_rates": {
                "under_permutation": _r(a["probe_index0"], cmp_n),
                "baseline_generation_order_same_set": _r(
                    a["baseline_index0_same_shortlist"], cmp_n
                ),
            },
            "per_seed": {
                s: {
                    "pairs": a["seed_pairs"][s],
                    "stability": _r(a["seed_same"][s], a["seed_pairs"][s]),
                    "theta": (
                        round(1 - a["seed_same"][s] / a["seed_pairs"][s], 4)
                        if a["seed_pairs"][s]
                        else None
                    ),
                    "index0_rate": _r(a["seed_index0"][s], a["seed_pairs"][s]),
                }
                for s in SEEDS
                if a["seed_pairs"][s]
            },
            "stability_by_stratum": {
                k: {
                    "pairs": a["strat_pairs"][k],
                    "stability": _r(a["strat_same"][k], a["strat_pairs"][k]),
                }
                for k in sorted(a["strat_pairs"])
            },
            "why_accuracy_could_not_see_it": {
                "complete_rate_baseline": _r(a["base_complete"], n),
                "complete_rate_permuted": _r(a["probe_complete"], n),
                "champion_moved": cmp_n - a["same_champion"],
                "moved_but_still_wrong_both_ways": a["moved_within_wrong"],
                "moved_and_correctness_changed": a["moved_and_correctness_changed"],
                "rescued": a["rescued"],
                "broken": a["broken"],
            },
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "order_stability.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "examples"},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n冠军被顺序改变的样例：")
    for r in examples[:14]:
        print(
            f"  [{r['family']}/{r['case']}/{r['seed']}] avail={str(r['complete_available']):5s} "
            f"{str(r['base_complete'])[0]}->{str(r['probe_complete'])[0]}  "
            f"{r['baseline'][:32]:34s} -> {r['probe'][:32]}"
        )


if __name__ == "__main__":
    main()
