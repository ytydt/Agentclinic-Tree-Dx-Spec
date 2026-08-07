#!/usr/bin/env python3
"""Block-2 execution-site 2x2 on the endpoints block 2 is actually judged on.

The site factor (AB04/AB05/AB06 vs M00) was only ever scored on open Acc@1,
while the operator factor (AB07-AB11, AB10b/c) is judged on ``any-hit@k`` and
``open-MRR`` per plan R1b/R1c. This script closes that gap: it scores all four
cells of the 2x2 with the same Prompt7 judge (``mcr.diag_accuracy``, K=5) used
for the operator arms, so the two factors become comparable.

It also runs paired McNemar (exact) on every edge of the 2x2 plus the joint
contrast, because the marginal deltas here are small enough that unpaired
accuracy differences cannot separate signal from judge noise.

Cells (dedupe = build-time semantic dedupe, route = decision-time gate):
    M00  dedupe ON  route ON   compat_synonym_v1 / eval_projection_compat
    AB05 dedupe ON  route OFF  compat_synonym_v1 / eval_projection_c1_mcr_ab05_precompat
    AB06 dedupe OFF route ON   c3_ab06_v1        / eval_projection_compat
    AB04 dedupe OFF route OFF  c3_ab04_v1        / eval_projection_compat

Zero new LLM calls when everything is cached; otherwise requires gnn-llm.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from math import comb
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

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
    LLMJudge,
    cache_key,
)

MCR = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1"
MAIN = MCR / "compat_synonym_v1"
ANN = pcj.resolve_annotate_dir(MAIN)
CACHE_PATH = ANN / "judge_cache_llm_rank_metrics.json"
OUT_JSON = ROOT / "runs/paper_v1/ablations_block2_site_rank_metrics.json"
PARQUET = (
    ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
)
K = 5

# (arm, dedupe, route, run_dir, projection_subdir) — rebuilt in main for --mcr-root
CELLS: tuple[tuple[str, str, str, Path, str], ...] = ()


def _build_cells(mcr: Path) -> tuple[tuple[str, str, str, Path, str], ...]:
    main = mcr / "compat_synonym_v1"
    return (
        ("M00", "on", "on", main, "eval_projection_compat"),
        ("AB05", "on", "off", main, "eval_projection_c1_mcr_ab05_precompat"),
        ("AB06", "off", "on", mcr / "c3_ab06_v1", "eval_projection_compat"),
        ("AB04", "off", "off", mcr / "c3_ab04_v1", "eval_projection_compat"),
    )


CELLS = _build_cells(MCR)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mean(xs: Sequence[float]) -> Optional[float]:
    return round(statistics.fmean(xs), 4) if xs else None


def proj_dir(run_dir: Path, subdir: str) -> Path:
    return pcj.resolve_annotate_dir(run_dir) / subdir


def load_labels(run_dir: Path, subdir: str, cid: str) -> list[str]:
    fp = proj_dir(run_dir, subdir) / f"{cid}.json"
    if not fp.is_file():
        return []
    doc = json.loads(fp.read_text(encoding="utf-8"))
    return [
        str(r.get("label") or "").strip()
        for r in (doc.get("pred_ddx") or [])
        if str(r.get("label") or "").strip()
    ]


def merge_existing_caches(into: JudgeCache) -> int:
    """Pull in every judge cache on disk; the official evals already hold top-1."""
    n = 0
    globs: list[Path] = [CACHE_PATH] if CACHE_PATH.is_file() else []
    for run_dir in {c[3] for c in CELLS}:
        ann = pcj.resolve_annotate_dir(run_dir)
        globs += list(ann.glob("official_eval_llm*/judge_cache.json"))
    for cp in globs:
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
    hit = cache.get(
        cache_key(
            prompt_id="mcr.diag_accuracy",
            model=JUDGE_MODEL_SLUG,
            payload={"predicted_diagnosis": pred, "actual_diagnosis": gold},
        )
    )
    return isinstance(hit, Mapping) and "text" in hit


def judge_pair(judge: LLMJudge, pred: str, gold: str) -> bool:
    return bool(judge.mcr_diagnosis_correct(pred, gold))


def ensure_pairs(
    pairs: set[tuple[str, str]], cache: JudgeCache, *, workers: int, dry: bool
) -> dict[str, Any]:
    missing = [(p, g) for p, g in sorted(pairs) if not pair_cached(cache, p, g)]
    info = {
        "n_pairs": len(pairs),
        "n_cached": len(pairs) - len(missing),
        "n_missing": len(missing),
    }
    print(f"  pairs={len(pairs)} cached={info['n_cached']} missing={len(missing)}", flush=True)
    if not missing or dry:
        return info

    def _work(batch: list[tuple[str, str]]) -> int:
        judge = LLMJudge(client=make_client(), cache=cache)
        for pred, gold in batch:
            judge_pair(judge, pred, gold)
        return len(batch)

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


def exact_mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar on discordant pairs only."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def main() -> int:
    global MCR, MAIN, ANN, CACHE_PATH, OUT_JSON, PARQUET, CELLS

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--dry", action="store_true", help="report cache coverage only")
    ap.add_argument(
        "--mcr-root",
        type=Path,
        default=ROOT / "logs/medcasereasoning_mcr_val_seq100_v1",
    )
    ap.add_argument(
        "--subset-parquet",
        type=Path,
        default=None,
        help="defaults to data/benchmarks/.../<slice>/cases.parquet inferred from mcr-root",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=None,
    )
    args = ap.parse_args()

    MCR = Path(args.mcr_root).resolve()
    MAIN = MCR / "compat_synonym_v1"
    ANN = pcj.resolve_annotate_dir(MAIN)
    CACHE_PATH = ANN / "judge_cache_llm_rank_metrics.json"
    CELLS = _build_cells(MCR)
    if args.subset_parquet is not None:
        PARQUET = Path(args.subset_parquet).resolve()
    else:
        name = MCR.name
        slice_name = (
            name[len("medcasereasoning_") :]
            if name.startswith("medcasereasoning_")
            else "mcr_val_seq100_v1"
        )
        PARQUET = (
            ROOT
            / "data/benchmarks/medcasereasoning/subsets"
            / slice_name
            / "cases.parquet"
        )
    OUT_JSON = (
        Path(args.out_json).resolve()
        if args.out_json is not None
        else ROOT / "runs/paper_v1/ablations_block2_site_rank_metrics.json"
    )

    ids = sorted(p.stem for p in proj_dir(MAIN, "eval_projection_compat").glob("*.json"))
    gold = io_gold.load_gold("medcasereasoning", PARQUET, case_ids=ids)
    print(f"cases={len(ids)} gold={len(gold)} mcr={MCR}", flush=True)

    cache = JudgeCache(CACHE_PATH)
    print(f"merged {merge_existing_caches(cache)} cached judgements", flush=True)

    pairs: set[tuple[str, str]] = set()
    for arm, _d, _r, run_dir, subdir in CELLS:
        for cid in ids:
            gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
            if not gdx:
                continue
            for lab in load_labels(run_dir, subdir, cid)[:K]:
                pairs.add((lab, gdx))
    pair_info = ensure_pairs(pairs, cache, workers=args.workers, dry=args.dry)
    if args.dry:
        print(json.dumps(pair_info, indent=2))
        return 0

    judge = LLMJudge(client=None, cache=cache)  # cache-only
    per_case: dict[str, dict[str, dict[str, float]]] = {}
    arms: dict[str, Any] = {}
    for arm, dedupe, route, run_dir, subdir in CELLS:
        top1 = anyh = rr = 0.0
        ncand = 0.0
        n = 0
        per_case[arm] = {}
        for cid in ids:
            gdx = str((gold.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
            labs = load_labels(run_dir, subdir, cid)
            if not gdx or not labs:
                continue
            top = labs[:K]
            hits = [judge_pair(judge, lab, gdx) for lab in top]
            first = next((i for i, h in enumerate(hits, start=1) if h), None)
            m = {
                "top1": float(hits[0]),
                "any_hit": float(first is not None),
                "rr": (1.0 / first) if first else 0.0,
                "n_cand": float(len(top)),
            }
            per_case[arm][cid] = m
            n += 1
            top1 += m["top1"]
            anyh += m["any_hit"]
            rr += m["rr"]
            ncand += m["n_cand"]
        arms[arm] = {
            "dedupe": dedupe,
            "route": route,
            "run_dir": str(run_dir),
            "projection_subdir": subdir,
            "n": n,
            "llm_acc_at_1": round(top1 / n, 4) if n else None,
            "llm_any_hit_at_k": round(anyh / n, 4) if n else None,
            "open_mrr_at_k": round(rr / n, 4) if n else None,
            "mean_surviving_candidates": round(ncand / n, 4) if n else None,
        }
        print(f"  {arm}: {json.dumps(arms[arm], ensure_ascii=False)}", flush=True)

    common = sorted(set.intersection(*[set(per_case[a]) for a, *_ in CELLS]))
    contrasts = [
        ("M00", "AB05", "route effect | dedupe ON"),
        ("AB06", "AB04", "route effect | dedupe OFF"),
        ("M00", "AB06", "dedupe effect | route ON"),
        ("AB05", "AB04", "dedupe effect | route OFF"),
        ("M00", "AB04", "joint (both removed)"),
    ]
    tests: list[dict[str, Any]] = []
    for a, b, label in contrasts:
        row: dict[str, Any] = {"contrast": label, "a": a, "b": b, "n": len(common)}
        for endpoint in ("top1", "any_hit", "rr"):
            A = [per_case[a][c][endpoint] for c in common]
            B = [per_case[b][c][endpoint] for c in common]
            delta = round(statistics.fmean(A) - statistics.fmean(B), 4)
            if endpoint == "rr":
                # graded endpoint: sign test on cases that moved
                pos = sum(1 for x, y in zip(A, B) if x > y)
                neg = sum(1 for x, y in zip(A, B) if x < y)
                row[endpoint] = {
                    "delta": delta,
                    "n_a_better": pos,
                    "n_b_better": neg,
                    "p_sign_exact": round(exact_mcnemar(pos, neg), 4),
                }
            else:
                bb = sum(1 for x, y in zip(A, B) if x > y)
                cc = sum(1 for x, y in zip(A, B) if x < y)
                row[endpoint] = {
                    "delta": delta,
                    "b_a_only": bb,
                    "c_b_only": cc,
                    "p_mcnemar_exact": round(exact_mcnemar(bb, cc), 4),
                }
        tests.append(row)

    # Holm over the whole 5x3 grid. Reported because every contrast here rests on
    # <=15 discordant cases, so an uncorrected p is easy to over-read.
    flat = sorted(
        (
            (
                float(t[ep].get("p_mcnemar_exact", t[ep].get("p_sign_exact", 1.0))),
                t["contrast"],
                ep,
            )
            for t in tests
            for ep in ("top1", "any_hit", "rr")
        )
    )
    holm: list[dict[str, Any]] = []
    running = 0.0
    for i, (p, contrast, ep) in enumerate(flat):
        adj = max(running, min(1.0, (len(flat) - i) * p))
        running = adj
        holm.append(
            {
                "contrast": contrast,
                "endpoint": ep,
                "p_raw": round(p, 4),
                "p_holm": round(adj, 4),
                "survives_holm_05": bool(adj < 0.05),
            }
        )

    # Additivity check: do the two single-site removals sum to the joint loss?
    def acc(arm: str, endpoint: str) -> float:
        return statistics.fmean([per_case[arm][c][endpoint] for c in common])

    interaction = {}
    for endpoint in ("top1", "any_hit", "rr"):
        route_on_dedupe = acc("M00", endpoint) - acc("AB05", endpoint)
        dedupe_on_route = acc("M00", endpoint) - acc("AB06", endpoint)
        joint = acc("M00", endpoint) - acc("AB04", endpoint)
        interaction[endpoint] = {
            "marginal_route_given_dedupe_on": round(route_on_dedupe, 4),
            "marginal_dedupe_given_route_on": round(dedupe_on_route, 4),
            "sum_of_marginals": round(route_on_dedupe + dedupe_on_route, 4),
            "joint_removal": round(joint, 4),
            "interaction_joint_minus_sum": round(
                joint - (route_on_dedupe + dedupe_on_route), 4
            ),
        }

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "purpose": (
            "Score the block-2 execution-site 2x2 on the endpoints block 2 is "
            "judged on (Prompt7 any-hit@5 / open-MRR), not just open Acc@1, and "
            "test every edge with paired exact McNemar."
        ),
        "judge": {"prompt_id": "mcr.diag_accuracy", "model": JUDGE_MODEL_SLUG, "k": K},
        "cache_path": str(CACHE_PATH),
        "pair_stats": pair_info,
        "n_common_cases": len(common),
        "arms": arms,
        "paired_tests": tests,
        "holm": holm,
        "interaction": interaction,
        "candidate_count_monotonicity": [
            {
                "arm": a,
                "mean_surviving_candidates": v["mean_surviving_candidates"],
                "llm_acc_at_1": v["llm_acc_at_1"],
                "dedupe": v["dedupe"],
                "route": v["route"],
            }
            for a, v in sorted(
                arms.items(), key=lambda kv: kv[1]["mean_surviving_candidates"] or 0.0
            )
        ],
        "caliber_note": (
            "Site arms AB04/AB06 are C3 rebuilds scored in their own run dirs; "
            "AB05 is a C1 replay on the reconstructed pre-compat joint. All four "
            "cells share the same judge, prompt and K, and M00 reproduces 0.50."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"arms": arms, "interaction": interaction}, indent=2, ensure_ascii=False))
    print("WROTE", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
