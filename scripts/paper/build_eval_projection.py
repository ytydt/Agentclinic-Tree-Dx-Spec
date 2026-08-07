#!/usr/bin/env python3
"""Build eval_projection JSON from shared_trees + P5 + case_results.

pred_ddx = global leaf posterior Top-K (dedup by label).
pred_interpretation / pred_reasoning_trace = deterministic templates from
selected facts + P5 support/oppose why (no KB chunk text).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from mapper_bind_repair import leaves_from_tree_state  # noqa: E402

DEFAULT_DDX_K = 5
DEFAULT_PER_L1_TOP = 2
# Gated hybrid: expand L1 to top2 only when rank≤2 and family is crowded/close.
GATED_L1_RANK_MAX = 2
GATED_LEAF_CLOSE_RATIO = 0.35
GATED_COMPETITIVE_FRAC = 0.5
MAX_WHY = 5


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_annotate_dir(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    if (run_dir / "annotate").is_dir():
        return run_dir / "annotate"
    if (run_dir / "shared_trees").is_dir():
        return run_dir
    # Baseline replicate dirs may already have annotate/eval_projection only
    # after build_baseline_eval_projection; still require annotate/.
    raise FileNotFoundError(
        "no annotate/ or shared_trees under %s "
        "(for baselines: run build_baseline_eval_projection.py first; "
        "do not pass --build-projection which expects shared_trees)" % run_dir
    )


def load_tree_state(tree_path: Path) -> dict[str, Any]:
    doc = _read_json(tree_path)
    if isinstance(doc, Mapping):
        st = doc.get("state")
        if isinstance(st, Mapping):
            return dict(st)
        if "branches" in doc:
            return dict(doc)
    return {}


def load_fixture_findings(fixture_path: Path | None) -> dict[str, dict[str, str]]:
    """case_id → {fact_id: text}."""
    out: dict[str, dict[str, str]] = {}
    if fixture_path is None or not fixture_path.is_file():
        return out
    doc = _read_json(fixture_path)
    cases = doc.get("cases") if isinstance(doc, Mapping) else None
    if not isinstance(cases, list):
        return out
    for row in cases:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("case_id") or "")
        fmap: dict[str, str] = {}
        for f in row.get("full_findings") or []:
            if not isinstance(f, Mapping):
                continue
            fid = str(f.get("id") or "").strip()
            text = str(f.get("text") or "").strip()
            if fid and text:
                fmap[fid] = text
        if cid:
            out[cid] = fmap
    return out


def _scored_leaves(tree_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    leaves = leaves_from_tree_state(tree_state)
    branches = tree_state.get("branches") or {}
    scored: list[dict[str, Any]] = []
    for row in leaves:
        lid = str(row["leaf_id"])
        node = branches.get(lid) or {}
        post = float(node.get("posterior") or 0.0)
        scored.append({
            "id": lid,
            "label": str(row.get("leaf_label") or ""),
            "posterior": post,
            "parent_id": str(row.get("parent_id") or ""),
        })
    scored.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    return scored


def top_leaf_posterior(
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
) -> list[dict[str, Any]]:
    """Global leaf posterior Top-K with label dedup (keep highest posterior)."""
    out: list[dict[str, Any]] = []
    seen_labels: set[str] = set()
    for row in _scored_leaves(tree_state):
        lab = str(row["label"]).strip()
        if not lab:
            continue
        key = lab.casefold()
        if key in seen_labels:
            continue
        seen_labels.add(key)
        out.append(row)
        if len(out) >= k:
            break
    return out


def top_leaf_per_l1_posterior(
    tree_state: Mapping[str, Any],
    *,
    per_l1: int = DEFAULT_PER_L1_TOP,
    max_pool: int = 0,
) -> list[dict[str, Any]]:
    """Keep up to ``per_l1`` highest-posterior leaves under each L1 parent.

    Global label-dedup: first occurrence (highest posterior overall within the
    per-parent selection pass) wins. Output is sorted by posterior descending
    so downstream compat sees a stable expanded pool — **not** yet compressed
    to the final short-list K.
    """
    per_l1 = max(1, int(per_l1))
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in _scored_leaves(tree_state):
        lab = str(row.get("label") or "").strip()
        if not lab:
            continue
        pid = str(row.get("parent_id") or "") or "_none"
        by_parent.setdefault(pid, []).append(row)

    selected: list[dict[str, Any]] = []
    for pid in sorted(by_parent):
        rows = by_parent[pid]
        rows.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
        seen_local: set[str] = set()
        taken = 0
        for row in rows:
            key = str(row["label"]).strip().casefold()
            if key in seen_local:
                continue
            seen_local.add(key)
            selected.append(dict(row))
            taken += 1
            if taken >= per_l1:
                break

    selected.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    # Global label dedup after merge (cross-parent duplicates).
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in selected:
        key = str(row["label"]).strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if max_pool and len(out) >= int(max_pool):
            break
    return out


def _l1_leaf_mass_axes(tree_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """L1 parents ranked by leaf-mass (parent.posterior often 0 in shared_trees)."""
    branches = tree_state.get("branches") or {}
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for row in _scored_leaves(tree_state):
        pid = str(row.get("parent_id") or "") or "_none"
        by_parent.setdefault(pid, []).append(row)

    axes: list[dict[str, Any]] = []
    for pid, rows in by_parent.items():
        rows = sorted(rows, key=lambda r: (-float(r["posterior"]), str(r["id"])))
        leaf_mass = sum(float(r["posterior"]) for r in rows)
        parent_post = float((branches.get(pid) or {}).get("posterior") or 0.0)
        mass = parent_post if parent_post > 0 else leaf_mass
        max_leaf = float(rows[0]["posterior"]) if rows else 0.0
        axes.append({
            "id": pid,
            "label": str((branches.get(pid) or {}).get("label") or ""),
            "posterior": mass,
            "max_leaf_posterior": max_leaf,
            "leaves": rows,
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


def l1_family_expand_gate(
    family_leaves: Sequence[Mapping[str, Any]],
    *,
    l1_rank: int,
    rank_max: int = GATED_L1_RANK_MAX,
    close_ratio: float = GATED_LEAF_CLOSE_RATIO,
    competitive_frac: float = GATED_COMPETITIVE_FRAC,
) -> dict[str, Any]:
    """Gold-blind: whether this L1 should keep top2 instead of top1."""
    posts = [float(r.get("posterior") or 0.0) for r in family_leaves]
    l1p = posts[0] if posts else 0.0
    l2p = posts[1] if len(posts) > 1 else 0.0
    competitive = sum(
        1 for x in posts if l1p > 0 and x >= competitive_frac * l1p
    )
    crowd = competitive >= 2 and len(posts) >= 2
    close = (l2p / l1p) >= close_ratio if l1p > 1e-12 else False
    rank_ok = int(l1_rank) <= int(rank_max)
    triggered = bool(rank_ok and (crowd or close))
    return {
        "triggered": triggered,
        "l1_rank": int(l1_rank),
        "rank_ok": rank_ok,
        "crowd": crowd,
        "leaf_close": close,
        "leaf_top2_ratio": (l2p / l1p) if l1p > 1e-12 else 0.0,
        "n_competitive_leaves": competitive,
        "keep_n": 2 if triggered else 1,
    }


def top_leaf_gated_hybrid_l1(
    tree_state: Mapping[str, Any],
    *,
    rank_max: int = GATED_L1_RANK_MAX,
    close_ratio: float = GATED_LEAF_CLOSE_RATIO,
    max_pool: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hybrid pool: top2 only on gated L1s; top1 elsewhere; sort by posterior.

    Gate (research candidate from ox_multi_gold_l1_rank_gate):
    ``l1_rank <= rank_max AND (crowd OR leaf2/leaf1 >= close_ratio)``.
    """
    axes = _l1_leaf_mass_axes(tree_state)
    selected: list[dict[str, Any]] = []
    n_expand = 0
    n_axes = 0
    expand_ids: list[str] = []
    for ax in axes:
        leaves = list(ax.get("leaves") or [])
        if not leaves:
            continue
        n_axes += 1
        # local label dedup before keep_n
        uniq: list[dict[str, Any]] = []
        seen_local: set[str] = set()
        for row in leaves:
            key = str(row.get("label") or "").strip().casefold()
            if not key or key in seen_local:
                continue
            seen_local.add(key)
            uniq.append(dict(row))
        gate = l1_family_expand_gate(
            uniq,
            l1_rank=int(ax["rank"]),
            rank_max=rank_max,
            close_ratio=close_ratio,
        )
        keep_n = int(gate["keep_n"])
        if gate["triggered"]:
            n_expand += 1
            expand_ids.append(str(ax["id"]))
        selected.extend(uniq[:keep_n])

    selected.sort(key=lambda r: (-float(r["posterior"]), str(r["id"])))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in selected:
        key = str(row.get("label") or "").strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(row)
        if max_pool and len(out) >= int(max_pool):
            break
    meta = {
        "gate": "rank2_and_crowd_or_close",
        "rank_max": int(rank_max),
        "close_ratio": float(close_ratio),
        "n_l1_axes": n_axes,
        "n_l1_expanded": n_expand,
        "expanded_l1_ids": expand_ids,
        "pool_len": len(out),
    }
    return out, meta


