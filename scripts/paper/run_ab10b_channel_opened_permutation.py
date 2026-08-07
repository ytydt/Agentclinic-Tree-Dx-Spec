#!/usr/bin/env python3
"""AB10b / AB10c permutation test on DA under channel-opened endpoints.

Background. The deployed compression is a pure deletion operator: representatives
are best-ranked members and clusters are ordered by that rank, so the globally
rank-1 leaf heads *every* count-matched partition. AB10b therefore cannot move any
Top-1 endpoint, and the closed-set option rematch additionally credits absorbed
leaves through ``member -> rep``, so absorbing the wrong leaf is free. Both facts
are measured in ``audit_ab10b_construct_validity.py``: DA option@1 moves in only
10/35 cases, and option_rank<=3 / best_rank<=3 have a null sd of exactly 0.

This script re-runs the same permutation under two channel-opening changes, each
applied symmetrically to the main method and to the blind arms (S-axis rule):

  AB10d  quotient-aggregated order. Cluster score = sum of 1/rank over members,
         so a class must pool evidence to outrank a better-ranked singleton.
         Verified to leave the main method's Top-1 unchanged on every gated case
         (DA 89/89, MCR 82/82), hence no main result is disturbed.

  OPEN   open-set scoring. Instead of projecting option maps through member->rep,
         match the gold option text against the *surviving representative labels*
         only. Leaves that were absorbed are genuinely gone, so a wrong absorption
         destroys the match. This is the DA analogue of MCR any-hit@k.

Endpoints are reported side by side with the pre-existing closed/deletion baseline
so the "before vs after channel opening" contrast is explicit. Every endpoint
carries its channel statistic (number of cases whose value is not constant across
draws, and the null sd); an endpoint with sd == 0 is an algebraic identity and its
p-value is reported as non-informative.

Zero LLM calls. Writes one JSON under runs/paper_v1/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import adaptive_merge_siblings as merge  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402
import run_ab10b_permutation as perm  # noqa: E402
import run_at1_calibration_smoke as smoke  # noqa: E402

OUT_JSON = ROOT / "runs/paper_v1/ablations_c1_ab10b_channel_opened.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(statistics.fmean(xs), 4) if xs else None


def score_closed(
    pack: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
    *,
    aggregated: bool,
) -> dict[str, Any]:
    """Closed-set option rematch (credits absorbed leaves via member -> rep)."""
    mapper = pack["mapper"]
    om = (mapper.get("projection") or {}).get("option_maps") or {}
    maps = mcc.project_option_maps_through_merge(om, merge_info) if om else om
    ordered = (
        mcc.aggregate_cluster_order(labels, merge_info)
        if aggregated
        else list(merge_info["representative_order"])
    )
    rep_labels = mcc._rep_labels_from_merge(
        labels, {**dict(merge_info), "representative_order": ordered}
    )
    work_mapper = {
        **mapper,
        "projection": {**(mapper.get("projection") or {}), "option_maps": maps},
    }
    return smoke.rematch_option_metrics(
        mapper_row=work_mapper, ordered_ids=ordered, ranking_labels=rep_labels
    )


def score_open(
    pack: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
    *,
    aggregated: bool,
    k: int,
    thr: float,
) -> dict[str, Any]:
    """Open-set scoring: gold option text vs surviving representative labels."""
    from mapper_bind_repair import leaf_match_score

    gold_text = str(pack["mapper"].get("gold_option_text") or "").strip()
    label_by_id = {
        str(r.get("id")): str(r.get("label") or "") for r in labels if r.get("id")
    }
    ordered = (
        mcc.aggregate_cluster_order(labels, merge_info)
        if aggregated
        else list(merge_info["representative_order"])
    )
    texts = [label_by_id.get(str(r), "") for r in ordered[:k]]
    texts = [t for t in texts if t]
    if not gold_text or not texts:
        return {"open_top1": 0, "open_any_hit": 0, "open_rr": 0.0, "n_survivors": 0}
    first = next(
        (
            i
            for i, t in enumerate(texts, start=1)
            if float(leaf_match_score(t, gold_text)) >= thr
        ),
        None,
    )
    return {
        "open_top1": int(first == 1),
        "open_any_hit": int(first is not None),
        "open_rr": (1.0 / first) if first else 0.0,
        "n_survivors": len(texts),
    }


# endpoint name -> (scoring family, aggregated, extractor)
ENDPOINTS: dict[str, tuple[str, bool, Any]] = {
    "closed_opt1_deletion": ("closed", False, lambda m: int(bool(m["option_top1"]))),
    "closed_opt2_deletion": ("closed", False, lambda m: int(bool(m["option_top2"]))),
    "closed_opt1_aggregated": ("closed", True, lambda m: int(bool(m["option_top1"]))),
    "closed_opt2_aggregated": ("closed", True, lambda m: int(bool(m["option_top2"]))),
    "open_top1_deletion": ("open", False, lambda m: int(m["open_top1"])),
    "open_anyhit_deletion": ("open", False, lambda m: int(m["open_any_hit"])),
    "open_rr_deletion": ("open", False, lambda m: float(m["open_rr"])),
    "open_top1_aggregated": ("open", True, lambda m: int(m["open_top1"])),
    "open_anyhit_aggregated": ("open", True, lambda m: int(m["open_any_hit"])),
    "open_rr_aggregated": ("open", True, lambda m: float(m["open_rr"])),
}

# Pure channel diagnostics: identity of the rank-1 leaf under each ordering rule.
# Reported as "how many cases can move at all", never as a p-value.
ORDER_RULES: dict[str, bool] = {"deletion": False, "aggregated": True}


def evaluate_all(
    pack: Mapping[str, Any],
    labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
    *,
    k: int,
    thr: float,
) -> dict[str, int]:
    """One partition -> value of every endpoint (two scorers x two orders)."""
    cache: dict[tuple[str, bool], Any] = {}
    out: dict[str, int] = {}
    for name, (family, aggregated, extract) in ENDPOINTS.items():
        key = (family, aggregated)
        if key not in cache:
            cache[key] = (
                score_closed(pack, labels, merge_info, aggregated=aggregated)
                if family == "closed"
                else score_open(
                    pack, labels, merge_info, aggregated=aggregated, k=k, thr=thr
                )
            )
        out[name] = int(extract(cache[key]))
    return out


def run(cohort: str, seeds: Sequence[int], k: int, thr: float) -> dict[str, Any]:
    table = perm.build_case_table(cohort)
    free = [
        r for r in table if r["gate"] and mcc.n_matched_partitions(r["profile"]) > 1
    ]
    n = len(free)
    print(f"  perturbable gated cases: {n}", flush=True)

    ref_vals = {name: 0.0 for name in ENDPOINTS}
    for r in free:
        vals = evaluate_all(r["pack"], r["labels"], r["ref"], k=k, thr=thr)
        for name, v in vals.items():
            ref_vals[name] += v

    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        nulls: dict[str, list[float]] = {name: [] for name in ENDPOINTS}
        seen: dict[str, dict[str, set]] = {name: {} for name in ENDPOINTS}
        top1_leaf: dict[str, dict[str, set]] = {rule: {} for rule in ORDER_RULES}
        for s in seeds:
            acc = {name: 0.0 for name in ENDPOINTS}
            for r in free:
                blocks = mcc.random_partition_matched(
                    r["labels"],
                    r["profile"],
                    seed=int(s),
                    match_top1=match_top1,
                    top1_size=r["top1_size"] if match_top1 else None,
                )
                bi = merge.merge_ranking_ids_from_blocks(r["labels"], blocks)
                vals = evaluate_all(r["pack"], r["labels"], bi, k=k, thr=thr)
                for name, v in vals.items():
                    acc[name] += v
                    seen[name].setdefault(r["case_id"], set()).add(v)
                for rule, aggregated in ORDER_RULES.items():
                    order = (
                        mcc.aggregate_cluster_order(r["labels"], bi)
                        if aggregated
                        else list(bi["representative_order"])
                    )
                    top1_leaf[rule].setdefault(r["case_id"], set()).add(
                        order[0] if order else ""
                    )
            for name in ENDPOINTS:
                nulls[name].append(acc[name] / n)

        order_channel = {}
        for rule, aggregated in ORDER_RULES.items():
            moving = 0
            for r in free:
                ref_order = (
                    mcc.aggregate_cluster_order(r["labels"], r["ref"])
                    if aggregated
                    else list(r["ref"]["representative_order"])
                )
                seen_ids = set(top1_leaf[rule][r["case_id"]])
                seen_ids.add(ref_order[0] if ref_order else "")
                if len(seen_ids) > 1:
                    moving += 1
            order_channel[rule] = {"n_cases": n, "n_cases_rank1_leaf_moving": moving}
            print(
                f"  {variant} [order:{rule:10s}] rank-1 leaf id can move in "
                f"{moving}/{n} cases",
                flush=True,
            )

        rows: dict[str, Any] = {"_order_channel": order_channel}
        for name in ENDPOINTS:
            null = nulls[name]
            obs = ref_vals[name] / n
            sd = round(statistics.pstdev(null), 4) if len(null) > 1 else 0.0
            moving = sum(1 for vs in seen[name].values() if len(vs) > 1)
            ge = sum(1 for x in null if x >= obs - 1e-12)
            rows[name] = {
                "n_cases": n,
                "n_cases_moving": moving,
                "has_channel": bool(moving > 0),
                "m00": round(obs, 4),
                "null_mean": _mean(null),
                "null_sd": sd,
                "null_min": round(min(null), 4),
                "null_max": round(max(null), 4),
                "p_one_sided": round((ge + 1) / (len(null) + 1), 4),
                "p_informative": bool(moving > 0),
            }
            flag = "" if moving else "   <-- identity, p meaningless"
            print(
                f"  {variant} {name:24s} moves={moving:2d}/{n} M00={obs:.4f} "
                f"null={rows[name]['null_mean']}±{sd} p={rows[name]['p_one_sided']}{flag}",
                flush=True,
            )
        out[variant] = rows
    return out


def run_mcr(seeds: Sequence[int], k: int, thr: float) -> dict[str, Any]:
    """Same contrast on MCR pre-compat joint, where scoring is already open-set."""
    import pre_compat_joint as pcj
    import run_mcr_c1_precompat_ablation as rmp
    from mapper_bind_repair import leaf_match_score
    from transfer_eval import io_gold

    annotate = pcj.resolve_annotate_dir(
        ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
    )
    ids = sorted(p.stem for p in (annotate / "case_results").glob("*.json"))
    gold = io_gold.load_gold("medcasereasoning", Path(rmp.DEFAULT_PARQUET), case_ids=ids)

    cases = []
    for cid in ids:
        _, labels, _ = pcj.load_pre_compat_inputs(annotate, cid)
        gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
        if not labels or not gdx:
            continue
        gate = mcc.fine_crowd_gate(labels)
        if not bool(gate.get("triggered")):
            continue
        ref = gate.get("merge_info") or merge.merge_ranking_ids(list(labels))
        profile = mcc.partition_profile(ref)
        if mcc.n_matched_partitions(profile) <= 1:
            continue
        cases.append({
            "case_id": cid,
            "labels": labels,
            "gold": gdx,
            "ref": ref,
            "profile": profile,
            "top1_size": len(gate.get("top1_members") or []) or profile[0],
        })
    n = len(cases)
    print(f"  MCR perturbable gated cases: {n}", flush=True)

    def score(labels, merge_info, gdx, aggregated) -> dict[str, float]:
        by_id = {str(r.get("id")): str(r.get("label") or "") for r in labels}
        order = (
            mcc.aggregate_cluster_order(labels, merge_info)
            if aggregated
            else list(merge_info["representative_order"])
        )
        texts = [by_id.get(str(r), "") for r in order[:k]]
        texts = [t for t in texts if t]
        first = next(
            (
                i
                for i, t in enumerate(texts, start=1)
                if float(leaf_match_score(t, gdx)) >= thr
            ),
            None,
        )
        return {
            "lex_top1": float(first == 1),
            "any_hit": float(first is not None),
            "rr": (1.0 / first) if first else 0.0,
        }

    specs = [
        (f"{m}_{rule}", metric, aggregated)
        for rule, aggregated in ORDER_RULES.items()
        for m, metric in (("lex_top1", "lex_top1"), ("anyhit", "any_hit"), ("rr", "rr"))
    ]
    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        ref_tot = {name: 0.0 for name, _, _ in specs}
        for c in cases:
            cache = {
                agg: score(c["labels"], c["ref"], c["gold"], agg) for agg in (False, True)
            }
            for name, metric, agg in specs:
                ref_tot[name] += cache[agg][metric]
        nulls: dict[str, list[float]] = {name: [] for name, _, _ in specs}
        seen: dict[str, dict[str, set]] = {name: {} for name, _, _ in specs}
        for s in seeds:
            acc = {name: 0.0 for name, _, _ in specs}
            for c in cases:
                blocks = mcc.random_partition_matched(
                    c["labels"],
                    c["profile"],
                    seed=int(s),
                    match_top1=match_top1,
                    top1_size=c["top1_size"] if match_top1 else None,
                )
                bi = merge.merge_ranking_ids_from_blocks(c["labels"], blocks)
                cache = {
                    agg: score(c["labels"], bi, c["gold"], agg) for agg in (False, True)
                }
                for name, metric, agg in specs:
                    v = cache[agg][metric]
                    acc[name] += v
                    seen[name].setdefault(c["case_id"], set()).add(round(v, 4))
            for name, _, _ in specs:
                nulls[name].append(acc[name] / n)
        rows: dict[str, Any] = {}
        for name, _, _ in specs:
            null = nulls[name]
            obs = ref_tot[name] / n
            sd = round(statistics.pstdev(null), 4) if len(null) > 1 else 0.0
            moving = sum(1 for vs in seen[name].values() if len(vs) > 1)
            ge = sum(1 for x in null if x >= obs - 1e-12)
            rows[name] = {
                "n_cases": n,
                "n_cases_moving": moving,
                "has_channel": bool(moving > 0),
                "m00": round(obs, 4),
                "null_mean": _mean(null),
                "null_sd": sd,
                "null_min": round(min(null), 4),
                "null_max": round(max(null), 4),
                "p_one_sided": round((ge + 1) / (len(null) + 1), 4),
                "p_informative": bool(moving > 0),
            }
            flag = "" if moving else "   <-- identity, p meaningless"
            print(
                f"  {variant} {name:20s} moves={moving:2d}/{n} M00={obs:.4f} "
                f"null={rows[name]['null_mean']}±{sd} p={rows[name]['p_one_sided']}{flag}",
                flush=True,
            )
        out[variant] = rows
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="all100")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=20260728)
    ap.add_argument("--k", type=int, default=5)
    args = ap.parse_args()

    from transfer_eval.matching import DEFAULT_LEXICAL_THRESHOLD

    thr = float(DEFAULT_LEXICAL_THRESHOLD)
    seeds = [int(args.seed0) + i for i in range(int(args.seeds))]

    print(f"[{_utc()}] DA cohort={args.cohort} seeds={args.seeds} thr={thr}", flush=True)
    arms = run(args.cohort, seeds, int(args.k), thr)
    print(f"[{_utc()}] MCR pre-compat joint", flush=True)
    arms_mcr = run_mcr(seeds, int(args.k), thr)

    payload = {
        "created_at": _utc(),
        "cohort": args.cohort,
        "seeds": int(args.seeds),
        "seed0": int(args.seed0),
        "k": int(args.k),
        "lexical_threshold": thr,
        "registered_in": "paper_ablation_plan.md 块 2 修订记录 R1c",
        "design": {
            "deletion_order": "rep = best-ranked member; clusters sorted by that rank",
            "aggregated_order": "AB10d: cluster score = sum 1/rank(member), tie-break best rank",
            "closed_scoring": "option rematch through member->rep (credits absorbed leaves)",
            "open_scoring": "gold_option_text vs surviving representative labels only",
            "symmetry": "each scoring/order pair applied identically to M00 and to the blind arms",
        },
        "DA": arms,
        "MCR": arms_mcr,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[wrote] {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
