#!/usr/bin/env python3
"""Phase 4: predictive covariates with bootstrap CI + BH correction + AUC."""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from pathlib import Path

import disagreement_census as dc
import r4_lib as r4
import trajectory_anatomy_lib as tal

OUT = r4.OUT / "r4_covariates"


def bh_correct(pvals: list[float]) -> list[float]:
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        # rank from end: k = n-rank+1
        k = n - rank + 1
        val = min(prev, pvals[i] * n / k)
        prev = val
        adj[i] = val
    return adj


def bootstrap_auc(y: list[int], scores: list[float], n_boot: int = 500) -> dict:
    """AUC via Mann-Whitney; bootstrap CI."""
    def auc(yy, ss):
        pos = [s for y_, s in zip(yy, ss) if y_ == 1]
        neg = [s for y_, s in zip(yy, ss) if y_ == 0]
        if not pos or not neg:
            return 0.5
        # brute pairwise
        gt = sum(1 for p in pos for n in neg if p > n)
        eq = sum(1 for p in pos for n in neg if p == n)
        return (gt + 0.5 * eq) / (len(pos) * len(neg))

    base = auc(y, scores)
    rng = random.Random(0)
    boots = []
    n = len(y)
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        boots.append(auc([y[i] for i in idx], [scores[i] for i in idx]))
    boots.sort()
    return {
        "auc": base,
        "lo": boots[int(0.025 * n_boot)],
        "hi": boots[int(0.975 * n_boot) - 1],
    }


def featurize(rows: list[dict]) -> list[dict]:
    # load vignettes per slice
    cache = {}
    out = []
    for r in rows:
        ds, sl, cid = r["dataset"], r["slice"], r["case_id"]
        key = (ds, sl)
        if key not in cache:
            slices = dc.DA_SLICES if ds == "da" else dc.MCR_SLICES
            spec = slices[sl]
            cache[key] = tal.load_cases(spec["subset"])
        case = cache[key].get(str(cid)) or {}
        text = tal.vignette_text(case)
        feats = tal.vignette_features(text)
        feats.update(tal.gold_features(r.get("gold") or ""))
        if ds == "da":
            opts = tal.da_options(case)
            feats.update(tal.option_structure(r.get("gold") or "", opts))
            # split sections if present in parquet-backed case_text — heuristic
            feats["has_pe_section"] = "Physical Examination" in text or "physical exam" in text.lower()
            feats["has_tests_section"] = "Diagnostic Tests" in text or "laboratory" in text.lower()
        else:
            ann = case.get("annotation") or {}
            feats["journal_len"] = len(str(ann.get("journal") or ""))
            feats["title_len"] = len(str(ann.get("title") or ""))
        feats["dataset"] = ds
        feats["slice"] = sl
        feats["case_id"] = cid
        feats["y_e7_chain_fail"] = int(not r4.truthy(r.get("e7_chain_correct")))
        feats["y_base_win_chain"] = int((r.get("layer_chain") or "") in ("base_win_rank", "base_win_recall"))
        feats["y_s4_miss"] = int((r.get("e7_locus") or r.get("tax_e7_locus") or "") == "s3_hit_s4_miss")
        out.append(feats)
    return out


def univariate(feats: list[dict], ykey: str, xkeys: list[str]) -> list[dict]:
    """Point-biserial-ish: mean diff + bootstrap CI on delta; crude p via permutation."""
    results = []
    y = [f[ykey] for f in feats]
    rng = random.Random(1)
    for xk in xkeys:
        xs = []
        ys = []
        for f in feats:
            v = f.get(xk)
            if v is None or v == "":
                continue
            try:
                xs.append(float(v))
                ys.append(f[ykey])
            except Exception:
                continue
        if len(xs) < 30:
            continue
        pos = [x for x, y_ in zip(xs, ys) if y_ == 1]
        neg = [x for x, y_ in zip(xs, ys) if y_ == 0]
        if not pos or not neg:
            continue
        delta = sum(pos) / len(pos) - sum(neg) / len(neg)
        # permutation p
        obs = abs(delta)
        count = 0
        n_perm = 500
        arr = list(zip(xs, ys))
        for _ in range(n_perm):
            rng.shuffle(ys_perm := [y for _, y in arr])
            # actually shuffle labels
            labels = [y for _, y in arr]
            rng.shuffle(labels)
            vals = [x for x, _ in arr]
            ppos = [v for v, y_ in zip(vals, labels) if y_ == 1]
            pneg = [v for v, y_ in zip(vals, labels) if y_ == 0]
            if not ppos or not pneg:
                continue
            d = abs(sum(ppos) / len(ppos) - sum(pneg) / len(pneg))
            if d >= obs - 1e-12:
                count += 1
        p = (count + 1) / (n_perm + 1)
        # score for AUC: use feature itself (or -feature if delta negative for fail)
        scores = xs if delta > 0 else [-x for x in xs]
        auc = bootstrap_auc(ys, scores)
        results.append(
            {
                "feature": xk,
                "target": ykey,
                "n": len(xs),
                "delta_pos_minus_neg": delta,
                "p_perm": p,
                "auc": auc["auc"],
                "auc_lo": auc["lo"],
                "auc_hi": auc["hi"],
            }
        )
    # BH
    if results:
        adj = bh_correct([r["p_perm"] for r in results])
        for r, q in zip(results, adj):
            r["q_bh"] = q
    results.sort(key=lambda r: r["p_perm"])
    return results


def cluster_base_wins(rows: list[dict]) -> dict:
    wins = [r for r in rows if (r.get("layer_chain") or "") in ("base_win_rank", "base_win_recall")]
    # simple clustering by gold length / subtype / dataset
    buckets = Counter()
    for r in wins:
        g = r.get("gold") or ""
        tag = []
        tag.append(r.get("dataset"))
        tag.append("subtype" if tal.SUBTYPE_RX.search(g) else "nosub")
        tag.append("short" if len(g.split()) <= 3 else "long")
        tag.append(r.get("layer_chain"))
        buckets["|".join(tag)] += 1
    return {
        "n": len(wins),
        "top_buckets": buckets.most_common(15),
        "note": "Descriptive only; if mass concentrates in few buckets, win set is typable.",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    feats = featurize(rows)
    r4.write_tsv(OUT / "features.tsv", feats)
    xkeys = [
        "vig_words",
        "vig_lab_dens",
        "vig_diff_dens",
        "gold_words",
        "gold_has_eponym",
        "gold_has_subtype",
        "gold_has_paren",
        "n_options",
        "n_opts_near_gold",
        "max_opt_gold_overlap",
        "has_pe_section",
        "has_tests_section",
        "journal_len",
        "title_len",
    ]
    all_res = []
    for yk in ("y_e7_chain_fail", "y_base_win_chain", "y_s4_miss"):
        all_res.extend(univariate(feats, yk, xkeys))
    (OUT / "univariate.json").write_text(
        json.dumps(all_res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # best AUC per target
    by_t = {}
    for r in all_res:
        by_t.setdefault(r["target"], []).append(r)
    best = {t: max(vs, key=lambda r: r["auc"]) for t, vs in by_t.items()}
    clusters = cluster_base_wins(rows)
    summary = {
        "best_auc_per_target": best,
        "n_sig_q05": sum(1 for r in all_res if r.get("q_bh", 1) < 0.05),
        "honest_null": all(best[t]["auc"] < 0.60 for t in best),
        "base_win_clusters": clusters,
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
