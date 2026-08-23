#!/usr/bin/env python3
"""Score MCR_SELECTOR_TRUNCATION_V1 on the frozen clinical endpoint. Zero LLM calls.

Reads the per-arm champions written by `mcr_selector_truncation.py` and scores
them with the same frozen `(case, label)` relation used everywhere else, then runs
the paired contrasts the preregistration fixed:

  main family (Holm, 2 comparisons)   group5 - frozen   (pure width)
                                      flat5  - group5   (framing + step collapse)
  reported separately                 flat3  - flat5    (dose)

The 233 MCR cases whose pool holds no clinical-complete label are excluded from
the cohort by construction: truncation only removes candidates, so those cases
cannot yield a complete champion under any slate. The full-400 clinical-complete
count is therefore exactly the cohort's complete count (preregistration §1).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from math import comb
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, _ROOT / "src", _ROOT / "analysis" / "backbone_v1", _ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import mcr_selector_truncation as M  # noqa: E402

from analysis.mechanism_v2.clinical_endpoint import (  # noqa: E402
    COMPLETE,
    ClinicalEndpoint,
    TaskEndpoint,
)

RESULTS = _ROOT / "analysis" / "mechanism_v2" / "results" / "MCR_SELECTOR_TRUNCATION"
RUNS = RESULTS / "runs"
ARMS = ("frozen", "group5", "flat5", "flat3")
DEV = ("mcr_v1", "mcr_v2")
N_FULL_SLICE = 400


def mcnemar(pairs: list[tuple[bool, bool]]) -> dict[str, Any]:
    """Exact two-sided McNemar on (base, test) pairs."""
    b = sum(1 for a, c in pairs if a and not c)  # base only
    c_ = sum(1 for a, c in pairs if c and not a)  # test only
    n = b + c_
    if n == 0:
        return {"base_only": 0, "test_only": 0, "n_discordant": 0, "p_two_sided": 1.0}
    k = min(b, c_)
    tail = sum(comb(n, i) for i in range(0, k + 1)) / (2**n)
    return {
        "base_only": b,
        "test_only": c_,
        "n_discordant": n,
        "p_two_sided": round(min(1.0, 2 * tail), 5),
    }


def holm(named: list[tuple[str, float]]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values, monotone-enforced."""
    order = sorted(named, key=lambda x: x[1])
    m = len(order)
    out: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(order):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[name] = round(running, 5)
    return out


def load_rows() -> dict[str, dict[tuple[str, str], dict]]:
    """arm -> (slice, case_id) -> row. `frozen` comes from the frozen logs."""
    out: dict[str, dict[tuple[str, str], dict]] = {}
    sl2log = {sl: log for log, _, sl in M.MCR_SLICES}
    for arm in ARMS:
        if arm == "frozen":
            continue
        p = RUNS / arm / "predictions.jsonl"
        if not p.is_file():
            raise SystemExit(f"missing {p}; run mcr_selector_truncation.py --arm {arm}")
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        out[arm] = {(r["slice"], r["case_id"]): r for r in rows}
    keys = set(out["group5"])
    frozen: dict[tuple[str, str], dict] = {}
    for sl, cid in keys:
        doc = M.load_doc(sl2log[sl], cid)
        stages = doc.get("stages") or {}
        cands = M.ordered_candidates(stages)
        frozen[(sl, cid)] = {
            "slice": sl,
            "case_id": cid,
            "arm": "frozen",
            "champion": str(doc.get("champion") or ""),
            "shortlist": [str(c.get("preferred_label") or "") for c in cands],
            "n_candidates": len(cands),
            "n_groups": len({(c.get("stances") or ["unassigned"])[0] for c in cands}),
            "champion_in_slate": True,
            "source": "frozen_log",
        }
    out["frozen"] = frozen
    for arm in ARMS:
        if set(out[arm]) != keys:
            raise SystemExit(f"arm {arm} cohort mismatch vs group5")
    return out


