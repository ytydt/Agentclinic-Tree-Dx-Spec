#!/usr/bin/env python3
"""R5 mechanism-level locus: six shared buckets + per-family subcodes.

Order of first hit:
  generation_miss -> identity_loss -> prune_loss -> decision_loss
  -> interface_loss -> ok

Legacy arms (e7/v0/B06/B07/APHHM) map their R2/R3 loci into the same six
buckets so cross-family tables stay comparable.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import r4_lib as r4
import r5_lib as r5

OUT = r5.R5_OUT
BUCKETS = (
    "generation_miss",
    "identity_loss",
    "prune_loss",
    "decision_loss",
    "interface_loss",
    "ok",
    "missing",
)


def _sub_aphhm_c(traj: dict[str, Any], gold: str, bucket: str) -> str:
    if bucket == "generation_miss":
        return "view_miss_all"
    if bucket == "identity_loss":
        return "merge_swallow"
    if bucket == "prune_loss":
        # gate veto on gold concept?
        gold_labs = {c["label"] for c in r5.gold_candidates(traj, gold)}
        for g in traj.get("gate") or []:
            vr = str(g.get("veto_reason") or "")
            if "shared_phenotype" in vr or vr == "p5_shared_phenotype":
                return "gate_veto_p5_shared_phenotype"
            if vr and vr not in ("", "not_admitted"):
                return "gate_veto_p4"
        # gold in pool but not shortlist. Selector arms (collapse3c /
        # multistance / msplit) keep registry.score == 0.0 because c4 is
        # skipped, so "score_below_frontier" was a false attribution —
        # rename to no_numeric_score (frontier cut is prompt / nomination,
        # not a numeric ledger rank).
        if traj.get("finalists") is not None and traj.get("finalists") == []:
            pass
        return "no_numeric_score"
    if bucket == "decision_loss":
        fins = traj.get("finalists") or []
        if fins:
            if r5.gold_in_shortlist(traj, gold) and not r5.gold_in_finalists(traj, gold):
                return "nominate_drop"
            if r5.gold_in_finalists(traj, gold):
                return "final_drop"
        return "selector_drop"
    if bucket == "interface_loss":
        return "mapper_or_judge_gap"
    return "ok"


def _sub_mosaic(traj: dict[str, Any], gold: str, bucket: str) -> str:
    if bucket == "generation_miss":
        # any view at all?
        return "view_miss_all"
    if bucket == "identity_loss":
        return "merge_swallow"
    if bucket == "prune_loss":
        for c in r5.gold_candidates(traj, gold):
            if c.get("status") not in ("live", "protected", "active", ""):
                return "status_not_live"
        return "status_not_live"
    if bucket == "decision_loss":
        if traj.get("adaptive_action") and "a5" in str(traj.get("adaptive_action")).lower():
            return "a5_pairwise_flip"
        return "selector_drop"
    if bucket == "interface_loss":
        return "mapper_or_judge_gap"
    return "ok"


def _sub_backbone(legacy_locus: str, bucket: str) -> str:
    if bucket == "generation_miss":
        return "s2_miss"
    if bucket == "prune_loss":
        if "s3_drop" in legacy_locus or "s2_hit_s3" in legacy_locus:
            return "s2_hit_s3_drop"
        return "s3_drop"
    if bucket == "decision_loss":
        return "s3_hit_s4_miss"
    if bucket == "interface_loss":
        return "s4_hit_judge_miss"
    return legacy_locus or "ok"


def assign_locus(
    traj: dict[str, Any],
    gold: str,
    *,
    chain_correct: Optional[bool] = None,
    scored_correct: Optional[bool] = None,
    legacy_locus: str = "",
) -> dict[str, str]:
    """Return {locus, subcode, family}."""
    family = traj.get("family") or ""
    if not traj.get("raw_available"):
        return {"locus": "missing", "subcode": "no_artifact", "family": family}

    # Prefer explicit chain if provided; else derive from champion match
    champ_ok = r5.champion_matches(traj, gold)
    if chain_correct is None:
        chain_correct = champ_ok

    if chain_correct:
        return {"locus": "ok", "subcode": "ok", "family": family}

    # generation
    proposed = r5.ever_proposed_gold(traj, gold)
    in_pool = r5.gold_in_pool(traj, gold)
    if not proposed and not in_pool:
        # legacy backbone shortcut
        if family == "backbone" and legacy_locus in ("s2_miss",):
            return {"locus": "generation_miss", "subcode": "s2_miss", "family": family}
        return {
            "locus": "generation_miss",
            "subcode": _sub_aphhm_c(traj, gold, "generation_miss")
            if family == "aphhm_c"
            else (
                _sub_mosaic(traj, gold, "generation_miss")
                if family == "mosaic"
                else _sub_backbone(legacy_locus, "generation_miss")
            ),
            "family": family,
        }

    # identity: proposed but not in active pool
    if proposed and not in_pool and r5.gold_merged_away(traj, gold):
        return {
            "locus": "identity_loss",
            "subcode": "merge_swallow",
            "family": family,
        }

    # prune: in pool but not shortlist / not reaching decision set
    in_short = r5.gold_in_shortlist(traj, gold)
    if in_pool and not in_short:
        # for multistance, shortlist == all active; if gold not shortlisted something pruned it
        sub = (
            _sub_aphhm_c(traj, gold, "prune_loss")
            if family == "aphhm_c"
            else (
                _sub_mosaic(traj, gold, "prune_loss")
                if family == "mosaic"
                else _sub_backbone(legacy_locus, "prune_loss")
            )
        )
        return {"locus": "prune_loss", "subcode": sub, "family": family}

    # decision: in shortlist (or pool when shortlist==pool) but champion wrong
    if in_pool or in_short:
        # interface: champion near-gold / fragment but chain says false while scored true
        if scored_correct and not chain_correct:
            return {"locus": "interface_loss", "subcode": "mapper_or_judge_gap", "family": family}
        sub = (
            _sub_aphhm_c(traj, gold, "decision_loss")
            if family == "aphhm_c"
            else (
                _sub_mosaic(traj, gold, "decision_loss")
                if family == "mosaic"
                else _sub_backbone(legacy_locus, "decision_loss")
            )
        )
        return {"locus": "decision_loss", "subcode": sub, "family": family}

    if scored_correct and not chain_correct:
        return {"locus": "interface_loss", "subcode": "mapper_or_judge_gap", "family": family}

    return {"locus": "generation_miss", "subcode": "fallback", "family": family}


def map_legacy_locus(arm: str, legacy: str, chain: Optional[bool], scored: Optional[bool]) -> dict[str, str]:
    """Map R2 locus strings into the six buckets without re-reading stages."""
    legacy = (legacy or "").strip()
    if chain:
        return {"locus": "ok", "subcode": "ok", "family": r5.FOCUS_ARMS[arm]["family"]}
    if scored and not chain:
        # may still be interface; only if locus says hit
        if "judge_miss" in legacy or "supervisor_miss_but_scored" in legacy or "diagnose_miss_but_scored" in legacy:
            return {"locus": "interface_loss", "subcode": legacy or "judge_miss", "family": r5.FOCUS_ARMS[arm]["family"]}
    mapping = {
        "s2_miss": ("generation_miss", "s2_miss"),
        "s2_hit_s3_drop": ("prune_loss", "s2_hit_s3_drop"),
        "s3_hit_s4_miss": ("decision_loss", "s3_hit_s4_miss"),
        "s4_hit_judge_miss": ("interface_loss", "s4_hit_judge_miss"),
        "ok": ("ok", "ok"),
        "agents_miss": ("generation_miss", "agents_miss"),
        "agents_hit_supervisor_drop": ("decision_loss", "supervisor_drop"),
        "supervisor_ok": ("ok", "ok"),
        "supervisor_miss_but_scored_ok": ("interface_loss", "supervisor_miss_but_scored_ok"),
        "supervisor_hit_judge_miss": ("interface_loss", "judge_miss"),
        "draft_miss": ("generation_miss", "draft_miss"),
        "diagnose_ok": ("ok", "ok"),
        "diagnose_miss_but_scored_ok": ("interface_loss", "diagnose_miss_but_scored_ok"),
        "diagnose_hit_judge_miss": ("interface_loss", "judge_miss"),
        "tree_miss": ("generation_miss", "tree_miss"),
        "tree_hit_final_drop": ("prune_loss", "tree_hit_final_drop"),
        "final_ok": ("ok", "ok"),
        "final_hit_judge_miss": ("interface_loss", "judge_miss"),
    }
    if legacy in mapping:
        loc, sub = mapping[legacy]
        return {"locus": loc, "subcode": sub, "family": r5.FOCUS_ARMS[arm]["family"]}
    if not chain:
        return {"locus": "decision_loss", "subcode": legacy or "unknown", "family": r5.FOCUS_ARMS[arm]["family"]}
    return {"locus": "ok", "subcode": "ok", "family": r5.FOCUS_ARMS[arm]["family"]}


def load_dual_for_arm(log_ds: str, arm: str) -> dict[str, dict[str, bool]]:
    """cid -> {scored, chain} from mapper / mcr judge / champion match."""
    d = r5.run_dir(log_ds, arm)
    out: dict[str, dict[str, bool]] = {}
    if d is None:
        return out
    dkey = "da" if "diagnosis" in log_ds else "mcr"
    if dkey == "da":
        hits = dc.load_mapper_hits(d)
        for cid, h in hits.items():
            scored = bool(h.get("correct") or h.get("option_top1"))
            out[str(cid)] = {"scored": scored, "chain": False}  # chain filled later
    else:
        # try official_eval_llm then compat
        hits = dc.load_mcr_hits(d, "official_eval_llm")
        if not hits:
            hits = dc.load_mcr_hits(d, "official_eval_llm_compat")
        for cid, h in hits.items():
            scored = bool(h.get("correct") or h.get("diagnostic_hit") or h.get("hit"))
            out[str(cid)] = {"scored": scored, "chain": False}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="", help="comma subset of FOCUS_ARMS keys")
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()] or list(r5.FOCUS_ARMS)
    gold = r5.load_gold()
    facts = r5.load_r4_facts()

    rows: list[dict[str, Any]] = []
    by_group: dict[str, list[dict[str, Any]]] = {"da": [], "mcr": [], "pooled": []}

    for log_ds, dkey, sl in r5.SLICES:
        print(f"=== {log_ds} ===")
        for arm in arms:
            if arm in r5.DEV_ONLY and sl.endswith("200b"):
                continue
            d = r5.run_dir(log_ds, arm)
            if d is None:
                print(f"  skip {arm}: no dir")
                continue
            dual = load_dual_for_arm(log_ds, arm)
            n = 0
            # case ids from gold for this slice
            cids = [cid for (dd, ss, cid), g in gold.items() if dd == dkey and ss == sl]
            for cid in cids:
                g = gold[(dkey, sl, cid)]
                fact = facts.get((dkey, sl, cid), {})
                traj = r5.load_trajectory(log_ds, arm, cid)
                family = r5.FOCUS_ARMS[arm]["family"]
                # chain from champion match (concept metric)
                chain = r5.champion_matches(traj, g) if traj.get("raw_available") else None
                scored = None
                if cid in dual:
                    scored = dual[cid]["scored"]
                elif family in ("backbone", "paper", "aphhm_orig"):
                    # fall back to r4 facts columns
                    col = {
                        "e7": "e7_scored_correct",
                        "v0": "v0_scored_correct",
                        "B06": "B06_scored_correct",
                        "B07": "B07_scored_correct",
                        "APHHM": "APHHM_scored_correct",
                    }.get(arm)
                    if col and fact.get(col) not in (None, ""):
                        scored = r4.truthy(fact.get(col))
                    ccol = {
                        "e7": "e7_chain_correct",
                        "v0": "v0_chain_correct",
                        "B06": "B06_chain_correct",
                        "B07": "B07_chain_correct",
                        "APHHM": "APHHM_chain_correct",
                    }.get(arm)
                    if ccol and fact.get(ccol) not in (None, "") and chain is None:
                        chain = r4.truthy(fact.get(ccol))

                legacy = ""
                if family in ("backbone", "paper", "aphhm_orig"):
                    loc_col = {
                        "e7": "e7_locus",
                        "v0": "v0_locus",
                        "B06": "B06_locus",
                        "B07": "B07_locus",
                        "APHHM": "APHHM_locus",
                    }.get(arm)
                    # r4 facts may use locus_ prefix or plain
                    legacy = str(
                        fact.get(loc_col or "")
                        or fact.get(f"locus_{loc_col}" if loc_col else "")
                        or ""
                    )
                    # also try trajectory_loci via fact join keys already in r4
                    if not legacy:
                        for k, v in fact.items():
                            if k.endswith("_locus") and arm.lower() in k.lower():
                                legacy = str(v)
                                break

                if family in ("aphhm_c", "mosaic") and traj.get("raw_available"):
                    assigned = assign_locus(
                        traj, g, chain_correct=chain, scored_correct=scored, legacy_locus=legacy
                    )
                elif family in ("backbone", "paper", "aphhm_orig"):
                    # prefer mapping legacy; if no legacy, use trajectory
                    if legacy:
                        assigned = map_legacy_locus(arm, legacy, chain, scored)
                    elif traj.get("raw_available"):
                        assigned = assign_locus(
                            traj, g, chain_correct=chain, scored_correct=scored
                        )
                    else:
                        assigned = {"locus": "missing", "subcode": "no_artifact", "family": family}
                else:
                    assigned = {"locus": "missing", "subcode": "unknown_family", "family": family}

                mapper_rescue = bool(scored) and not bool(chain)
                row = {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "arm": arm,
                    "family": family,
                    "gold": g,
                    "champion": traj.get("champion") or "",
                    "locus": assigned["locus"],
                    "subcode": assigned["subcode"],
                    "chain_correct": int(bool(chain)) if chain is not None else "",
                    "scored_correct": int(bool(scored)) if scored is not None else "",
                    "mapper_rescue": int(mapper_rescue) if scored is not None and chain is not None else "",
                    "n_candidates": len(traj.get("candidates") or []),
                    "n_shortlist": len(traj.get("shortlist") or []),
                    "pool_has_gold": int(r5.gold_in_pool(traj, g)) if traj.get("raw_available") else "",
                    "shortlist_has_gold": int(r5.gold_in_shortlist(traj, g)) if traj.get("raw_available") else "",
                    "llm_calls": traj.get("llm_calls") if traj.get("llm_calls") is not None else "",
                    "raw_available": int(bool(traj.get("raw_available"))),
                }
                rows.append(row)
                by_group[dkey].append(row)
                by_group["pooled"].append(row)
                n += 1
            print(f"  {arm}: {n}")

    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("da", "mcr", "pooled"):
        r4.write_tsv(OUT / f"{name}.tsv", by_group[name])

    # cross tabs
    tabs: dict[str, Any] = {}
    for name, rs in by_group.items():
        by_arm: dict[str, Counter] = defaultdict(Counter)
        by_arm_sub: dict[str, Counter] = defaultdict(Counter)
        for r in rs:
            by_arm[r["arm"]][r["locus"]] += 1
            by_arm_sub[r["arm"]][f"{r['locus']}:{r['subcode']}"] += 1
        tabs[name] = {
            "locus": {a: dict(c) for a, c in by_arm.items()},
            "subcode": {a: dict(c) for a, c in by_arm_sub.items()},
            "n": {a: sum(c.values()) for a, c in by_arm.items()},
        }
        # rates
        rates = {}
        for a, c in by_arm.items():
            tot = sum(c.values()) or 1
            rates[a] = {b: round(c.get(b, 0) / tot, 4) for b in BUCKETS}
        tabs[name]["locus_rate"] = rates

    r5.write_json(OUT / "cross_tabs.json", tabs)
    print(f"wrote {OUT}")
    # headline print
    print("\n=== DA locus rates (chain) ===")
    for a, rates in (tabs.get("da") or {}).get("locus_rate", {}).items():
        print(f"  {a:16} " + " ".join(f"{b[0]}={rates.get(b,0):.3f}" for b in BUCKETS if b != "missing"))
    print("\n=== MCR locus rates ===")
    for a, rates in (tabs.get("mcr") or {}).get("locus_rate", {}).items():
        print(f"  {a:16} " + " ".join(f"{b[0]}={rates.get(b,0):.3f}" for b in BUCKETS if b != "missing"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
