#!/usr/bin/env python3
"""L1 family-level closed-pool calibration after F6 freeze (Track B: support/pair/b12).

Does not open new L1 families. Gold labels must never appear in LLM payloads.
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional, Sequence

# Reuse Dual/MAC-style prompts, but candidates are L1 family labels.
L1_EXAMINE_PROMPT = """You are a diagnostic examiner for a CLOSED pool of L1 disease families.
You receive a vignette, observed findings, and candidate FAMILY labels (not fine diseases).
For EACH family label:
- list vignette/finding items that SUPPORT that family
- list vignette/finding items that CONTRADICT that family
Do not invent findings. Do not add families outside the candidate list.
Use candidate labels exactly as keys.

Return JSON only:
{
  "support": {"Family A": ["reason", ...], "Family B": ["reason", ...]},
  "contradict": {"Family A": ["reason", ...], "Family B": ["reason", ...]}
}
"""

L1_PAIR_PROMPT = """You are adjudicating which of two nearly-tied L1 disease families
should rank first. Use only the vignette and findings. Prefer causal, temporal,
treatment-response, and localizing evidence. Do not invent findings.

Return JSON only:
{"winner":"__A_OR_B__", "rationale":"short reason"}
where winner must be exactly one of the two family labels provided.
"""

FORBIDDEN_KEYS = frozenset({
    "is_gold", "gold", "gold_option", "gold_diagnosis", "gold_letter",
    "role", "favors", "decisive", "direction_target", "target",
})

ARMS = frozenset({"ours", "support", "pair", "b12"})


def _norm_label(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def _assert_no_gold(payload: Any, *, path: str = "payload") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                raise ValueError(f"gold-leak field at {path}.{key}")
            _assert_no_gold(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, value in enumerate(payload):
            _assert_no_gold(value, path=f"{path}[{i}]")


def normalize_l1_rows(l1_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        {
            "id": str(r.get("id") or "").strip(),
            "label": str(r.get("label") or "").strip(),
            "posterior": float(r.get("posterior") or 0.0),
        }
        for r in l1_rows
        if str(r.get("id") or "").strip()
    ]
    rows.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    return rows


def posterior_gap(rows: Sequence[Mapping[str, Any]]) -> float:
    if len(rows) < 2:
        return float("inf")
    return abs(float(rows[0]["posterior"]) - float(rows[1]["posterior"]))


def _parse_reason_map(raw: Any, key: str) -> dict[str, list[str]]:
    if not isinstance(raw, Mapping):
        return {}
    block = raw.get(key)
    if not isinstance(block, Mapping):
        if key == "support" and raw and all(
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
            out[name] = [str(x).strip() for x in reasons if str(x).strip()]
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


def examine_families(
    cache: Any,
    *,
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    pool: Sequence[Mapping[str, Any]],
    dry_run: bool = False,
    injected_counts: Optional[Mapping[str, Mapping[str, int]]] = None,
) -> dict[str, dict[str, int]]:
    """Return {family_id: {n_support, n_contradict}}."""
    empty = {str(r["id"]): {"n_support": 0, "n_contradict": 0} for r in pool}
    if injected_counts is not None:
        out = dict(empty)
        for fid, c in injected_counts.items():
            if fid in out:
                out[fid] = {
                    "n_support": int(c.get("n_support") or 0),
                    "n_contradict": int(c.get("n_contradict") or 0),
                }
        return out
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
    _assert_no_gold(payload)
    raw = cache.call("L1FamilyCalibrationExamine", L1_EXAMINE_PROMPT, payload)
    support_map = _parse_reason_map(raw, "support")
    contradict_map = _parse_reason_map(raw, "contradict")
    out: dict[str, dict[str, int]] = {}
    for row in pool:
        n_sup, n_con = _match_counts(str(row["label"]), support_map, contradict_map)
        out[str(row["id"])] = {"n_support": n_sup, "n_contradict": n_con}
    return out


def score_families(
    pool: Sequence[Mapping[str, Any]],
    counts: Mapping[str, Mapping[str, int]],
    *,
    gamma: float = 0.5,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in pool:
        fid = str(row["id"])
        c = counts.get(fid) or {}
        scores[fid] = (
            float(c.get("n_support") or 0)
            - float(c.get("n_contradict") or 0)
            + gamma * float(row.get("posterior") or 0.0)
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
                -float(r.get("posterior") or 0.0),
                str(r.get("id") or ""),
            ),
        )
    ]


def assign_monotonic_posteriors(
    ordered_ids: Sequence[str],
    by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rewrite posteriors as a decreasing geometric series (sum=1) by new rank."""
    n = len(ordered_ids)
    if n == 0:
        return []
    # Prefer preserving relative mass: use rank-based softmax of original posts
    # after permutation — here geometric for stability when posts collapse.
    raw = [math.exp(-0.5 * i) for i in range(n)]
    z = sum(raw) or 1.0
    out: list[dict[str, Any]] = []
    for i, fid in enumerate(ordered_ids):
        src = by_id.get(fid) or {"id": fid, "label": fid, "posterior": 0.0}
        out.append({
            "id": fid,
            "label": str(src.get("label") or fid),
            "posterior": float(raw[i] / z),
        })
    return out


