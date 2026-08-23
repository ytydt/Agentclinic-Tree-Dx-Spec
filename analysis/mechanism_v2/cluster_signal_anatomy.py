#!/usr/bin/env python3
"""Why the cluster signal does not convert: between-case vs within-case anatomy.

Q9 left a paradox on the record. The candidate-level monotonicity is real
(`n_high_groups` 0/1/2/3 -> complete rate 0.030/0.054/0.086/0.120, a 4x spread),
yet *ranking* by that same quantity is strictly worse than generation order
(0.3072 vs 0.5602 top-1 conversion). A signal cannot be both informative and
useless unless the level it lives on is not the level the selector acts on.

The selector always chooses among candidates *inside one case*. So the pooled
monotonicity decomposes into two parts that are worth very different amounts:

    between-case   cases differ in how much high-specificity evidence exists
                   at all. Raises the pooled rate, but the selector never
                   compares across cases, so it is unusable.
    within-case    inside a case, the complete candidate carries more distinct
                   high-specificity groups than its rivals. This is the only
                   part a selector could exploit.

Everything here reads frozen artifacts. Zero LLM calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

# Must stay `medcasereasoning*`: a bare `*` also matches other datasets, whose
# slices are absent from SLICE_OF_DIR and would silently score as incomplete.
ARM = "logs/backbone_v1/medcasereasoning*/aphhm_c_multistance_v1/case_stages/*.json"
SLICE_OF_DIR = {
    "medcasereasoning": "mcr_v1",
    "medcasereasoning_v2": "mcr_v2",
    "medcasereasoning_200b": "mcr_200b",
}
OUT = ROOT / "analysis/mechanism_v2/results/CLUSTER_SIGNAL_ANATOMY"


def load_cohort() -> list[dict[str, Any]]:
    """Per-case candidate tables, with evidence width from the frozen ledger.

    Uses `support_fact_ids` rather than Q9's substring span matching: the join is
    exact, so a null result cannot be blamed on the fuzzy matcher.
    """
    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()
    cases: list[dict[str, Any]] = []
    for path in sorted(ROOT.glob(ARM)):
        sl = SLICE_OF_DIR.get(path.parts[-4])
        if sl is None:
            raise SystemExit(f"unmapped slice dir {path.parts[-4]!r}: would score as incomplete")
        cid = path.stem
        stages = json.loads(path.read_text()).get("stages") or {}
        registry = stages.get("registry") or []
        if not registry:
            continue
        group_of: dict[str, str] = {}
        high_groups: set[str] = set()
        for f in (stages.get("facts") or []):
            g = str(f.get("correlation_group") or "")
            group_of[str(f.get("fact_id"))] = g
            if str(f.get("specificity") or "") == "high":
                high_groups.add(g)
        cands = []
        for i, cand in enumerate(registry):
            fids = [str(x) for x in (cand.get("support_fact_ids") or [])]
            groups = {group_of[f] for f in fids if f in group_of}
            cands.append({
                "i": i,
                "neg_i": -i,
                "label": str(cand.get("preferred_label") or ""),
                "origin": str(cand.get("origin") or ""),
                "n_groups": len(groups),
                "n_high_groups": len(groups & high_groups),
                "n_spans": len(cand.get("support_spans") or []),
                "complete": endpoint.relation("mcr", sl, cid, cand.get("preferred_label") or "")
                == COMPLETE,
            })
        cases.append({
            "slice": sl,
            "case_id": cid,
            "n_high_groups_available": len(high_groups),
            "candidates": cands,
        })
    return cases


def pooled_monotonicity(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    buckets: dict[int, list[bool]] = {}
    for case in cases:
        for c in case["candidates"]:
            buckets.setdefault(int(c[key]), []).append(bool(c["complete"]))
    out = {}
    for k in sorted(buckets):
        v = buckets[k]
        out[str(k)] = {
            "candidates": len(v),
            "complete": sum(v),
            "complete_rate": round(sum(v) / len(v), 4),
        }
    return out


def within_case_concordance(cases: list[dict[str, Any]], key: str, higher_is_better: bool = True):
    """P(complete ranks above incomplete) over all such pairs *inside* a case.

    This is the only quantity a within-case ranker can convert. 0.5 means the
    signal carries nothing usable at selection time, regardless of how strong the
    pooled association looks.
    """
    wins = ties = losses = 0
    for case in cases:
        comp = [c for c in case["candidates"] if c["complete"]]
        inc = [c for c in case["candidates"] if not c["complete"]]
        if not comp or not inc:
            continue
        for a in comp:
            for b in inc:
                va, vb = a[key], b[key]
                if not higher_is_better:
                    va, vb = -va, -vb
                if va > vb:
                    wins += 1
                elif va == vb:
                    ties += 1
                else:
                    losses += 1
    n = wins + ties + losses
    return {
        "pairs": n,
        "wins": wins,
        "ties": ties,
        "losses": losses,
        # ties split evenly: a ranker breaking them arbitrarily gets half
        "concordance": round((wins + 0.5 * ties) / n, 4) if n else None,
        "tie_rate": round(ties / n, 4) if n else None,
    }


def between_vs_within(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Split the pooled association into a case-level part and a deviation part."""
    reachable = [c for c in cases if any(x["complete"] for x in c["candidates"])]
    unreachable = [c for c in cases if not any(x["complete"] for x in c["candidates"])]

    def case_mean(case, k):
        vals = [c[k] for c in case["candidates"]]
        return mean(vals) if vals else 0.0

    dev_buckets: dict[str, list[bool]] = {}
    for case in reachable:
        mu = case_mean(case, key)
        for c in case["candidates"]:
            d = c[key] - mu
            band = "<-1" if d < -1 else "-1..0" if d < 0 else "0" if d == 0 else "0..1" if d <= 1 else ">1"
            dev_buckets.setdefault(band, []).append(bool(c["complete"]))
    dev = {}
    for band in ("<-1", "-1..0", "0", "0..1", ">1"):
        v = dev_buckets.get(band) or []
        if v:
            dev[band] = {
                "candidates": len(v),
                "complete": sum(v),
                "complete_rate": round(sum(v) / len(v), 4),
            }
    return {
        "case_mean_of_key_reachable": round(mean([case_mean(c, key) for c in reachable]), 4),
        "case_mean_of_key_unreachable": round(mean([case_mean(c, key) for c in unreachable]), 4)
        if unreachable else None,
        "high_groups_available_reachable": round(
            mean([c["n_high_groups_available"] for c in reachable]), 4),
        "high_groups_available_unreachable": round(
            mean([c["n_high_groups_available"] for c in unreachable]), 4) if unreachable else None,
        "complete_rate_by_deviation_from_case_mean": dev,
    }


