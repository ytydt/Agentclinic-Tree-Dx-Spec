#!/usr/bin/env python3
"""Replace lexical secondary metrics with Prompt7 LLM judge (MCR).

Computes for every C1 precompat / pool15 arm, and for the AB10b/AB10c
permutation null on the perturbable subset:

  llm_acc_at_1, llm_any_hit_at_k, llm_rr_at_k

using ``mcr.diag_accuracy`` (same prompt as official Acc). Shared disk cache
under annotate/judge_cache_llm_rank_metrics.json; merges existing
official_eval_llm_* caches first.

Also writes a short root-cause note explaining why full-sample lexical RR
(Δ≈0.02) looked incompatible with §2.7 (M00 0.474 vs null 0.426, p=0.005):
the full sample mixes 56 forced ties (non-perturbable) with 42 free cases,
and §2.7 compares M00 to a 200-draw null — not to a single AB10b seed.

Zero new LLM calls when everything is cached. Otherwise requires gnn-llm +
clashon.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import pre_compat_joint as pcj  # noqa: E402
import run_mcr_c1_precompat_ablation as rmp  # noqa: E402
from transfer_eval import io_gold  # noqa: E402
from transfer_eval.judges import (  # noqa: E402
    JUDGE_MODEL_SLUG,
    JudgeCache,
    LLMJudge,
    cache_key,
)

ANN = pcj.resolve_annotate_dir(
    ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
)
CACHE_PATH = ANN / "judge_cache_llm_rank_metrics.json"
OUT_JSON = ROOT / "runs/paper_v1/ablations_c1_mcr_llm_rank_metrics.json"
OUT_PERM = ROOT / "runs/paper_v1/ablations_c1_ab10b_llm_permutation.json"
DEFAULT_PARQUET = Path(rmp.DEFAULT_PARQUET)
K = 5
SEED0 = 20260728


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configure_paths(
    *,
    run_dir: Path,
    out_json: Path,
    out_perm: Path,
    subset_parquet: Path,
) -> None:
    global ANN, CACHE_PATH, OUT_JSON, OUT_PERM, DEFAULT_PARQUET
    ANN = pcj.resolve_annotate_dir(run_dir)
    CACHE_PATH = ANN / "judge_cache_llm_rank_metrics.json"
    OUT_JSON = out_json
    OUT_PERM = out_perm
    DEFAULT_PARQUET = subset_parquet


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(statistics.fmean(xs), 4) if xs else None


def merge_existing_caches(into: JudgeCache) -> int:
    n = 0
    for cp in list(ANN.glob("official_eval_llm_*/judge_cache.json")) + (
        [CACHE_PATH] if CACHE_PATH.is_file() else []
    ):
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


def make_client():
    from agentclinic_tree_dx.llm_client import RobustLLMClient

    return RobustLLMClient(
        model=JUDGE_MODEL_SLUG,
        call_timeout=120,
        max_retries=4,
        timeout_retry_cap=2,
        temperature=0.0,
        min_response_length=1,
    )


def pair_cached(cache: JudgeCache, pred: str, gold: str) -> bool:
    key = cache_key(
        prompt_id="mcr.diag_accuracy",
        model=JUDGE_MODEL_SLUG,
        payload={"predicted_diagnosis": pred, "actual_diagnosis": gold},
    )
    hit = cache.get(key)
    return isinstance(hit, Mapping) and "text" in hit


def judge_pair(judge: LLMJudge, pred: str, gold: str) -> bool:
    return bool(judge.mcr_diagnosis_correct(pred, gold))


def rr_metrics(
    labels: Sequence[str], gold: str, judge: LLMJudge, *, k: int = K
) -> dict[str, float]:
    labs = [str(x).strip() for x in labels[:k] if str(x).strip()]
    if not gold or not labs:
        return {"llm_top1": 0.0, "llm_any_hit": 0.0, "llm_rr": 0.0}
    hits = [judge_pair(judge, lab, gold) for lab in labs]
    first = next((i for i, h in enumerate(hits, start=1) if h), None)
    return {
        "llm_top1": float(hits[0]),
        "llm_any_hit": float(first is not None),
        "llm_rr": (1.0 / first) if first else 0.0,
    }


def load_proj_labels(arm: str, tag: str, cid: str) -> list[str]:
    fp = ANN / f"eval_projection_c1_mcr_{arm.lower()}_{tag}" / f"{cid}.json"
    if not fp.is_file():
        return []
    proj = json.loads(fp.read_text(encoding="utf-8"))
    return [
        str(r.get("label") or "").strip()
        for r in (proj.get("pred_ddx") or [])
        if str(r.get("label") or "").strip()
    ]


def collect_arm_pairs(arms: Sequence[str], tag: str, gold: Mapping[str, Any]) -> set[tuple[str, str]]:
    m00 = ANN / f"eval_projection_c1_mcr_m00_{tag}"
    ids = sorted(p.stem for p in m00.glob("*.json")) if m00.is_dir() else []
    pairs: set[tuple[str, str]] = set()
    for arm in arms:
        for cid in ids:
            gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
            if not gdx:
                continue
            for lab in load_proj_labels(arm, tag, cid)[:K]:
                pairs.add((lab, gdx))
    return pairs


def ensure_pairs(
    pairs: set[tuple[str, str]],
    cache: JudgeCache,
    *,
    workers: int,
    dry: bool,
) -> dict[str, Any]:
    missing = [(p, g) for p, g in sorted(pairs) if not pair_cached(cache, p, g)]
    info = {
        "n_pairs": len(pairs),
        "n_cached": len(pairs) - len(missing),
        "n_missing": len(missing),
    }
    print(
        f"  pairs={len(pairs)} cached={info['n_cached']} missing={len(missing)}",
        flush=True,
    )
    if not missing or dry:
        return info

    def _work(batch: list[tuple[str, str]]) -> int:
        client = make_client()
        judge = LLMJudge(client=client, cache=cache)
        ok = 0
        for pred, gold in batch:
            judge_pair(judge, pred, gold)
            ok += 1
        return ok

    w = max(1, int(workers))
    chunks = [missing[i::w] for i in range(w)]
    with ThreadPoolExecutor(max_workers=w) as ex:
        futs = [ex.submit(_work, ch) for ch in chunks if ch]
        done = 0
        for fut in as_completed(futs):
            done += int(fut.result())
            print(f"  judged {done}/{len(missing)}", flush=True)
    cache.flush()
    return info


def score_arms(
    arms: Sequence[str], tag: str, gold: Mapping[str, Any], cache: JudgeCache
) -> dict[str, Any]:
    judge = LLMJudge(client=None, cache=cache)  # cache-only; misses raise
    ids = sorted(
        p.stem
        for p in (ANN / f"eval_projection_c1_mcr_m00_{tag}").glob("*.json")
    )
    out: dict[str, Any] = {}
    for arm in arms:
        top1 = anyh = rr = 0.0
        n = 0
        for cid in ids:
            gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
            labs = load_proj_labels(arm, tag, cid)
            if not gdx or not labs:
                continue
            m = rr_metrics(labs, gdx, judge, k=K)
            n += 1
            top1 += m["llm_top1"]
            anyh += m["llm_any_hit"]
            rr += m["llm_rr"]
        out[arm] = {
            "n": n,
            "llm_acc_at_1": round(top1 / n, 4) if n else None,
            "llm_any_hit_at_k": round(anyh / n, 4) if n else None,
            "llm_rr_at_k": round(rr / n, 4) if n else None,
        }
        print(
            f"  [{tag}] {arm:6s} @1={out[arm]['llm_acc_at_1']} "
            f"anyhit={out[arm]['llm_any_hit_at_k']} RR={out[arm]['llm_rr_at_k']} n={n}",
            flush=True,
        )
    return out


def perturbable_cases(gold: Mapping[str, Any]) -> list[dict[str, Any]]:
    ids = sorted(p.stem for p in (ANN / "case_results").glob("*.json"))
    cases = []
    for cid in ids:
        gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
        _, labels, _ = pcj.load_pre_compat_inputs(ANN, cid)
        if not labels or not gdx:
            continue
        gate = mcc.fine_crowd_gate(labels)
        if not bool(gate.get("triggered")):
            continue
        ref = gate.get("merge_info") or merge.merge_ranking_ids(list(labels))
        profile = mcc.partition_profile(ref)
        if mcc.n_matched_partitions(profile) <= 1:
            continue
        cases.append(
            {
                "case_id": cid,
                "labels": labels,
                "gold": gdx,
                "ref": ref,
                "profile": profile,
                "top1_size": len(gate.get("top1_members") or []) or profile[0],
            }
        )
    return cases


def perm_pairs(cases: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    """All leaf labels on perturbable cases (covers every matched partition)."""
    pairs: set[tuple[str, str]] = set()
    for c in cases:
        gdx = c["gold"]
        for r in c["labels"]:
            lab = str(r.get("label") or "").strip()
            if lab:
                pairs.add((lab, gdx))
    return pairs


def run_permutation(
    cases: Sequence[Mapping[str, Any]],
    cache: JudgeCache,
    seeds: Sequence[int],
) -> dict[str, Any]:
    judge = LLMJudge(client=None, cache=cache)
    n = len(cases)

    def score(labels, mi, gdx):
        by = {str(r.get("id")): str(r.get("label") or "") for r in labels}
        order = list(mi["representative_order"])
        texts = [by.get(str(r), "") for r in order[:K]]
        texts = [t for t in texts if t]
        return rr_metrics(texts, gdx, judge, k=K)

    ref_tot = {"llm_top1": 0.0, "llm_any_hit": 0.0, "llm_rr": 0.0}
    for c in cases:
        m = score(c["labels"], c["ref"], c["gold"])
        for k, v in m.items():
            ref_tot[k] += v

    out: dict[str, Any] = {}
    for variant, match_top1 in (("AB10b", False), ("AB10c", True)):
        nulls = {k: [] for k in ref_tot}
        seen = {k: {} for k in ref_tot}
        for s in seeds:
            acc = {k: 0.0 for k in ref_tot}
            for c in cases:
                blocks = mcc.random_partition_matched(
                    c["labels"],
                    c["profile"],
                    seed=int(s),
                    match_top1=match_top1,
                    top1_size=c["top1_size"] if match_top1 else None,
                )
                bi = merge.merge_ranking_ids_from_blocks(c["labels"], blocks)
                m = score(c["labels"], bi, c["gold"])
                for k, v in m.items():
                    acc[k] += v
                    seen[k].setdefault(c["case_id"], set()).add(round(v, 4))
            for k in ref_tot:
                nulls[k].append(acc[k] / n)
        rows = {}
        for k in ref_tot:
            null = nulls[k]
            obs = ref_tot[k] / n
            sd = round(statistics.pstdev(null), 4) if len(null) > 1 else 0.0
            moving = sum(1 for vs in seen[k].values() if len(vs) > 1)
            ge = sum(1 for x in null if x >= obs - 1e-12)
            rows[k] = {
                "n_cases": n,
                "n_cases_moving": moving,
                "has_channel": bool(moving > 0),
                "m00": round(obs, 4),
                "null_mean": _mean(null),
                "null_sd": sd,
                "null_min": round(min(null), 4),
                "null_max": round(max(null), 4),
                "p_one_sided": round((ge + 1) / (len(null) + 1), 4),
            }
            print(
                f"  {variant} {k:12s} moves={moving:2d}/{n} "
                f"M00={obs:.4f} null={rows[k]['null_mean']}±{sd} "
                f"p={rows[k]['p_one_sided']}",
                flush=True,
            )
        out[variant] = rows
    return out


def root_cause_block() -> dict[str, Any]:
    return {
        "question": (
            "Why does full-sample open-RR (M00 0.54 vs AB10b 0.53) look near-null "
            "while §2.7 reports M00 0.474 vs null 0.426, p=0.005?"
        ),
        "answer": [
            "Different populations: full sample n=98 mixes 56 non-perturbable cases "
            "(AB10b≡M00 by construction, Δ≡0) with 42 perturbable cases.",
            "On the perturbable subset alone, even a single AB10b seed already shows "
            "lexical RR 0.474 vs 0.431 (Δ=+0.044); full-sample Δ is diluted to +0.019.",
            "§2.7's confirmatory contrast is M00 vs the 200-draw semantics-blind NULL "
            "distribution (mean 0.426), not vs one AB10b projection seed (0.431).",
            "AB10d (aggregated order) is a diagnostic scoring rule; it does not change "
            "the deletion-order any-hit channel. Confusing full-sample arm table RR "
            "with the permutation null is a category error, not a contradiction.",
        ],
        "numbers_lexical": {
            "full_n": 98,
            "pert_n": 42,
            "nonpert_n": 56,
            "full_m00_rr": 0.544,
            "full_ab10b_rr": 0.5253,
            "pert_m00_rr": 0.4742,
            "pert_ab10b_single_seed_rr": 0.4306,
            "pert_null_mean_rr_200": 0.426,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--dry-cache-only", action="store_true",
                    help="do not call LLM; fail if cache incomplete")
    ap.add_argument("--skip-perm", action="store_true")
    ap.add_argument(
        "--run-dir",
        type=Path,
        default=ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
    )
    ap.add_argument(
        "--subset-parquet",
        type=Path,
        default=rmp.DEFAULT_PARQUET,
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "runs/paper_v1/ablations_c1_mcr_llm_rank_metrics.json",
    )
    ap.add_argument(
        "--out-perm",
        type=Path,
        default=ROOT / "runs/paper_v1/ablations_c1_ab10b_llm_permutation.json",
    )
    args = ap.parse_args()
    _configure_paths(
        run_dir=Path(args.run_dir),
        out_json=Path(args.out_json),
        out_perm=Path(args.out_perm),
        subset_parquet=Path(args.subset_parquet),
    )

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Point JudgeCache at our dedicated file
    cache = JudgeCache(CACHE_PATH)
    n_merged = merge_existing_caches(cache)
    print(f"[{_utc()}] merged {n_merged} cache entries → {CACHE_PATH}", flush=True)

    ids_all = sorted(
        p.stem for p in (ANN / "eval_projection_c1_mcr_m00_precompat").glob("*.json")
    )
    gold = io_gold.load_gold(
        "medcasereasoning", Path(DEFAULT_PARQUET), case_ids=ids_all
    )

    pre_arms = list(rmp.ARMS)
    print("[precompat] collecting pairs", flush=True)
    pairs = collect_arm_pairs(pre_arms, "precompat", gold)
    print("[pool15] collecting pairs", flush=True)
    pool_arms = ["M00", "AB07", "AB10"]
    pairs |= collect_arm_pairs(pool_arms, "pool15", gold)

    cases = perturbable_cases(gold)
    print(f"[perm] perturbable cases={len(cases)}", flush=True)
    pairs |= perm_pairs(cases)

    info = ensure_pairs(
        pairs, cache, workers=int(args.workers), dry=bool(args.dry_cache_only)
    )
    if args.dry_cache_only and info["n_missing"]:
        raise SystemExit(f"cache incomplete: {info['n_missing']} missing pairs")

    # Re-open cache after writes
    cache = JudgeCache(CACHE_PATH)
    merge_existing_caches(cache)

    print("[score precompat]", flush=True)
    pre = score_arms(pre_arms, "precompat", gold, cache)
    print("[score pool15]", flush=True)
    pool = score_arms(pool_arms, "pool15", gold, cache)

    perm = None
    if not args.skip_perm:
        print(f"[perm] seeds={args.seeds}", flush=True)
        seeds = [SEED0 + i for i in range(int(args.seeds))]
        perm = run_permutation(cases, cache, seeds)

    payload = {
        "created_at": _utc(),
        "judge": "mcr.diag_accuracy / Prompt7 LLM",
        "model": JUDGE_MODEL_SLUG,
        "k": K,
        "cache_path": str(CACHE_PATH),
        "pair_stats": info,
        "root_cause_full_vs_perm": root_cause_block(),
        "precompat": pre,
        "pool15": pool,
        "permutation": perm,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if perm is not None:
        OUT_PERM.write_text(
            json.dumps(
                {
                    "created_at": _utc(),
                    "judge": "mcr.diag_accuracy",
                    "seeds": int(args.seeds),
                    "seed0": SEED0,
                    "arms": perm,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[wrote] {OUT_PERM}", flush=True)
    print(f"[wrote] {OUT_JSON}", flush=True)

    # Patch live result JSONs: replace lexical secondary with LLM fields
    for path, key in (
        (ROOT / "runs/paper_v1/ablations_c1_mcr_precompat_live_results.json", "precompat"),
        (ROOT / "runs/paper_v1/ablations_c1_mcr_pool15_live_results.json", "pool15"),
    ):
        if not path.is_file():
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        block = payload[key]
        # keep old lexical under lexical_legacy; primary secondary metrics → llm
        if "lexical" in d and "lexical_legacy" not in d:
            d["lexical_legacy"] = d["lexical"]
        d["lexical"] = {
            arm: {
                "n": row["n"],
                "lex_acc_at_1": row["llm_acc_at_1"],  # name retained for table code; values are LLM
                "lex_any_hit_at_k": row["llm_any_hit_at_k"],
                "lex_rr_at_k": row["llm_rr_at_k"],
                "judge": "llm:mcr.diag_accuracy",
            }
            for arm, row in block.items()
        }
        d["llm_rank_metrics"] = block
        d["llm_rank_metrics_source"] = str(OUT_JSON)
        path.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"[patched] {path}", flush=True)


if __name__ == "__main__":
    # ThreadLocal imported by mistake earlier — keep import clean for runtime
    main()
