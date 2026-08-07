#!/usr/bin/env python3
"""Audit multi-gold L1 families: L1 rank, within-family top-2 cover, gate proxies.

Reads existing same-L1 multi-gold groups + shared_trees / official_eval golds.
Gold is used only for oracle coverage stats; proposed gate features are gold-blind.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from build_eval_projection import load_tree_state  # noqa: E402
from mapper_bind_repair import leaves_from_tree_state  # noqa: E402

STOP = {
    "disease", "syndrome", "disorder", "infection", "acute", "chronic",
    "primary", "secondary", "with", "without", "and", "the", "of", "in",
    "due", "to", "or", "a", "an", "type", "stage", "other", "causes", "cause",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().casefold())


def _tokens(s: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", str(s).casefold())
        if len(t) >= 3 and t not in STOP
    }


def _l1_axes(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """L1 axes ranked by leaf-mass (sum of child-leaf posteriors).

    ``shared_trees`` often stores parent ``posterior=0``; ranking by the raw
    parent field would collapse to id-order and be meaningless.
    """
    branches = state.get("branches") or {}
    axes: list[dict[str, Any]] = []
    for bid, b in branches.items():
        if not isinstance(b, Mapping):
            continue
        children = list(b.get("children") or [])
        leaf_kids = []
        leaf_mass = 0.0
        max_leaf = 0.0
        for cid in children:
            node = branches.get(str(cid)) or {}
            if list(node.get("children") or []):
                continue
            leaf_kids.append(str(cid))
            lp = float(node.get("posterior") or 0.0)
            leaf_mass += lp
            max_leaf = max(max_leaf, lp)
        if not leaf_kids:
            continue
        parent_post = float(b.get("posterior") or 0.0)
        # Prefer explicit parent mass when present; else leaf-sum.
        mass = parent_post if parent_post > 0 else leaf_mass
        axes.append({
            "id": str(bid),
            "label": str(b.get("label") or ""),
            "posterior": mass,
            "parent_posterior_raw": parent_post,
            "leaf_mass": leaf_mass,
            "max_leaf_posterior": max_leaf,
            "n_children": len(leaf_kids),
            "leaf_ids": leaf_kids,
        })
    axes.sort(
        key=lambda r: (
            -float(r["posterior"]),
            -float(r["max_leaf_posterior"]),
            str(r["id"]),
        )
    )
    for i, ax in enumerate(axes, start=1):
        ax["rank"] = i
    return axes


def _family_leaves(
    state: Mapping[str, Any], parent_id: str
) -> list[dict[str, Any]]:
    branches = state.get("branches") or {}
    parent = branches.get(str(parent_id)) or {}
    rows: list[dict[str, Any]] = []
    for cid in parent.get("children") or []:
        node = branches.get(str(cid)) or {}
        if list(node.get("children") or []):
            continue
        rows.append({
            "id": str(cid),
            "label": str(node.get("label") or ""),
            "posterior": float(node.get("posterior") or 0.0),
            "parent_id": str(parent_id),
        })
    rows.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    for i, r in enumerate(rows, start=1):
        r["rank_in_family"] = i
    return rows


def _match_leaf_rank(
    matched_leaf_label: str, family: Sequence[Mapping[str, Any]]
) -> int | None:
    key = _norm(matched_leaf_label)
    if not key:
        return None
    for r in family:
        if _norm(str(r.get("label") or "")) == key:
            return int(r["rank_in_family"])
    # soft token overlap fallback
    gt = _tokens(matched_leaf_label)
    best = None
    best_j = 0.0
    for r in family:
        lt = _tokens(str(r.get("label") or ""))
        if not gt or not lt:
            continue
        j = len(gt & lt) / max(1, len(gt | lt))
        if j > best_j:
            best_j = j
            best = int(r["rank_in_family"])
    return best if best_j >= 0.5 else None


def _gate_features(
    axes: Sequence[Mapping[str, Any]],
    ax: Mapping[str, Any],
    family: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Gold-blind proxies for 'this L1 may need top2 keep'."""
    ranks = {str(a["id"]): int(a["rank"]) for a in axes}
    posts = [float(a["posterior"]) for a in axes]
    total = sum(posts) or 1.0
    p = float(ax["posterior"])
    r1 = float(axes[0]["posterior"]) if axes else 0.0
    r2 = float(axes[1]["posterior"]) if len(axes) > 1 else 0.0
    leaf_posts = [float(x["posterior"]) for x in family]
    l1p = leaf_posts[0] if leaf_posts else 0.0
    l2p = leaf_posts[1] if len(leaf_posts) > 1 else 0.0
    # Fine-crowd-ish: multiple competitive leaves under one L1
    competitive = sum(1 for x in leaf_posts if x >= 0.5 * l1p and l1p > 0)
    return {
        "l1_rank": int(ax.get("rank") or ranks.get(str(ax["id"]), 99)),
        "l1_posterior": p,
        "l1_mass_share": p / total,
        "l1_gap_to_r1": (r1 - p) if axes else 0.0,
        "l1_top2_margin": r1 - r2,
        "n_family_leaves": len(family),
        "leaf1_posterior": l1p,
        "leaf2_posterior": l2p,
        "leaf_top2_ratio": (l2p / l1p) if l1p > 1e-12 else 0.0,
        "n_competitive_leaves": competitive,
        # Proposed gate predicates (gold-blind)
        "gate_l1_rank_le2": int(ax.get("rank") or 99) <= 2,
        "gate_l1_rank1": int(ax.get("rank") or 99) == 1,
        "gate_crowd": competitive >= 2 and len(family) >= 2,
        "gate_leaf_close": (l2p / l1p) >= 0.35 if l1p > 1e-12 else False,
        "gate_mass_ge015": (p / total) >= 0.15,
        "gate_mass_ge025": (p / total) >= 0.25,
        # Stricter: top L1 only + close second leaf (cheaper expand)
        "gate_rank1_and_leaf_close": (
            int(ax.get("rank") or 99) == 1
            and ((l2p / l1p) >= 0.35 if l1p > 1e-12 else False)
        ),
    }