def score(
    rows: dict[str, dict[tuple[str, str], dict]],
    ce: ClinicalEndpoint,
    te: TaskEndpoint,
    *,
    uncertain_as: str = "fail",
) -> dict[str, Any]:
    keys = sorted(rows["frozen"], key=lambda k: (k[0], int(k[1]) if k[1].isdigit() else 0))
    gold = r5.load_gold()

    per: dict[str, dict[str, Any]] = {}
    flags: dict[str, dict[tuple[str, str], Optional[bool]]] = {a: {} for a in ARMS}
    cop: dict[str, dict[tuple[str, str], bool]] = {a: {} for a in ARMS}
    legacy: dict[str, dict[tuple[str, str], bool]] = {a: {} for a in ARMS}
    task: dict[str, dict[tuple[str, str], Optional[bool]]] = {a: {} for a in ARMS}

    for arm in ARMS:
        rel_counts: Counter = Counter()
        for k in keys:
            sl, cid = k
            champ = rows[arm][k]["champion"]
            rel = ce.relation("mcr", sl, cid, champ)
            rel_counts[str(rel)] += 1
            if rel == "uncertain" and uncertain_as == "drop":
                flags[arm][k] = None
            else:
                flags[arm][k] = rel == COMPLETE
            cop[arm][k] = ce.is_complete_or_partial("mcr", sl, cid, champ)
            g = gold.get(("mcr", sl, cid), "")
            legacy[arm][k] = bool(dc.match(champ, g)) if g else False
            task[arm][k] = te.correct("mcr", sl, cid, champ)
        n = len(keys)
        judged = [k for k in keys if flags[arm][k] is not None]
        comp = sum(1 for k in judged if flags[arm][k])
        per[arm] = {
            "n": n,
            "n_judged": len(judged),
            "clinical_complete": comp,
            "conditional_conversion": round(comp / max(len(judged), 1), 4),
            "implied_full_slice_rate": round(comp / N_FULL_SLICE, 4),
            "complete_or_partial": sum(1 for k in keys if cop[arm][k]),
            "legacy_dc_match": sum(1 for k in keys if legacy[arm][k]),
            "task_judged": sum(1 for k in keys if task[arm][k] is not None),
            "task_correct": sum(1 for k in keys if task[arm][k] is True),
            "mean_width": round(sum(rows[arm][k]["n_candidates"] for k in keys) / n, 4),
            "mean_groups": round(sum(rows[arm][k]["n_groups"] for k in keys) / n, 4),
            "champion_in_slate": sum(1 for k in keys if rows[arm][k]["champion_in_slate"]),
            "served": sum(1 for k in keys if rows[arm][k]["champion"].strip()),
            "agreement_with_frozen": round(
                sum(1 for k in keys if rows[arm][k]["champion"] == rows["frozen"][k]["champion"])
                / n,
                4,
            ),
            "champion_relations": dict(rel_counts.most_common()),
        }
        for name in ("dev", "holdout"):
            sub = [k for k in keys if (k[0] in DEV) == (name == "dev")]
            sj = [k for k in sub if flags[arm][k] is not None]
            per[arm][f"{name}_complete"] = f"{sum(1 for k in sj if flags[arm][k])}/{len(sub)}"

    def pair(base: str, test: str, table: dict) -> dict[str, Any]:
        ks = [k for k in keys if table[base][k] is not None and table[test][k] is not None]
        res = mcnemar([(bool(table[base][k]), bool(table[test][k])) for k in ks])
        res["n_paired"] = len(ks)
        res["delta_cases"] = res["test_only"] - res["base_only"]
        res["delta_pp_cohort"] = round(100 * res["delta_cases"] / max(len(ks), 1), 2)
        res["delta_pp_full_slice"] = round(100 * res["delta_cases"] / N_FULL_SLICE, 2)
        return res

    contrasts = {
        "group5_minus_frozen": pair("frozen", "group5", flags),
        "flat5_minus_group5": pair("group5", "flat5", flags),
        "flat3_minus_flat5": pair("flat5", "flat3", flags),
        "flat5_minus_frozen": pair("frozen", "flat5", flags),
        "flat3_minus_frozen": pair("frozen", "flat3", flags),
    }
    family = [
        ("group5_minus_frozen", contrasts["group5_minus_frozen"]["p_two_sided"]),
        ("flat5_minus_group5", contrasts["flat5_minus_group5"]["p_two_sided"]),
    ]
    secondary = {
        ep: {
            name: pair(b, t, tbl)
            for name, (b, t) in (
                ("group5_minus_frozen", ("frozen", "group5")),
                ("flat5_minus_frozen", ("frozen", "flat5")),
                ("flat3_minus_frozen", ("frozen", "flat3")),
            )
        }
        for ep, tbl in (
            ("complete_or_partial", cop),
            ("legacy_dc_match", legacy),
            ("task", task),
        )
    }

    # forced regressions: frozen champion was complete, arm's slate dropped it
    forced: dict[str, dict[str, int]] = {}
    for arm in ARMS:
        if arm == "frozen":
            continue
        lost = [
            k
            for k in keys
            if flags["frozen"][k]
            and rows["frozen"][k]["champion"] not in rows[arm][k]["shortlist"]
        ]
        forced[arm] = {
            "frozen_complete_champion_dropped_from_slate": len(lost),
            "of_those_still_complete": sum(1 for k in lost if flags[arm][k]),
        }

    # self-consistency: cases where truncation is a no-op must reproduce frozen
    noop = [k for k in keys if rows["group5"][k]["shortlist"] == rows["frozen"][k]["shortlist"]]
    return {
        "uncertain_as": uncertain_as,
        "cohort": {
            "n": len(keys),
            "dev": sum(1 for k in keys if k[0] in DEV),
            "holdout": sum(1 for k in keys if k[0] not in DEV),
        },
        "per_arm": per,
        "primary_endpoint": "clinical_complete_top1",
        "contrasts": contrasts,
        "holm_main_family": holm(family),
        "secondary_contrasts": secondary,
        "forced_regressions": forced,
        "self_consistency_noop_cases": {
            "n": len(noop),
            "champion_identical_to_frozen": sum(
                1 for k in noop if rows["group5"][k]["champion"] == rows["frozen"][k]["champion"]
            ),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop-source-conflicts", action="store_true")
    ap.add_argument("--out", type=Path, default=RESULTS / "score.json")
    args = ap.parse_args()

    ce = ClinicalEndpoint()
    if args.drop_source_conflicts and ce.conflicts:
        for c in ce.conflicts:
            ce._rel.pop((c.get("case_key", ""), c.get("label", "")), None)
    te = TaskEndpoint()
    rows = load_rows()

    out = {
        "primary": score(rows, ce, te, uncertain_as="fail"),
        "sensitivity_uncertain_dropped": score(rows, ce, te, uncertain_as="drop"),
        "drop_source_conflicts": bool(args.drop_source_conflicts),
        "n_source_conflicts": len(ce.conflicts),
    }
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    p = out["primary"]
    print(f"cohort n={p['cohort']['n']} (dev {p['cohort']['dev']} / holdout {p['cohort']['holdout']})\n")
    hdr = f"{'arm':<10}{'complete':>9}{'cond.conv':>11}{'full400':>9}{'C∪P':>6}{'legacy':>8}{'task':>10}{'width':>7}{'agree':>7}"
    print(hdr)
    for arm in ARMS:
        a = p["per_arm"][arm]
        print(
            f"{arm:<10}{a['clinical_complete']:>9}{a['conditional_conversion']:>11.4f}"
            f"{a['implied_full_slice_rate']:>9.4f}{a['complete_or_partial']:>6}"
            f"{a['legacy_dc_match']:>8}{str(a['task_correct'])+'/'+str(a['task_judged']):>10}"
            f"{a['mean_width']:>7.2f}{a['agreement_with_frozen']:>7.3f}"
        )
    print("\nprimary endpoint: clinical-complete top-1, paired exact McNemar")
    for name, c in p["contrasts"].items():
        adj = p["holm_main_family"].get(name)
        tag = f"  holm={adj}" if adj is not None else ""
        print(
            f"  {name:<24} base_only={c['base_only']:>3} test_only={c['test_only']:>3}"
            f"  Δ={c['delta_cases']:>+4} ({c['delta_pp_full_slice']:>+5.2f}pp/400)"
            f"  p={c['p_two_sided']}{tag}"
        )
    print("\nforced regressions (frozen complete champion dropped from slate):")
    for arm, f in p["forced_regressions"].items():
        print(f"  {arm:<10} {f['frozen_complete_champion_dropped_from_slate']}")
    sc = p["self_consistency_noop_cases"]
    print(f"\nno-op cases (group5 slate == frozen slate): {sc['n']}, "
          f"champion identical: {sc['champion_identical_to_frozen']}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
