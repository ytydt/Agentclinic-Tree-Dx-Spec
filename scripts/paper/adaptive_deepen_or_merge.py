#!/usr/bin/env python3
"""AdaptiveDeepenOrMerge: Fine→Merge, Coarse→Subdivide, then caller calibrates.

Fine gate uses the tightened fine_crowd_gate (Top1 cluster≥2 or Top1–Top2 synonym),
shared with merge_calib_compat — not the old full-ranking any-cluster trigger.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

import adaptive_merge_siblings as merge
import adaptive_subdivide_under_l2 as subdivide
from merge_calib_compat import fine_crowd_gate


def fine_signal(
    ranking_labels: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Tight Fine crowd gate (aligned with merge_calib_compat)."""
    gate = fine_crowd_gate(ranking_labels)
    return {
        "triggered": bool(gate["triggered"]),
        "n_leaves": gate.get("n_leaves"),
        "n_clusters": gate.get("n_clusters"),
        "top_synonym": gate.get("top_synonym"),
        "top1_crowd": gate.get("top1_crowd"),
        "merge_info": gate.get("merge_info"),
    }


def coarse_signal(
    ranking_labels: Sequence[Mapping[str, Any]],
    *,
    option_maps: Optional[Mapping[str, Any]] = None,
    options: Optional[Mapping[str, str]] = None,
    top_k: int = 5,
) -> dict[str, Any]:
    coarse_ids: list[str] = []
    if option_maps:
        coarse_ids = [
            lid
            for lid in subdivide.detect_coarse_leaves(
                option_maps, options=options or None
            )
            if any(str(r.get("id")) == lid for r in ranking_labels[:top_k])
            or any(str(r.get("id")) == lid for r in ranking_labels)
        ]
        # restrict to leaves that appear in ranking
        rank_ids = {str(r.get("id")) for r in ranking_labels}
        coarse_ids = [c for c in coarse_ids if c in rank_ids]
    specs: list[tuple[str, list[str]]] = []
    if not coarse_ids and options:
        specs = subdivide.detect_coarse_from_options_vs_labels(
            ranking_labels, options, top_k=top_k
        )
        coarse_ids = [s[0] for s in specs]
    return {
        "triggered": bool(coarse_ids),
        "coarse_leaf_ids": coarse_ids,
        "specs": specs,
    }


def route_case(
    ranking_labels: Sequence[Mapping[str, Any]],
    *,
    option_maps: Optional[Mapping[str, Any]] = None,
    options: Optional[Mapping[str, str]] = None,
    gold_letter: str = "",
    vignette: str = "",
    cache: Any = None,
    dry_run: bool = True,
    top_k: int = 5,
    force_path: str = "",
) -> dict[str, Any]:
    """Apply Fine merge and/or Coarse subdivide; return transformed ranking.

    Paths: merge | subdivide | merge_then_subdivide | calibrate_only
    Coarse path never ends as support_rerank-only (caller must not skip subdivide
    when path includes subdivide).
    """
    labels = [
        {
            "id": str(r.get("id") or "").strip(),
            "label": str(r.get("label") or "").strip(),
            "parent": str(r.get("parent") or "").strip(),
            "rank": int(r.get("rank") or idx),
            "synthetic": bool(r.get("synthetic")),
        }
        for idx, r in enumerate(ranking_labels, start=1)
        if str(r.get("id") or "").strip()
    ]
    options = dict(options or {})
    if not options and vignette:
        options = subdivide.parse_options_from_case_text(vignette)

    force = (force_path or "").strip().lower()
    fine = fine_signal(labels)
    coarse = coarse_signal(
        labels, option_maps=option_maps, options=options, top_k=top_k
    )

    do_merge = False
    do_sub = False
    if force in {"merge", "merge_only"}:
        do_merge = True
    elif force in {"subdivide", "subdivide_only"}:
        # Still require coarse signal — do not subdivide every case.
        do_sub = bool(coarse["triggered"])
    elif force in {"deepen", "auto", ""}:
        do_merge = bool(fine["triggered"])
        # Mutual exclusion: Fine merge first; Coarse subdivide only if not Fine.
        # Empirically merge_then_subdivide can dilute Top-2 on mixed cases.
        do_sub = bool(coarse["triggered"]) and not do_merge
    elif force in {"calibrate_only", "none", "off"}:
        do_merge = False
        do_sub = False
    else:
        do_merge = bool(fine["triggered"])
        do_sub = bool(coarse["triggered"]) and not do_merge

    merge_info = None
    sub_result = None
    working = labels
    maps = dict(option_maps or {})

    if do_merge:
        merge_info = merge.merge_ranking_ids(working)
        rep_labels = []
        for i, rep in enumerate(merge_info["representative_order"], start=1):
            src = next(
                (r for r in working if str(r.get("id")) == rep),
                {"id": rep, "label": rep, "parent": ""},
            )
            rep_labels.append({
                "id": rep,
                "label": src.get("label"),
                "parent": src.get("parent"),
                "rank": i,
                "synthetic": bool(src.get("synthetic")),
            })
        # Project option maps onto representatives
        if maps:
            proj: dict[str, Any] = {}
            for letter, mapped in maps.items():
                lids = [
                    merge_info["member_to_rep"].get(str(x), str(x))
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
            maps = proj
        working = rep_labels
        # Never chain Coarse subdivide after merge (including force=merge).
        do_sub = False

    if do_sub:
        sub_result = subdivide.subdivide_ranking(
            working,
            option_maps=maps or None,
            options=options,
            gold_letter=gold_letter,
            cache=cache,
            vignette=vignette,
            dry_run=dry_run,
            top_k=top_k,
        )
        working = list(sub_result["ranking_labels"])
        maps = dict(sub_result.get("option_maps") or maps)

    if do_merge and do_sub:
        path = "merge_then_subdivide"
    elif do_merge:
        path = "merge"
    elif do_sub:
        path = "subdivide"
    else:
        path = "calibrate_only"

    return {
        "path": path,
        "ranking_labels": working,
        "ordered_ids": [str(r["id"]) for r in working],
        "option_maps": maps,
        "fine": {k: v for k, v in fine.items() if k != "merge_info"},
        "coarse": coarse,
        "merge_info": merge_info,
        "subdivide": (
            {
                "path_applied": sub_result.get("path_applied"),
                "subdivided_parents": sub_result.get("subdivided_parents"),
                "n_synthetic": sub_result.get("n_synthetic"),
                "letter_to_l3": sub_result.get("letter_to_l3"),
                "children_by_parent": sub_result.get("children_by_parent"),
            }
            if sub_result
            else None
        ),
        "forbids_support_only": path in {"subdivide", "merge_then_subdivide"},
    }