def pair_adjudicate_families(
    cache: Any,
    *,
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    counts: Mapping[str, Mapping[str, int]],
    tau_score: float = 0.5,
    dry_run: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    """Swap Top1/Top2 when |Δscore| < tau_score."""
    ordered = list(rows)
    if len(ordered) < 2:
        return ordered, False
    a, b = str(ordered[0]["id"]), str(ordered[1]["id"])
    gap = abs(float(scores.get(a) or 0.0) - float(scores.get(b) or 0.0))
    if gap >= tau_score:
        return ordered, False

    label_a = str(ordered[0]["label"])
    label_b = str(ordered[1]["label"])
    winner = None
    if dry_run or cache is None:
        ca, cb = counts.get(a) or {}, counts.get(b) or {}
        key_a = (
            -int(ca.get("n_support") or 0),
            int(ca.get("n_contradict") or 0),
            -float(ordered[0].get("posterior") or 0.0),
        )
        key_b = (
            -int(cb.get("n_support") or 0),
            int(cb.get("n_contradict") or 0),
            -float(ordered[1].get("posterior") or 0.0),
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
        _assert_no_gold(payload)
        raw = cache.call("L1FamilyCalibrationPair", L1_PAIR_PROMPT, payload)
        w = str((raw or {}).get("winner") or "").strip()
        na, nb = _norm_label(label_a), _norm_label(label_b)
        nw = _norm_label(w)
        if nw == na or na in nw or nw in na:
            winner = label_a
        elif nw == nb or nb in nw or nw in nb:
            winner = label_b
        else:
            winner = label_a

    if winner == label_b:
        swapped = [dict(ordered[1]), dict(ordered[0])] + [dict(r) for r in ordered[2:]]
        # Re-assign monotonic posts after swap so Softmax order matches list order.
        by_id = {str(r["id"]): r for r in swapped}
        ids = [str(r["id"]) for r in swapped]
        return assign_monotonic_posteriors(ids, by_id), True
    return ordered, False


def _support_rerank(
    rows: Sequence[Mapping[str, Any]],
    *,
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    cache: Any,
    m: int,
    gamma: float,
    dry_run: bool,
    injected_counts: Optional[Mapping[str, Mapping[str, int]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]], dict[str, float]]:
    pool = [dict(r) for r in rows[: max(1, m)]]
    tail = [dict(r) for r in rows[len(pool):]]
    counts = examine_families(
        cache,
        vignette=vignette,
        findings=findings,
        pool=pool,
        dry_run=dry_run,
        injected_counts=injected_counts,
    )
    scores = score_families(pool, counts, gamma=gamma)
    ordered_ids = order_by_scores(pool, scores)
    by_id = {str(r["id"]): r for r in pool}
    new_pool = assign_monotonic_posteriors(ordered_ids, by_id)
    # Tail keeps original relative posts but may need renorm with head — keep as-is
    # for closed-set ranking; downstream sorts by posterior.
    # To keep global sort consistent, rescale tail below min head post.
    if new_pool and tail:
        floor = min(float(r["posterior"]) for r in new_pool) * 0.5
        t_posts = [max(float(r.get("posterior") or 0.0), 1e-9) for r in tail]
        t_sum = sum(t_posts) or 1.0
        mass = max(floor * len(tail), 1e-6)
        for i, r in enumerate(tail):
            r = dict(r)
            r["posterior"] = mass * (t_posts[i] / t_sum)
            tail[i] = r
    combined = new_pool + tail
    # Final renormalize
    z = sum(float(r["posterior"]) for r in combined) or 1.0
    for r in combined:
        r["posterior"] = float(r["posterior"]) / z
    combined.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    return combined, counts, scores


def calibrate_l1_families(
    l1_rows: Sequence[Mapping[str, Any]],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    *,
    arm: str = "b12",
    cache: Any = None,
    m: int = 5,
    tau_post: float = 0.15,
    gamma: float = 0.5,
    tau_score: float = 0.5,
    dry_run: bool = False,
    injected_counts: Optional[Mapping[str, Mapping[str, int]]] = None,
    force_calibrate: bool = False,
) -> dict[str, Any]:
    """Closed L1 family recalibration. arm: ours|support|pair|b12.

    ``force_calibrate`` bypasses the Top1–Top2 ``tau_post`` skip gate (used for
    force-MISRANK ablation smokes only; production defaults keep force off).
    """
    arm_n = str(arm or "ours").strip().lower()
    if arm_n not in ARMS:
        raise ValueError(f"unsupported l1 calib arm: {arm}")
    rows = normalize_l1_rows(l1_rows)
    original_ids = [str(r["id"]) for r in rows]
    meta: dict[str, Any] = {
        "arm": arm_n,
        "skipped_gate": False,
        "swapped": False,
        "m": int(m),
        "tau_post": float(tau_post),
        "force_calibrate": bool(force_calibrate),
        "n_families": len(rows),
        "gap_pre": posterior_gap(rows) if rows else None,
    }
    if arm_n == "ours" or not rows:
        return {
            "ordered_rows": rows,
            "arm": arm_n,
            "skipped_gate": False,
            "swapped": False,
            "counts": {},
            "scores": {},
            "meta": meta,
            "original_ids": original_ids,
        }

    gap = posterior_gap(rows)
    # tau_post <= 0 means never skip (full-cohort ablation). Otherwise skip when
    # Top1–Top2 gap is strictly larger than tau (near-ties with gap≈0 still run).
    skip = (float(tau_post) > 0.0) and (gap > float(tau_post))
    if (not force_calibrate) and skip:
        meta["skipped_gate"] = True
        return {
            "ordered_rows": rows,
            "arm": arm_n,
            "skipped_gate": True,
            "swapped": False,
            "counts": {},
            "scores": {},
            "meta": meta,
            "original_ids": original_ids,
        }

    counts: dict[str, dict[str, int]] = {}
    scores: dict[str, float] = {}
    out_rows = [dict(r) for r in rows]
    swapped = False

    if arm_n in {"support", "b12"}:
        out_rows, counts, scores = _support_rerank(
            out_rows,
            vignette=vignette,
            findings=findings,
            cache=cache,
            m=m,
            gamma=gamma,
            dry_run=dry_run,
            injected_counts=injected_counts,
        )

    if arm_n in {"pair", "b12"}:
        # For pair-only without prior support, score gap uses posteriors;
        # injected_counts (tests) only seed the dry-run support heuristic.
        if not scores:
            scores = {
                str(r["id"]): float(r.get("posterior") or 0.0) for r in out_rows
            }
            if injected_counts is not None:
                counts = {
                    str(r["id"]): {
                        "n_support": int(
                            (injected_counts.get(str(r["id"])) or {}).get("n_support")
                            or 0
                        ),
                        "n_contradict": int(
                            (injected_counts.get(str(r["id"])) or {}).get(
                                "n_contradict"
                            )
                            or 0
                        ),
                    }
                    for r in out_rows
                }
            else:
                counts = {
                    str(r["id"]): {"n_support": 0, "n_contradict": 0}
                    for r in out_rows
                }
        # Re-check near-tie on current Top2 score gap for pair step.
        out_rows, swapped = pair_adjudicate_families(
            cache,
            vignette=vignette,
            findings=findings,
            rows=out_rows,
            scores=scores,
            counts=counts,
            tau_score=tau_score,
            dry_run=dry_run,
        )
        meta["swapped"] = swapped

    # Closed-set integrity
    out_ids = {str(r["id"]) for r in out_rows}
    assert out_ids == set(original_ids), "L1 calib must not add/drop family ids"

    return {
        "ordered_rows": out_rows,
        "arm": arm_n,
        "skipped_gate": False,
        "swapped": swapped,
        "counts": counts,
        "scores": scores,
        "meta": meta,
        "original_ids": original_ids,
    }