def universe_gate_stats(run_dir: Path, groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Trigger rates over ALL L1 axes (gold-blind false-expand cost)."""
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    trees = ann / "shared_trees"
    multi_keys = {(str(g["cid"]), str(g["l1_id"])) for g in groups}
    multi_lab = {(str(g["cid"]), _norm(g.get("l1_label") or "")) for g in groups}

    n_axes = 0
    trig = Counter()
    trig_multi = Counter()
    trig_other = Counter()
    per_case_expand: list[int] = []
    pool_sel: list[int] = []
    pool_t1: list[int] = []
    pool_t2: list[int] = []

    def _dedup_len(rows: Sequence[Mapping[str, Any]]) -> int:
        seen: set[str] = set()
        n = 0
        for r in rows:
            k = str(r.get("label") or "").casefold()
            if not k or k in seen:
                continue
            seen.add(k)
            n += 1
        return n

    for tp in sorted(trees.glob("*.json")):
        cid = tp.stem
        state = load_tree_state(tp)
        axes = _l1_axes(state)
        expand = 0
        sel: list[dict[str, Any]] = []
        t1: list[dict[str, Any]] = []
        t2: list[dict[str, Any]] = []
        for ax in axes:
            fam = _family_leaves(state, str(ax["id"]))
            if not fam:
                continue
            n_axes += 1
            feats = _gate_features(axes, ax, fam)
            is_multi = (
                (cid, str(ax["id"])) in multi_keys
                or (cid, _norm(ax["label"])) in multi_lab
            )
            combo = bool(
                feats["gate_l1_rank_le2"]
                and (feats["gate_crowd"] or feats["gate_leaf_close"])
            )
            for name, hit in (
                ("gate_l1_rank_le2", feats["gate_l1_rank_le2"]),
                ("gate_l1_rank1", feats["gate_l1_rank1"]),
                ("gate_rank1_and_leaf_close", feats["gate_rank1_and_leaf_close"]),
                ("gate_rank2_and_crowd_or_close", combo),
            ):
                if not hit:
                    continue
                trig[name] += 1
                (trig_multi if is_multi else trig_other)[name] += 1
            if combo:
                expand += 1
                sel.extend(fam[:2])
            else:
                sel.extend(fam[:1])
            t1.extend(fam[:1])
            t2.extend(fam[:2])
        per_case_expand.append(expand)
        pool_sel.append(_dedup_len(sel))
        pool_t1.append(_dedup_len(t1))
        pool_t2.append(_dedup_len(t2))

    def _mean(xs: Sequence[int | float]) -> float | None:
        return (sum(xs) / len(xs)) if xs else None

    out: dict[str, Any] = {
        "n_axes": n_axes,
        "n_cases": len(per_case_expand),
        "triggers": {},
        "mean_expanded_l1s_per_case": _mean(per_case_expand),
        "mean_pool_top1": _mean(pool_t1),
        "mean_pool_selective_combo": _mean(pool_sel),
        "mean_pool_all_l1_top2": _mean(pool_t2),
    }
    for name, n in trig.items():
        out["triggers"][name] = {
            "n": n,
            "rate_over_axes": (n / n_axes) if n_axes else None,
            "n_on_multi_gold_l1": trig_multi[name],
            "n_on_other_l1": trig_other[name],
            "precision_vs_multi_gold_l1": (
                trig_multi[name] / n if n else None
            ),
        }
    return out


def analyze(
    *,
    run_dir: Path,
    groups_json: Path,
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    trees = ann / "shared_trees"
    doc = _read_json(groups_json)
    groups = list(doc.get("groups") or [])

    enriched: list[dict[str, Any]] = []
    # oracle counters
    n_groups = 0
    n_l1_rank1 = 0
    n_l1_rank_le2 = 0
    n_l1_rank_le3 = 0
    gold_leaf_rows = 0
    gold_in_top1 = 0
    gold_in_top2 = 0
    gold_in_top3 = 0
    gold_rank_missing = 0
    distinct_leaf_top2_hit_groups = 0
    groups_all_golds_in_top2 = 0
    groups_ge2_distinct_leaves_in_top2 = 0

    # gate recall/precision vs oracle "needs top2" (= group has ≥2 golds matched
    # to distinct leaves, or ≥2 golds with at least one outside family top1)
    oracle_need_top2 = []  # bool per group
    gate_hits: dict[str, list[bool]] = defaultdict(list)

    for g in groups:
        cid = str(g["cid"])
        l1_id = str(g["l1_id"])
        tree_path = trees / ("%s.json" % cid)
        if not tree_path.is_file():
            continue
        state = load_tree_state(tree_path)
        axes = _l1_axes(state)
        ax_by = {str(a["id"]): a for a in axes}
        ax = ax_by.get(l1_id)
        if ax is None:
            # fallback: label match
            for a in axes:
                if _norm(a["label"]) == _norm(g.get("l1_label") or ""):
                    ax = a
                    l1_id = str(a["id"])
                    break
        if ax is None:
            continue
        family = _family_leaves(state, l1_id)
        feats = _gate_features(axes, ax, family)

        # oracle: where do matched gold leaves sit in family ranking
        ranks: list[int] = []
        matched_leaf_ids: list[str] = []
        per_gold: list[dict[str, Any]] = []
        for row in g.get("golds") or []:
            if not row.get("covered"):
                per_gold.append({**row, "rank_in_family": None})
                continue
            rk = _match_leaf_rank(str(row.get("matched_leaf") or ""), family)
            per_gold.append({**row, "rank_in_family": rk})
            if rk is None:
                gold_rank_missing += 1
                continue
            ranks.append(rk)
            gold_leaf_rows += 1
            if rk == 1:
                gold_in_top1 += 1
            if rk <= 2:
                gold_in_top2 += 1
            if rk <= 3:
                gold_in_top3 += 1
            for fr in family:
                if int(fr["rank_in_family"]) == rk:
                    matched_leaf_ids.append(str(fr["id"]))
                    break

        distinct_in_top2 = {
            lid for lid, rk in zip(matched_leaf_ids, ranks) if rk <= 2
        }
        n_distinct_matched = len(set(matched_leaf_ids))
        # Need top2 keep if ≥2 golds map to ≥2 distinct leaves OR any gold at rank≥2
        need = (n_distinct_matched >= 2) or any(rk >= 2 for rk in ranks)
        # Stricter: ≥2 distinct gold-matched leaves under family
        need_strict = n_distinct_matched >= 2

        n_groups += 1
        if feats["l1_rank"] == 1:
            n_l1_rank1 += 1
        if feats["l1_rank"] <= 2:
            n_l1_rank_le2 += 1
        if feats["l1_rank"] <= 3:
            n_l1_rank_le3 += 1
        if ranks and all(rk <= 2 for rk in ranks):
            groups_all_golds_in_top2 += 1
        if len(distinct_in_top2) >= 1:
            distinct_leaf_top2_hit_groups += 1
        if len(distinct_in_top2) >= 2:
            groups_ge2_distinct_leaves_in_top2 += 1

        oracle_need_top2.append(need_strict)
        for key in (
            "gate_l1_rank_le2",
            "gate_l1_rank1",
            "gate_crowd",
            "gate_leaf_close",
            "gate_mass_ge015",
            "gate_mass_ge025",
            "gate_rank1_and_leaf_close",
        ):
            gate_hits[key].append(bool(feats[key]))
        # combo proposed
        combo = bool(feats["gate_l1_rank_le2"] and (
            feats["gate_crowd"] or feats["gate_leaf_close"]
        ))
        gate_hits["gate_rank2_and_crowd_or_close"].append(combo)
        gate_hits["gate_rank1_and_crowd"].append(
            bool(feats["gate_l1_rank1"] and feats["gate_crowd"])
        )
        gate_hits["gate_rank1_and_mass025_and_close"].append(
            bool(
                feats["gate_l1_rank1"]
                and feats["gate_mass_ge025"]
                and feats["gate_leaf_close"]
            )
        )

        enriched.append({
            "cid": cid,
            "l1_id": l1_id,
            "l1_label": g.get("l1_label"),
            "n_golds": g.get("n_golds"),
            "n_covered": g.get("n_covered"),
            "n_children": len(family),
            "l1_rank": feats["l1_rank"],
            "l1_posterior": feats["l1_posterior"],
            "l1_mass_share": feats["l1_mass_share"],
            "leaf_ranks_of_golds": ranks,
            "n_distinct_matched_leaves": n_distinct_matched,
            "n_distinct_in_family_top2": len(distinct_in_top2),
            "all_golds_in_family_top2": bool(ranks) and all(rk <= 2 for rk in ranks),
            "oracle_need_top2_strict": need_strict,
            "oracle_need_top2_loose": need,
            "features": feats,
            "golds": per_gold,
        })

    def _rate(num: int, den: int) -> float | None:
        return (num / den) if den else None

    # gate metrics vs oracle_need_top2_strict
    y = oracle_need_top2
    gate_eval: dict[str, Any] = {}
    for name, preds in gate_hits.items():
        tp = fp = fn = tn = 0
        for yi, pi in zip(y, preds):
            if yi and pi:
                tp += 1
            elif (not yi) and pi:
                fp += 1
            elif yi and (not pi):
                fn += 1
            else:
                tn += 1
        prec = tp / (tp + fp) if (tp + fp) else None
        rec = tp / (tp + fn) if (tp + fn) else None
        f1 = (
            (2 * prec * rec / (prec + rec))
            if prec is not None and rec is not None and (prec + rec) > 0
            else None
        )
        gate_eval[name] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": prec, "recall": rec, "f1": f1,
            "trigger_rate": _rate(tp + fp, len(y)),
            "oracle_positive_rate": _rate(tp + fn, len(y)),
        }

    # characteristics
    size_hist = Counter(int(g["n_golds"] or 0) for g in enriched)
    child_hist = Counter(int(g["n_children"] or 0) for g in enriched)
    rank_hist = Counter(int(g["l1_rank"] or 0) for g in enriched)
    mass = [float(g["l1_mass_share"] or 0) for g in enriched]
    n_child = [int(g["n_children"] or 0) for g in enriched]

    # theoretical: among golds with leaf rank, fraction in top2
    # also distinct-leaf view: for groups with ≥2 distinct matched leaves,
    # how often BOTH sit in family top2
    multi_distinct = [e for e in enriched if e["n_distinct_matched_leaves"] >= 2]
    both_in_top2 = sum(
        1 for e in multi_distinct if e["n_distinct_in_family_top2"] >= 2
    )

    out = {
        "protocol": "ox_multi_gold_l1_rank_gate_v1",
        "n_groups_enriched": n_groups,
        "ranking_note": (
            "L1 rank uses sum of child-leaf posteriors when parent.posterior==0 "
            "(common in annotate/shared_trees)."
        ),
        "characteristics": {
            "n_golds_per_group_hist": dict(sorted(size_hist.items())),
            "n_family_leaves_hist": dict(sorted(child_hist.items())),
            "mean_n_family_leaves": (sum(n_child) / len(n_child)) if n_child else None,
            "mean_l1_mass_share": (sum(mass) / len(mass)) if mass else None,
            "median_l1_mass_share": (
                sorted(mass)[len(mass) // 2] if mass else None
            ),
            "note": (
                "Multi-gold L1s are typically small sibling sets (~3–4 leaves), "
                "often high leaf-mass share, and frequently among the case's "
                "top L1 axes (by leaf-mass)."
            ),
        },
        "l1_ranking": {
            "hist": dict(sorted(rank_hist.items())),
            "frac_rank1": _rate(n_l1_rank1, n_groups),
            "frac_rank_le2": _rate(n_l1_rank_le2, n_groups),
            "frac_rank_le3": _rate(n_l1_rank_le3, n_groups),
            "n_rank1": n_l1_rank1,
            "n_rank_le2": n_l1_rank_le2,
            "n_rank_le3": n_l1_rank_le3,
            "n_groups": n_groups,
        },
        "family_top2_cover": {
            "n_gold_leaf_rows_ranked": gold_leaf_rows,
            "n_rank_unresolved": gold_rank_missing,
            "frac_gold_in_family_top1": _rate(gold_in_top1, gold_leaf_rows),
            "frac_gold_in_family_top2": _rate(gold_in_top2, gold_leaf_rows),
            "frac_gold_in_family_top3": _rate(gold_in_top3, gold_leaf_rows),
            "n_gold_in_top1": gold_in_top1,
            "n_gold_in_top2": gold_in_top2,
            "n_gold_in_top3": gold_in_top3,
            "frac_groups_all_golds_in_top2": _rate(
                groups_all_golds_in_top2, n_groups
            ),
            "n_groups_ge2_distinct_matched": len(multi_distinct),
            "frac_multi_distinct_both_in_top2": _rate(
                both_in_top2, len(multi_distinct)
            ),
            "n_multi_distinct_both_in_top2": both_in_top2,
        },
        "oracle_need_top2_strict": {
            "definition": (
                "group has ≥2 distinct gold-matched leaves under the L1 "
                "(keeping only family top1 would structurally drop ≥1 gold leaf)"
            ),
            "n_positive": sum(1 for x in y if x),
            "rate": _rate(sum(1 for x in y if x), len(y)),
        },
        "gate_eval_vs_oracle_strict": gate_eval,
        "universe_gate_stats": universe_gate_stats(
            run_dir, groups
        ),
        "recommended_gate": {
            "name": "rank2_and_crowd_or_close",
            "predicate": (
                "l1_rank<=2 AND (n_competitive_leaves>=2 OR leaf2/leaf1>=0.35); "
                "L1 rank by leaf-mass"
            ),
            "metrics": gate_eval.get("gate_rank2_and_crowd_or_close"),
            "action_if_triggered": (
                "keep per-L1 top2 for that parent only; other L1s stay top1; "
                "then compress global shortlist to K"
            ),
            "status": "research_candidate",
            "caveat": (
                "Within multi-gold groups, crowd/close are near-tautological; "
                "use universe_gate_stats for false-expand cost. "
                "Prefer selective expand over global per-L1 top2."
            ),
        },
        "groups": enriched,
    }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1",
    )
    ap.add_argument(
        "--groups-json",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/ox_same_l1_multi_gold_structural.json",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/ox_multi_gold_l1_rank_gate.json",
    )
    ap.add_argument(
        "--out-md",
        type=Path,
        default=ROOT
        / "analysis/transfer_metrics_v1/ox_multi_gold_l1_rank_gate.md",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    out = analyze(run_dir=args.run_dir, groups_json=args.groups_json)
    # write slim json (drop bulky golds detail optional — keep for audit)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lr = out["l1_ranking"]
    ft = out["family_top2_cover"]
    ch = out["characteristics"]
    ge = out["gate_eval_vs_oracle_strict"]
    rec = out["recommended_gate"]
    o = out["oracle_need_top2_strict"]
    uni = out.get("universe_gate_stats") or {}

    def pct(x: float | None) -> str:
        return "n/a" if x is None else "%.1f%%" % (100 * x)

    lines = [
        "# OX：多金标 L1 族的排名特征与 top-2 / 门控",
        "",
        "日期：2026-07-26  ",
        "范围：`ox_seq100` 同 L1 多金标组（n=%d，来自 `ox_same_l1_multi_gold_structural`）  " % out["n_groups_enriched"],
        "叶宇宙：`shared_trees`；**L1 排名 = 子叶后验之和**（parent.posterior 常为 0）  ",
        "机器表：[`ox_multi_gold_l1_rank_gate.json`](ox_multi_gold_l1_rank_gate.json)",
        "",
        "> %s" % out.get("ranking_note", ""),
        "",
        "## 1. 多金标 L1 族有什么特点？",
        "",
        "| 特征 | 值 |",
        "|------|---:|",
        "| 组规模分布 (n_golds) | `%s` |" % ch["n_golds_per_group_hist"],
        "| 族内叶数均值 | %.2f |" % (ch["mean_n_family_leaves"] or 0),
        "| 族内叶数分布 | `%s` |" % ch["n_family_leaves_hist"],
        "| L1 leaf-mass 份额均值 / 中位 | %.3f / %.3f |" % (
            ch["mean_l1_mass_share"] or 0,
            ch["median_l1_mass_share"] or 0,
        ),
        "",
        ch["note"],
        "",
        "## 2. 有多大比例是 ranking 靠前的 L1？",
        "",
        "| L1 leaf-mass 名次 | 组数 | 占比 |",
        "|------------|-----:|-----:|",
        "| rank = 1 | %d | %s |" % (lr["n_rank1"], pct(lr["frac_rank1"])),
        "| rank ≤ 2 | %d | %s |" % (lr["n_rank_le2"], pct(lr["frac_rank_le2"])),
        "| rank ≤ 3 | %d | %s |" % (lr["n_rank_le3"], pct(lr["frac_rank_le3"])),
        "",
        "名次直方图：`%s`" % lr["hist"],
        "",
        "## 3. 这些金标落在族内 top-2 的比例？",
        "",
        "口径：已覆盖金标 → 命中叶在该 L1 子叶后验序中的名次（n=%d 条可排名；%d 条未解析）。"
        % (ft["n_gold_leaf_rows_ranked"], ft["n_rank_unresolved"]),
        "",
        "| 覆盖 | 条数 | 占比 |",
        "|------|-----:|-----:|",
        "| 族内 top-1 | %d | %s |" % (ft["n_gold_in_top1"], pct(ft["frac_gold_in_family_top1"])),
        "| 族内 top-2 | %d | %s |" % (ft["n_gold_in_top2"], pct(ft["frac_gold_in_family_top2"])),
        "| 族内 top-3 | %d | %s |" % (ft["n_gold_in_top3"], pct(ft["frac_gold_in_family_top3"])),
        "| 组内全部金标都在 top-2 | — | %s |" % pct(ft["frac_groups_all_golds_in_top2"]),
        "",
        "对「≥2 个不同命中叶」的组（n=%d）：**两个及以上命中叶同在族内 top-2** 的比例 = **%s**（%d 组）。"
        % (
            ft["n_groups_ge2_distinct_matched"],
            pct(ft["frac_multi_distinct_both_in_top2"]),
            ft["n_multi_distinct_both_in_top2"],
        ),
        "",
        "## 4. 能否做门控？",
        "",
        "Oracle 正例（严格）：同 L1 上金标命中 **≥2 个不同叶** → 只留族内 top1 会结构性丢掉至少一叶。",
        "",
        "| | 值 |",
        "|--|---:|",
        "| 正例组数 / 占比 | %d / %s |" % (o["n_positive"], pct(o["rate"])),
        "",
        "### 4.1 在多金标组内的召回（上界乐观）",
        "",
        "| 门控 | trigger | P | R | F1 |",
        "|------|--------:|------:|------:|------:|",
    ]
    order = [
        "gate_l1_rank1",
        "gate_l1_rank_le2",
        "gate_crowd",
        "gate_leaf_close",
        "gate_mass_ge015",
        "gate_mass_ge025",
        "gate_rank1_and_crowd",
        "gate_rank1_and_leaf_close",
        "gate_rank1_and_mass025_and_close",
        "gate_rank2_and_crowd_or_close",
    ]
    for name in order:
        m = ge[name]
        lines.append(
            "| `%s` | %s | %s | %s | %s |"
            % (
                name,
                pct(m["trigger_rate"]),
                pct(m["precision"]),
                pct(m["recall"]),
                pct(m["f1"]),
            )
        )
    rm = rec["metrics"] or {}
    combo_u = (uni.get("triggers") or {}).get("gate_rank2_and_crowd_or_close") or {}
    r1close_u = (uni.get("triggers") or {}).get("gate_rank1_and_leaf_close") or {}
    lines += [
        "",
        "说明：`gate_crowd` / `gate_leaf_close` 在多金标组内接近恒真（近同义反复），**不能**单独当门控。",
        "",
        "### 4.2 全库 L1 轴上的误扩成本（更关键）",
        "",
        "全 `shared_trees`：**%d** 条 L1 轴 / %d 例。"
        % (int(uni.get("n_axes") or 0), int(uni.get("n_cases") or 0)),
        "",
        "| 门控 | 触发轴数 | 轴触发率 | 落在多金标 L1 | 相对多金标精确率* |",
        "|------|--------:|--------:|-------------:|-----------------:|",
    ]
    for name in (
        "gate_l1_rank1",
        "gate_l1_rank_le2",
        "gate_rank1_and_leaf_close",
        "gate_rank2_and_crowd_or_close",
    ):
        t = (uni.get("triggers") or {}).get(name) or {}
        lines.append(
            "| `%s` | %s | %s | %s | %s |"
            % (
                name,
                t.get("n"),
                pct(t.get("rate_over_axes")),
                t.get("n_on_multi_gold_l1"),
                pct(t.get("precision_vs_multi_gold_l1")),
            )
        )
    lines += [
        "",
        "\\*精确率 = 触发轴中属于「同 L1 多金标组」的比例（金标盲部署时的代理 P）。",
        "",
        "| 扩池策略 | 均值池大小（label-dedup） |",
        "|----------|-------------------------:|",
        "| 每 L1 top1 | %.2f |" % (uni.get("mean_pool_top1") or 0),
        "| 选择性 combo（推荐动作） | %.2f |" % (uni.get("mean_pool_selective_combo") or 0),
        "| 全体 L1 top2（已证实伤 F1） | %.2f |" % (uni.get("mean_pool_all_l1_top2") or 0),
        "",
        "选择性 combo：每例平均扩 **%.2f** 个 L1；池均值 %.2f（介于 top1 与全局 top2 之间）。"
        % (
            uni.get("mean_expanded_l1s_per_case") or 0,
            uni.get("mean_pool_selective_combo") or 0,
        ),
        "",
        "### 推荐候选",
        "",
        "- **谓词**：`%s`" % rec["predicate"],
        "- **动作**：%s" % rec["action_if_triggered"],
        "- **多金标组内**：P=%s R=%s F1=%s"
        % (pct(rm.get("precision")), pct(rm.get("recall")), pct(rm.get("f1"))),
        "- **全库代理 P**：%s（%s/%s 触发轴落在多金标 L1）"
        % (
            pct(combo_u.get("precision_vs_multi_gold_l1")),
            combo_u.get("n_on_multi_gold_l1"),
            combo_u.get("n"),
        ),
        "- **更省触发**：`gate_rank1_and_leaf_close` 全库代理 P=%s，轴触发率 %s"
        % (
            pct(r1close_u.get("precision_vs_multi_gold_l1")),
            pct(r1close_u.get("rate_over_axes")),
        ),
        "- **状态**：`research_candidate` — 实现 **selective per-L1 top2** 后再压 K；勿全局 top2。",
        "- **caveat**：%s" % rec.get("caveat", ""),
        "",
        "## 一句话",
        "",
        "多金标 L1 多为 **leaf-mass 靠前轴**（rank≤2 约 %s），金标叶落在族内 top-2 约 **%s**；"
        "可做金标盲门控，但必须看全库误扩——推荐 **选择性 top2**（池 ~%.1f）而非全体 L1 top2（池 ~%.1f）。"
        % (
            pct(lr["frac_rank_le2"]),
            pct(ft["frac_gold_in_family_top2"]),
            uni.get("mean_pool_selective_combo") or 0,
            uni.get("mean_pool_all_l1_top2") or 0,
        ),
        "",
    ]
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
        "l1_rank_le2": lr["frac_rank_le2"],
        "gold_in_family_top2": ft["frac_gold_in_family_top2"],
        "mean_mass_share": ch["mean_l1_mass_share"],
        "recommended": rec["name"],
        "recommended_metrics": rm,
        "universe_combo_precision": combo_u.get("precision_vs_multi_gold_l1"),
        "mean_pool_selective": uni.get("mean_pool_selective_combo"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
