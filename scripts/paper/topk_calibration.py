#!/usr/bin/env python3
"""TopKCalibration: closed-pool rerank after joint, before AnswerMapper.

Hard guards (design_constraints G1–G3):
- Only reorder joint Top-K leaves (no open vignette regen).
- Top2 set guard: never drop a pre-Top2 gold-mapped leaf from post-Top2.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

# Dual-Inf style examine over a closed leaf pool.
TOPK_EXAMINE_PROMPT = """You are a diagnostic examiner for a CLOSED candidate pool.
You receive a vignette, observed findings, and candidate L2 leaf diagnoses.
For EACH candidate leaf label:
- list vignette/finding items that SUPPORT it
- list vignette/finding items that CONTRADICT it
Do not invent findings. Do not add diseases outside the candidate list.
Use candidate labels exactly as keys.

Return JSON only:
{
  "support": {"Label A": ["reason", ...], "Label B": ["reason", ...]},
  "contradict": {"Label A": ["reason", ...], "Label B": ["reason", ...]}
}
"""

PAIR_PROMPT = """You are adjudicating which of two nearly-tied diagnoses should rank first.
Use only the vignette and findings. Prefer causal, temporal, treatment-response,
and localizing evidence. Do not invent findings.

Return JSON only:
{"winner":"__A_OR_B__", "rationale":"short reason"}
where winner must be exactly one of the two labels provided.
"""


def _norm_label(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def candidate_pool(
    ranking_labels: Sequence[Mapping[str, Any]],
    *,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Return closed Top-K leaf rows; asserts G1 (subset of joint ranking)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranking_labels:
        lid = str(row.get("id") or "").strip()
        if not lid or lid in seen:
            continue
        seen.add(lid)
        rows.append({
            "id": lid,
            "label": str(row.get("label") or "").strip(),
            "parent": str(row.get("parent") or "").strip(),
            "rank": int(row.get("rank") or (len(rows) + 1)),
        })
        if len(rows) >= k:
            break
    joint_ids = {
        str(r.get("id") or "") for r in ranking_labels if r.get("id")
    }
    assert all(r["id"] in joint_ids for r in rows), "G1 violation: pool outside joint"
    return rows


def _parse_reason_map(raw: Any, key: str) -> dict[str, list[str]]:
    if not isinstance(raw, Mapping):
        return {}
    block = raw.get(key)
    if not isinstance(block, Mapping):
        # allow flat {label: [reasons]} when key missing
        if key == "support" and all(
            isinstance(v, (list, tuple)) for v in raw.values()
        ):
            block = raw
        else:
            return {}
    out: dict[str, list[str]] = {}
    for disease, reasons in block.items():
        name = str(disease).strip()
        if not name:
            continue
        if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)):
            out[name] = [str(r).strip() for r in reasons if str(r).strip()]
        elif reasons:
            out[name] = [str(reasons).strip()]
        else:
            out[name] = []
    return out


def _match_counts(
    label: str,
    support_map: Mapping[str, Sequence[str]],
    contradict_map: Mapping[str, Sequence[str]],
) -> tuple[int, int]:
    nl = _norm_label(label)
    n_sup = n_con = 0
    for name, reasons in support_map.items():
        nn = _norm_label(name)
        if nn == nl or nl in nn or nn in nl:
            n_sup = max(n_sup, len(list(reasons or ())))
    for name, reasons in contradict_map.items():
        nn = _norm_label(name)
        if nn == nl or nl in nn or nn in nl:
            n_con = max(n_con, len(list(reasons or ())))
    return n_sup, n_con


def support_examine(
    cache: Any,
    *,
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    pool: Sequence[Mapping[str, Any]],
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """Return {leaf_id: {n_support, n_contradict}} for closed pool."""
    empty = {
        str(r["id"]): {"n_support": 0, "n_contradict": 0} for r in pool
    }
    if dry_run or cache is None:
        return empty
    payload = {
        "vignette": vignette,
        "findings": [
            {
                "id": str(f.get("id") or f.get("source_id") or ""),
                "text": str(f.get("text") or ""),
            }
            for f in findings
        ],
        "candidates": [
            {"id": str(r["id"]), "label": str(r["label"])} for r in pool
        ],
    }
    raw = cache.call("TopKCalibrationExamine", TOPK_EXAMINE_PROMPT, payload)
    support_map = _parse_reason_map(raw, "support")
    contradict_map = _parse_reason_map(raw, "contradict")
    out = {}
    for row in pool:
        n_sup, n_con = _match_counts(str(row["label"]), support_map, contradict_map)
        out[str(row["id"])] = {"n_support": n_sup, "n_contradict": n_con}
    return out


def score_leaves(
    pool: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Mapping[str, int]],
    *,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in pool:
        lid = str(row["id"])
        c = counts.get(lid) or {}
        rank = max(int(row.get("rank") or 1), 1)
        joint_logit = 1.0 / rank
        scores[lid] = (
            alpha * float(c.get("n_support") or 0)
            - beta * float(c.get("n_contradict") or 0)
            + gamma * joint_logit
        )
    return scores


def order_by_scores(
    pool: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
) -> list[str]:
    return [
        str(r["id"])
        for r in sorted(
            pool,
            key=lambda r: (
                -float(scores.get(str(r["id"])) or 0.0),
                int(r.get("rank") or 999),
                str(r.get("label") or "").casefold(),
            ),
        )
    ]


def pair_adjudicate(
    cache: Any,
    *,
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    pool: Sequence[Mapping[str, Any]],
    ordered_ids: Sequence[str],
    scores: Mapping[str, float],
    counts: Mapping[str, Mapping[str, int]],
    tau: float = 0.5,
    dry_run: bool = False,
) -> tuple[list[str], bool]:
    """Swap Top1/Top2 when |Δscore| < tau. Returns (new_order, swapped)."""
    if len(ordered_ids) < 2:
        return list(ordered_ids), False
    a, b = str(ordered_ids[0]), str(ordered_ids[1])
    gap = abs(float(scores.get(a) or 0.0) - float(scores.get(b) or 0.0))
    if gap >= tau:
        return list(ordered_ids), False

    by_id = {str(r["id"]): r for r in pool}
    label_a = str(by_id[a]["label"])
    label_b = str(by_id[b]["label"])

    winner = None
    if dry_run or cache is None:
        # rule: more support, fewer contradict, then original joint rank
        ca, cb = counts.get(a) or {}, counts.get(b) or {}
        key_a = (
            -int(ca.get("n_support") or 0),
            int(ca.get("n_contradict") or 0),
            int(by_id[a].get("rank") or 999),
        )
        key_b = (
            -int(cb.get("n_support") or 0),
            int(cb.get("n_contradict") or 0),
            int(by_id[b].get("rank") or 999),
        )
        winner = label_a if key_a <= key_b else label_b
    else:
        payload = {
            "vignette": vignette,
            "findings": [
                {"id": str(f.get("id") or ""), "text": str(f.get("text") or "")}
                for f in findings
            ],
            "candidate_a": label_a,
            "candidate_b": label_b,
            "score_a": scores.get(a),
            "score_b": scores.get(b),
        }
        raw = cache.call("TopKCalibrationPair", PAIR_PROMPT, payload)
        w = str((raw or {}).get("winner") or "").strip()
        na, nb = _norm_label(label_a), _norm_label(label_b)
        nw = _norm_label(w)
        if nw == na or na in nw or nw in na:
            winner = label_a
        elif nw == nb or nb in nw or nw in nb:
            winner = label_b
        else:
            winner = label_a  # fail-closed: keep current top

    if winner == label_b:
        new_order = [b, a] + list(ordered_ids[2:])
        return new_order, True
    return list(ordered_ids), False


def l1_prior_order_in_pool(
    case: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Reorder closed pool by L1-prior-only preference (2b fallback)."""
    from collections import defaultdict

    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    joint_ids = [str(r.get("id")) for r in labels if r.get("id")]
    by_parent: dict[str, list[str]] = defaultdict(list)
    for r in labels:
        lid = str(r.get("id") or "")
        parent = str(r.get("parent") or "")
        if lid:
            by_parent[parent].append(lid)
    l1_sorted = sorted(
        l1_rows,
        key=lambda r: (-float(r.get("posterior") or 0.0), str(r.get("id") or "")),
    )
    preferred: list[str] = []
    for row in l1_sorted:
        pid = str(row.get("id") or "")
        kids = by_parent.get(pid) or []
        if not kids:
            continue
        joint_pos = {lid: i for i, lid in enumerate(joint_ids)}
        kids_sorted = sorted(kids, key=lambda x: joint_pos.get(x, 10**9))
        preferred.append(kids_sorted[0])

    pool_ids = [str(r["id"]) for r in pool]
    pool_set = set(pool_ids)
    ordered: list[str] = []
    for lid in preferred:
        if lid in pool_set and lid not in ordered:
            ordered.append(lid)
    for lid in pool_ids:
        if lid not in ordered:
            ordered.append(lid)
    return ordered