def top1_by(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Top-1 conversion on pool-reachable cases, ties broken by generation order."""
    reachable = [c for c in cases if any(x["complete"] for x in c["candidates"])]
    hit = 0
    for case in reachable:
        best = max(case["candidates"], key=lambda x: (x[key], -x["i"]))
        hit += int(best["complete"])
    return {
        "reachable_cases": len(reachable),
        "top1_complete": hit,
        "conversion": round(hit / len(reachable), 4) if reachable else None,
    }


def residual_vs_gen_order(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """On pairs where the cluster signal and generation order disagree, who is right?

    Concordance alone cannot tell a weaker-but-additive signal from a dominated
    one. Restricting to disagreements isolates exactly the decisions where using
    the cluster signal would override position, which is the only place it could
    ever add value.
    """
    cluster_right = gen_right = 0
    for case in cases:
        comp = [c for c in case["candidates"] if c["complete"]]
        inc = [c for c in case["candidates"] if not c["complete"]]
        for a in comp:
            for b in inc:
                # gen_order always has an opinion (no ties); skip cluster ties
                if a[key] == b[key]:
                    continue
                cluster_prefers_complete = a[key] > b[key]
                gen_prefers_complete = a["i"] < b["i"]
                if cluster_prefers_complete == gen_prefers_complete:
                    continue
                if cluster_prefers_complete:
                    cluster_right += 1
                else:
                    gen_right += 1
    n = cluster_right + gen_right
    return {
        "disagreement_pairs": n,
        "cluster_signal_right": cluster_right,
        "gen_order_right": gen_right,
        "cluster_win_share": round(cluster_right / n, 4) if n else None,
    }


def oracle_ceiling(cases: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Best conversion the signal could reach if every tie were broken perfectly.

    Bounds the signal's value from above: even a flawless tie-breaker cannot beat
    this, so if it sits at or below the incumbent the signal has no headroom.
    """
    from math import comb

    reachable = [c for c in cases if any(x["complete"] for x in c["candidates"])]
    hit = 0
    null_p: list[float] = []
    set_sizes: list[int] = []
    pool_sizes: list[int] = []
    for case in reachable:
        cands = case["candidates"]
        best = max(c[key] for c in cands)
        tied = [c for c in cands if c[key] == best]
        hit += int(any(c["complete"] for c in tied))
        n, k = len(cands), len(tied)
        n_comp = sum(1 for c in cands if c["complete"])
        set_sizes.append(k)
        pool_sizes.append(n)
        # A size-matched null: a signal carrying no information, but with this
        # signal's tie structure, still gets k draws. Without this, a wide tied
        # set would make the oracle look strong for free.
        null_p.append(1.0 - (comb(n - n_comp, k) / comb(n, k) if n - n_comp >= k else 0.0))
    return {
        "reachable_cases": len(reachable),
        "oracle_top1_complete": hit,
        "oracle_conversion": round(hit / len(reachable), 4) if reachable else None,
        "mean_tied_max_set_size": round(mean(set_sizes), 4) if set_sizes else None,
        "mean_pool_size": round(mean(pool_sizes), 4) if pool_sizes else None,
        "size_matched_random_null_conversion": round(mean(null_p), 4) if null_p else None,
        "oracle_lift_over_null": round(
            hit / len(reachable) - mean(null_p), 4) if reachable else None,
    }


def main() -> int:
    cases = load_cohort()
    reachable = [c for c in cases if any(x["complete"] for x in c["candidates"])]

    result: dict[str, Any] = {
        "n_cases": len(cases),
        "n_pool_reachable": len(reachable),
        "n_candidates": sum(len(c["candidates"]) for c in cases),
        "pooled_monotonicity_n_high_groups": pooled_monotonicity(cases, "n_high_groups"),
        "pooled_monotonicity_n_groups": pooled_monotonicity(cases, "n_groups"),
        "within_case_concordance": {
            "n_high_groups": within_case_concordance(cases, "n_high_groups"),
            "n_groups": within_case_concordance(cases, "n_groups"),
            "n_spans": within_case_concordance(cases, "n_spans"),
            "gen_order_earlier_is_better": within_case_concordance(
                cases, "i", higher_is_better=False),
        },
        "between_vs_within_n_high_groups": between_vs_within(cases, "n_high_groups"),
        "top1_conversion": {
            # gen_order top-1 is the first candidate emitted, so rank on -i.
            "gen_order": top1_by(cases, "neg_i"),
            "n_high_groups": top1_by(cases, "n_high_groups"),
            "n_groups": top1_by(cases, "n_groups"),
        },
    }

    # Is the cluster signal simply a shadow of generation order?
    early_high, late_high = [], []
    for case in cases:
        for c in case["candidates"]:
            (early_high if c["i"] < 3 else late_high).append(c["n_high_groups"])
    result["n_high_groups_by_position"] = {
        "first_3_generated_mean": round(mean(early_high), 4),
        "later_mean": round(mean(late_high), 4),
    }
    result["residual_vs_gen_order"] = {
        "n_high_groups": residual_vs_gen_order(cases, "n_high_groups"),
        "n_groups": residual_vs_gen_order(cases, "n_groups"),
    }
    result["oracle_ceiling"] = {
        "n_high_groups": oracle_ceiling(cases, "n_high_groups"),
        "n_groups": oracle_ceiling(cases, "n_groups"),
        "incumbent_gen_order_actual": result["top1_conversion"]["gen_order"],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "anatomy.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
