#!/usr/bin/env python3
"""R6 win-set geometry with replicate noise null and stable wins.

Pivots r5_dual into 800x13 matrices, computes pairwise exclusive wins,
Jaccard of win sets, case difficulty, replicate exclusive-win null, and a
simple Rasch residual screen for true arm-specific items.
"""
from __future__ import annotations

import itertools
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import r4_lib as r4
import r5_lib as r5
import r6_lib as r6

OUT = r6.R6_OUT
ARMS = list(r5.FOCUS_ARMS.keys())


def pivot_dual(metric: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Return wide rows keyed by (dataset,slice,case_id) with arm columns."""
    rows = r4.load_tsv(r5.OUT / "mosaic_eval" / "r5_dual" / "dual.tsv")
    by: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        key = (r["dataset"], r["slice"], r["case_id"])
        if key not in by:
            by[key] = {
                "dataset": r["dataset"],
                "slice": r["slice"],
                "case_id": r["case_id"],
                "gold": r.get("gold") or "",
            }
        val = r.get(metric)
        if val in ("", None):
            by[key][r["arm"]] = ""
        else:
            by[key][r["arm"]] = int(val)
    wide = list(by.values())
    return wide, ARMS


def case_difficulty(wide: list[dict], arms: list[str]) -> None:
    for r in wide:
        vals = [int(r[a]) for a in arms if r.get(a) not in ("", None)]
        r["n_arms_scored"] = len(vals)
        r["n_arms_correct"] = sum(vals)
        r["difficulty"] = (
            1.0 - (sum(vals) / len(vals)) if vals else None
        )


def pairwise_exclusive(wide: list[dict], arms: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a, b in itertools.combinations(arms, 2):
        a_only = b_only = both = neither = n = 0
        for r in wide:
            if r.get(a) in ("", None) or r.get(b) in ("", None):
                continue
            n += 1
            va, vb = int(r[a]), int(r[b])
            if va and not vb:
                a_only += 1
            elif vb and not va:
                b_only += 1
            elif va and vb:
                both += 1
            else:
                neither += 1
        set_a = {i for i, r in enumerate(wide) if r.get(a) not in ("", None) and int(r[a])}
        set_b = {i for i, r in enumerate(wide) if r.get(b) not in ("", None) and int(r[b])}
        inter = len(set_a & set_b)
        union = len(set_a | set_b) or 1
        out[f"{a}__{b}"] = {
            "n": n,
            "a_only": a_only,
            "b_only": b_only,
            "both": both,
            "neither": neither,
            "a_exclusive_rate": round(a_only / n, 4) if n else None,
            "b_exclusive_rate": round(b_only / n, 4) if n else None,
            "jaccard": round(inter / union, 4),
            "a_acc": round((a_only + both) / n, 4) if n else None,
            "b_acc": round((b_only + both) / n, 4) if n else None,
        }
    return out


def arm_specificity(wide: list[dict], arms: list[str]) -> dict[str, Any]:
    """Share of an arm's wins that no other focus arm got."""
    out = {}
    for a in arms:
        solo = shared = 0
        for r in wide:
            if r.get(a) in ("", None) or not int(r[a]):
                continue
            others = [
                int(r[b])
                for b in arms
                if b != a and r.get(b) not in ("", None)
            ]
            if others and sum(others) == 0:
                solo += 1
            else:
                shared += 1
        tot = solo + shared
        out[a] = {
            "wins": tot,
            "solo_wins": solo,
            "solo_rate": round(solo / tot, 4) if tot else None,
        }
    return out


def replicate_chain(arm: str) -> dict[str, dict[str, bool]]:
    """cid_key -> {primary, replicate} chain flags on DEV slices."""
    gold = r5.load_gold()
    out: dict[str, dict[str, bool]] = {}
    rdir = r6.REPLICATE_DIRS.get(arm)
    if not rdir:
        return out
    for log_ds, dkey, sl in r6.DEV_SLICES:
        if not (r5.LOGS / log_ds / rdir / "case_stages").is_dir():
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            ta = r5.load_trajectory(log_ds, arm, cid)
            doc_b = r6.load_replicate_doc(log_ds, arm, cid)
            if not ta.get("raw_available") or doc_b is None:
                continue
            # adapt replicate
            fam = r5.FOCUS_ARMS[arm]["family"]
            if fam == "aphhm_c":
                tb = r5.adapt_aphhm_c(doc_b, arm)
            elif fam == "mosaic":
                tb = r5.adapt_mosaic(doc_b, arm)
            elif fam == "backbone":
                tb = r5.adapt_backbone(doc_b, arm)
            else:
                continue
            key = f"{dkey}:{sl}:{cid}"
            out[key] = {
                "primary": r5.champion_matches(ta, g),
                "replicate": r5.champion_matches(tb, g),
            }
    return out


def replicate_null(arm: str) -> Optional[dict[str, Any]]:
    pairs = replicate_chain(arm)
    if not pairs:
        return None
    a_only = b_only = both = neither = 0
    for v in pairs.values():
        if v["primary"] and not v["replicate"]:
            a_only += 1
        elif v["replicate"] and not v["primary"]:
            b_only += 1
        elif v["primary"] and v["replicate"]:
            both += 1
        else:
            neither += 1
    n = len(pairs)
    return {
        "arm": arm,
        "n": n,
        "primary_only": a_only,
        "replicate_only": b_only,
        "both": both,
        "neither": neither,
        "exclusive_rate_either": round((a_only + b_only) / n, 4) if n else None,
        "primary_only_rate": round(a_only / n, 4) if n else None,
        "stable_win_rate": round(both / n, 4) if n else None,
        "champ_agree": round((both + neither) / n, 4) if n else None,
    }


def stable_matrix(wide_chain: list[dict], arms_with_r2: list[str]) -> list[dict]:
    """Overwrite arm cells with stable_win = primary AND replicate on DEV."""
    gold = r5.load_gold()
    # build lookup
    stable: dict[tuple[str, str, str, str], int] = {}
    for arm in arms_with_r2:
        pairs = replicate_chain(arm)
        for key, v in pairs.items():
            dkey, sl, cid = key.split(":", 2)
            stable[(dkey, sl, cid, arm)] = int(v["primary"] and v["replicate"])
    out = []
    for r in wide_chain:
        nr = dict(r)
        for arm in arms_with_r2:
            k = (r["dataset"], r["slice"], r["case_id"], arm)
            if k in stable:
                nr[arm] = stable[k]
                nr[f"{arm}_stable"] = 1
            else:
                nr[f"{arm}_stable"] = 0
        out.append(nr)
    return out


def fit_rasch(wide: list[dict], arms: list[str]) -> dict[str, Any]:
    """Approximate Rasch via sklearn logistic with arm + case effects.

    P(correct) ~ sigmoid(ability_arm + easiness_case). Residual = obs - pred.
    Large |resid| flags potential arm-specific items.
    """
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception as e:
        return {"error": f"sklearn unavailable: {e}"}

    y = []
    meta = []
    arm_idx = {a: i for i, a in enumerate(arms)}
    case_ids = []
    case_key_to_i = {}
    for r in wide:
        key = (r["dataset"], r["slice"], r["case_id"])
        if key not in case_key_to_i:
            case_key_to_i[key] = len(case_ids)
            case_ids.append(key)
    n_cases = len(case_ids)
    n_arms = len(arms)
    X_rows = []
    for r in wide:
        ci = case_key_to_i[(r["dataset"], r["slice"], r["case_id"])]
        for a in arms:
            if r.get(a) in ("", None):
                continue
            y.append(int(r[a]))
            row = [0.0] * (n_arms + n_cases)
            row[arm_idx[a]] = 1.0
            row[n_arms + ci] = 1.0
            X_rows.append(row)
            meta.append((r["dataset"], r["slice"], r["case_id"], a, int(r[a])))
    if len(y) < 50:
        return {"error": "too few observations"}
    X = np.asarray(X_rows, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    model = LogisticRegression(max_iter=300, solver="lbfgs", fit_intercept=False)
    try:
        model.fit(X, y_arr)
    except Exception as e:
        return {"error": str(e)}
    pred = model.predict_proba(X)[:, 1]
    residuals = []
    for (ds, sl, cid, a, obs), p in zip(meta, pred):
        residuals.append(
            {
                "dataset": ds,
                "slice": sl,
                "case_id": cid,
                "arm": a,
                "obs": obs,
                "pred": round(float(p), 4),
                "resid": round(float(obs - p), 4),
            }
        )
    coef = model.coef_.ravel()
    abilities = {a: round(float(coef[i]), 4) for a, i in arm_idx.items()}
    # center abilities
    mean_ab = sum(abilities.values()) / len(abilities)
    abilities = {k: round(v - mean_ab, 4) for k, v in abilities.items()}
    specific = [
        r
        for r in residuals
        if (r["obs"] == 1 and r["pred"] < 0.25) or (r["obs"] == 0 and r["pred"] > 0.75)
    ]
    return {
        "abilities": abilities,
        "n_obs": len(y),
        "pseudo_r2": None,
        "n_arm_specific_flags": len(specific),
        "arm_specific_sample": specific[:40],
        "mean_abs_resid": round(float(np.mean(np.abs(pred - y_arr))), 4),
        "backend": "sklearn",
    }


def gate_pairs(
    pairs: dict[str, Any], nulls: dict[str, Any]
) -> dict[str, Any]:
    """Mark pairwise exclusive rates as resolvable vs noise floor."""
    # aggregate null = max exclusive_rate_either across arms
    floors = [
        n["exclusive_rate_either"]
        for n in nulls.values()
        if n and n.get("exclusive_rate_either") is not None
    ]
    floor = max(floors) if floors else 0.15
    out = {}
    for k, v in pairs.items():
        a, b = k.split("__", 1)
        a_ex = v.get("a_exclusive_rate") or 0
        b_ex = v.get("b_exclusive_rate") or 0
        out[k] = {
            **v,
            "noise_floor": floor,
            "a_resolvable": a_ex > floor,
            "b_resolvable": b_ex > floor,
            "either_resolvable": (a_ex > floor) or (b_ex > floor),
        }
    return out


def main() -> int:
    print("pivoting dual…")
    wide_c, arms = pivot_dual("chain_correct")
    wide_s, _ = pivot_dual("scored_correct")
    case_difficulty(wide_c, arms)
    case_difficulty(wide_s, arms)
    OUT.mkdir(parents=True, exist_ok=True)
    r4.write_tsv(OUT / "matrix_chain.tsv", wide_c)
    r4.write_tsv(OUT / "matrix_scored.tsv", wide_s)

    print("pairwise exclusive…")
    pairs_c = pairwise_exclusive(wide_c, arms)
    pairs_s = pairwise_exclusive(wide_s, arms)
    spec_c = arm_specificity(wide_c, arms)

    print("replicate nulls…")
    nulls = {}
    for arm in r6.REPLICATE_DIRS:
        print(f"  null {arm}")
        nulls[arm] = replicate_null(arm)
        if nulls[arm]:
            print(
                f"    n={nulls[arm]['n']} excl={nulls[arm]['exclusive_rate_either']} "
                f"stable={nulls[arm]['stable_win_rate']}"
            )

    gated = gate_pairs(pairs_c, {k: v for k, v in nulls.items() if v})
    # focus pairs for report
    focus_pairs = {
        k: gated[k]
        for k in gated
        if any(
            k == f"{a}__{b}" or k == f"{b}__{a}"
            for a, b in r6.PAIR_ARMS
        )
        or any(
            x in k
            for x in (
                "forest__collapse3c",
                "collapse3c__forest",
                "multistance__collapse3c",
                "collapse3c__multistance",
                "forest__e7",
                "e7__forest",
                "lite__collapse3c",
                "collapse3c__lite",
                "forest__lite",
                "lite__forest",
            )
        )
    }

    print("stable matrix…")
    arms_r2 = [a for a, n in nulls.items() if n and n.get("n", 0) > 50]
    stable = stable_matrix(wide_c, arms_r2)
    # only DEV rows have stable flags filled; filter to those with any stable
    stable_dev = [
        r
        for r in stable
        if any(r.get(f"{a}_stable") for a in arms_r2)
    ]
    pairs_stable = pairwise_exclusive(stable_dev, arms_r2) if stable_dev else {}

    print("Rasch…")
    # Rasch on core deep arms with full coverage
    rasch_arms = [a for a in ("collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07") if a in arms]
    rasch = fit_rasch(wide_c, rasch_arms)

    summary = {
        "n_cases_chain": len(wide_c),
        "arms": arms,
        "difficulty_hist": {
            str(k): v
            for k, v in sorted(
                (
                    (d, sum(1 for r in wide_c if r.get("n_arms_correct") == d))
                    for d in range(0, len(arms) + 1)
                ),
                key=lambda x: x[0],
            )
        },
        "arm_specificity_chain": spec_c,
        "replicate_nulls": nulls,
        "pairwise_chain_gated": gated,
        "focus_pairs": focus_pairs,
        "pairwise_stable": pairs_stable,
        "arms_with_replicate": arms_r2,
        "rasch": {
            k: rasch[k]
            for k in (
                "abilities",
                "n_obs",
                "pseudo_r2",
                "n_arm_specific_flags",
                "mean_abs_resid",
                "error",
            )
            if k in rasch
        },
        "rasch_arm_specific_sample": rasch.get("arm_specific_sample", [])[:20],
        "noise_floor_exclusive": max(
            (
                n["exclusive_rate_either"]
                for n in nulls.values()
                if n and n.get("exclusive_rate_either") is not None
            ),
            default=None,
        ),
    }
    r6.write_json(OUT / "summary.json", summary)
    r4.write_tsv(OUT / "matrix_chain_stable.tsv", stable_dev)
    print(f"wrote {OUT}")
    print("noise floor exclusive", summary["noise_floor_exclusive"])
    print("focus pairs:")
    for k, v in focus_pairs.items():
        print(
            f"  {k}: a_only={v['a_only']} b_only={v['b_only']} "
            f"jacc={v['jaccard']} resolvable={v['either_resolvable']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
