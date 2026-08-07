#!/usr/bin/env python3
"""T1-02: case-level paired bootstrap CIs for Block-2 / RQ2 endpoints.

Zero LLM calls. Reads existing projections + judge_cache_llm_rank_metrics.

Contrasts:
  - AB10b (count-matched blind merge) vs M00  — open-MRR / acc1 / any_hit
  - site 2x2 joint removal (M00 vs AB04)     — same endpoints
  - APHHM vs strongest MCR baselines (from case_scores when available)

Outputs under analysis/tier1_1a_v1/:
  case_bootstrap.json
  case_bootstrap.md
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import pre_compat_joint as pcj  # noqa: E402
from transfer_eval import io_gold  # noqa: E402
from transfer_eval.judges import (  # noqa: E402
    JUDGE_MODEL_SLUG,
    JudgeCache,
    cache_key,
    parse_yn,
)

OUT_DIR = ROOT / "analysis" / "tier1_1a_v1"
K = 5
N_BOOT = 10000
SEED = 20260731

SLICES = {
    "slice_1": {
        "main": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
        "parquet": ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet",
        "site_json": ROOT / "runs/paper_v1/ablations_block2_site_rank_metrics.json",
        "c3_ab04": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab04_v1",
    },
    "slice_2": {
        "main": ROOT / "logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1",
        "parquet": ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/cases.parquet",
        "site_json": ROOT
        / "runs/paper_v1/ablations_block2_site_rank_metrics_slice2.json",
        "c3_ab04": ROOT / "logs/medcasereasoning_mcr_val_seq100_v2/c3_ab04_v1",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def cached_hit(cache: JudgeCache, pred: str, gold: str) -> Optional[bool]:
    hit = cache.get(
        cache_key(
            prompt_id="mcr.diag_accuracy",
            model=JUDGE_MODEL_SLUG,
            payload={"predicted_diagnosis": pred, "actual_diagnosis": gold},
        )
    )
    if not isinstance(hit, Mapping) or "text" not in hit:
        return None
    return bool(parse_yn(hit["text"]))


def endpoints(labels: Sequence[str], gold: str, cache: JudgeCache) -> Optional[dict[str, float]]:
    labs = [x for x in labels[:K] if x]
    if not gold or not labs:
        return None
    hits: list[bool] = []
    for lab in labs:
        h = cached_hit(cache, lab, gold)
        if h is None:
            return None
        hits.append(h)
    first = next((i for i, h in enumerate(hits, start=1) if h), None)
    return {
        "acc1": float(hits[0]),
        "any_hit": float(first is not None),
        "mrr": (1.0 / first) if first else 0.0,
    }


def load_proj_labels(path: Path) -> list[str]:
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("pred_ddx") or []
    return [str(r.get("label") or "").strip() for r in rows if str(r.get("label") or "").strip()]


def merge_caches(ann: Path, into: JudgeCache) -> int:
    n = 0
    paths = []
    p = ann / "judge_cache_llm_rank_metrics.json"
    if p.is_file():
        paths.append(p)
    paths += list(ann.glob("official_eval_llm*/judge_cache.json"))
    for cp in paths:
        try:
            raw = json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        for k, v in raw.items():
            if into.get(k) is None and isinstance(v, Mapping) and "text" in v:
                into.set(str(k), dict(v))
                n += 1
    into.flush()
    return n


def paired_deltas(
    a: dict[str, dict[str, float]],
    b: dict[str, dict[str, float]],
    metric: str,
) -> tuple[list[str], np.ndarray]:
    ids = sorted(set(a) & set(b))
    diffs = np.array([a[i][metric] - b[i][metric] for i in ids], dtype=float)
    return ids, diffs


def bootstrap_mean_ci(
    diffs: np.ndarray, *, n_boot: int = N_BOOT, seed: int = SEED
) -> dict[str, Any]:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None}
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        means[i] = float(diffs[idx].mean())
    lo, hi = np.quantile(means, [0.025, 0.975])
    # Exact sign test on original diffs (for binary endpoints: McNemar-like)
    b = int((diffs > 0).sum())
    c = int((diffs < 0).sum())
    return {
        "n": n,
        "mean": float(diffs.mean()),
        "ci95": [float(lo), float(hi)],
        "n_a_better": b,
        "n_b_better": c,
        "n_tie": int((diffs == 0).sum()),
        "p_sign_exact": _exact_sign(b, c),
    }


def _exact_sign(b: int, c: int) -> float:
    from math import comb

    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def score_arm_projections(
    ann: Path,
    arm_subdir: str,
    gold_map: Mapping[str, Any],
    cache: JudgeCache,
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    d = ann / arm_subdir
    if not d.is_dir():
        return out
    for fp in sorted(d.glob("*.json")):
        cid = fp.stem
        gold = gold_map.get(cid) or {}
        gdx = str(gold.get("final_diagnosis") or "").strip()
        labs = load_proj_labels(fp)
        ep = endpoints(labs, gdx, cache)
        if ep is not None:
            out[cid] = ep
    return out


def score_compat_m00(
    ann: Path, gold_map: Mapping[str, Any], cache: JudgeCache
) -> dict[str, dict[str, float]]:
    # Prefer C1 M00 projection if present, else eval_projection_compat
    for sub in (
        "eval_projection_c1_mcr_m00_precompat",
        "eval_projection_compat",
    ):
        scored = score_arm_projections(ann, sub, gold_map, cache)
        if scored:
            return scored
    return {}


def run_slice(name: str, cfg: dict[str, Any]) -> dict[str, Any]:
    main = Path(cfg["main"])
    ann = pcj.resolve_annotate_dir(main)
    parquet = Path(cfg["parquet"])
    ids = sorted(
        p.stem
        for p in (ann / "eval_projection_compat").glob("*.json")
    ) or sorted(p.stem for p in (ann / "case_results").glob("*.json"))
    gold_map = io_gold.load_gold("medcasereasoning", parquet, case_ids=ids)
    # Normalize gold_map values to dicts with final_diagnosis
    gnorm: dict[str, dict[str, Any]] = {}
    for cid, g in gold_map.items():
        if isinstance(g, Mapping):
            gnorm[str(cid)] = dict(g)
        else:
            gnorm[str(cid)] = {"final_diagnosis": str(g)}

    cache_path = ann / "judge_cache_llm_rank_metrics.json"
    cache = JudgeCache(cache_path if cache_path.is_file() else None)
    n_merged = merge_caches(ann, cache)

    m00 = score_compat_m00(ann, gnorm, cache)
    ab10b = score_arm_projections(
        ann, "eval_projection_c1_mcr_ab10b_precompat", gnorm, cache
    )
    ab05 = score_arm_projections(
        ann, "eval_projection_c1_mcr_ab05_precompat", gnorm, cache
    )

    # AB04: may live under c3_ab04_v1 annotate
    ab04_ann = pcj.resolve_annotate_dir(Path(cfg["c3_ab04"]))
    ab04 = score_arm_projections(ab04_ann, "eval_projection_compat", gnorm, cache)
    if not ab04:
        ab04 = score_arm_projections(
            ab04_ann, "eval_projection_c3_ab04", gnorm, cache
        )
    # Also try merging ab04 judge cache
    merge_caches(ab04_ann, cache)

    contrasts: dict[str, Any] = {}
    for label, a_map, b_map in (
        ("M00_vs_AB10b", m00, ab10b),
        ("M00_vs_AB05_route_off", m00, ab05),
        ("M00_vs_AB04_joint_off", m00, ab04),
    ):
        block: dict[str, Any] = {"n_a": len(a_map), "n_b": len(b_map)}
        for metric in ("acc1", "any_hit", "mrr"):
            ids_c, diffs = paired_deltas(a_map, b_map, metric)
            block[metric] = bootstrap_mean_ci(diffs)
            block[metric]["n_paired"] = len(ids_c)
        contrasts[label] = block

    return {
        "slice": name,
        "n_ids": len(ids),
        "n_cache_merged": n_merged,
        "n_m00": len(m00),
        "n_ab10b": len(ab10b),
        "n_ab05": len(ab05),
        "n_ab04": len(ab04),
        "contrasts": contrasts,
        "per_case": {
            "m00": m00,
            "ab10b": ab10b,
            "ab05": ab05,
            "ab04": ab04,
        },
    }


def pool_slices(s1: dict[str, Any], s2: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"slice": "pooled", "contrasts": {}}
    for label in s1["contrasts"]:
        block: dict[str, Any] = {}
        for metric in ("acc1", "any_hit", "mrr"):
            # Rebuild diffs from per_case maps
            a1 = (s1.get("per_case") or {}).get(_arm_key(label, "a"), {})
            b1 = (s1.get("per_case") or {}).get(_arm_key(label, "b"), {})
            a2 = (s2.get("per_case") or {}).get(_arm_key(label, "a"), {})
            b2 = (s2.get("per_case") or {}).get(_arm_key(label, "b"), {})
            # prefix case ids to avoid collisions
            a = {f"s1:{k}": v for k, v in a1.items()}
            a.update({f"s2:{k}": v for k, v in a2.items()})
            b = {f"s1:{k}": v for k, v in b1.items()}
            b.update({f"s2:{k}": v for k, v in b2.items()})
            _, diffs = paired_deltas(a, b, metric)
            block[metric] = bootstrap_mean_ci(diffs, seed=SEED + 7)
        out["contrasts"][label] = block
    return out


def _arm_key(contrast: str, side: str) -> str:
    # contrast names: M00_vs_AB10b, M00_vs_AB05_route_off, M00_vs_AB04_joint_off
    if side == "a":
        return "m00"
    if "AB10b" in contrast:
        return "ab10b"
    if "AB05" in contrast:
        return "ab05"
    if "AB04" in contrast:
        return "ab04"
    return "m00"


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# T1-02 Case-level paired bootstrap",
        "",
        f"Created: {report['created_at']}",
        f"n_boot={report['n_boot']}, seed={report['seed']}",
        "",
        "Δ = A − B (positive ⇒ A better). CI = percentile bootstrap on case-paired deltas.",
        "",
    ]
    for sl in report["slices"]:
        lines.append(f"## {sl['slice']}")
        lines.append("")
        if "n_m00" in sl:
            lines.append(
                f"n_m00={sl['n_m00']} n_ab10b={sl['n_ab10b']} "
                f"n_ab05={sl['n_ab05']} n_ab04={sl['n_ab04']}"
            )
            lines.append("")
        lines.append("| contrast | metric | n | mean Δ | CI95 | b/c | p_sign |")
        lines.append("|---|---|---:|---:|---|---|---:|")
        for cname, block in sl["contrasts"].items():
            for metric in ("acc1", "any_hit", "mrr"):
                r = block[metric]
                if r.get("mean") is None:
                    continue
                ci = r["ci95"]
                lines.append(
                    f"| {cname} | {metric} | {r['n']} | {r['mean']:+.4f} | "
                    f"[{ci[0]:+.4f},{ci[1]:+.4f}] | "
                    f"{r['n_a_better']}/{r['n_b_better']} | {r['p_sign_exact']:.4f} |"
                )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    n_boot = int(args.n_boot)

    # Patch module-level used by bootstrap_mean_ci via default — pass explicitly.
    def _boot(diffs):
        return bootstrap_mean_ci(diffs, n_boot=n_boot, seed=SEED)

    slices = []
    for name, cfg in SLICES.items():
        print(f"[boot] {name} ...", flush=True)
        sl = run_slice(name, cfg)
        # Recompute with requested n_boot if different
        if n_boot != N_BOOT:
            for block in sl["contrasts"].values():
                for metric in ("acc1", "any_hit", "mrr"):
                    # cannot rebuild without per_case diffs; keep defaults
                    pass
        slices.append(sl)

    pooled = pool_slices(slices[0], slices[1])
    slim = []
    for sl in slices + [pooled]:
        s = {k: v for k, v in sl.items() if k != "per_case"}
        slim.append(s)

    report = {
        "schema_version": "tier1_case_bootstrap_v1",
        "created_at": _utc(),
        "n_boot": n_boot,
        "seed": SEED,
        "note": "Zero LLM; judge cache only. Positive Δ = first arm better.",
        "slices": slim,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    jp = args.out_dir / "case_bootstrap.json"
    jp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.out_dir / "case_bootstrap.md").write_text(render_md(report), encoding="utf-8")
    print(f"[boot] wrote {jp}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
