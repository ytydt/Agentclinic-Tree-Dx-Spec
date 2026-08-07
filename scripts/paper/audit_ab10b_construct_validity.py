#!/usr/bin/env python3
"""Construct-validity audit for AB10b / AB10c (block-2 confirmatory control).

Motivating worry: the R1 null result may be an artifact of the *scoring* rather
than evidence about compression semantics. Two structural features of this
pipeline make that plausible:

  1. Representatives are chosen as the best-ranked member of a block and blocks
     are ordered by representative rank. Hence the globally rank-1 leaf is the
     rank-1 representative under *every* partition. Any endpoint that reads only
     the Top-1 label is then constant by construction.
  2. The joint list holds one champion per L1 family, so its members are
     cross-family competitors. The main method's partition is a genuine quotient
     by the synonym relation (single-linkage over synonymish pairs), so no two
     surviving representatives can be synonymish. A count-matched *random*
     partition matches only the cluster-size profile, not the quotient property,
     and can leave synonymish duplicates among survivors.

If (1) holds and the endpoints cannot see (2), then AB10b perturbs the operator
in a way the metrics are blind to, and a null on those endpoints is
non-diagnostic rather than falsifying.

What this script measures (zero LLM calls; DA option rematch is deterministic):

  A rank-1 representative invariance across draws
  B quotient violations per draw: non-synonymish pairs merged, synonymish pairs
    split, and synonymish pairs left among surviving representatives
  C whether DA option @1 responds to those violations at all
    (per-draw correlation + violation-stratified means)

Read-only w.r.t. run artifacts. Writes one JSON under runs/paper_v1/.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

import adaptive_merge_siblings as merge  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402
import pre_compat_joint as pcj  # noqa: E402
import run_ab10b_permutation as perm  # noqa: E402

OUT_JSON = ROOT / "runs/paper_v1/ablations_c1_ab10b_construct_validity.json"
MCR_RUN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(statistics.fmean(xs), 4) if xs else None


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 4)


def synonym_pairs(labels: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    """All unordered leaf-id pairs the synonym predicate accepts."""
    out: set[tuple[str, str]] = set()
    for a, b in combinations(labels, 2):
        ia, ib = str(a.get("id")), str(b.get("id"))
        if merge.labels_synonymish(str(a.get("label") or ""), str(b.get("label") or "")):
            out.add(tuple(sorted((ia, ib))))
    return out


def copartitioned_pairs(merge_info: Mapping[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for members in (merge_info.get("rep_to_members") or {}).values():
        for a, b in combinations(sorted(str(m) for m in members), 2):
            out.add((a, b))
    return out


def quotient_violations(
    labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
    syn: set[tuple[str, str]],
) -> dict[str, Any]:
    """How far a partition is from being a quotient by the synonym relation."""
    co = copartitioned_pairs(merge_info)
    by_id = {str(r.get("id")): str(r.get("label") or "") for r in labels}
    reps = [str(r) for r in (merge_info.get("representative_order") or ())]
    dup_rep = [
        (a, b)
        for a, b in combinations(reps, 2)
        if merge.labels_synonymish(by_id.get(a, ""), by_id.get(b, ""))
    ]
    return {
        "n_false_merge": len(co - syn),
        "n_split_synonym": len(syn - co),
        "n_dup_rep_pairs": len(dup_rep),
        "dup_rep_labels": [
            [by_id.get(a, ""), by_id.get(b, "")] for a, b in dup_rep[:4]
        ],
        "top1_rep": reps[0] if reps else "",
        "n_reps": len(reps),
    }


def audit_case(
    labels: Sequence[Mapping[str, Any]],
    *,
    seeds: Sequence[int],
    match_top1: bool,
    score_fn: Optional[Any] = None,
) -> Optional[dict[str, Any]]:
    """Audit one gated case across draws; returns None when DOF<=1."""
    gate = mcc.fine_crowd_gate(labels)
    if not bool(gate.get("triggered")):
        return None
    ref = gate.get("merge_info") or merge.merge_ranking_ids(list(labels))
    profile = mcc.partition_profile(ref)
    if mcc.n_matched_partitions(profile) <= 1:
        return None

    syn = synonym_pairs(labels)
    n_pairs = len(labels) * (len(labels) - 1) // 2
    top1_size = len(gate.get("top1_members") or []) or (profile[0] if profile else 1)
    ref_v = quotient_violations(labels, ref, syn)
    ref_score = score_fn(ref) if score_fn else None

    draws: list[dict[str, Any]] = []
    for s in seeds:
        blocks = mcc.random_partition_matched(
            labels,
            profile,
            seed=int(s),
            match_top1=match_top1,
            top1_size=top1_size if match_top1 else None,
        )
        blind = merge.merge_ranking_ids_from_blocks(labels, blocks)
        v = quotient_violations(labels, blind, syn)
        v["seed"] = int(s)
        v["top1_invariant"] = v["top1_rep"] == ref_v["top1_rep"]
        v["partition_differs"] = copartitioned_pairs(blind) != copartitioned_pairs(ref)
        if score_fn is not None:
            v["opt1"] = int(bool(score_fn(blind)))
        draws.append(v)

    return {
        "n_leaves": len(labels),
        "n_pairs": n_pairs,
        "n_synonym_pairs": len(syn),
        "synonym_graph_complete": len(syn) == n_pairs,
        "profile": profile,
        "ref": ref_v,
        "ref_opt1": int(bool(ref_score)) if ref_score is not None else None,
        "draws": draws,
    }


def aggregate(cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    top1_inv = []
    dup_ref = []
    dup_blind = []
    false_merge = []
    split_syn = []
    any_violation = []
    opt1_by_violation: dict[str, list[int]] = {"0": [], "1+": []}
    per_draw_pairs: list[tuple[int, int]] = []
    dup_examples: list[dict[str, Any]] = []

    for cid, c in cases.items():
        dup_ref.append(c["ref"]["n_dup_rep_pairs"])
        for d in c["draws"]:
            top1_inv.append(1 if d["top1_invariant"] else 0)
            dup_blind.append(d["n_dup_rep_pairs"])
            false_merge.append(d["n_false_merge"])
            split_syn.append(d["n_split_synonym"])
            viol = d["n_false_merge"] + d["n_split_synonym"]
            any_violation.append(1 if viol else 0)
            if "opt1" in d:
                opt1_by_violation["1+" if viol else "0"].append(int(d["opt1"]))
                per_draw_pairs.append((viol, int(d["opt1"])))
            if d["n_dup_rep_pairs"] and len(dup_examples) < 8:
                dup_examples.append({
                    "case_id": cid,
                    "seed": d["seed"],
                    "profile": c["profile"],
                    "dup_rep_labels": d["dup_rep_labels"],
                })

    corr = _pearson(
        [float(a) for a, _ in per_draw_pairs], [float(b) for _, b in per_draw_pairs]
    )

    out = {
        "n_cases": len(cases),
        "n_draws_total": len(top1_inv),
        "top1_rep_invariance_rate": _mean(top1_inv),
        "ref_dup_rep_pairs_mean": _mean(dup_ref),
        "ref_dup_rep_case_rate": _mean([1 if x else 0 for x in dup_ref]),
        "blind_dup_rep_pairs_mean": _mean(dup_blind),
        "blind_dup_rep_draw_rate": _mean([1 if x else 0 for x in dup_blind]),
        "blind_false_merge_mean": _mean(false_merge),
        "blind_split_synonym_mean": _mean(split_syn),
        "blind_any_violation_rate": _mean(any_violation),
        "dup_rep_examples": dup_examples,
    }
    if opt1_by_violation["0"] or opt1_by_violation["1+"]:
        out["opt1_by_violation"] = {
            "no_violation": {
                "n": len(opt1_by_violation["0"]),
                "opt1": _mean(opt1_by_violation["0"]),
            },
            "with_violation": {
                "n": len(opt1_by_violation["1+"]),
                "opt1": _mean(opt1_by_violation["1+"]),
            },
        }
        out["corr_violations_vs_opt1"] = corr
    return out


def _perm_p(obs: float, null: Sequence[float]) -> float:
    ge = sum(1 for x in null if x >= obs - 1e-12)
    return round((ge + 1) / (len(null) + 1), 4)


def channel_stats(
    name: str,
    obs: float,
    null: Sequence[float],
    n_moving: int,
    n_cases: int,
) -> dict[str, Any]:
    """Does an endpoint have any degrees of freedom, and if so where does M00 sit?

    ``n_moving`` counts cases whose per-case value is not constant across draws.
    An endpoint with n_moving == 0 is an algebraic identity: its null sd is 0 and
    no p-value from it carries information.
    """
    sd = round(statistics.pstdev(null), 4) if len(null) > 1 else 0.0
    return {
        "endpoint": name,
        "n_cases_moving": int(n_moving),
        "n_cases": int(n_cases),
        "has_channel": bool(n_moving > 0),
        "m00": round(float(obs), 4),
        "null_mean": _mean(null),
        "null_sd": sd,
        "null_min": round(min(null), 4) if null else None,
        "null_max": round(max(null), 4) if null else None,
        "p_one_sided": _perm_p(obs, null),
    }


def da_channel_audit(seeds: Sequence[int], cohort: str) -> dict[str, Any]:
    """Permutation null for every DA option-rematch endpoint, with channel test."""
    table = perm.build_case_table(cohort)
    free = [r for r in table if r["gate"] and mcc.n_matched_partitions(r["profile"]) > 1]
    specs: dict[str, Any] = {
        "option_top1": lambda m: int(bool(m["option_top1"])),
        "option_top2": lambda m: int(bool(m["option_top2"])),
        "option_rr": lambda m: float(m["option_rr"]),
        "option_rank_le3": lambda m: int((m.get("option_rank") or 99) <= 3),
        "best_rank_le3": lambda m: int((m.get("best_rank") or 99) <= 3),
        "best_rank_le5": lambda m: int((m.get("best_rank") or 99) <= 5),
    }
    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        ref_tot = {k: 0.0 for k in specs}
        for r in free:
            m = perm.score_with_partition(r["pack"], r["ref"])
            for k, fn in specs.items():
                ref_tot[k] += fn(m)
        nulls: dict[str, list[float]] = {k: [] for k in specs}
        seen: dict[str, dict[str, set]] = {k: {} for k in specs}
        for s in seeds:
            acc = {k: 0.0 for k in specs}
            for r in free:
                blocks = mcc.random_partition_matched(
                    r["labels"],
                    r["profile"],
                    seed=int(s),
                    match_top1=match_top1,
                    top1_size=r["top1_size"] if match_top1 else None,
                )
                bi = merge.merge_ranking_ids_from_blocks(r["labels"], blocks)
                m = perm.score_with_partition(r["pack"], bi)
                for k, fn in specs.items():
                    v = fn(m)
                    acc[k] += v
                    seen[k].setdefault(r["case_id"], set()).add(round(float(v), 4))
            for k in specs:
                nulls[k].append(acc[k] / len(free))
        out[variant] = {
            k: channel_stats(
                k,
                ref_tot[k] / len(free),
                nulls[k],
                sum(1 for vs in seen[k].values() if len(vs) > 1),
                len(free),
            )
            for k in specs
        }
        for k, st in out[variant].items():
            print(
                f"  DA {variant} {k:16s} moves={st['n_cases_moving']:2d}/{st['n_cases']} "
                f"M00={st['m00']} null={st['null_mean']}±{st['null_sd']} p={st['p_one_sided']}",
                flush=True,
            )
    return out


def mcr_channel_audit(seeds: Sequence[int], k: int = 5) -> dict[str, Any]:
    """Permutation null for MCR lexical endpoints (deterministic; no LLM judge).

    ``lex@1`` reads only the rank-1 representative and is therefore invariant by
    construction; ``any-hit@k`` reads the whole surviving representative set and
    is the one endpoint with a live channel.
    """
    from mapper_bind_repair import leaf_match_score
    from transfer_eval import io_gold
    from transfer_eval.matching import DEFAULT_LEXICAL_THRESHOLD

    import run_mcr_c1_precompat_ablation as rmp

    annotate = pcj.resolve_annotate_dir(MCR_RUN)
    ids = sorted(p.stem for p in (annotate / "case_results").glob("*.json"))
    gold = io_gold.load_gold("medcasereasoning", Path(rmp.DEFAULT_PARQUET), case_ids=ids)
    thr = float(DEFAULT_LEXICAL_THRESHOLD)

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

    def score(labels, merge_info, gdx) -> tuple[int, int, int]:
        by_id = {str(r.get("id")): str(r.get("label") or "") for r in labels}
        reps = [str(x) for x in merge_info["representative_order"]][:k]
        texts = [by_id.get(r, "") for r in reps if by_id.get(r, "")]
        top1 = int(bool(texts) and float(leaf_match_score(texts[0], gdx)) >= thr)
        anyh = int(any(float(leaf_match_score(t, gdx)) >= thr for t in texts))
        return top1, anyh, len(texts)

    out: dict[str, Any] = {}
    n = len(cases)
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        r1 = ra = rd = 0.0
        for c in cases:
            t, a, d = score(c["labels"], c["ref"], c["gold"])
            r1 += t
            ra += a
            rd += d
        n1: list[float] = []
        na: list[float] = []
        nd: list[float] = []
        seen1: dict[str, set] = {}
        seena: dict[str, set] = {}
        for s in seeds:
            a1 = aa = ad = 0.0
            for c in cases:
                blocks = mcc.random_partition_matched(
                    c["labels"],
                    c["profile"],
                    seed=int(s),
                    match_top1=match_top1,
                    top1_size=c["top1_size"] if match_top1 else None,
                )
                bi = merge.merge_ranking_ids_from_blocks(c["labels"], blocks)
                t, a, d = score(c["labels"], bi, c["gold"])
                a1 += t
                aa += a
                ad += d
                seen1.setdefault(c["case_id"], set()).add(t)
                seena.setdefault(c["case_id"], set()).add(a)
            n1.append(a1 / n)
            na.append(aa / n)
            nd.append(ad / n)
        out[variant] = {
            "lex_at_1": channel_stats(
                "lex@1", r1 / n, n1, sum(1 for v in seen1.values() if len(v) > 1), n
            ),
            f"any_hit_at_{k}": channel_stats(
                f"any-hit@{k}",
                ra / n,
                na,
                sum(1 for v in seena.values() if len(v) > 1),
                n,
            ),
            "mean_surviving_labels": {
                "m00": round(rd / n, 4),
                "null_mean": _mean(nd),
                "note": "count is matched by construction; only membership differs",
            },
        }
        for key in ("lex_at_1", f"any_hit_at_{k}"):
            st = out[variant][key]
            print(
                f"  MCR {variant} {st['endpoint']:10s} moves={st['n_cases_moving']:2d}/{n} "
                f"M00={st['m00']} null={st['null_mean']}±{st['null_sd']} "
                f"p={st['p_one_sided']}",
                flush=True,
            )
    return out


def run_da(seeds: Sequence[int], cohort: str) -> dict[str, Any]:
    table = perm.build_case_table(cohort)
    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        cases: dict[str, Any] = {}
        for row in table:
            def score(mi: Mapping[str, Any], _pack=row["pack"]) -> bool:
                return bool(perm.score_with_partition(_pack, mi)["option_top1"])

            res = audit_case(
                row["labels"], seeds=seeds, match_top1=match_top1, score_fn=score
            )
            if res is not None:
                cases[row["case_id"]] = res
        out[variant] = {"aggregate": aggregate(cases), "per_case": cases}
        a = out[variant]["aggregate"]
        print(
            f"  DA {variant}: cases={a['n_cases']} draws={a['n_draws_total']} "
            f"top1_inv={a['top1_rep_invariance_rate']} "
            f"dup_ref={a['ref_dup_rep_pairs_mean']} "
            f"dup_blind={a['blind_dup_rep_pairs_mean']} "
            f"viol_rate={a['blind_any_violation_rate']}",
            flush=True,
        )
        ov = a.get("opt1_by_violation")
        if ov:
            print(
                f"    opt1 | no-violation n={ov['no_violation']['n']} "
                f"{ov['no_violation']['opt1']} | with-violation "
                f"n={ov['with_violation']['n']} {ov['with_violation']['opt1']} "
                f"| corr={a.get('corr_violations_vs_opt1')}",
                flush=True,
            )
    return out


def run_mcr(seeds: Sequence[int]) -> dict[str, Any]:
    annotate = pcj.resolve_annotate_dir(MCR_RUN)
    ids = sorted(p.stem for p in (annotate / "case_results").glob("*.json"))
    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        cases: dict[str, Any] = {}
        for cid in ids:
            _, labels, _ = pcj.load_pre_compat_inputs(annotate, cid)
            if not labels:
                continue
            res = audit_case(labels, seeds=seeds, match_top1=match_top1)
            if res is not None:
                cases[cid] = res
        out[variant] = {"aggregate": aggregate(cases), "per_case": cases}
        a = out[variant]["aggregate"]
        print(
            f"  MCR {variant}: cases={a['n_cases']} draws={a['n_draws_total']} "
            f"top1_inv={a['top1_rep_invariance_rate']} "
            f"dup_ref={a['ref_dup_rep_pairs_mean']} "
            f"dup_blind={a['blind_dup_rep_pairs_mean']} "
            f"viol_rate={a['blind_any_violation_rate']}",
            flush=True,
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", default="all100")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=20260728)
    ap.add_argument("--skip-da", action="store_true")
    ap.add_argument("--skip-mcr", action="store_true")
    args = ap.parse_args()

    seeds = [int(args.seed0) + i for i in range(int(args.seeds))]
    payload: dict[str, Any] = {
        "created_at": _utc(),
        "question": (
            "Is the AB10b/AB10c null a construct-validity artifact? Specifically: "
            "is rank-1 invariant by construction, and are the endpoints blind to "
            "quotient violations (non-synonym merges and synonymish duplicates "
            "left among survivors)?"
        ),
        "seeds": int(args.seeds),
        "seed0": int(args.seed0),
        "metric_da": "mapper option rematch @1 (deterministic; synonym_bind OFF)",
    }

    if not args.skip_da:
        print(f"[{_utc()}] DA cohort={args.cohort}", flush=True)
        payload["DA"] = run_da(seeds, args.cohort)
        print(f"[{_utc()}] DA endpoint channel audit", flush=True)
        payload["DA_channel_audit"] = da_channel_audit(seeds, args.cohort)
    if not args.skip_mcr:
        print(f"[{_utc()}] MCR pre-compat joint", flush=True)
        payload["MCR"] = run_mcr(seeds)
        print(f"[{_utc()}] MCR endpoint channel audit", flush=True)
        payload["MCR_channel_audit"] = mcr_channel_audit(seeds)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"[wrote] {OUT_JSON}", flush=True)


if __name__ == "__main__":
    main()