def _label_keys(label: str) -> set[str]:
    lab = str(label or "").strip().casefold()
    return {lab} if lab else set()


def aggregate_p5_interpretation(
    p5_doc: Mapping[str, Any],
    pred_ddx: Sequence[Mapping[str, Any]],
    *,
    max_why: int = MAX_WHY,
) -> dict[str, list[str]]:
    """Aggregate P5 support/oppose why strings per predicted leaf label."""
    buckets: dict[str, list[str]] = {
        str(r["label"]): [] for r in pred_ddx if str(r.get("label") or "").strip()
    }
    label_norm = {k.casefold(): k for k in buckets}
    # Also index by candidate substring soft match later
    for rule in p5_doc.get("rules") or []:
        if not isinstance(rule, Mapping):
            continue
        for eff in rule.get("effects") or []:
            if not isinstance(eff, Mapping):
                continue
            effect = str(eff.get("effect") or "").strip().lower()
            if effect not in {"support", "oppose"}:
                continue
            why = str(eff.get("why") or "").strip()
            if not why:
                continue
            cand = str(eff.get("candidate") or "").strip()
            if not cand:
                continue
            cn = cand.casefold()
            target = label_norm.get(cn)
            if target is None:
                # soft: candidate contained in label or vice versa
                for ln, orig in label_norm.items():
                    if cn in ln or ln in cn:
                        target = orig
                        break
            if target is None:
                continue
            bucket = buckets[target]
            if why not in bucket:
                bucket.append(why)
            # trim later
    for lab in list(buckets):
        buckets[lab] = buckets[lab][:max_why]
    return buckets


def selected_fact_snippets(
    case_doc: Mapping[str, Any],
    fact_texts: Mapping[str, str],
    *,
    max_facts: int = 6,
) -> list[str]:
    ids = list((case_doc.get("l1") or {}).get("selected_fact_ids") or [])
    out: list[str] = []
    for fid in ids[:max_facts]:
        text = fact_texts.get(str(fid))
        if text:
            out.append(text)
    return out


DDX_SOURCE_POSTERIOR = "shared_trees_global_leaf_posterior_topk"
DDX_SOURCE_COMPAT = "compat_parallel_final_ranking"
DDX_SOURCE_COMPAT_THEN_PAD = "compat_then_pad_posterior"
DDX_SOURCE_GATE_ON_POST = "compat_gate_on_posterior_pool"
DDX_SOURCE_CALIB_ONLY_POST = "calib_only_on_posterior_topk"
# OX-oriented: expand per-L1 top2 → decoupled compat_parallel → compress to K
DDX_SOURCE_L1_TOP2_COMPAT = "l1_top2_compat_then_compress"
# Selective: gated hybrid top2 (± decoupled compat) → compress to K
DDX_SOURCE_GATED_HYBRID = "gated_hybrid_top2_compress"
DDX_SOURCE_GATED_HYBRID_COMPAT = "gated_hybrid_top2_compat_then_compress"
# MCR R3 dialect compat_parallel; input = gated hybrid top2 (not posterior Top-K)
DDX_SOURCE_GATED_HYBRID_MCR = "gated_hybrid_top2_mcr_compat"
DDX_SOURCE_POST_N_MCR = "posterior_n_mcr_compat"
DEFAULT_POST_N_MCR_POOL = 7
# OX←MAC transfer arms
DDX_SOURCE_MULTI_ARM_RRF = "multi_arm_rrf"
DDX_SOURCE_CLOSED_POOL_RRF = "closed_pool_views_rrf"
DDX_SOURCE_CLOSED_MAC_TRACE_RRF = "closed_mac_trace_rrf"
DDX_SOURCE_CLOSED_LIVE_MAC = "closed_live_mac_supervisor"
DDX_SOURCE_TREE_MAC_PAD = "tree_mac_pad"
DDX_SOURCE_TREE_MAC_PAD_SELECTIVE = "tree_mac_pad_selective"
DEFAULT_CLOSED_POOL_N = 12
DEFAULT_LIVE_CLOSED_POOL_N = 15
DEFAULT_MAC_PAD_N = 2
DEFAULT_CLOSED_MATCH_THR = 0.7

ALL_DDX_SOURCES = (
    DDX_SOURCE_POSTERIOR,
    DDX_SOURCE_COMPAT,
    DDX_SOURCE_COMPAT_THEN_PAD,
    DDX_SOURCE_GATE_ON_POST,
    DDX_SOURCE_CALIB_ONLY_POST,
    DDX_SOURCE_L1_TOP2_COMPAT,
    DDX_SOURCE_GATED_HYBRID,
    DDX_SOURCE_GATED_HYBRID_COMPAT,
    DDX_SOURCE_GATED_HYBRID_MCR,
    DDX_SOURCE_POST_N_MCR,
    DDX_SOURCE_MULTI_ARM_RRF,
    DDX_SOURCE_CLOSED_POOL_RRF,
    DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
    DDX_SOURCE_CLOSED_LIVE_MAC,
    DDX_SOURCE_TREE_MAC_PAD,
    DDX_SOURCE_TREE_MAC_PAD_SELECTIVE,
)


def normalize_ddx_source(ddx_source: str) -> str:
    src = str(ddx_source or DDX_SOURCE_POSTERIOR).strip()
    aliases = {
        "posterior": DDX_SOURCE_POSTERIOR,
        "compat": DDX_SOURCE_COMPAT,
        "compat_final_ranking": DDX_SOURCE_COMPAT,
        "final_ranking": DDX_SOURCE_COMPAT,
        "compat_then_pad": DDX_SOURCE_COMPAT_THEN_PAD,
        "gate_on_post": DDX_SOURCE_GATE_ON_POST,
        "calib_only_post": DDX_SOURCE_CALIB_ONLY_POST,
        "l1_top2_compat": DDX_SOURCE_L1_TOP2_COMPAT,
        "l1_top2": DDX_SOURCE_L1_TOP2_COMPAT,
        "per_l1_top2_compat": DDX_SOURCE_L1_TOP2_COMPAT,
        "gated_hybrid": DDX_SOURCE_GATED_HYBRID,
        "gated_hybrid_top2": DDX_SOURCE_GATED_HYBRID,
        "gated_top2": DDX_SOURCE_GATED_HYBRID,
        "gated_hybrid_compat": DDX_SOURCE_GATED_HYBRID_COMPAT,
        "gated_hybrid_top2_compat": DDX_SOURCE_GATED_HYBRID_COMPAT,
        "gated_top2_compat": DDX_SOURCE_GATED_HYBRID_COMPAT,
        "gated_hybrid_mcr": DDX_SOURCE_GATED_HYBRID_MCR,
        "gated_hybrid_mcr_compat": DDX_SOURCE_GATED_HYBRID_MCR,
        "gated_top2_mcr": DDX_SOURCE_GATED_HYBRID_MCR,
        "post_n_mcr": DDX_SOURCE_POST_N_MCR,
        "posterior_n_mcr": DDX_SOURCE_POST_N_MCR,
        "post7_mcr": DDX_SOURCE_POST_N_MCR,
        "posterior_n7_mcr": DDX_SOURCE_POST_N_MCR,
        "multi_arm_rrf": DDX_SOURCE_MULTI_ARM_RRF,
        "tree_rrf": DDX_SOURCE_MULTI_ARM_RRF,
        "closed_pool_rrf": DDX_SOURCE_CLOSED_POOL_RRF,
        "closed_pool_views_rrf": DDX_SOURCE_CLOSED_POOL_RRF,
        "closed_mac_trace_rrf": DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
        "closed_mac_rrf": DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
        "mac_supervisor_on_pool": DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
        "closed_live_mac_supervisor": DDX_SOURCE_CLOSED_LIVE_MAC,
        "closed_live_mac": DDX_SOURCE_CLOSED_LIVE_MAC,
        "live_closed_mac": DDX_SOURCE_CLOSED_LIVE_MAC,
        "tree_mac_pad": DDX_SOURCE_TREE_MAC_PAD,
        "mac_pad": DDX_SOURCE_TREE_MAC_PAD,
        "tree_mac_pad_selective": DDX_SOURCE_TREE_MAC_PAD_SELECTIVE,
        "mac_pad_selective": DDX_SOURCE_TREE_MAC_PAD_SELECTIVE,
    }
    return aliases.get(src, src)


