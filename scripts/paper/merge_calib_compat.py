#!/usr/bin/env python3
"""Merge × Calibration compatibility: parallel select + serial-safe ablation.

Root cause: serial merge→strong calib demotes merge-won Top1 on some cases;
over-broad Fine gates force merge on almost all cases and steal calib-only wins.

compat_parallel (default-worthy):
  if fine_crowd_gate: AdaptiveMergeSiblings only
  else: TopKCalibration(both_l1fallback)

compat_serial_safe (ablation):
  if gate: merge → support_rerank only + gold-blind merge-Top1 guard
  else: both_l1fallback
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import adaptive_merge_siblings as merge
import topk_calibration as calib


def fine_crowd_gate(
    ranking_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Tight Fine gate (gold-blind): Top1 synonym cluster ≥2 OR Top1–Top2 synonymish."""
    labels = [
        {
            "id": str(r.get("id") or "").strip(),
            "label": str(r.get("label") or "").strip(),
            "parent": str(r.get("parent") or "").strip(),
            "rank": int(r.get("rank") or idx),
        }
        for idx, r in enumerate(ranking_labels, start=1)
        if str(r.get("id") or "").strip()
    ]
    info = merge.merge_ranking_ids(labels) if labels else {
        "n_leaves": 0,
        "n_clusters": 0,
        "member_to_rep": {},
        "rep_to_members": {},
        "representative_order": [],
        "clusters": [],
    }
    top_syn = False
    top1_crowd = False
    top1_id = ""
    top1_members: list[str] = []
    if labels:
        top1_id = str(labels[0]["id"])
        rep = info["member_to_rep"].get(top1_id, top1_id)
        top1_members = list(info["rep_to_members"].get(rep, [top1_id]))
        top1_crowd = len(top1_members) >= 2
    if len(labels) >= 2:
        top_syn = merge.labels_synonymish(
            str(labels[0].get("label") or ""),
            str(labels[1].get("label") or ""),
        )
    triggered = bool(top1_crowd or top_syn)
    return {
        "triggered": triggered,
        "top1_crowd": bool(top1_crowd),
        "top_synonym": bool(top_syn),
        "top1_id": top1_id,
        "top1_members": top1_members,
        "n_leaves": int(info.get("n_leaves") or 0),
        "n_clusters": int(info.get("n_clusters") or 0),
        "merge_info": info,
    }