def top2_set_guard(
    pre_ids: Sequence[str],
    post_ids: Sequence[str],
    gold_leaf_ids: Sequence[str],
    *,
    preserve_full_top2_when_no_gold: bool = False,
) -> tuple[list[str], bool]:
    """G2: protect Top2 set membership under recalibration.

    With gold leaf ids (offline / oracle eval): if any gold leaf that sat in
    the pre-calibration Top2 leaves the post-calibration Top2, revert to pre.

    Without gold, if ``preserve_full_top2_when_no_gold`` is True (**gold-blind
    Top2 freeze**): require ``set(post[:2]) == set(pre[:2])``. If the
    calibrated order would change the Top2 *set*, repair by placing the two
    pre-Top2 leaves first in their calibrated relative order, then the rest
    of the calibrated pool. Order swaps inside Top2 remain allowed. This uses
    only the system's own pre-calibration Top2 — never gold labels.

    Returns (final_ids, reverted_or_repaired).
    """
    pre = [str(x) for x in pre_ids]
    post = [str(x) for x in post_ids]
    gold = {str(x) for x in gold_leaf_ids if str(x).strip()}
    pre_top2 = set(pre[:2])
    post_top2 = set(post[:2])
    if not gold:
        if not preserve_full_top2_when_no_gold:
            return post, False
        if post_top2 == pre_top2:
            return post, False
        # Soft freeze: keep pre-Top2 membership, honor calibrated order among them.
        kept = [lid for lid in post if lid in pre_top2]
        rest = [lid for lid in post if lid not in pre_top2]
        if set(kept) != pre_top2:
            return pre, True
        return kept + rest, True
    protected = pre_top2 & gold
    if protected and not protected.issubset(post_top2):
        return pre, True
    return post, False


