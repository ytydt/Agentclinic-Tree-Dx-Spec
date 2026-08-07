#!/usr/bin/env python3
"""Channel audit for the block-2 *operator* arms on MCR (AB05, AB07-AB11, AB20).

Plan clause R1b requires reporting an endpoint's moving-case count before any
null from it is interpreted. That audit was only ever run for AB10b/AB10c
(§2.6). This script closes the gap for the remaining operator arms, which all
land within +/-0.03 of M00 on MCR and would otherwise be read as "the gate's
implementation does not matter".

For every arm it reports, against M00 on the same pre-compat joint:

  n_same_ordering    arm delivered exactly M00's ranked id list
  n_same_top5_set    same set of delivered labels (order may differ)
  n_same_top1        same rank-1 label
  n_discordant       cases where the delivered list differs at all
                     -> the only cases that can carry information

and then re-scores Acc@1 / any-hit@5 / open-MRR *restricted to the discordant
subset*, with an exact paired sign test. A full-sample delta averages the
effect over cases where the two arms are identical by construction, which
shrinks it toward zero regardless of the truth.

Also reports padding saturation: with mean |survivors| ~2 and K=5, any-hit@5
may read most of the joint list for every arm, making it structurally blind to
the operator. ``n_cand`` vs ``k`` quantifies that.

Cache-only judge: zero LLM calls (all pairs already judged by
run_mcr_llm_rank_metrics.py / run_block2_site_rank_metrics.py).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
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
    cache_key,
    parse_yn,
)

MAIN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
ANN = pcj.resolve_annotate_dir(MAIN)
CACHE_PATH = ANN / "judge_cache_llm_rank_metrics.json"
PARQUET = (
    ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
)
OUT_JSON = ROOT / "runs/paper_v1/ablations_block2_operator_channel.json"
TAG = "precompat"
K = 5
ARMS = ("AB05", "AB07", "AB08", "AB09", "AB10", "AB10b", "AB10c", "AB11", "AB20")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def proj_path(arm: str, cid: str) -> Path:
    return ANN / f"eval_projection_c1_mcr_{arm.lower()}_{TAG}" / f"{cid}.json"


def load_case(arm: str, cid: str) -> Optional[dict[str, Any]]:
    fp = proj_path(arm, cid)
    if not fp.is_file():
        return None
    doc = json.loads(fp.read_text(encoding="utf-8"))
    rows = doc.get("pred_ddx") or []
    return {
        "ids": [str(r.get("id") or "").strip() for r in rows],
        "labels": [str(r.get("label") or "").strip() for r in rows],
        "meta": doc.get("meta") or {},
    }


def merge_caches(into: JudgeCache) -> int:
    n = 0
    paths = [CACHE_PATH] if CACHE_PATH.is_file() else []
    paths += list(ANN.glob("official_eval_llm*/judge_cache.json"))
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


def cached_hit(cache: JudgeCache, pred: str, gold: str) -> Optional[bool]:
    """None when the pair was never judged, so callers can count coverage gaps."""
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
        "n_cand": float(len(labs)),
    }


def exact_sign(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=OUT_JSON)
    args = ap.parse_args()

    ids = sorted(p.stem for p in (ANN / f"eval_projection_c1_mcr_m00_{TAG}").glob("*.json"))
    gold_map = io_gold.load_gold("medcasereasoning", PARQUET, case_ids=ids)
    cache = JudgeCache(CACHE_PATH)
    print(f"cases={len(ids)} merged_cached={merge_caches(cache)}", flush=True)

    m00 = {cid: load_case("M00", cid) for cid in ids}
    m00_ep: dict[str, dict[str, float]] = {}
    for cid in ids:
        gdx = str((gold_map.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
        c = m00.get(cid)
        if not c:
            continue
        ep = endpoints(c["labels"], gdx, cache)
        if ep:
            m00_ep[cid] = ep

    saturation = {
        "k": K,
        "m00_mean_delivered_candidates": round(
            statistics.fmean([v["n_cand"] for v in m00_ep.values()]), 4
        ),
        "m00_cases_delivering_fewer_than_k": sum(
            1 for v in m00_ep.values() if v["n_cand"] < K
        ),
        "n_scored": len(m00_ep),
        "note": (
            "any-hit@K reads min(K, |delivered|) labels. When |delivered| < K for "
            "most cases there is no padding headroom, so any-hit@K is a function "
            "of the surviving set only -- it cannot distinguish operators that "
            "deliver the same set in a different order."
        ),
    }
    print(f"saturation: {json.dumps(saturation, ensure_ascii=False)}", flush=True)

    rows: list[dict[str, Any]] = []
    for arm in ARMS:
        same_order = same_set = same_top1 = 0
        n = 0
        disc: list[str] = []
        for cid in ids:
            a, b = m00.get(cid), load_case(arm, cid)
            if not a or not b:
                continue
            n += 1
            if a["ids"] == b["ids"]:
                same_order += 1
            else:
                disc.append(cid)
            if set(a["labels"][:K]) == set(b["labels"][:K]):
                same_set += 1
            if (a["labels"][:1] or [""])[0] == (b["labels"][:1] or [""])[0]:
                same_top1 += 1

        row: dict[str, Any] = {
            "arm": arm,
            "n": n,
            "n_same_ordering": same_order,
            "n_same_top5_set": same_set,
            "n_same_top1_label": same_top1,
            "n_discordant": len(disc),
            "discordant_rate": round(len(disc) / n, 4) if n else None,
        }

        # full sample vs discordant-subset re-scoring
        for scope, subset in (("full", ids), ("discordant", disc)):
            pairs = []
            for cid in subset:
                gdx = str((gold_map.get(str(cid)) or {}).get("final_diagnosis") or "").strip()
                b = load_case(arm, cid)
                if not b or cid not in m00_ep:
                    continue
                eb = endpoints(b["labels"], gdx, cache)
                if eb:
                    pairs.append((m00_ep[cid], eb))
            block: dict[str, Any] = {"n": len(pairs)}
            for ep in ("acc1", "any_hit", "mrr"):
                A = [x[ep] for x, _ in pairs]
                B = [y[ep] for _, y in pairs]
                if not pairs:
                    block[ep] = None
                    continue
                bb = sum(1 for x, y in zip(A, B) if x > y)
                cc = sum(1 for x, y in zip(A, B) if x < y)
                block[ep] = {
                    "m00": round(statistics.fmean(A), 4),
                    "arm": round(statistics.fmean(B), 4),
                    "delta_m00_minus_arm": round(
                        statistics.fmean(A) - statistics.fmean(B), 4
                    ),
                    "n_m00_better": bb,
                    "n_arm_better": cc,
                    "p_sign_exact": round(exact_sign(bb, cc), 4),
                }
            row[scope] = block
        rows.append(row)
        print(
            f"  {arm}: disc={row['n_discordant']}/{row['n']} "
            f"same_set={row['n_same_top5_set']} same_top1={row['n_same_top1_label']}",
            flush=True,
        )

    # --- why the ceiling is low, and what n would be needed ---
    # A frequency-matched routing arm keeps n_merge fixed, so it can differ from
    # M00 on at most 2*min(n_merge, n_calib) cases. At an 82% firing rate that
    # ceiling is ~38/101 no matter how the arm is designed: the gate agreeing
    # with always-merge on 82% of cases is a property of the slice, not of the
    # contrast. Slices with a firing rate near 0.5 maximise the ceiling.
    m00_meta = [(m00[c] or {}).get("meta") or {} for c in ids if m00.get(c)]
    n_gate_on = sum(1 for m in m00_meta if m.get("gate_empirical"))
    n_tot = len(m00_meta)
    ceiling = 2 * min(n_gate_on, n_tot - n_gate_on)
    # An exact two-sided sign test with b unidirectional moves gives p = 2*2^-b,
    # so p < 0.05 needs b >= 6.
    b_needed = 6
    power = {
        "gate_firing_rate": round(n_gate_on / n_tot, 4) if n_tot else None,
        "n_gate_on": n_gate_on,
        "n_gate_off": n_tot - n_gate_on,
        "frequency_matched_discordance_ceiling": ceiling,
        "ceiling_note": (
            "Max cases a frequency-matched routing arm can differ on is "
            "2*min(n_merge, n_calib). AB10 already reaches most of it, so no "
            "redesign of a frequency-matched routing contrast can do better on "
            "this slice."
        ),
        "sign_test_moves_needed_for_p_lt_05": b_needed,
        "projection": [],
    }
    for r in rows:
        mv = (r["full"].get("mrr") or {}).get("n_m00_better")
        opp = (r["full"].get("mrr") or {}).get("n_arm_better")
        n_now = r["full"].get("n") or 0
        if mv is None or not n_now:
            continue
        if opp:
            need: Any = "not unidirectional; sign test needs a larger margin"
        elif mv == 0:
            need = "structural identity on this endpoint; no n suffices"
        elif mv >= b_needed:
            need = f"already significant at n={n_now}"
        else:
            need = int(round(n_now * b_needed / mv))
        power["projection"].append(
            {
                "arm": r["arm"],
                "open_mrr_moves_at_n100": mv,
                "open_mrr_moves_against": opp,
                "n_required_for_p_lt_05": need,
            }
        )

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "purpose": (
            "R1b channel audit for block-2 operator arms on MCR: how many cases "
            "can each arm move at all, and what do the endpoints say once the "
            "structurally-identical cases are removed."
        ),
        "judge": {"prompt_id": "mcr.diag_accuracy", "model": JUDGE_MODEL_SLUG, "k": K},
        "input": "pre_compat_joint (stored-compat config)",
        "saturation": saturation,
        "power": power,
        "arms": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("WROTE", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