def ddx_from_compat_ranking(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    pad_posterior: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Use l2.final_ranking after compat_parallel (label-dedup, cap K).

    Default ``pad_posterior=False`` preserves the delivered short list (Block-2
    candidate-count / any-hit / open-MRR require this). Pass True only via
    ``compat_then_pad`` / ``ddx_compat_then_pad``. Padded rows carry
    ``fill_source="posterior_pad"``; Top-1 stays the arbiter winner when pad
    is on.
    """
    ranking = list((case_doc.get("l2") or {}).get("final_ranking_labels") or [])
    branches = tree_state.get("branches") or {}
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranking:
        if not isinstance(row, Mapping):
            continue
        lab = str(row.get("label") or "").strip()
        lid = str(row.get("id") or "").strip()
        if not lab:
            continue
        key = lab.casefold()
        if key in seen:
            continue
        seen.add(key)
        post = float((branches.get(lid) or {}).get("posterior") or 0.0)
        out.append({
            "id": lid,
            "label": lab,
            "posterior": post,
            "parent_id": str(row.get("parent") or ""),
            "rank": int(row.get("rank") or (len(out) + 1)),
            "fill_source": "arbiter",
        })
        if len(out) >= k:
            break
    meta: dict[str, Any] = {
        "compat_len_raw": len(out),
        "n_padded": 0,
        "pad_posterior": bool(pad_posterior),
        "fallback": None,
    }
    if not out:
        post = top_leaf_posterior(tree_state, k=k)
        for i, row in enumerate(post, start=1):
            item = dict(row)
            item["rank"] = i
            item["fill_source"] = "posterior_fallback"
            out.append(item)
        meta["fallback"] = "empty_compat"
        return out[:k], meta
    if pad_posterior and len(out) < k:
        before = len(out)
        post = top_leaf_posterior(tree_state, k=max(k * 3, k))
        for row in post:
            lab = str(row.get("label") or "").strip()
            if not lab:
                continue
            key = lab.casefold()
            if key in seen:
                continue
            seen.add(key)
            item = dict(row)
            item["label"] = lab
            item["rank"] = len(out) + 1
            item["fill_source"] = "posterior_pad"
            out.append(item)
            if len(out) >= k:
                break
        meta["n_padded"] = len(out) - before
    return out[:k], meta


def _as_ranking_rows(pred_ddx: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(pred_ddx, start=1):
        out.append({
            "id": str(row.get("id") or ""),
            "label": str(row.get("label") or ""),
            "parent": str(row.get("parent_id") or row.get("parent") or ""),
            "rank": int(row.get("rank") or i),
        })
    return out


def _dedup_pad_to_k(
    primary: Sequence[Mapping[str, Any]],
    filler: Sequence[Mapping[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    """Keep primary order, append filler by order until K (label-dedup)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in (primary, filler):
        for row in src:
            lab = str(row.get("label") or "").strip()
            if not lab:
                continue
            key = lab.casefold()
            if key in seen:
                continue
            seen.add(key)
            item = dict(row)
            item["label"] = lab
            item["rank"] = len(out) + 1
            out.append(item)
            if len(out) >= k:
                return out
    return out


def ddx_compat_then_pad(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """R2: compat order first, pad with global posterior to K (alias of S1 pad)."""
    return ddx_from_compat_ranking(case_doc, tree_state, k=k, pad_posterior=True)


def _findings_from_texts(fact_texts: Mapping[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for fid, text in fact_texts.items():
        t = str(text or "").strip()
        if t:
            out.append({"id": str(fid), "text": t})
    return out


def _make_calib_cache(cache_path: Path | None, *, dry: bool) -> Any:
    """Disk-cached LLM for TopKCalibration; dry/None → no live calls."""
    if dry or cache_path is None:
        return None
    import baseline_common as bc
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    return bc.SimpleCachedLLM(RobustLLMClient(), cache_path, "gemini-2.5-flash")


def ddx_gate_on_posterior_pool(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """R3: FineCrowdGate on posterior Top-K; merge pads back to K; else calib."""
    pool = top_leaf_posterior(tree_state, k=k)
    return ddx_mcr_compat_parallel_on_pool(
        case_doc,
        pool,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )


def ddx_mcr_compat_parallel_on_pool(
    case_doc: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """MCR R3-style compat_parallel on an arbitrary posterior-sorted pool.

    Differs from ``run_compat_parallel`` / ``_compat_rerank_pool_then_compress``:
    - merge branch pads back to K (not leave short reps only)
    - calib uses ``preserve_full_top2_when_no_gold=True``
    - calib ``k`` is the final short-list K (MCR R3), not ``len(pool)``
    """
    import merge_calib_compat as mcc
    import topk_calibration as calib

    pool_list = [dict(r) for r in pool]
    meta: dict[str, Any] = {
        "compat_dialect": "mcr_r3",
        "pool_len": len(pool_list),
        "gate_triggered": False,
        "branch": None,
        "calib_mode": None,
        "preserve_full_top2_when_no_gold": True,
    }
    if not pool_list:
        meta["fallback"] = "empty_pool"
        return [], meta

    ranking = _as_ranking_rows(pool_list)
    gate = mcc.fine_crowd_gate(ranking)
    meta["gate_triggered"] = bool(gate.get("triggered"))
    if gate.get("triggered"):
        merge_info = gate["merge_info"]
        reps = mcc._rep_labels_from_merge(ranking, merge_info)
        rep_ddx = []
        by_id = {str(r.get("id")): r for r in pool_list}
        for i, row in enumerate(reps, start=1):
            lid = str(row.get("id") or "")
            src = by_id.get(lid) or {
                "id": lid,
                "label": str(row.get("label") or ""),
                "posterior": 0.0,
                "parent_id": str(row.get("parent") or ""),
            }
            item = dict(src)
            item["rank"] = i
            rep_ddx.append(item)
        out = _dedup_pad_to_k(rep_ddx, pool_list, k=k)
        meta["branch"] = "merge_only_pad"
        meta["n_reps_before_pad"] = len(rep_ddx)
        meta["n_after_compress"] = len(out)
        return out, meta

    case_for = {
        **dict(case_doc),
        "l2": {
            **(case_doc.get("l2") or {}),
            "final_ranking_labels": ranking,
            "final_ranking_ids": [r["id"] for r in ranking if r.get("id")],
        },
    }
    live = (not dry_calib) and calib_cache is not None
    result = calib.calibrate_case(
        case=case_for,
        vignette=str(vignette or case_doc.get("case_text") or ""),
        findings=list(findings),
        gold_leaf_ids=[],
        arm="both_l1fallback",
        cache=calib_cache if live else None,
        k=k,
        dry_run=not live,
        preserve_full_top2_when_no_gold=True,
    )
    by_id = {str(r.get("id")): r for r in pool_list}
    ordered: list[dict[str, Any]] = []
    for i, lid in enumerate(result.get("ordered_ids") or [], start=1):
        src = by_id.get(str(lid))
        if not src:
            continue
        item = dict(src)
        item["rank"] = i
        ordered.append(item)
        if len(ordered) >= k:
            break
    if not ordered:
        ordered = list(pool_list)
    # If calib returned <K (or pool longer), pad from original pool order.
    out = _dedup_pad_to_k(ordered[:k], pool_list, k=k)
    meta["branch"] = "calib_only"
    meta["calib_mode"] = "live_both_l1fallback" if live else "dry_both_l1fallback"
    meta["calib_swapped"] = bool(result.get("swapped"))
    meta["n_after_compress"] = len(out)
    return out, meta


def ddx_calib_only_on_posterior(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """R4: force calib on posterior Top-K (no merge)."""
    import topk_calibration as calib

    pool = top_leaf_posterior(tree_state, k=k)
    ranking = _as_ranking_rows(pool)
    case_for = {
        **dict(case_doc),
        "l2": {
            **(case_doc.get("l2") or {}),
            "final_ranking_labels": ranking,
            "final_ranking_ids": [r["id"] for r in ranking if r.get("id")],
        },
    }
    live = (not dry_calib) and calib_cache is not None
    result = calib.calibrate_case(
        case=case_for,
        vignette=str(vignette or case_doc.get("case_text") or ""),
        findings=list(findings),
        gold_leaf_ids=[],
        arm="both_l1fallback",
        cache=calib_cache if live else None,
        k=k,
        dry_run=not live,
        preserve_full_top2_when_no_gold=True,
    )
    by_id = {str(r.get("id")): r for r in pool}
    ordered: list[dict[str, Any]] = []
    for i, lid in enumerate(result.get("ordered_ids") or [], start=1):
        src = by_id.get(str(lid))
        if not src:
            continue
        item = dict(src)
        item["rank"] = i
        ordered.append(item)
        if len(ordered) >= k:
            break
    meta = {
        "branch": "calib_only",
        "calib_mode": "live_both_l1fallback" if live else "dry_both_l1fallback",
        "gate_triggered": False,
        "calib_swapped": bool(result.get("swapped")),
    }
    return (ordered[:k] if ordered else list(pool)), meta


def _compat_rerank_pool_then_compress(
    case_doc: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
    *,
    k: int,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Decoupled compat_parallel on ``pool`` (k≥|pool|), then compress/pad to K."""
    import merge_calib_compat as mcc

    meta: dict[str, Any] = {
        "pool_len": len(pool),
        "branch": None,
        "calib_mode": None,
        "fallback": None,
    }
    if not pool:
        meta["fallback"] = "empty_pool"
        return [], meta

    ranking = _as_ranking_rows(pool)
    live = (not dry_calib) and calib_cache is not None
    routed = mcc.run_compat_parallel(
        case=case_doc,
        ranking_labels=ranking,
        vignette=str(vignette or case_doc.get("case_text") or ""),
        findings=list(findings),
        option_maps=None,
        gold_leaf_ids=[],
        cache=calib_cache if live else None,
        dry_run=not live,
        k=max(int(k), len(ranking)),
    )
    by_id = {str(r.get("id")): r for r in pool}
    primary: list[dict[str, Any]] = []
    for i, lid in enumerate(routed.get("ordered_ids") or [], start=1):
        src = by_id.get(str(lid))
        if not src:
            for row in routed.get("ranking_labels") or ():
                if str(row.get("id") or "") == str(lid):
                    src = {
                        "id": str(lid),
                        "label": str(row.get("label") or ""),
                        "posterior": float(
                            by_id.get(str(lid), {}).get("posterior") or 0.0
                        ),
                        "parent_id": str(row.get("parent") or ""),
                    }
                    break
        if not src:
            continue
        item = dict(src)
        item["rank"] = i
        primary.append(item)

    out = _dedup_pad_to_k(primary, pool, k=k)
    meta["branch"] = routed.get("branch")
    meta["compat_mode"] = routed.get("mode")
    meta["gate_triggered"] = bool((routed.get("gate") or {}).get("triggered"))
    meta["n_after_compat"] = len(primary)
    meta["n_after_compress"] = len(out)
    meta["calib_mode"] = (
        "live_both_l1fallback" if live else "dry_both_l1fallback"
    )
    if (routed.get("calib") or {}).get("swapped") is not None:
        meta["calib_swapped"] = bool((routed.get("calib") or {}).get("swapped"))
    return out, meta


def ddx_l1_top2_compat_then_compress(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    per_l1: int = DEFAULT_PER_L1_TOP,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expand per-L1 top-N → decoupled compat_parallel rerank → compress to K.

    Unlike annotate (compat on an already-short joint list) and unlike
    ``gate_on_post`` (compat on global posterior Top-K), this keeps diversity
    across L1 families first, reranks the **expanded** pool, then truncates.
    If compat shrinks below K, pad from the pre-compat pool by posterior.
    """
    pool = top_leaf_per_l1_posterior(tree_state, per_l1=per_l1)
    meta: dict[str, Any] = {
        "per_l1": int(per_l1),
        "pool_len": len(pool),
        "branch": None,
        "calib_mode": None,
        "fallback": None,
    }
    if not pool:
        meta["fallback"] = "empty_l1_pool"
        return top_leaf_posterior(tree_state, k=k), meta

    out, cmeta = _compat_rerank_pool_then_compress(
        case_doc,
        pool,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    meta.update(cmeta)
    if not out:
        meta["fallback"] = "empty_after_compat"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def ddx_gated_hybrid_top2_compress(
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gated hybrid top2 pool → compress to K (no compat rerank)."""
    pool, gmeta = top_leaf_gated_hybrid_l1(tree_state)
    meta = dict(gmeta)
    meta["compat"] = False
    if not pool:
        meta["fallback"] = "empty_gated_pool"
        return top_leaf_posterior(tree_state, k=k), meta
    out = _dedup_pad_to_k(pool, pool, k=k)
    meta["n_after_compress"] = len(out)
    return out, meta


def ddx_gated_hybrid_top2_compat_then_compress(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gated hybrid top2 → decoupled compat_parallel → compress to K."""
    pool, gmeta = top_leaf_gated_hybrid_l1(tree_state)
    meta = dict(gmeta)
    meta["compat"] = True
    if not pool:
        meta["fallback"] = "empty_gated_pool"
        return top_leaf_posterior(tree_state, k=k), meta

    out, cmeta = _compat_rerank_pool_then_compress(
        case_doc,
        pool,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    meta = {**gmeta, **cmeta, "compat": True, "pool_len": len(pool)}
    if not out:
        meta["fallback"] = "empty_after_compat"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def ddx_gated_hybrid_top2_mcr_compat(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """MCR R3 compat_parallel with input = gated hybrid top2 (posterior-sorted)."""
    pool, gmeta = top_leaf_gated_hybrid_l1(tree_state)
    if not pool:
        meta = dict(gmeta)
        meta["fallback"] = "empty_gated_pool"
        meta["compat_dialect"] = "mcr_r3"
        return top_leaf_posterior(tree_state, k=k), meta
    out, cmeta = ddx_mcr_compat_parallel_on_pool(
        case_doc,
        pool,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    meta = {**gmeta, **cmeta, "compat": True, "pool_len": len(pool)}
    if not out:
        meta["fallback"] = "empty_after_mcr_compat"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def ddx_posterior_n_mcr_compat(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Posterior Top-N pool → MCR R3 compat → truncate/pad to final K."""
    n = max(int(pool_n), int(k))
    pool = top_leaf_posterior(tree_state, k=n)
    out, cmeta = ddx_mcr_compat_parallel_on_pool(
        case_doc,
        pool,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    meta = {
        **cmeta,
        "compat": True,
        "pool_n": n,
        "pool_len": len(pool),
    }
    if not out:
        meta["fallback"] = "empty_after_mcr_compat"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def _labels_of(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(r.get("label") or "").strip() for r in rows if str(r.get("label") or "").strip()]


def _rows_from_labels(
    labels: Sequence[str],
    catalogue: Sequence[Mapping[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for r in catalogue:
        lab = str(r.get("label") or "").strip()
        if not lab:
            continue
        key = " ".join(lab.casefold().split()).replace("-", " ")
        by_key.setdefault(key, dict(r))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, lab in enumerate(labels, start=1):
        key = " ".join(str(lab).casefold().split()).replace("-", " ")
        if not key or key in seen:
            continue
        src = by_key.get(key)
        if src is None:
            item = {
                "id": "__open_%s__" % key[:32],
                "label": str(lab).strip(),
                "posterior": 1e-6,
                "parent_id": "",
            }
        else:
            item = dict(src)
        item["rank"] = i
        out.append(item)
        seen.add(key)
        if len(out) >= k:
            break
    return out


def ddx_multi_arm_rrf(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """C3: RRF over posterior / compat_then_pad / gated_hybrid_mcr / post7_mcr."""
    import baseline_aggregate as bagg

    post = top_leaf_posterior(tree_state, k=k)
    ctp, _ = ddx_compat_then_pad(case_doc, tree_state, k=k)
    gh, _ = ddx_gated_hybrid_top2_mcr_compat(
        case_doc,
        tree_state,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    p7, _ = ddx_posterior_n_mcr_compat(
        case_doc,
        tree_state,
        k=k,
        pool_n=pool_n,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    lists = [_labels_of(post), _labels_of(ctp), _labels_of(gh), _labels_of(p7)]
    fused = bagg.rrf_aggregate(lists, top_n=k)
    catalogue = post + ctp + gh + p7
    out = _rows_from_labels(fused, catalogue, k=k)
    meta = {
        "compat_dialect": "multi_arm_rrf",
        "n_lists": len(lists),
        "list_lens": [len(x) for x in lists],
        "fused": fused,
    }
    if not out:
        meta["fallback"] = "empty_rrf"
        return post, meta
    return out, meta


def ddx_closed_pool_views_rrf(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    pool_n: int = DEFAULT_CLOSED_POOL_N,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """C1 cheap proxy: RRF of multiple orderings restricted to posterior Top-N pool."""
    import baseline_aggregate as bagg

    n = max(int(pool_n), int(k))
    pool = top_leaf_posterior(tree_state, k=n)
    pool_labs = _labels_of(pool)
    pool_keys = {
        " ".join(x.casefold().split()).replace("-", " ") for x in pool_labs
    }

    def _restrict(labels: Sequence[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for lab in labels:
            key = " ".join(str(lab).casefold().split()).replace("-", " ")
            if key in pool_keys and key not in seen:
                out.append(lab)
                seen.add(key)
        # pad from pool order
        for lab in pool_labs:
            key = " ".join(lab.casefold().split()).replace("-", " ")
            if key not in seen:
                out.append(lab)
                seen.add(key)
            if len(out) >= n:
                break
        return out[:n]

    gh, _ = ddx_gated_hybrid_top2_mcr_compat(
        case_doc,
        tree_state,
        k=min(k, n),
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    ctp, _ = ddx_compat_then_pad(case_doc, tree_state, k=k)
    lists = [
        pool_labs,
        _restrict(_labels_of(gh)),
        _restrict(_labels_of(ctp)),
    ]
    fused = bagg.rrf_aggregate(lists, top_n=k)
    out = _rows_from_labels(fused, pool, k=k)
    meta = {
        "compat_dialect": "closed_pool_views_rrf",
        "pool_n": n,
        "pool_len": len(pool),
        "n_lists": len(lists),
        "fused": fused,
    }
    if not out:
        meta["fallback"] = "empty_closed_rrf"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def _map_names_to_pool(
    names: Sequence[str],
    pool_labs: Sequence[str],
    *,
    thr: float = DEFAULT_CLOSED_MATCH_THR,
) -> list[str]:
    """Greedy map free-form names onto closed pool labels (lexical thr)."""
    from mapper_bind_repair import leaf_match_score

    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        best_lab = ""
        best = -1.0
        for lab in pool_labs:
            sc = float(leaf_match_score(str(name), str(lab)))
            if sc > best:
                best = sc
                best_lab = str(lab)
        if best < float(thr) or not best_lab:
            continue
        key = " ".join(best_lab.casefold().split()).replace("-", " ")
        if key in seen:
            continue
        out.append(best_lab)
        seen.add(key)
    return out


def ddx_closed_mac_trace_rrf(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    pool_n: int = DEFAULT_CLOSED_POOL_N,
    mac_doctor_lists: Sequence[Sequence[str]] = (),
    match_thr: float = DEFAULT_CLOSED_MATCH_THR,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """C1 offline: map MAC doctor Top-5 onto posterior pool, then RRF→K."""
    import baseline_aggregate as bagg

    n = max(int(pool_n), int(k))
    pool = top_leaf_posterior(tree_state, k=n)
    pool_labs = _labels_of(pool)
    lists: list[list[str]] = []
    mapped_meta: list[dict[str, Any]] = []
    for ranked in mac_doctor_lists:
        mapped = _map_names_to_pool(list(ranked or []), pool_labs, thr=match_thr)
        # pad with pool order so RRF always has pool coverage
        seen = {
            " ".join(x.casefold().split()).replace("-", " ") for x in mapped
        }
        for lab in pool_labs:
            key = " ".join(lab.casefold().split()).replace("-", " ")
            if key not in seen:
                mapped.append(lab)
                seen.add(key)
            if len(mapped) >= n:
                break
        lists.append(mapped[:n])
        mapped_meta.append({
            "n_in": len(list(ranked or [])),
            "n_mapped": len(_map_names_to_pool(list(ranked or []), pool_labs, thr=match_thr)),
        })
    if len(lists) < 2:
        # fallback to closed pool views when MAC discussion missing
        return ddx_closed_pool_views_rrf(
            case_doc,
            tree_state,
            k=k,
            pool_n=n,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
    fused = bagg.rrf_aggregate(lists, top_n=k)
    out = _rows_from_labels(fused, pool, k=k)
    meta = {
        "compat_dialect": "closed_mac_trace_rrf",
        "pool_n": n,
        "n_doctor_lists": len(lists),
        "mapped": mapped_meta,
        "match_thr": float(match_thr),
        "fused": fused,
    }
    if not out:
        meta["fallback"] = "empty_closed_mac_rrf"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


CLOSED_LIVE_MAC_DOCTOR = """You are __DOCTOR_NAME__, a medical expert on a CLOSED differential panel.
Analyze the vignette and prior discussion. You MUST rank ONLY diseases from
candidate_pool, copying each label EXACTLY as written (no paraphrases).
Return exactly Top-__K__ pool labels, best first.
Return JSON only:
{"ranked_diagnoses":["exact pool label",...],
 "commentary":"brief engagement with prior opinions"}
"""

CLOSED_LIVE_MAC_SUPERVISOR = """You are the Medical Supervisor for a CLOSED differential panel.
Review doctors' ranked lists and finalize an ordered Top-__K__.
You MUST choose ONLY from candidate_pool using exact label strings.
Return JSON only:
{"ordered_diagnoses":[{"diagnosis":"exact pool label","reasoning_summary":"..."}, ...]}
"""


def _project_closed_names(
    names: Sequence[str],
    pool_labs: Sequence[str],
    *,
    k: int,
    thr: float = DEFAULT_CLOSED_MATCH_THR,
) -> list[str]:
    mapped = _map_names_to_pool(names, pool_labs, thr=thr)
    seen = {" ".join(x.casefold().split()).replace("-", " ") for x in mapped}
    out = list(mapped)
    for lab in pool_labs:
        key = " ".join(lab.casefold().split()).replace("-", " ")
        if key in seen:
            continue
        out.append(lab)
        seen.add(key)
        if len(out) >= k:
            break
    return out[:k]


def ddx_closed_live_mac_supervisor(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    pool_n: int = DEFAULT_LIVE_CLOSED_POOL_N,
    vignette: str = "",
    closed_mac_cache: Any = None,
    match_thr: float = DEFAULT_CLOSED_MATCH_THR,
    dry_calib: bool = True,
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fair C1: live 3-doctor + supervisor restricted to posterior Top-N pool."""
    import baseline_aggregate as bagg
    import baseline_arms as barms
    import baseline_common as bc

    n = max(int(pool_n), int(k), DEFAULT_LIVE_CLOSED_POOL_N)
    # honor explicit smaller pool if caller set pool_n > default post7
    if int(pool_n) >= int(k):
        n = max(int(pool_n), int(k))
    pool = top_leaf_posterior(tree_state, k=n)
    pool_labs = _labels_of(pool)
    meta: dict[str, Any] = {
        "compat_dialect": "closed_live_mac_supervisor",
        "pool_n": n,
        "pool_len": len(pool_labs),
    }
    if closed_mac_cache is None:
        # dry / no client: cheap closed RRF proxy (not a fair live score)
        pred, fmeta = ddx_closed_pool_views_rrf(
            case_doc,
            tree_state,
            k=k,
            pool_n=n,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        meta.update(fmeta)
        meta["fallback"] = "dry_closed_pool_views_rrf"
        meta["live"] = False
        return pred, meta

    case_payload = {
        "vignette": vignette or str(case_doc.get("case_text") or ""),
        "candidate_pool": pool_labs,
        "list_k": int(k),
    }
    history: list[dict[str, Any]] = []
    doctor_lists: list[list[str]] = []
    for index, doctor_name in enumerate(
        ("Doctor A", "Doctor B", "Doctor C"), start=1
    ):
        prompt = (
            CLOSED_LIVE_MAC_DOCTOR.replace("__DOCTOR_NAME__", doctor_name)
            .replace("__K__", str(k))
        )
        raw = closed_mac_cache.call(
            "PaperClosedMACDoctor_%d" % index,
            prompt,
            {
                **case_payload,
                "doctor_name": doctor_name,
                "discussion_history": history,
            },
        )
        ranked = barms._names_from_any(raw, k=max(5, k))
        if len(ranked) < 2:
            ranked = bc.clean_topk_from_response(raw, k=max(5, k))
        projected = _project_closed_names(
            ranked, pool_labs, k=k, thr=match_thr
        )
        doctor_lists.append(projected)
        history.append({
            "speaker": doctor_name,
            "ranked_diagnoses": projected,
            "commentary": (
                raw.get("commentary") if isinstance(raw, Mapping) else None
            ),
        })

    sup_prompt = CLOSED_LIVE_MAC_SUPERVISOR.replace("__K__", str(k))
    supervisor = closed_mac_cache.call(
        "PaperClosedMACSupervisor",
        barms._adapt_prompt_for_k(sup_prompt, k),
        {**case_payload, "discussion_history": history},
    )
    top = bc.clean_topk_from_response(supervisor, k=k)
    if not top or not top[0]:
        top = barms._names_from_any(supervisor, k=k)
    fused = _project_closed_names(top, pool_labs, k=k, thr=match_thr)
    if not fused or not fused[0]:
        fused = bagg.rrf_aggregate(doctor_lists, top_n=k)
        fused = _project_closed_names(fused, pool_labs, k=k, thr=match_thr)
        meta["supervisor_fallback"] = "rrf_doctors"
    out = _rows_from_labels(fused, pool, k=k)
    meta.update({
        "live": True,
        "n_doctor_lists": len(doctor_lists),
        "doctor_lists": doctor_lists,
        "fused": fused,
        "match_thr": float(match_thr),
    })
    if not out:
        meta["fallback"] = "empty_live_closed_mac"
        return top_leaf_posterior(tree_state, k=k), meta
    return out, meta


def ddx_tree_mac_pad(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    mac_labels: Sequence[str] = (),
    pad_n: int = DEFAULT_MAC_PAD_N,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """C2: gated_hybrid_mcr shortlist, replace trailing slots with MAC open names."""
    base, gmeta = ddx_gated_hybrid_top2_mcr_compat(
        case_doc,
        tree_state,
        k=k,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    base_labs = _labels_of(base)
    base_keys = {
        " ".join(x.casefold().split()).replace("-", " ") for x in base_labs
    }
    extras: list[str] = []
    for lab in mac_labels:
        key = " ".join(str(lab).casefold().split()).replace("-", " ")
        if not key or key in base_keys:
            continue
        extras.append(str(lab).strip())
        base_keys.add(key)
        if len(extras) >= int(pad_n):
            break
    keep = max(0, k - len(extras))
    kept = list(base[:keep])
    out = list(kept)
    seen = {
        " ".join(str(x.get("label") or "").casefold().split()).replace("-", " ")
        for x in out
    }
    for i, lab in enumerate(extras):
        out.append({
            "id": "__mac_pad_%d__" % i,
            "label": lab,
            "posterior": 1e-6,
            "parent_id": "",
            "rank": len(out) + 1,
            "mac_pad": True,
        })
        seen.add(" ".join(lab.casefold().split()).replace("-", " "))
    for r in base:
        if len(out) >= k:
            break
        key = " ".join(str(r.get("label") or "").casefold().split()).replace("-", " ")
        if key in seen:
            continue
        item = dict(r)
        item["rank"] = len(out) + 1
        out.append(item)
        seen.add(key)
    meta = {
        **gmeta,
        "compat_dialect": "tree_mac_pad",
        "n_mac_padded": len(extras),
        "mac_padded": extras,
        "pad_n": int(pad_n),
        "n_mac_candidates": len(list(mac_labels or [])),
    }
    return out[:k], meta


def ddx_tree_mac_pad_selective(
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    *,
    k: int = DEFAULT_DDX_K,
    mac_labels: Sequence[str] = (),
    pad_n: int = DEFAULT_MAC_PAD_N,
    match_thr: float = DEFAULT_CLOSED_MATCH_THR,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """C2 selective: pad only MAC names that do not match any full-tree leaf."""
    leaves = [
        str(r.get("label") or "")
        for r in _scored_leaves(tree_state)
        if str(r.get("label") or "").strip()
    ]
    open_only: list[str] = []
    skipped_in_tree = 0
    for lab in mac_labels:
        mapped = _map_names_to_pool([str(lab)], leaves, thr=match_thr)
        if mapped:
            skipped_in_tree += 1
            continue
        open_only.append(str(lab).strip())
    pred, meta = ddx_tree_mac_pad(
        case_doc,
        tree_state,
        k=k,
        mac_labels=open_only,
        pad_n=pad_n,
        dry_calib=dry_calib,
        vignette=vignette,
        findings=findings,
        calib_cache=calib_cache,
    )
    meta = {
        **meta,
        "compat_dialect": "tree_mac_pad_selective",
        "n_mac_open_only": len(open_only),
        "n_mac_skipped_in_tree": skipped_in_tree,
        "mac_open_candidates": open_only[:10],
    }
    return pred, meta


def resolve_pred_ddx(
    *,
    case_doc: Mapping[str, Any],
    tree_state: Mapping[str, Any],
    ddx_source: str,
    ddx_k: int,
    dry_calib: bool = True,
    vignette: str = "",
    findings: Sequence[Mapping[str, Any]] = (),
    calib_cache: Any = None,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
    mac_labels: Sequence[str] = (),
    mac_doctor_lists: Sequence[Sequence[str]] = (),
    closed_mac_cache: Any = None,
) -> tuple[list[dict[str, Any]], str, dict[str, Any], str]:
    """Return (pred_ddx, canonical_source, meta, rank_note_template)."""
    src = normalize_ddx_source(ddx_source)
    meta: dict[str, Any] = {}

    if src == DDX_SOURCE_COMPAT:
        # Must NOT pad: pad collapses Block-2 |cand| discrimination and pollutes
        # ordered endpoints (see mcr_val_seq100_v2 audit, 2026-07-31).
        pred, meta = ddx_from_compat_ranking(
            case_doc, tree_state, k=ddx_k, pad_posterior=False
        )
        if meta.get("fallback") == "empty_compat":
            note = "Rank note: empty compat ranking; fallback posterior Top-1 is %s."
            return pred, DDX_SOURCE_COMPAT, meta, note
        return pred, DDX_SOURCE_COMPAT, meta, (
            "Rank note: Top-1 by compat_parallel final_ranking is %s."
        )

    if src == DDX_SOURCE_COMPAT_THEN_PAD:
        pred, meta = ddx_from_compat_ranking(
            case_doc, tree_state, k=ddx_k, pad_posterior=True
        )
        return pred, DDX_SOURCE_COMPAT_THEN_PAD, meta, (
            "Rank note: Top-1 by compat_then_pad_posterior is %s."
        )

    if src == DDX_SOURCE_GATE_ON_POST:
        pred, meta = ddx_gate_on_posterior_pool(
            case_doc,
            tree_state,
            k=ddx_k,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_GATE_ON_POST, meta, (
            "Rank note: Top-1 by compat_gate_on_posterior_pool is %s."
        )

    if src == DDX_SOURCE_CALIB_ONLY_POST:
        pred, meta = ddx_calib_only_on_posterior(
            case_doc,
            tree_state,
            k=ddx_k,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_CALIB_ONLY_POST, meta, (
            "Rank note: Top-1 by calib_only_on_posterior_topk is %s."
        )

    if src == DDX_SOURCE_L1_TOP2_COMPAT:
        pred, meta = ddx_l1_top2_compat_then_compress(
            case_doc,
            tree_state,
            k=ddx_k,
            per_l1=DEFAULT_PER_L1_TOP,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_L1_TOP2_COMPAT, meta, (
            "Rank note: Top-1 by l1_top2_compat_then_compress is %s."
        )

    if src == DDX_SOURCE_GATED_HYBRID:
        pred, meta = ddx_gated_hybrid_top2_compress(tree_state, k=ddx_k)
        return pred, DDX_SOURCE_GATED_HYBRID, meta, (
            "Rank note: Top-1 by gated_hybrid_top2_compress is %s."
        )

    if src == DDX_SOURCE_GATED_HYBRID_COMPAT:
        pred, meta = ddx_gated_hybrid_top2_compat_then_compress(
            case_doc,
            tree_state,
            k=ddx_k,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_GATED_HYBRID_COMPAT, meta, (
            "Rank note: Top-1 by gated_hybrid_top2_compat_then_compress is %s."
        )

    if src == DDX_SOURCE_GATED_HYBRID_MCR:
        pred, meta = ddx_gated_hybrid_top2_mcr_compat(
            case_doc,
            tree_state,
            k=ddx_k,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_GATED_HYBRID_MCR, meta, (
            "Rank note: Top-1 by gated_hybrid_top2_mcr_compat is %s."
        )

    if src == DDX_SOURCE_POST_N_MCR:
        pred, meta = ddx_posterior_n_mcr_compat(
            case_doc,
            tree_state,
            k=ddx_k,
            pool_n=pool_n,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_POST_N_MCR, meta, (
            "Rank note: Top-1 by posterior_n_mcr_compat is %s."
        )

    if src == DDX_SOURCE_MULTI_ARM_RRF:
        pred, meta = ddx_multi_arm_rrf(
            case_doc,
            tree_state,
            k=ddx_k,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
            pool_n=pool_n,
        )
        return pred, DDX_SOURCE_MULTI_ARM_RRF, meta, (
            "Rank note: Top-1 by multi_arm_rrf is %s."
        )

    if src == DDX_SOURCE_CLOSED_POOL_RRF:
        pred, meta = ddx_closed_pool_views_rrf(
            case_doc,
            tree_state,
            k=ddx_k,
            pool_n=max(int(pool_n), DEFAULT_CLOSED_POOL_N)
            if int(pool_n) == DEFAULT_POST_N_MCR_POOL
            else int(pool_n),
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_CLOSED_POOL_RRF, meta, (
            "Rank note: Top-1 by closed_pool_views_rrf is %s."
        )

    if src == DDX_SOURCE_CLOSED_MAC_TRACE_RRF:
        pred, meta = ddx_closed_mac_trace_rrf(
            case_doc,
            tree_state,
            k=ddx_k,
            pool_n=max(int(pool_n), DEFAULT_CLOSED_POOL_N)
            if int(pool_n) == DEFAULT_POST_N_MCR_POOL
            else int(pool_n),
            mac_doctor_lists=mac_doctor_lists,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_CLOSED_MAC_TRACE_RRF, meta, (
            "Rank note: Top-1 by closed_mac_trace_rrf is %s."
        )

    if src == DDX_SOURCE_CLOSED_LIVE_MAC:
        live_pool = (
            DEFAULT_LIVE_CLOSED_POOL_N
            if int(pool_n) == DEFAULT_POST_N_MCR_POOL
            else max(int(pool_n), int(ddx_k))
        )
        pred, meta = ddx_closed_live_mac_supervisor(
            case_doc,
            tree_state,
            k=ddx_k,
            pool_n=live_pool,
            vignette=vignette,
            closed_mac_cache=closed_mac_cache,
            dry_calib=dry_calib,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_CLOSED_LIVE_MAC, meta, (
            "Rank note: Top-1 by closed_live_mac_supervisor is %s."
        )

    if src == DDX_SOURCE_TREE_MAC_PAD:
        pred, meta = ddx_tree_mac_pad(
            case_doc,
            tree_state,
            k=ddx_k,
            mac_labels=mac_labels,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_TREE_MAC_PAD, meta, (
            "Rank note: Top-1 by tree_mac_pad is %s."
        )

    if src == DDX_SOURCE_TREE_MAC_PAD_SELECTIVE:
        pred, meta = ddx_tree_mac_pad_selective(
            case_doc,
            tree_state,
            k=ddx_k,
            mac_labels=mac_labels,
            dry_calib=dry_calib,
            vignette=vignette,
            findings=findings,
            calib_cache=calib_cache,
        )
        return pred, DDX_SOURCE_TREE_MAC_PAD_SELECTIVE, meta, (
            "Rank note: Top-1 by tree_mac_pad_selective is %s."
        )

    pred = top_leaf_posterior(tree_state, k=ddx_k)
    return pred, DDX_SOURCE_POSTERIOR, meta, (
        "Rank note: Top-1 by global leaf posterior is %s."
    )


def build_reasoning_trace(
    *,
    observed: Sequence[str],
    pred_ddx: Sequence[Mapping[str, Any]],
    pred_interpretation: Mapping[str, Sequence[str]],
    axes: Sequence[str] = (),
    rank_note: str = "",
) -> str:
    """Deterministic template; must not include KB chunk bodies."""
    lines: list[str] = []
    lines.append("Observed:")
    if observed:
        for s in observed:
            lines.append("- %s" % s)
    else:
        lines.append("- (no selected facts)")
    if axes:
        lines.append("Axes:")
        for a in axes:
            lines.append("- %s" % a)
    lines.append("Differential diagnosis:")
    for i, row in enumerate(pred_ddx, 1):
        lab = str(row.get("label") or "")
        post = float(row.get("posterior") or 0.0)
        lines.append("%d. %s (posterior=%.4f)" % (i, lab, post))
        for why in pred_interpretation.get(lab) or []:
            lines.append("   - %s" % why)
    if pred_ddx:
        top = str(pred_ddx[0].get("label") or "")
        note = rank_note or (
            "Rank note: Top-1 by global leaf posterior is %s." % top
        )
        if "%s" in note:
            note = note % top
        lines.append(note)
    return "\n".join(lines)


def build_one_projection(
    *,
    case_id: str,
    tree_state: Mapping[str, Any],
    p5_doc: Mapping[str, Any],
    case_doc: Mapping[str, Any],
    fact_texts: Mapping[str, str],
    ddx_k: int = DEFAULT_DDX_K,
    ddx_source: str = DDX_SOURCE_POSTERIOR,
    dry_calib: bool = True,
    vignette: str = "",
    calib_cache: Any = None,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
    mac_labels: Sequence[str] = (),
    mac_doctor_lists: Sequence[Sequence[str]] = (),
    closed_mac_cache: Any = None,
) -> dict[str, Any]:
    ranking = list((case_doc.get("l2") or {}).get("final_ranking_labels") or [])
    findings = _findings_from_texts(fact_texts)
    pred_ddx, src, src_meta, rank_note = resolve_pred_ddx(
        case_doc=case_doc,
        tree_state=tree_state,
        ddx_source=ddx_source,
        ddx_k=ddx_k,
        dry_calib=dry_calib,
        vignette=vignette or str(case_doc.get("case_text") or ""),
        findings=findings,
        calib_cache=calib_cache,
        pool_n=pool_n,
        mac_labels=mac_labels,
        mac_doctor_lists=mac_doctor_lists,
        closed_mac_cache=closed_mac_cache,
    )

    pred_interp = aggregate_p5_interpretation(p5_doc, pred_ddx)
    # Optionally prepend short selected facts into each interp list (capped)
    observed = selected_fact_snippets(case_doc, fact_texts)
    for lab in list(pred_interp):
        # Keep why-only primary; attach up to 2 observed as context bullets
        extras = ["Observed: %s" % s for s in observed[:2]]
        merged = list(pred_interp[lab])
        for e in extras:
            if e not in merged and len(merged) < MAX_WHY:
                merged.append(e)
        pred_interp[lab] = merged[:MAX_WHY]

    # L1 axis labels if present
    axes: list[str] = []
    for row in (case_doc.get("l1") or {}).get("l1_posteriors") or []:
        if isinstance(row, Mapping):
            lab = str(row.get("label") or row.get("name") or "").strip()
            if lab and lab not in axes:
                axes.append(lab)

    trace = build_reasoning_trace(
        observed=observed,
        pred_ddx=pred_ddx,
        pred_interpretation=pred_interp,
        axes=axes[:8],
        rank_note=rank_note,
    )
    pred_diagnosis = str(pred_ddx[0]["label"]) if pred_ddx else ""
    gran = (case_doc.get("l2") or {}).get("granularity") or {}
    return {
        "case_id": str(case_id),
        "schema_version": 1,
        "pred_ddx": pred_ddx,
        "pred_interpretation": pred_interp,
        "pred_diagnosis": pred_diagnosis,
        "pred_reasoning_trace": trace,
        "sources": {
            "ddx_source": src,
            "ddx_k": int(ddx_k),
            "evidence": ["p5_audit.support_oppose_why", "l1.selected_fact_ids"],
            "final_ranking_len": len(ranking),
            "compat_path": gran.get("path"),
            "n_leaves_considered": len(leaves_from_tree_state(tree_state)),
            "policy_meta": src_meta,
            "fallback": src_meta.get("fallback"),
            "pool_n": src_meta.get("pool_n"),
        },
    }


def iter_case_ids(annotate_dir: Path, case_ids: Sequence[str] = ()) -> list[str]:
    if case_ids:
        return [str(x) for x in case_ids]
    tree_dir = annotate_dir / "shared_trees"
    ids = sorted(
        p.stem for p in tree_dir.glob("*.json") if p.is_file()
    )
    return ids


def _auto_proj_subdir(src: str) -> str:
    mapping = {
        DDX_SOURCE_POSTERIOR: "eval_projection",
        DDX_SOURCE_COMPAT: "eval_projection_compat",
        DDX_SOURCE_COMPAT_THEN_PAD: "eval_projection_compat_then_pad",
        DDX_SOURCE_GATE_ON_POST: "eval_projection_gate_on_post",
        DDX_SOURCE_CALIB_ONLY_POST: "eval_projection_calib_only_post",
        DDX_SOURCE_L1_TOP2_COMPAT: "eval_projection_l1_top2_compat",
        DDX_SOURCE_GATED_HYBRID: "eval_projection_gated_hybrid_top2",
        DDX_SOURCE_GATED_HYBRID_COMPAT: "eval_projection_gated_hybrid_top2_compat",
        DDX_SOURCE_GATED_HYBRID_MCR: "eval_projection_gated_hybrid_top2_mcr",
        DDX_SOURCE_POST_N_MCR: "eval_projection_post_n_mcr",
        DDX_SOURCE_MULTI_ARM_RRF: "eval_projection_multi_arm_rrf",
        DDX_SOURCE_CLOSED_POOL_RRF: "eval_projection_closed_pool_rrf",
        DDX_SOURCE_CLOSED_MAC_TRACE_RRF: "eval_projection_closed_mac_trace_rrf",
        DDX_SOURCE_CLOSED_LIVE_MAC: "eval_projection_closed_live_mac",
        DDX_SOURCE_TREE_MAC_PAD: "eval_projection_tree_mac_pad",
        DDX_SOURCE_TREE_MAC_PAD_SELECTIVE: "eval_projection_tree_mac_pad_selective",
    }
    return mapping.get(src, "eval_projection_%s" % src.replace("/", "_")[:48])


def build_eval_projections(
    run_dir: Path,
    *,
    ddx_k: int = DEFAULT_DDX_K,
    case_ids: Sequence[str] = (),
    resume: bool = False,
    ddx_source: str = DDX_SOURCE_POSTERIOR,
    out_subdir: str = "",
    dry_calib: bool = True,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
    mac_pred_by_cid: Mapping[str, Sequence[str]] | None = None,
    mac_doctors_by_cid: Mapping[str, Sequence[Sequence[str]]] | None = None,
    live_closed_mac: bool = False,
) -> dict[str, Any]:
    annotate = resolve_annotate_dir(run_dir)
    src = normalize_ddx_source(ddx_source)
    sub = out_subdir.strip().strip("/") if out_subdir else _auto_proj_subdir(src)
    if src == DDX_SOURCE_POST_N_MCR and not out_subdir:
        # Disambiguate common N=7 arm in dir names.
        if int(pool_n) == DEFAULT_POST_N_MCR_POOL:
            sub = "eval_projection_post7_mcr"
        else:
            sub = "eval_projection_post%d_mcr" % int(pool_n)
    out_dir = annotate / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = annotate / "finding_fixture_v1.json"
    fixtures = load_fixture_findings(fixture_path)
    vignette_by_id: dict[str, str] = {}
    nc_path = annotate / "normalized_cases.json"
    if nc_path.is_file():
        try:
            nc = _read_json(nc_path)
            for row in (nc.get("cases") or []) if isinstance(nc, Mapping) else []:
                if not isinstance(row, Mapping):
                    continue
                cid0 = str(row.get("id") or row.get("case_id") or "")
                if cid0:
                    vignette_by_id[cid0] = str(row.get("case_text") or "")
        except Exception:  # noqa: BLE001
            pass
    needs_calib = src in {
        DDX_SOURCE_GATE_ON_POST,
        DDX_SOURCE_CALIB_ONLY_POST,
        DDX_SOURCE_L1_TOP2_COMPAT,
        DDX_SOURCE_GATED_HYBRID_COMPAT,
        DDX_SOURCE_GATED_HYBRID_MCR,
        DDX_SOURCE_POST_N_MCR,
        DDX_SOURCE_MULTI_ARM_RRF,
        DDX_SOURCE_CLOSED_POOL_RRF,
        DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
        DDX_SOURCE_TREE_MAC_PAD,
        DDX_SOURCE_TREE_MAC_PAD_SELECTIVE,
    }
    calib_cache = None
    if needs_calib and not dry_calib:
        calib_cache = _make_calib_cache(
            annotate / "cache" / "open_acc_ablation_topk_calib.json",
            dry=False,
        )
    closed_mac_cache = None
    if src == DDX_SOURCE_CLOSED_LIVE_MAC and live_closed_mac:
        closed_mac_cache = _make_calib_cache(
            annotate / "cache" / "closed_live_mac_supervisor.json",
            dry=False,
        )
    ids = iter_case_ids(annotate, case_ids)
    written = 0
    skipped = 0
    n_empty_fallback = 0
    n_live = 0
    errors: list[dict[str, str]] = []
    mac_map = {str(k): list(v) for k, v in dict(mac_pred_by_cid or {}).items()}
    mac_doc_map = {
        str(k): [list(x) for x in v]
        for k, v in dict(mac_doctors_by_cid or {}).items()
    }
    for cid in ids:
        dest = out_dir / ("%s.json" % cid)
        if resume and dest.is_file():
            skipped += 1
            continue
        tree_path = annotate / "shared_trees" / ("%s.json" % cid)
        p5_path = annotate / "p5_audit" / ("%s.json" % cid)
        case_path = annotate / "case_results" / ("%s.json" % cid)
        try:
            if not tree_path.is_file():
                raise FileNotFoundError("missing tree %s" % tree_path)
            tree_state = load_tree_state(tree_path)
            p5_doc = _read_json(p5_path) if p5_path.is_file() else {}
            case_doc = _read_json(case_path) if case_path.is_file() else {}
            proj = build_one_projection(
                case_id=cid,
                tree_state=tree_state,
                p5_doc=p5_doc if isinstance(p5_doc, Mapping) else {},
                case_doc=case_doc if isinstance(case_doc, Mapping) else {},
                fact_texts=fixtures.get(cid) or {},
                ddx_k=ddx_k,
                ddx_source=src,
                dry_calib=dry_calib,
                vignette=vignette_by_id.get(cid, ""),
                calib_cache=calib_cache,
                pool_n=pool_n,
                mac_labels=list(mac_map.get(str(cid)) or []),
                mac_doctor_lists=list(mac_doc_map.get(str(cid)) or []),
                closed_mac_cache=closed_mac_cache,
            )
            if (proj.get("sources") or {}).get("fallback") == "empty_compat":
                n_empty_fallback += 1
            if ((proj.get("sources") or {}).get("policy_meta") or {}).get("live"):
                n_live += 1
            _write_json(dest, proj)
            written += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"case_id": cid, "error": "%s: %s" % (type(exc).__name__, exc)})
    return {
        "annotate_dir": str(annotate),
        "out_dir": str(out_dir),
        "n_ids": len(ids),
        "written": written,
        "skipped_resume": skipped,
        "n_errors": len(errors),
        "errors": errors[:20],
        "ddx_k": ddx_k,
        "ddx_source": src,
        "pool_n": int(pool_n) if src in {
            DDX_SOURCE_POST_N_MCR,
            DDX_SOURCE_CLOSED_POOL_RRF,
            DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
            DDX_SOURCE_CLOSED_LIVE_MAC,
            DDX_SOURCE_MULTI_ARM_RRF,
        } else None,
        "out_subdir": sub,
        "n_empty_compat_fallback": n_empty_fallback,
        "dry_calib": bool(dry_calib),
        "live_closed_mac": bool(live_closed_mac and closed_mac_cache is not None),
        "n_live_closed_mac_cases": n_live,
        "calib_cache_calls": int(getattr(calib_cache, "calls", 0) or 0),
        "closed_mac_cache_calls": int(getattr(closed_mac_cache, "calls", 0) or 0),
        "n_mac_cases": len(mac_map),
        "n_mac_doctor_cases": len(mac_doc_map),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--ddx-k", type=int, default=DEFAULT_DDX_K)
    ap.add_argument(
        "--ddx-source",
        default=DDX_SOURCE_POSTERIOR,
        choices=list(ALL_DDX_SOURCES) + [
            "compat",
            "compat_final_ranking",
            "final_ranking",
            "posterior",
            "compat_then_pad",
            "gate_on_post",
            "calib_only_post",
            "l1_top2_compat",
            "l1_top2",
            "per_l1_top2_compat",
            "gated_hybrid",
            "gated_hybrid_top2",
            "gated_top2",
            "gated_hybrid_compat",
            "gated_hybrid_top2_compat",
            "gated_top2_compat",
            "gated_hybrid_mcr",
            "gated_hybrid_mcr_compat",
            "gated_top2_mcr",
            "post_n_mcr",
            "posterior_n_mcr",
            "post7_mcr",
            "posterior_n7_mcr",
            "multi_arm_rrf",
            "tree_rrf",
            "closed_pool_rrf",
            "closed_pool_views_rrf",
            "closed_mac_trace_rrf",
            "closed_mac_rrf",
            "mac_supervisor_on_pool",
            "closed_live_mac_supervisor",
            "closed_live_mac",
            "live_closed_mac",
            "tree_mac_pad",
            "mac_pad",
            "tree_mac_pad_selective",
            "mac_pad_selective",
        ],
    )
    ap.add_argument("--out-subdir", default="", help="annotate/<subdir> (auto by source)")
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--resume", action="store_true")
    ap.add_argument(
        "--pool-n",
        type=int,
        default=DEFAULT_POST_N_MCR_POOL,
        help="for post_n_mcr / closed_pool_rrf / closed_live_mac: pool size",
    )
    ap.add_argument(
        "--mac-predictions",
        type=Path,
        default=None,
        help="predictions.jsonl for tree_mac_pad (B06 ordered_diagnoses)",
    )
    ap.add_argument(
        "--mac-trace",
        type=Path,
        default=None,
        help="trace.jsonl for closed_mac_trace_rrf (B06 discussion doctor lists)",
    )
    ap.add_argument(
        "--live-calib",
        action="store_true",
        help="for gate/calib arms: call live both_l1fallback (needs LLM)",
    )
    ap.add_argument(
        "--live-closed-mac",
        action="store_true",
        help="for closed_live_mac_supervisor: run live 3-doctor+supervisor (needs LLM)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    mac_map: dict[str, list[str]] = {}
    if args.mac_predictions and Path(args.mac_predictions).is_file():
        import re as _re

        for line in Path(args.mac_predictions).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            m = _re.search(r"(\d+)$", str(row.get("case_id") or ""))
            cid = str(int(m.group(1))) if m else str(row.get("case_id") or "")
            mac_map[cid] = list(row.get("ordered_diagnoses") or [])
    mac_docs: dict[str, list[list[str]]] = {}
    if args.mac_trace and Path(args.mac_trace).is_file():
        import re as _re

        for line in Path(args.mac_trace).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            m = _re.search(r"(\d+)$", str(row.get("case_id") or ""))
            cid = str(int(m.group(1))) if m else str(row.get("case_id") or "")
            disc = ((row.get("trace") or {}) if isinstance(row.get("trace"), Mapping) else {}).get(
                "discussion"
            ) or []
            lists: list[list[str]] = []
            for turn in disc:
                if not isinstance(turn, Mapping):
                    continue
                ranked = turn.get("ranked_diagnoses") or []
                if isinstance(ranked, list) and ranked:
                    lists.append([str(x) for x in ranked])
            if lists:
                mac_docs[cid] = lists
    summary = build_eval_projections(
        args.run_dir,
        ddx_k=int(args.ddx_k),
        case_ids=list(args.case_id or []),
        resume=bool(args.resume),
        ddx_source=str(args.ddx_source),
        out_subdir=str(args.out_subdir or ""),
        dry_calib=not bool(args.live_calib),
        pool_n=int(args.pool_n),
        mac_pred_by_cid=mac_map,
        mac_doctors_by_cid=mac_docs,
        live_closed_mac=bool(args.live_closed_mac),
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["n_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