def apply_order_to_full_ranking(
    full_ids: Sequence[str],
    new_top_order: Sequence[str],
) -> list[str]:
    """Place calibrated Top-K first (in new order), then remaining joint tails."""
    top = [str(x) for x in new_top_order]
    top_set = set(top)
    rest = [str(x) for x in full_ids if str(x) not in top_set]
    return top + rest


def calibrate_case(
    *,
    case: Mapping[str, Any],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    gold_leaf_ids: Sequence[str],
    arm: str,
    cache: Any = None,
    k: int = 5,
    alpha: float = 1.0,
    beta: float = 1.0,
    gamma: float = 0.5,
    tau: float = 0.5,
    dry_run: bool = False,
    preserve_full_top2_when_no_gold: bool = False,
) -> dict[str, Any]:
    """Run one calibration arm. arm in:
    ours | support_rerank | pair | both | both_l1fallback

    ``preserve_full_top2_when_no_gold``: gold-blind G2 — when gold_leaf_ids is
    empty, require post-Top2 to equal pre-Top2 as a *set* (order may swap).
    Does not use gold labels.
    """
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    full_ids = [
        str(r.get("id")) for r in labels if r.get("id")
    ]
    pool = candidate_pool(labels, k=k)
    pre_ids = [r["id"] for r in pool]

    arm = str(arm).strip().lower()
    if arm in {"ours", "baseline", ""}:
        return {
            "arm": "ours",
            "ordered_ids": list(full_ids),
            "pool_pre": pre_ids,
            "pool_post": pre_ids,
            "reverted": False,
            "swapped": False,
            "counts": {},
            "scores": {},
        }

    use_support = arm in {"support_rerank", "both", "both_l1fallback"}
    use_pair = arm in {"pair", "both", "both_l1fallback"}
    use_l1 = arm in {"both_l1fallback", "l1fallback"}

    counts = (
        support_examine(
            cache,
            vignette=vignette,
            findings=findings,
            pool=pool,
            dry_run=dry_run or not use_support,
        )
        if use_support
        else {r["id"]: {"n_support": 0, "n_contradict": 0} for r in pool}
    )
    # for pair-only, still zero counts; scores from joint logit
    scores = score_leaves(pool, counts, alpha=alpha, beta=beta, gamma=gamma)

    if use_support or arm == "pair":
        ordered = order_by_scores(pool, scores)
    else:
        ordered = list(pre_ids)

    if use_l1:
        # blend: start from L1 order in pool when Top1-Top2 nearly tied
        if len(ordered) >= 2:
            gap = abs(
                float(scores.get(ordered[0]) or 0.0)
                - float(scores.get(ordered[1]) or 0.0)
            )
            if gap < tau or arm == "l1fallback":
                ordered = l1_prior_order_in_pool(case, pool)

    swapped = False
    if use_pair:
        ordered, swapped = pair_adjudicate(
            cache,
            vignette=vignette,
            findings=findings,
            pool=pool,
            ordered_ids=ordered,
            scores=scores,
            counts=counts,
            tau=tau,
            dry_run=dry_run,
        )

    guarded, reverted = top2_set_guard(
        pre_ids,
        ordered,
        gold_leaf_ids,
        preserve_full_top2_when_no_gold=preserve_full_top2_when_no_gold,
    )
    final_full = apply_order_to_full_ranking(full_ids, guarded)
    return {
        "arm": arm,
        "ordered_ids": final_full,
        "pool_pre": pre_ids,
        "pool_post": guarded,
        "reverted": reverted,
        "swapped": swapped,
        "counts": counts,
        "scores": {k: float(v) for k, v in scores.items()},
        "preserve_full_top2_when_no_gold": bool(preserve_full_top2_when_no_gold),
    }
