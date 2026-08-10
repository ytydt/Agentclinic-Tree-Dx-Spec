#!/usr/bin/env python3
"""R6 predictive models: covariates vs mechanism vars, pairwise win models."""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r6_models.json"

COV_COLS = [
    "gold_prevalence_pct",
    "gold_is_rare",
    "gold_has_subtype",
    "gold_has_paren",
    "vig_chars",
    "vig_words",
    "pathology_or_genetics_needed",
    "vig_has_pathology",
    "vig_has_genetics",
    "vig_has_imaging",
    "n_option_near_pairs",
    "max_distractor_gold_jaccard",
]

MECH_COLS_COMMON = [
    "n_candidates",
    "n_shortlist",
    "gold_disc",
    "champ_disc",
    "gold_span_verbatim_rate",
    "score_gap_champ_minus_gold",
    "gold_n_for",
    "gold_n_against",
]
# Intentionally EXCLUDED from incremental claim: pool_has_gold /
# shortlist_has_gold (near-necessary for chain_correct → AUC leakage).
MECH_COLS_MOSAIC = [
    "top_margin",
    "unexplained_n",
    "generator_jaccard",
    "gold_rejected",
]
MECH_COLS_APHHM = [
    "n_facts",
    "n_high_specific_facts",
    "has_pathology_fact",
    "has_genetics_fact",
    "frontier_n",
]

DEV_SLICES = {"d2_seq100", "d2_heldout100", "mcr_v1", "mcr_v2"}
HOLD_SLICES = {"d2_heldout200b", "mcr_200b"}


