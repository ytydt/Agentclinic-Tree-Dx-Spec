#!/usr/bin/env python3
"""T1-08: pool → joint arbiter structural attribution controls.

Arms (DA seq100):
  1. offline_rrf_sc10     — zero LLM: RRF over persisted SC10 ranked lists
  2. sc10_union_arbiter   — union(SC10 top-k) → synthetic champions → arbiter
  3. b02_pool_arbiter     — B02 trace.candidates → synthetic champions → arbiter

Also emits a pointer for flat-stateful eval of c3_ab02_v1 (annotate already done).

Writes under analysis/tier1_1b_v1/ and runs/paper_v1/ablations_t108_*.json.
New LLM caches go under analysis/tier1_1b_v1/arbiter_cache/ (never touches
logs/diagnosisarena_d2_m01_v1 frozen trees).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
    _sp = str(_p)
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

import baseline_aggregate as agg  # noqa: E402
from baseline_common import SimpleCachedLLM  # noqa: E402

OUT = ROOT / "analysis" / "tier1_1b_v1"
SC10_TRACE = (
    ROOT
    / "runs/paper_v1/diagnosisarena_b02_compute_matched_sc10_v1"
    / "B02-flat-compute-matched-sc10"
    / "replicate_01"
    / "trace.jsonl"
)
B02_TRACE = (
    ROOT
    / "runs/paper_v1/diagnosisarena_b02_compute_matched_v1"
    / "B02-flat-compute-matched"
    / "replicate_01"
    / "trace.jsonl"
)
# Fallback if compute-matched path differs
B02_TRACE_ALT = (
    ROOT
    / "runs/paper_v1/diagnosisarena_d2_seq100_baselines"
    / "B02-flat-compute-matched"
    / "replicate_01"
    / "trace.jsonl"
)

JOINT_PROMPT = (
    ROOT
    / "src/agentclinic_tree_dx/prompts/l2_joint_champion_arbiter.txt"
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trace(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            cid = str(row.get("case_id") or "")
            out[cid] = row.get("trace") or {}
    return out


def offline_rrf(sc10: Mapping[str, Mapping[str, Any]], *, top_n: int = 5) -> dict[str, list[str]]:
    ranked = {}
    for cid, tr in sc10.items():
        samples = tr.get("samples") or []
        lists = [list(s.get("ranked") or []) for s in samples if s.get("ranked")]
        if not lists:
            continue
        ranked[cid] = agg.rrf_aggregate(lists, top_n=top_n)
    return ranked


def union_pool(sc10_case: Mapping[str, Any], *, max_n: int = 15) -> list[str]:
    seen = set()
    out = []
    for s in sc10_case.get("samples") or []:
        for name in s.get("ranked") or []:
            key = agg.normalize_disease_key(name)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(str(name).strip())
            if len(out) >= max_n:
                return out
    return out


def synthetic_champions(labels: Sequence[str]) -> list[dict[str, Any]]:
    champs = []
    for i, lab in enumerate(labels):
        champs.append(
            {
                "id": f"F{i+1}",
                "label": lab,
                "parent_id": "FLAT",
                "parent_label": "Flat candidate pool",
                "local_rank": i + 1,
                "local_score": 1.0 / (i + 1),
                "parent_posterior": 1.0,
                "explanatory_coverage": 0.0,
                "local_evidence_ids": [],
            }
        )
    return champs


def run_arbiter_on_pools(
    *,
    pools: Mapping[str, Sequence[str]],
    vignettes: Mapping[str, str],
    cache: SimpleCachedLLM,
    top_n: int = 5,
) -> dict[str, Any]:
    import eval_l2_joint_dynamic_pipeline as joint

    prompt = JOINT_PROMPT.read_text(encoding="utf-8")
    results = {}
    for cid, labels in pools.items():
        labs = [x for x in labels if str(x).strip()][:15]
        if not labs:
            continue
        champs = synthetic_champions(labs)
        # Minimal evidence stub so arbiter still runs
        facts = [{"id": "E0", "text": "case presentation", "label": "vignette"}]
        arb = joint._joint_arbitrate(
            cache=cache,
            module="L2JointArbiter_T108",
            prompt=prompt,
            case_text=vignettes.get(cid) or "",
            findings=facts,
            selected_facts=facts,
            champions=champs,
            include_prior=True,
            include_audit=False,
            context_mode="full",
            selector_effects=[],
        )
        ranking_ids = list(arb.get("ranking") or [])
        id2lab = {c["id"]: c["label"] for c in champs}
        ranked_labels = [id2lab[i] for i in ranking_ids if i in id2lab][:top_n]
        if not ranked_labels:
            ranked_labels = labs[:top_n]
        results[cid] = {
            "ranked": ranked_labels,
            "schema_valid": bool(arb.get("schema_valid")),
            "n_pool": len(labs),
        }
    return results


def load_vignettes_da() -> dict[str, str]:
    # Prefer subset normalized cases
    for p in (
        ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100/normalized_cases.json",
        ROOT / "data/benchmarks/diagnosisarena/subsets/d2_m01/normalized_cases.json",
        ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1/normalized_cases.json",
        ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/normalized_cases.json",
    ):
        if not p.is_file():
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        cases = doc.get("cases") or doc if isinstance(doc, list) else doc.get("cases") or []
        out = {}
        for c in cases:
            if not isinstance(c, Mapping):
                continue
            cid = str(c.get("id") or c.get("case_id") or "")
            text = str(c.get("case_text") or c.get("vignette") or "")
            if cid and text:
                out[cid] = text
        if out:
            return out
    return {}


def score_option_top1(
    ranked: Mapping[str, Sequence[str]],
) -> dict[str, Any]:
    """Lexical option match against DA gold from synonym_bind TSV if present."""
    tsv = ROOT / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv"
    # Also try metrics from main method
    from mapper_bind_repair import leaf_match_score

    gold: dict[str, str] = {}
    # Pull golds from at1_compat case_results
    cr_dirs = [
        ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1/case_results",
        ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results",
    ]
    for d in cr_dirs:
        if not d.is_dir():
            continue
        for fp in d.glob("*.json"):
            doc = json.loads(fp.read_text(encoding="utf-8"))
            g = str(
                doc.get("gold_diagnosis")
                or (
                    (doc.get("gold") or {}).get("final_diagnosis")
                    if isinstance(doc.get("gold"), Mapping)
                    else doc.get("gold")
                )
                or ""
            ).strip()
            # DA often has options; gold option text
            opts = doc.get("options") or []
            ans = doc.get("answer") or doc.get("gold_option")
            if not g and ans is not None and opts:
                try:
                    g = str(opts[int(ans)] if isinstance(ans, int) else ans)
                except Exception:
                    g = str(ans)
            if g:
                gold[fp.stem] = g
        if gold:
            break

    n = 0
    hits = 0
    for cid, labs in ranked.items():
        g = gold.get(cid)
        if not g or not labs:
            continue
        n += 1
        top = str(labs[0])
        try:
            if float(leaf_match_score(top, g)) >= 0.7:
                hits += 1
        except Exception:
            if top.strip().lower() == g.strip().lower():
                hits += 1
    return {"n": n, "hits": hits, "acc": (hits / n) if n else None, "n_gold": len(gold)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--skip-llm", action="store_true", help="Only offline RRF")
    ap.add_argument("--max-cases", type=int, default=100)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    sc10 = load_trace(SC10_TRACE)
    b02_path = B02_TRACE if B02_TRACE.is_file() else B02_TRACE_ALT
    b02 = load_trace(b02_path)
    print(f"[t108] sc10_cases={len(sc10)} b02_cases={len(b02)} b02_path={b02_path}", flush=True)

    rrf = offline_rrf(sc10, top_n=5)
    # Truncate
    cids = sorted(rrf)[: int(args.max_cases)]
    rrf = {k: rrf[k] for k in cids}
    rrf_score = score_option_top1(rrf)
    report: dict[str, Any] = {
        "created_at": _utc(),
        "offline_rrf_sc10": {"n": len(rrf), "score": rrf_score},
        "flat_stateful_note": {
            "run_dir": "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1",
            "status": "annotate complete; needs eval_projection + official_eval",
        },
    }
    (OUT / "t108_offline_rrf.json").write_text(
        json.dumps({"rrf": rrf, "score": rrf_score}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if args.skip_llm:
        (OUT / "t108_summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    vignettes = load_vignettes_da()
    print(f"[t108] vignettes={len(vignettes)}", flush=True)

    from agentclinic_tree_dx.llm_client import RobustLLMClient

    client = RobustLLMClient(model="meta-llama/llama-3.3-70b-instruct", temperature=0.0)
    cache_path = OUT / "arbiter_cache" / "t108_arbiter_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = SimpleCachedLLM(
        client, cache_path, model="meta-llama/llama-3.3-70b-instruct"
    )

    # SC10 union pools
    union_pools = {cid: union_pool(sc10[cid]) for cid in cids if cid in sc10}
    print(f"[t108] arbiter on sc10_union n={len(union_pools)}", flush=True)
    sc10_arb = run_arbiter_on_pools(pools=union_pools, vignettes=vignettes, cache=cache)
    sc10_ranked = {cid: v["ranked"] for cid, v in sc10_arb.items()}
    report["sc10_union_arbiter"] = {
        "n": len(sc10_arb),
        "score": score_option_top1(sc10_ranked),
        "n_schema_valid": sum(1 for v in sc10_arb.values() if v.get("schema_valid")),
    }

    # B02 candidate pools
    b02_pools = {}
    for cid in cids:
        tr = b02.get(cid) or {}
        cands = list(tr.get("candidates") or [])
        if cands:
            b02_pools[cid] = cands
    print(f"[t108] arbiter on b02_pool n={len(b02_pools)}", flush=True)
    b02_arb = run_arbiter_on_pools(pools=b02_pools, vignettes=vignettes, cache=cache)
    b02_ranked = {cid: v["ranked"] for cid, v in b02_arb.items()}
    report["b02_pool_arbiter"] = {
        "n": len(b02_arb),
        "score": score_option_top1(b02_ranked),
        "n_schema_valid": sum(1 for v in b02_arb.values() if v.get("schema_valid")),
    }

    # cache persists on every call; no separate flush
    (OUT / "t108_summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (ROOT / "runs/paper_v1/ablations_t108_pool_arbiter.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