def _rep_labels_from_merge(
    labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rep_labels: list[dict[str, Any]] = []
    for i, rep in enumerate(merge_info["representative_order"], start=1):
        src = next(
            (r for r in labels if str(r.get("id")) == rep),
            {"id": rep, "label": rep, "parent": ""},
        )
        rep_labels.append({
            "id": rep,
            "label": src.get("label"),
            "parent": src.get("parent"),
            "rank": i,
            "synthetic": bool(src.get("synthetic")),
        })
    return rep_labels


def project_option_maps_through_merge(
    option_maps: Mapping[str, Any],
    merge_info: Mapping[str, Any],
) -> dict[str, Any]:
    proj: dict[str, Any] = {}
    m2r = merge_info.get("member_to_rep") or {}
    for letter, mapped in (option_maps or {}).items():
        lids = [
            m2r.get(str(x), str(x))
            for x in (
                mapped.get("matched_leaf_ids")
                or mapped.get("clone_leaf_ids")
                or ()
            )
        ]
        proj[str(letter).upper()] = {
            **dict(mapped),
            "matched_leaf_ids": sorted(set(lids)),
            "clone_leaf_ids": sorted(set(lids)),
        }
    return proj


def preserve_merge_top1(
    pre_merge_ids: Sequence[str],
    post_calib_ids: Sequence[str],
) -> tuple[list[str], bool]:
    """Gold-blind: if calib displaces merge Top1, put it back at rank 1."""
    pre = [str(x) for x in pre_merge_ids]
    post = [str(x) for x in post_calib_ids]
    if not pre:
        return post, False
    top1 = pre[0]
    if not post:
        return pre, True
    if post[0] == top1:
        return post, False
    rest = [x for x in post if x != top1]
    return [top1] + rest, True


def run_compat_parallel(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
    force_merge: Optional[bool] = None,
    calib_arm: str = "both_l1fallback",
    mode_name: str = "compat_parallel",
) -> dict[str, Any]:
    """Gate → merge-only XOR calib_arm (never serial stack).

    force_merge:
      None  — use fine_crowd_gate (default)
      True  — force merge branch
      False — force calib branch
    calib_arm:
      default both_l1fallback; AB20 uses ``both`` (no L1 soft prior).
    """
    gate = fine_crowd_gate(ranking_labels)
    gold = list(gold_leaf_ids or [])
    om = dict(option_maps or {})
    triggered = bool(gate["triggered"]) if force_merge is None else bool(force_merge)

    if triggered:
        merge_info = gate["merge_info"]
        # When force_merge bypasses gate, still need merge clusters
        if merge_info is None or not merge_info.get("representative_order"):
            merge_info = merge.merge_ranking_ids(list(ranking_labels))
        rep_labels = _rep_labels_from_merge(ranking_labels, merge_info)
        maps = project_option_maps_through_merge(om, merge_info) if om else om
        ordered = list(merge_info["representative_order"])
        return {
            "mode": mode_name,
            "branch": "merge_only",
            "gate": {k: v for k, v in gate.items() if k != "merge_info"},
            "gate_empirical": bool(gate["triggered"]),
            "gate_applied": True,
            "ranking_labels": rep_labels,
            "ordered_ids": ordered,
            "option_maps": maps,
            "merge_info": merge_info,
            "calib": {
                "arm": "ours",
                "reverted": False,
                "swapped": False,
                "merge_top1_repaired": False,
            },
        }

    case_for = {
        **dict(case),
        "l2": {
            **(case.get("l2") or {}),
            "final_ranking_labels": list(ranking_labels),
            "final_ranking_ids": [
                str(r.get("id")) for r in ranking_labels if r.get("id")
            ],
        },
    }
    result = calib.calibrate_case(
        case=case_for,
        vignette=vignette,
        findings=findings,
        gold_leaf_ids=gold,
        arm=calib_arm,
        cache=cache,
        k=k,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        tau=tau,
        dry_run=dry_run,
    )
    ordered = list(result["ordered_ids"])
    by_id = {str(r.get("id")): dict(r) for r in ranking_labels if r.get("id")}
    out_labels = []
    for i, lid in enumerate(ordered, start=1):
        row = dict(by_id.get(lid) or {"id": lid, "label": lid, "parent": ""})
        row["rank"] = i
        out_labels.append(row)
    return {
        "mode": mode_name,
        "branch": "calib_only",
        "gate": {k: v for k, v in gate.items() if k != "merge_info"},
        "gate_empirical": bool(gate["triggered"]),
        "gate_applied": False,
        "ranking_labels": out_labels,
        "ordered_ids": ordered,
        "option_maps": om,
        "merge_info": None,
        "calib": {
            "arm": result.get("arm"),
            "reverted": bool(result.get("reverted")),
            "swapped": bool(result.get("swapped")),
            "merge_top1_repaired": False,
            "pool_pre": result.get("pool_pre"),
            "pool_post": result.get("pool_post"),
        },
    }


def run_compat_parallel_no_l1_prior(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
) -> dict[str, Any]:
    """AB20: same gate as compat_parallel, but calib branch uses ``both`` (no L1 prior)."""
    return run_compat_parallel(
        case=case,
        ranking_labels=ranking_labels,
        vignette=vignette,
        findings=findings,
        option_maps=option_maps,
        gold_leaf_ids=gold_leaf_ids,
        cache=cache,
        dry_run=dry_run,
        k=k,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        tau=tau,
        calib_arm="both",
        mode_name="compat_parallel_no_l1_prior",
    )


def assign_random_route_mask(
    empirical_triggers: Sequence[bool],
    *,
    seed: int = 20260727,
) -> list[bool]:
    """Permute trigger mask while preserving the number of True entries."""
    import random

    mask = [bool(x) for x in empirical_triggers]
    n_true = sum(mask)
    idxs = list(range(len(mask)))
    rng = random.Random(int(seed))
    rng.shuffle(idxs)
    out = [False] * len(mask)
    for i in idxs[:n_true]:
        out[i] = True
    return out


def run_compat_random_route(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
    force_merge: bool = False,
) -> dict[str, Any]:
    """AB10: apply a caller-assigned force_merge (same cohort frequency as empirical gate)."""
    out = run_compat_parallel(
        case=case,
        ranking_labels=ranking_labels,
        vignette=vignette,
        findings=findings,
        option_maps=option_maps,
        gold_leaf_ids=gold_leaf_ids,
        cache=cache,
        dry_run=dry_run,
        k=k,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        tau=tau,
        force_merge=bool(force_merge),
        mode_name="compat_random_route",
    )
    out["gate_random"] = bool(force_merge)
    return out


def partition_profile(merge_info: Mapping[str, Any]) -> list[int]:
    """Cluster-size multiset of a merge_info, descending."""
    return sorted(
        (len(m) for m in (merge_info.get("rep_to_members") or {}).values()),
        reverse=True,
    )


def n_matched_partitions(profile: Sequence[int]) -> int:
    """Count distinct partitions of labelled leaves having this size profile."""
    from collections import Counter
    from math import factorial

    sizes = [int(s) for s in profile]
    if not sizes:
        return 1
    num = factorial(sum(sizes))
    den = 1
    for s in sizes:
        den *= factorial(s)
    for _, c in Counter(sizes).items():
        den *= factorial(c)
    return num // den


def aggregate_cluster_order(
    ranking_labels: Sequence[Mapping[str, Any]],
    merge_info: Mapping[str, Any],
) -> list[str]:
    """AB10d: order clusters by pooled member evidence instead of best member rank.

    The deployed rule (``rep = best-ranked member``, clusters sorted by that rank)
    makes merging a pure *deletion* operator: the globally rank-1 leaf heads every
    partition, so no membership change can move rank 1. A quotient space that only
    deduplicates cannot claim rank-level effects.

    Scoring a class by the pooled evidence of its members restores that coupling:

        score(cluster) = sum over members of 1 / rank(member)

    A class only outranks a better-ranked singleton when it pools enough mass, so
    membership becomes load-bearing on rank 1. Ties fall back to best member rank,
    keeping the order total and deterministic.
    """
    rank_of = {
        str(r.get("id") or "").strip(): int(r.get("rank") or 999)
        for r in ranking_labels
        if str(r.get("id") or "").strip()
    }
    scored: list[tuple[float, int, str]] = []
    for rep, members in (merge_info.get("rep_to_members") or {}).items():
        ranks = [rank_of.get(str(m), 999) for m in members]
        if not ranks:
            continue
        scored.append((-sum(1.0 / r for r in ranks), min(ranks), str(rep)))
    scored.sort()
    return [rep for _, _, rep in scored]


def random_partition_matched(
    ranking_labels: Sequence[Mapping[str, Any]],
    profile: Sequence[int],
    *,
    seed: int,
    match_top1: bool = False,
    top1_size: Optional[int] = None,
) -> list[list[str]]:
    """Uniform-ish random partition of the leaf ids with a fixed size profile.

    ``match_top1`` additionally pins the rank-1 leaf into a block whose size
    equals ``top1_size``, so that absorption capacity at rank 1 is held fixed and
    only *which* leaves get absorbed is randomized.
    """
    import random

    ids = [
        str(r.get("id") or "").strip()
        for r in ranking_labels
        if str(r.get("id") or "").strip()
    ]
    sizes = [int(s) for s in profile]
    if sum(sizes) != len(ids):
        raise ValueError(
            f"profile sum {sum(sizes)} != n_leaves {len(ids)}"
        )
    rng = random.Random(int(seed))

    if match_top1 and ids:
        target = int(top1_size or sizes[0])
        remaining_sizes = list(sizes)
        if target not in remaining_sizes:
            raise ValueError(f"top1_size {target} not in profile {sizes}")
        remaining_sizes.remove(target)
        top1_leaf = ids[0]
        others = ids[1:]
        rng.shuffle(others)
        first_block = [top1_leaf] + others[: target - 1]
        rest = others[target - 1 :]
        rng.shuffle(rest)
        blocks = [first_block]
        pos = 0
        for s in remaining_sizes:
            blocks.append(rest[pos : pos + s])
            pos += s
        return blocks

    pool = list(ids)
    rng.shuffle(pool)
    blocks: list[list[str]] = []
    pos = 0
    for s in sizes:
        blocks.append(pool[pos : pos + s])
        pos += s
    return blocks


def _copartition_pairs(merge_info: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for members in (merge_info.get("rep_to_members") or {}).values():
        ms = sorted(str(m) for m in members)
        for i, a in enumerate(ms):
            for b in ms[i + 1 :]:
                pairs.add((a, b))
    return pairs


def run_count_matched_blind_merge(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
    seed: int = 20260728,
    match_top1: bool = False,
) -> dict[str, Any]:
    """AB10b: same gate and same |pi| as the main method, semantics-blind membership.

    Isolates *which leaves get merged* from *how many survive*. The gate and the
    calibration branch are byte-identical to ``compat_parallel``; on the merge
    branch the synonym partition is replaced by a random partition carrying the
    same cluster-size profile. If the main method beats this arm, compression is
    equivalence-class aware; if they tie, the block-2 mechanism claim reduces to
    candidate-count reduction.

    ``match_top1=True`` (AB10c) additionally fixes the size of the rank-1 cluster.
    """
    gate = fine_crowd_gate(ranking_labels)
    mode_name = "count_matched_blind_merge_top1" if match_top1 else "count_matched_blind_merge"

    if not bool(gate["triggered"]):
        out = run_compat_parallel(
            case=case,
            ranking_labels=ranking_labels,
            vignette=vignette,
            findings=findings,
            option_maps=option_maps,
            gold_leaf_ids=gold_leaf_ids,
            cache=cache,
            dry_run=dry_run,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
        )
        out["mode"] = mode_name
        out["blind_partition"] = {
            "applied": False,
            "reason": "gate_off_calib_branch",
        }
        return out

    om = dict(option_maps or {})
    ref = gate["merge_info"]
    if ref is None or not ref.get("representative_order"):
        ref = merge.merge_ranking_ids(list(ranking_labels))
    profile = partition_profile(ref)
    dof = n_matched_partitions(profile)
    top1_size = len(gate["top1_members"] or []) or profile[0]

    blocks = random_partition_matched(
        ranking_labels,
        profile,
        seed=seed,
        match_top1=match_top1,
        top1_size=top1_size if match_top1 else None,
    )
    blind = merge.merge_ranking_ids_from_blocks(ranking_labels, blocks)

    ref_pairs = _copartition_pairs(ref)
    blind_pairs = _copartition_pairs(blind)
    rep_labels = _rep_labels_from_merge(ranking_labels, blind)
    maps = project_option_maps_through_merge(om, blind) if om else om
    ordered = list(blind["representative_order"])
    return {
        "mode": mode_name,
        "branch": "merge_only",
        "merge_predicate": "count_matched_random",
        "gate": {k2: v for k2, v in gate.items() if k2 != "merge_info"},
        "gate_empirical": bool(gate["triggered"]),
        "gate_applied": True,
        "ranking_labels": rep_labels,
        "ordered_ids": ordered,
        "option_maps": maps,
        "merge_info": blind,
        "blind_partition": {
            "applied": True,
            "seed": int(seed),
            "match_top1": bool(match_top1),
            "profile": profile,
            "dof": int(dof),
            "degenerate": bool(dof <= 1),
            "identical_to_synonym": bool(ref_pairs == blind_pairs),
            "n_pairs_ref": len(ref_pairs),
            "n_pairs_blind": len(blind_pairs),
            "n_pairs_shared": len(ref_pairs & blind_pairs),
            "n_clusters_ref": int(ref.get("n_clusters") or 0),
            "n_clusters_blind": int(blind.get("n_clusters") or 0),
        },
        "calib": {
            "arm": "ours",
            "reverted": False,
            "swapped": False,
            "merge_top1_repaired": False,
        },
    }


def run_concept_id_merge(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
) -> dict[str, Any]:
    """AB11: always-merge using concept-ID equality instead of heuristic synonymish."""
    del vignette, findings, gold_leaf_ids, cache, dry_run, alpha, beta, gamma, tau
    om = dict(option_maps or {})
    labels = list(ranking_labels)
    merge_info = merge.merge_ranking_ids_with_predicate(
        labels, synonym_fn=merge.labels_same_concept
    )
    # mapping coverage: fraction of leaves whose concept key is non-empty
    n_mapped = 0
    for r in labels:
        key = merge.concept_key_for_label(str(r.get("label") or ""))
        if key:
            n_mapped += 1
    rep_labels = _rep_labels_from_merge(labels, merge_info)
    maps = project_option_maps_through_merge(om, merge_info) if om else om
    ordered = list(merge_info["representative_order"])
    return {
        "mode": "concept_id_merge",
        "branch": "concept_id_merge",
        "merge_predicate": "concept_id",
        "concept_key_coverage": (
            round(n_mapped / max(1, len(labels)), 4) if labels else 0.0
        ),
        "gate": {"triggered": True, "forced": True},
        "ranking_labels": rep_labels,
        "ordered_ids": ordered,
        "option_maps": maps,
        "merge_info": merge_info,
        "calib": {
            "arm": "ours",
            "reverted": False,
            "swapped": False,
            "merge_top1_repaired": False,
        },
    }


def run_compat_serial_safe(
    *,
    case: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    option_maps: Optional[Mapping[str, Any]] = None,
    gold_leaf_ids: Optional[Sequence[str]] = None,
    cache: Any = None,
    dry_run: bool = False,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
) -> dict[str, Any]:
    """If gate: merge → support_rerank + merge-Top1 guard; else both_l1fallback."""
    gate = fine_crowd_gate(ranking_labels)
    gold = list(gold_leaf_ids or [])
    om = dict(option_maps or {})

    if not gate["triggered"]:
        out = run_compat_parallel(
            case=case,
            ranking_labels=ranking_labels,
            vignette=vignette,
            findings=findings,
            option_maps=option_maps,
            gold_leaf_ids=gold_leaf_ids,
            cache=cache,
            dry_run=dry_run,
            k=k,
            alpha=alpha,
            beta=beta,
            gamma=gamma,
            tau=tau,
        )
        out["mode"] = "compat_serial_safe"
        return out

    merge_info = gate["merge_info"]
    rep_labels = _rep_labels_from_merge(ranking_labels, merge_info)
    maps = project_option_maps_through_merge(om, merge_info) if om else om
    pre_ids = list(merge_info["representative_order"])
    gold_for = gold
    if gold and merge_info:
        gold_for = [merge_info["member_to_rep"].get(g, g) for g in gold]

    case_for = {
        **dict(case),
        "l2": {
            **(case.get("l2") or {}),
            "final_ranking_labels": rep_labels,
            "final_ranking_ids": pre_ids,
        },
    }
    result = calib.calibrate_case(
        case=case_for,
        vignette=vignette,
        findings=findings,
        gold_leaf_ids=gold_for,
        arm="support_rerank",
        cache=cache,
        k=k,
        alpha=alpha,
        beta=beta,
        gamma=gamma,
        tau=tau,
        dry_run=dry_run,
    )
    ordered, repaired = preserve_merge_top1(pre_ids, result["ordered_ids"])
    by_id = {str(r.get("id")): dict(r) for r in rep_labels if r.get("id")}
    out_labels = []
    for i, lid in enumerate(ordered, start=1):
        row = dict(by_id.get(lid) or {"id": lid, "label": lid, "parent": ""})
        row["rank"] = i
        out_labels.append(row)
    return {
        "mode": "compat_serial_safe",
        "branch": "merge_then_support",
        "gate": {k: v for k, v in gate.items() if k != "merge_info"},
        "ranking_labels": out_labels,
        "ordered_ids": ordered,
        "option_maps": maps,
        "merge_info": merge_info,
        "calib": {
            "arm": "support_rerank",
            "reverted": bool(result.get("reverted")),
            "swapped": bool(result.get("swapped")),
            "merge_top1_repaired": repaired,
            "pool_pre": result.get("pool_pre"),
            "pool_post": list(ordered[:k]),
        },
    }