def _f(v: Any) -> Optional[float]:
    if v in ("", None, "None"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def bh(pvals: list[float]) -> list[float]:
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    q = [1.0] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        # rank from end: BH
        r = n - rank + 1
        val = min(prev, pvals[i] * n / r)
        q[i] = val
        prev = val
    return q


def auc_score(y: np.ndarray, s: np.ndarray) -> float:
    # Mann-Whitney AUC
    pos = s[y == 1]
    neg = s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    # handle ties via average rank
    from scipy.stats import rankdata

    ranks = rankdata(np.concatenate([pos, neg]))
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def matrix(
    rows: list[dict], cols: list[str], ycol: str
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    X_list = []
    y_list = []
    for r in rows:
        yv = _f(r.get(ycol))
        if yv is None:
            continue
        vec = []
        for c in cols:
            v = _f(r.get(c))
            vec.append(np.nan if v is None else v)
        X_list.append(vec)
        y_list.append(yv)
    return np.asarray(X_list, float), np.asarray(y_list, float), cols


def fit_logit(
    X: np.ndarray, y: np.ndarray
) -> tuple[Optional[Any], Optional[np.ndarray], dict[str, Any]]:
    """Fit L2-logistic via sklearn (statsmodels broken on this scipy)."""
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        return None, None, {"error": str(e)}
    if y.sum() < 5 or (len(y) - y.sum()) < 5:
        return None, None, {"error": "too few positives/negatives"}
    keep = [i for i in range(X.shape[1]) if np.nanstd(X[:, i]) > 1e-8]
    if not keep:
        return None, None, {"error": "no variance"}
    Xk = X[:, keep].copy()
    col_mean = np.nanmean(Xk, axis=0)
    inds = np.where(np.isnan(Xk))
    Xk[inds] = np.take(col_mean, inds[1])
    scaler = StandardScaler()
    Xs = scaler.fit_transform(Xk)
    model = LogisticRegression(
        max_iter=500, solver="lbfgs", class_weight="balanced"
    )
    try:
        model.fit(Xs, y)
    except Exception as e:
        return None, None, {"error": str(e)}
    # attach helpers for predict
    model._r6_scaler = scaler
    model._r6_col_mean = col_mean
    model._r6_keep = np.array(keep)
    # fake params/pvalues interface via coef magnitudes; p from none
    model.params = np.concatenate([[0.0], model.coef_.ravel()])
    model.pvalues = np.ones_like(model.params)
    return model, np.array(keep), {"ok": True, "backend": "sklearn"}


def _predict(model, X_raw: np.ndarray) -> np.ndarray:
    keep = model._r6_keep
    Xk = X_raw[:, keep].copy()
    inds = np.where(np.isnan(Xk))
    Xk[inds] = np.take(model._r6_col_mean, inds[1])
    Xs = model._r6_scaler.transform(Xk)
    return model.predict_proba(Xs)[:, 1]


def eval_split(
    rows_tr: list[dict],
    rows_te: list[dict],
    cols: list[str],
    ycol: str,
) -> dict[str, Any]:
    Xtr, ytr, _ = matrix(rows_tr, cols, ycol)
    Xte, yte, _ = matrix(rows_te, cols, ycol)
    if len(ytr) < 30 or len(yte) < 10:
        return {"error": "small_n", "n_tr": len(ytr), "n_te": len(yte)}
    model, keep, meta = fit_logit(Xtr, ytr)
    if model is None:
        return {**meta, "n_tr": len(ytr), "n_te": len(yte)}
    pred_te = _predict(model, Xte)
    pred_tr = _predict(model, Xtr)
    auc = auc_score(yte, pred_te)
    names = [cols[i] for i in keep]
    coefs = {}
    # coefficient magnitude as importance proxy (standardised)
    for i, name in enumerate(names):
        coefs[name] = {
            "beta_std": round(float(model.coef_.ravel()[i]), 4),
            "abs_beta": round(float(abs(model.coef_.ravel()[i])), 4),
        }
    # top features by |beta|
    top = sorted(coefs.items(), key=lambda kv: -kv[1]["abs_beta"])[:8]
    return {
        "n_tr": int(len(ytr)),
        "n_te": int(len(yte)),
        "auc_holdout": round(auc, 4),
        "auc_train": round(auc_score(ytr, pred_tr), 4),
        "coefs": coefs,
        "top_features": [{k: v} for k, v in top],
        "y_rate_te": round(float(yte.mean()), 4),
        "backend": "sklearn",
    }


def join_cov_mech() -> dict[str, list[dict]]:
    cov = {
        (r["dataset"], r["slice"], r["case_id"]): r
        for r in load_tsv(r5.OUT / "mosaic_eval" / "r6_covariates.tsv")
    }
    mech = load_tsv(r5.OUT / "mosaic_eval" / "r6_mechvars.tsv")
    locus = {
        (r["dataset"], r["slice"], r["case_id"], r["arm"]): r
        for r in load_tsv(r5.R5_OUT / "pooled.tsv")
    }
    by_arm: dict[str, list[dict]] = defaultdict(list)
    for r in mech:
        key = (r["dataset"], r["slice"], r["case_id"])
        row = dict(r)
        row.update({f"cov_{k}": v for k, v in (cov.get(key) or {}).items() if k not in row})
        # flatten cov without prefix for model cols
        c = cov.get(key) or {}
        for k in COV_COLS:
            if k in c:
                row[k] = c[k]
        loc = locus.get((r["dataset"], r["slice"], r["case_id"], r["arm"]))
        if loc:
            row["locus"] = loc.get("locus")
            row["subcode"] = loc.get("subcode")
        by_arm[r["arm"]].append(row)
    return by_arm


def pairwise_rows_from_cov(
    cov_rows: list[dict], dual_rows: list[dict], a: str, b: str
) -> list[dict]:
    """Build pairwise win rows using covariates + dual chain for any arms."""
    cov = {(r["dataset"], r["slice"], r["case_id"]): r for r in cov_rows}
    # dual long -> chain per arm
    chain: dict[tuple, dict[str, int]] = {}
    for r in dual_rows:
        key = (r["dataset"], r["slice"], r["case_id"])
        chain.setdefault(key, {})
        if r.get("chain_correct") not in ("", None):
            chain[key][r["arm"]] = int(r["chain_correct"])
    out = []
    for key, ca_map in chain.items():
        if a not in ca_map or b not in ca_map:
            continue
        c = cov.get(key) or {}
        ca, cb = ca_map[a], ca_map[b]
        row = {col: c.get(col) for col in COV_COLS}
        row.update(
            {
                "dataset": key[0],
                "slice": key[1],
                "case_id": key[2],
                "y_a_win_b_lose": int(ca == 1 and cb == 0),
                "y_b_win_a_lose": int(cb == 1 and ca == 0),
            }
        )
        out.append(row)
    return out


def main() -> int:
    print("joining…")
    by_arm = join_cov_mech()
    cov_rows = load_tsv(r5.OUT / "mosaic_eval" / "r6_covariates.tsv")
    dual_rows = load_tsv(r5.OUT / "mosaic_eval" / "r5_dual" / "dual.tsv")
    report: dict[str, Any] = {
        "per_arm_chain": {},
        "per_arm_locus_genmiss": {},
        "per_arm_chain_given_pool": {},
        "pairwise": {},
        "incremental": {},
        "note": (
            "Mechanism cols exclude pool_has_gold/shortlist_has_gold to avoid "
            "near-necessary leakage into chain_correct. Incremental AUC uses "
            "non-leaky mech vars. Separately, among pool_has_gold==1, we report "
            "mech-only AUC for decision conversion."
        ),
    }

    for arm, rows in by_arm.items():
        tr = [r for r in rows if r["slice"] in DEV_SLICES]
        te = [r for r in rows if r["slice"] in HOLD_SLICES]
        if not te:
            tr = [r for r in rows if r["slice"] in ("d2_seq100", "mcr_v1")]
            te = [r for r in rows if r["slice"] in ("d2_heldout100", "mcr_v2")]
        cov_res = eval_split(tr, te, COV_COLS, "chain_correct")
        mcols = list(MECH_COLS_COMMON)
        if arm in ("forest", "lite"):
            mcols += MECH_COLS_MOSAIC
        if arm in ("collapse3c", "multistance", "aphhm_c_v1"):
            mcols += MECH_COLS_APHHM
        mech_res = eval_split(tr, te, mcols, "chain_correct")
        both_res = eval_split(tr, te, COV_COLS + mcols, "chain_correct")
        for r in rows:
            r["y_genmiss"] = int(r.get("locus") == "generation_miss")
        gen_res = eval_split(tr, te, COV_COLS, "y_genmiss")
        # conditioned on pool hit
        tr_p = [r for r in tr if _f(r.get("pool_has_gold")) == 1]
        te_p = [r for r in te if _f(r.get("pool_has_gold")) == 1]
        pool_mech = eval_split(tr_p, te_p, mcols, "chain_correct")
        pool_cov = eval_split(tr_p, te_p, COV_COLS, "chain_correct")
        report["per_arm_chain"][arm] = {
            "covariates": cov_res,
            "mechanism": mech_res,
            "both": both_res,
        }
        report["per_arm_locus_genmiss"][arm] = gen_res
        report["per_arm_chain_given_pool"][arm] = {
            "covariates": pool_cov,
            "mechanism": pool_mech,
            "n_tr": len(tr_p),
            "n_te": len(te_p),
        }
        ca = (cov_res or {}).get("auc_holdout")
        ba = (both_res or {}).get("auc_holdout")
        delta = None if ca is None or ba is None else round(ba - ca, 4)
        # prereg: incremental among decision-relevant mech
        pca = (pool_cov or {}).get("auc_holdout")
        pma = (pool_mech or {}).get("auc_holdout")
        pdelta = None if pca is None or pma is None else round(pma - pca, 4)
        report["incremental"][arm] = {
            "auc_cov": ca,
            "auc_both": ba,
            "delta": delta,
            "claims_mech_better_unconditional": bool(delta is not None and delta > 0.02),
            "given_pool_auc_cov": pca,
            "given_pool_auc_mech": pma,
            "given_pool_delta_mech_minus_cov": pdelta,
            "claims_mech_better_given_pool": bool(pdelta is not None and pdelta > 0.02),
        }
        print(
            f"{arm}: cov={ca} both={ba} Δ={delta} | "
            f"given_pool cov={pca} mech={pma} Δ={pdelta}"
        )

    for a, b in r6.PAIR_ARMS:
        rows = pairwise_rows_from_cov(cov_rows, dual_rows, a, b)
        tr = [r for r in rows if r["slice"] in DEV_SLICES]
        te = [r for r in rows if r["slice"] in HOLD_SLICES]
        if not te:
            tr = [r for r in rows if r["slice"] in ("d2_seq100", "mcr_v1")]
            te = [r for r in rows if r["slice"] in ("d2_heldout100", "mcr_v2")]
        res_ab = eval_split(tr, te, COV_COLS, "y_a_win_b_lose")
        res_ba = eval_split(tr, te, COV_COLS, "y_b_win_a_lose")
        report["pairwise"][f"{a}_vs_{b}"] = {
            "a_win_b_lose": res_ab,
            "b_win_a_lose": res_ba,
            "n": len(rows),
            "rate_a_excl": round(sum(r["y_a_win_b_lose"] for r in rows) / len(rows), 4)
            if rows
            else None,
            "rate_b_excl": round(sum(r["y_b_win_a_lose"] for r in rows) / len(rows), 4)
            if rows
            else None,
        }
        print(
            f"pair {a}/{b}: a_excl_auc={(res_ab or {}).get('auc_holdout')} "
            f"b_excl_auc={(res_ba or {}).get('auc_holdout')}"
        )

    disc_block = {}
    for arm, rows in by_arm.items():
        sub = [
            r
            for r in rows
            if _f(r.get("pool_has_gold")) == 1 and _f(r.get("gold_disc")) is not None
        ]
        if len(sub) < 40:
            continue
        te = [
            r
            for r in sub
            if r["slice"] in HOLD_SLICES or r["slice"] in ("d2_heldout100", "mcr_v2")
        ]
        use = te if len(te) >= 20 else sub
        y = np.array([_f(r["chain_correct"]) for r in use], float)
        s = np.array([_f(r["gold_disc"]) for r in use], float)
        auc = auc_score(y, s)
        disc_block[arm] = {
            "n": len(use),
            "auc_disc_predicts_chain": round(float(auc), 4),
            "passes_prereg": bool(auc > 0.55),
        }
    report["disc_predicts_chain"] = disc_block

    r6.write_json(OUT, report)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
