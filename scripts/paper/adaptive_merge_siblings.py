#!/usr/bin/env python3
"""Offline AdaptiveMergeSiblings: collapse synonymous leaf labels into clusters.

No tree regeneration. Mapper rematch treats any cluster member hit as the
cluster representative rank (min original joint rank among members).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Optional, Sequence

SynonymFn = Callable[[str, str], bool]


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def labels_synonymish(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter >= max(2, min(len(ta), len(tb)) // 2)


def concept_key_for_label(label: str) -> str:
    """Deterministic concept key via DiseaseNameResolver normalization + alias table.

    Falls back to whitespace-normalized surface form when resolver import fails.
    """
    try:
        from agentclinic_tree_dx.knowledge.disease_name_resolver import (
            _ABBREVIATION_EXPANSIONS,
            _REVERSE_ALIAS,
            _extract_abbreviation,
            _normalize_label,
        )
    except Exception:
        return _norm(label)
    norm = _normalize_label(label)
    if not norm:
        return ""
    if norm in _REVERSE_ALIAS:
        return str(_REVERSE_ALIAS[norm])
    abbrev = _extract_abbreviation(label)
    if abbrev and abbrev in _ABBREVIATION_EXPANSIONS:
        for exp in _ABBREVIATION_EXPANSIONS[abbrev]:
            exp_low = str(exp).strip().lower()
            if exp_low in _REVERSE_ALIAS:
                return str(_REVERSE_ALIAS[exp_low])
            if exp_low:
                return exp_low
    # bare abbreviation as label
    toks = norm.split()
    if len(toks) == 1 and toks[0] in _ABBREVIATION_EXPANSIONS:
        exp0 = str(_ABBREVIATION_EXPANSIONS[toks[0]][0]).strip().lower()
        return str(_REVERSE_ALIAS.get(exp0, exp0))
    return norm


def labels_same_concept(a: str, b: str) -> bool:
    ka, kb = concept_key_for_label(a), concept_key_for_label(b)
    if not ka or not kb:
        return False
    return ka == kb


class _UF:
    def __init__(self, ids: Sequence[str]) -> None:
        self.p = {i: i for i in ids}

    def find(self, x: str) -> str:
        if self.p[x] != x:
            self.p[x] = self.find(self.p[x])
        return self.p[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def build_synonym_clusters(
    ranking_labels: Sequence[Mapping[str, Any]],
    synonym_fn: Optional[SynonymFn] = None,
) -> list[dict[str, Any]]:
    """Cluster all ranking leaves by synonym predicate (default: synonymish)."""
    pred = synonym_fn or labels_synonymish
    rows = []
    for r in ranking_labels:
        lid = str(r.get("id") or "").strip()
        if not lid:
            continue
        rows.append({
            "id": lid,
            "label": str(r.get("label") or "").strip(),
            "parent": str(r.get("parent") or "").strip(),
            "rank": int(r.get("rank") or 999),
        })
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    uf = _UF(ids)
    by_id = {r["id"]: r for r in rows}
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            if pred(a["label"], b["label"]):
                uf.union(a["id"], b["id"])
    groups: dict[str, list[str]] = {}
    for lid in ids:
        groups.setdefault(uf.find(lid), []).append(lid)

    clusters: list[dict[str, Any]] = []
    for members in groups.values():
        members_sorted = sorted(members, key=lambda x: by_id[x]["rank"])
        rep = members_sorted[0]
        clusters.append({
            "representative_id": rep,
            "member_ids": members_sorted,
            "label": by_id[rep]["label"],
            "rank": by_id[rep]["rank"],
            "parent": by_id[rep]["parent"],
        })
    clusters.sort(key=lambda c: (int(c["rank"]), str(c["representative_id"])))
    return clusters


def merge_ranking_ids(
    ranking_labels: Sequence[Mapping[str, Any]],
    synonym_fn: Optional[SynonymFn] = None,
) -> dict[str, Any]:
    """Return merged representative order + membership maps."""
    clusters = build_synonym_clusters(ranking_labels, synonym_fn=synonym_fn)
    rep_order = [c["representative_id"] for c in clusters]
    member_to_rep: dict[str, str] = {}
    rep_to_members: dict[str, list[str]] = {}
    for c in clusters:
        rep = c["representative_id"]
        rep_to_members[rep] = list(c["member_ids"])
        for m in c["member_ids"]:
            member_to_rep[m] = rep
    return {
        "clusters": clusters,
        "representative_order": rep_order,
        "member_to_rep": member_to_rep,
        "rep_to_members": rep_to_members,
        "n_clusters": len(clusters),
        "n_leaves": len(member_to_rep),
    }


def merge_ranking_ids_with_predicate(
    ranking_labels: Sequence[Mapping[str, Any]],
    synonym_fn: SynonymFn,
) -> dict[str, Any]:
    """Explicit alias for callers that inject a custom synonym predicate."""
    return merge_ranking_ids(ranking_labels, synonym_fn=synonym_fn)


def merge_ranking_ids_from_blocks(
    ranking_labels: Sequence[Mapping[str, Any]],
    blocks: Sequence[Sequence[str]],
) -> dict[str, Any]:
    """Build merge_info from an externally supplied partition of the leaf ids.

    Representative selection and cluster ordering follow the same rule as
    ``build_synonym_clusters`` (rep = best-ranked member; clusters sorted by rep
    rank then id), so the only thing a caller can vary is *membership*. Used by
    AB10b to substitute a semantics-blind partition for the synonym partition
    while holding cluster granularity fixed.
    """
    rows = []
    for r in ranking_labels:
        lid = str(r.get("id") or "").strip()
        if not lid:
            continue
        rows.append({
            "id": lid,
            "label": str(r.get("label") or "").strip(),
            "parent": str(r.get("parent") or "").strip(),
            "rank": int(r.get("rank") or 999),
        })
    by_id = {r["id"]: r for r in rows}
    seen: set[str] = set()
    norm_blocks: list[list[str]] = []
    for blk in blocks:
        members = [str(x) for x in blk if str(x) in by_id and str(x) not in seen]
        seen.update(members)
        if members:
            norm_blocks.append(members)
    missing = [r["id"] for r in rows if r["id"] not in seen]
    if missing:
        raise ValueError(f"blocks do not cover all leaves; missing={missing}")

    clusters: list[dict[str, Any]] = []
    for members in norm_blocks:
        members_sorted = sorted(members, key=lambda x: by_id[x]["rank"])
        rep = members_sorted[0]
        clusters.append({
            "representative_id": rep,
            "member_ids": members_sorted,
            "label": by_id[rep]["label"],
            "rank": by_id[rep]["rank"],
            "parent": by_id[rep]["parent"],
        })
    clusters.sort(key=lambda c: (int(c["rank"]), str(c["representative_id"])))

    rep_order = [c["representative_id"] for c in clusters]
    member_to_rep: dict[str, str] = {}
    rep_to_members: dict[str, list[str]] = {}
    for c in clusters:
        rep = c["representative_id"]
        rep_to_members[rep] = list(c["member_ids"])
        for m in c["member_ids"]:
            member_to_rep[m] = rep
    return {
        "clusters": clusters,
        "representative_order": rep_order,
        "member_to_rep": member_to_rep,
        "rep_to_members": rep_to_members,
        "n_clusters": len(clusters),
        "n_leaves": len(member_to_rep),
    }


def expand_gold_hits_via_clusters(
    gold_leaf_ids: Sequence[str],
    member_to_rep: Mapping[str, str],
    rep_to_members: Mapping[str, Sequence[str]],
) -> set[str]:
    """Any gold leaf expands to all members of its synonym cluster."""
    hit: set[str] = set()
    for gid in gold_leaf_ids:
        g = str(gid)
        rep = member_to_rep.get(g, g)
        hit.add(rep)
        for m in rep_to_members.get(rep, [rep]):
            hit.add(str(m))
    return hit


def cluster_rank_of_gold(
    representative_order: Sequence[str],
    gold_leaf_ids: Sequence[str],
    member_to_rep: Mapping[str, str],
) -> Optional[int]:
    gold_reps = {
        member_to_rep.get(str(g), str(g)) for g in gold_leaf_ids if str(g).strip()
    }
    for i, rep in enumerate(representative_order, start=1):
        if rep in gold_reps:
            return i
    return None


def expand_gold_hits_via_clusters(
    gold_leaf_ids: Sequence[str],
    member_to_rep: Mapping[str, str],
    rep_to_members: Mapping[str, Sequence[str]],
) -> set[str]:
    """Any gold leaf expands to all members of its synonym cluster."""
    hit: set[str] = set()
    for gid in gold_leaf_ids:
        g = str(gid)
        rep = member_to_rep.get(g, g)
        hit.add(rep)
        for m in rep_to_members.get(rep, [rep]):
            hit.add(str(m))
    return hit


def cluster_rank_of_gold(
    representative_order: Sequence[str],
    gold_leaf_ids: Sequence[str],
    member_to_rep: Mapping[str, str],
) -> Optional[int]:
    gold_reps = {
        member_to_rep.get(str(g), str(g)) for g in gold_leaf_ids if str(g).strip()
    }
    for i, rep in enumerate(representative_order, start=1):
        if rep in gold_reps:
            return i
    return None
