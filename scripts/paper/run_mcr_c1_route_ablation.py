#!/usr/bin/env python3
"""MCR C1 route ablation: same posterior pool → M00/AB07/AB10.

Why: DA AB07/AB10 vs compat_parallel deltas were marginal (<0.10 @1).
This script reuses MCR annotate trees (no frozen rewrite) and applies
decision-time operators on a shared posterior pool, then scores open Acc
via paper_aligned LLM judge.

Arms:
  M00_pool  — compat_parallel (FineCrowdGate → merge XOR both_l1fallback)
  AB07      — always-merge (heuristic synonymish)
  AB10      — frequency-matched random route (seed=20260727)

Protocol note:
  Paper M00 on MCR is stored ``final_ranking`` Acc≈0.50 (annotate-time compat
  on joint). That joint list is not persisted. This suite therefore compares
  operators on a **reconstructed posterior Top-N pool** (fair within-pool),
  and separately cites stored compat Acc as the paper anchor — do not mix
  the two rows as if they shared the same input ranking.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import adaptive_merge_siblings as merge  # noqa: E402
import baseline_common as bc  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402
import topk_calibration as calib  # noqa: E402
from build_eval_projection import (  # noqa: E402
    _as_ranking_rows,
    _dedup_pad_to_k,
    load_fixture_findings,
    load_tree_state,
    resolve_annotate_dir,
    top_leaf_posterior,
)
from run_ox_mcr_official_eval import run_eval  # noqa: E402

DEFAULT_RUN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
DEFAULT_PARQUET = (
    ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
)
SEED = 20260727
ARMS = ("M00", "AB07", "AB10")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _vignette(case_doc: Mapping[str, Any]) -> str:
    text = str(case_doc.get("case_text") or "")
    if "\nOptions:" in text:
        text = text.split("\nOptions:", 1)[0]
    return text.strip()


def _findings_list(
    fmap: Mapping[str, str] | None,
) -> list[dict[str, str]]:
    if not fmap:
        return []
    return [{"id": k, "text": v} for k, v in fmap.items()]


def route_on_pool(
    *,
    arm: str,
    case_doc: Mapping[str, Any],
    pool: Sequence[Mapping[str, Any]],
    k: int,
    dry_calib: bool,
    calib_cache: Any,
    force_merge: Optional[bool],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """MCR-pad dialect: merge pads back to K; calib returns shortlist padded to K."""
    pool_list = [dict(r) for r in pool]
    ranking = _as_ranking_rows(pool_list)
    meta: dict[str, Any] = {
        "arm": arm,
        "pool_len": len(pool_list),
        "k": k,
        "gate_empirical": None,
        "gate_applied": None,
        "branch": None,
    }
    if not pool_list:
        return [], {**meta, "fallback": "empty_pool"}

    gate = mcc.fine_crowd_gate(ranking)
    meta["gate_empirical"] = bool(gate.get("triggered"))

    if arm == "AB07":
        merge_info = merge.merge_ranking_ids(ranking)
        reps = mcc._rep_labels_from_merge(ranking, merge_info)
        by_id = {str(r.get("id")): r for r in pool_list}
        rep_ddx = []
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
        meta.update({
            "branch": "always_merge_pad",
            "gate_applied": True,
            "n_clusters": merge_info.get("n_clusters"),
            "n_reps_before_pad": len(rep_ddx),
        })
        return out, meta

    # M00_pool or AB10
    if arm == "AB10":
        if force_merge is None:
            raise ValueError("AB10 requires force_merge")
        triggered = bool(force_merge)
        meta["gate_random"] = triggered
    else:
        # M00 and default: empirical FineCrowdGate
        triggered = bool(gate.get("triggered"))

    meta["gate_applied"] = triggered
    if triggered:
        merge_info = gate.get("merge_info") or merge.merge_ranking_ids(ranking)
        reps = mcc._rep_labels_from_merge(ranking, merge_info)
        by_id = {str(r.get("id")): r for r in pool_list}
        rep_ddx = []
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
        meta["n_clusters"] = merge_info.get("n_clusters")
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
        vignette=vignette,
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
    out = _dedup_pad_to_k(ordered[:k], pool_list, k=k)
    meta["branch"] = "calib_only"
    meta["calib_mode"] = "live_both_l1fallback" if live else "dry_both_l1fallback"
    return out, meta


def build_arm_projections(
    *,
    annotate: Path,
    arm: str,
    pool_n: int,
    k: int,
    dry_calib: bool,
    force_by_cid: Mapping[str, bool],
    calib_cache: Any,
    findings_by_case: Mapping[str, Mapping[str, str]],
    out_subdir: str,
) -> dict[str, Any]:
    trees = annotate / "shared_trees"
    cases = annotate / "case_results"
    out_dir = annotate / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(p.stem for p in cases.glob("*.json"))
    n_gate = 0
    n_ok = 0
    for cid in ids:
        case_doc = _read_json(cases / f"{cid}.json")
        # attach vignette text if missing
        if not case_doc.get("case_text"):
            # try normalized later; empty ok for dry
            pass
        state = load_tree_state(trees / f"{cid}.json")
        pool = top_leaf_posterior(state, k=pool_n)
        vignette = _vignette(case_doc)
        findings = _findings_list(findings_by_case.get(cid))
        pred, meta = route_on_pool(
            arm=arm,
            case_doc=case_doc,
            pool=pool,
            k=k,
            dry_calib=dry_calib,
            calib_cache=calib_cache,
            force_merge=force_by_cid.get(cid) if arm == "AB10" else None,
            vignette=vignette,
            findings=findings,
        )
        if meta.get("gate_empirical"):
            n_gate += 1
        pred_ddx = [
            {
                "rank": i,
                "id": str(r.get("id") or ""),
                "label": str(r.get("label") or ""),
                "posterior": float(r.get("posterior") or 0.0),
                "parent_id": str(r.get("parent_id") or ""),
            }
            for i, r in enumerate(pred, start=1)
        ]
        doc = {
            "case_id": cid,
            "ddx_source": f"c1_{arm.lower()}_pool{pool_n}",
            "pred_ddx": pred_ddx,
            "meta": meta,
            "created_at": _utc(),
        }
        _write_json(out_dir / f"{cid}.json", doc)
        n_ok += 1
    summary = {
        "arm": arm,
        "n": n_ok,
        "pool_n": pool_n,
        "k": k,
        "dry_calib": dry_calib,
        "gate_empirical_rate": round(n_gate / max(1, n_ok), 4),
        "out_subdir": out_subdir,
        "created_at": _utc(),
    }
    _write_json(out_dir / "_summary.json", summary)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--pool-n", type=int, default=15, help="posterior pool size before route")
    ap.add_argument("--ddx-k", type=int, default=5, help="final shortlist K")
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--live-calib", action="store_true", help="live both_l1fallback on calib branch")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--skip-reasoning-recall", action="store_true", default=True)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    args = ap.parse_args()

    annotate = resolve_annotate_dir(Path(args.run_dir))
    dry_calib = not bool(args.live_calib)
    pool_n = int(args.pool_n)
    k = int(args.ddx_k)

    # Backup checksums of trees (lightweight)
    bak = ROOT / "backups" / f"c1_mcr_preflight_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    bak.mkdir(parents=True, exist_ok=True)
    (bak / "note.txt").write_text(
        f"MCR C1 route ablation\nrun_dir={args.run_dir}\npool_n={pool_n} k={k}\n",
        encoding="utf-8",
    )
    # only manifest case ids + tree hashes, not full copy (trees large; policy: no overwrite)
    ids = sorted(p.stem for p in (annotate / "case_results").glob("*.json"))
    hashes = []
    for cid in ids:
        tp = annotate / "shared_trees" / f"{cid}.json"
        if tp.is_file():
            import hashlib
            h = hashlib.sha256(tp.read_bytes()).hexdigest()
            hashes.append(f"{h}  shared_trees/{cid}.json")
    (bak / "sha256sums_trees.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    print(f"[backup] {bak} n_trees={len(hashes)}", flush=True)

    # Load findings / vignettes
    fixture = annotate / "finding_fixture_v1.json"
    findings_by_case = load_fixture_findings(fixture if fixture.is_file() else None)
    # enrich case_text from normalized_cases if present
    norm = annotate / "normalized_cases.json"
    text_by_id: dict[str, str] = {}
    if norm.is_file():
        doc = _read_json(norm)
        for c in doc.get("cases") or ():
            text_by_id[str(c.get("id"))] = str(c.get("case_text") or "")

    # Precompute empirical gates for AB10 mask (pool-dependent)
    trees = annotate / "shared_trees"
    cases = annotate / "case_results"
    empirical: list[bool] = []
    cids: list[str] = []
    for cid in ids:
        state = load_tree_state(trees / f"{cid}.json")
        pool = top_leaf_posterior(state, k=pool_n)
        ranking = _as_ranking_rows(pool)
        gate = mcc.fine_crowd_gate(ranking)
        empirical.append(bool(gate.get("triggered")))
        cids.append(cid)
    random_mask = mcc.assign_random_route_mask(empirical, seed=int(args.seed))
    force_by_cid = {cid: bool(m) for cid, m in zip(cids, random_mask)}
    mask_doc = {
        "seed": int(args.seed),
        "pool_n": pool_n,
        "n": len(cids),
        "n_empirical_true": int(sum(empirical)),
        "n_random_true": int(sum(random_mask)),
        "cases": [
            {"case_id": cid, "gate_empirical": bool(e), "gate_random": bool(r)}
            for cid, e, r in zip(cids, empirical, random_mask)
        ],
    }
    mask_path = annotate / f"c1_mcr_random_route_mask_pool{pool_n}.json"
    _write_json(mask_path, mask_doc)
    print(
        f"[AB10] empirical_true={mask_doc['n_empirical_true']} "
        f"random_true={mask_doc['n_random_true']} pool_n={pool_n}",
        flush=True,
    )

    cache_path = annotate / "cache" / f"c1_mcr_topk_calib_pool{pool_n}.json"
    calib_cache = None
    if not dry_calib:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        calib_cache = bc.SimpleCachedLLM(
            RobustLLMClient(
                model="meta-llama/llama-3.3-70b-instruct",
                call_timeout=120,
                max_retries=4,
                timeout_retry_cap=2,
                temperature=0.0,
            ),
            cache_path,
            "meta-llama/llama-3.3-70b-instruct",
        )

    # Patch case_text into a lightweight overlay via rewriting only our projection meta
    # (case_results untouched). Pass vignette from normalized_cases in route.
    class _CaseProxy(dict):
        pass

    proj_summaries = []
    for arm in args.arms:
        sub = f"eval_projection_c1_mcr_{arm.lower()}_pool{pool_n}"
        if (annotate / sub).exists():
            print(f"[rebuild] {sub}", flush=True)
        # inject case_text into a copy for vignette only inside loop
        # monkey: wrap build to set case_doc case_text
        orig_build = build_arm_projections

        def _build_with_text(arm=arm, sub=sub):
            trees_p = annotate / "shared_trees"
            cases_p = annotate / "case_results"
            out_dir = annotate / sub
            out_dir.mkdir(parents=True, exist_ok=True)
            n_gate = 0
            n_ok = 0
            for cid in ids:
                case_doc = _read_json(cases_p / f"{cid}.json")
                if text_by_id.get(cid):
                    case_doc = {**case_doc, "case_text": text_by_id[cid]}
                state = load_tree_state(trees_p / f"{cid}.json")
                pool = top_leaf_posterior(state, k=pool_n)
                pred, meta = route_on_pool(
                    arm=arm,
                    case_doc=case_doc,
                    pool=pool,
                    k=k,
                    dry_calib=dry_calib,
                    calib_cache=calib_cache,
                    force_merge=force_by_cid.get(cid) if arm == "AB10" else None,
                    vignette=_vignette(case_doc),
                    findings=_findings_list(findings_by_case.get(cid)),
                )
                if meta.get("gate_empirical"):
                    n_gate += 1
                pred_ddx = [
                    {
                        "rank": i,
                        "id": str(r.get("id") or ""),
                        "label": str(r.get("label") or ""),
                        "posterior": float(r.get("posterior") or 0.0),
                        "parent_id": str(r.get("parent_id") or ""),
                    }
                    for i, r in enumerate(pred, start=1)
                ]
                _write_json(
                    out_dir / f"{cid}.json",
                    {
                        "case_id": cid,
                        "ddx_source": f"c1_{arm.lower()}_pool{pool_n}",
                        "pred_ddx": pred_ddx,
                        "meta": meta,
                        "created_at": _utc(),
                    },
                )
                n_ok += 1
            summary = {
                "arm": arm,
                "n": n_ok,
                "pool_n": pool_n,
                "k": k,
                "dry_calib": dry_calib,
                "gate_empirical_rate": round(n_gate / max(1, n_ok), 4),
                "out_subdir": sub,
                "created_at": _utc(),
            }
            _write_json(out_dir / "_summary.json", summary)
            return summary

        s = _build_with_text()
        proj_summaries.append(s)
        print(f"[proj] {arm}: {s}", flush=True)

    eval_summaries: dict[str, Any] = {}
    if not args.skip_eval:
        for arm in args.arms:
            sub = f"eval_projection_c1_mcr_{arm.lower()}_pool{pool_n}"
            out_name = f"official_eval_llm_c1_mcr_{arm.lower()}_pool{pool_n}"
            print(f"[eval] {arm} → {out_name}", flush=True)
            summary = run_eval(
                dataset="medcasereasoning",
                run_dir=Path(args.run_dir),
                subset_parquet=Path(args.subset_parquet),
                judge_kind="llm",
                ddx_k=k,
                workers=int(args.workers),
                build_projection=False,
                resume_projection=False,
                resume_scores=True,
                nlg_metrics=False,
                case_ids=[],
                write_md=True,
                out_name=out_name,
                skip_reasoning_recall=bool(args.skip_reasoning_recall),
                ddx_source="posterior",
                pool_n=pool_n,
                projection_subdir=sub,
                dry_calib=True,
                mac_predictions=None,
                mac_trace=None,
                live_closed_mac=False,
            )
            eval_summaries[arm] = summary

    # Aggregate report snippet
    report = {
        "created_at": _utc(),
        "run_dir": str(args.run_dir),
        "backup": str(bak),
        "pool_n": pool_n,
        "ddx_k": k,
        "dry_calib": dry_calib,
        "seed": int(args.seed),
        "workers": int(args.workers),
        "mask": {
            "n_empirical_true": mask_doc["n_empirical_true"],
            "n_random_true": mask_doc["n_random_true"],
        },
        "projections": proj_summaries,
        "evals": {},
        "paper_m00_stored_compat_acc": 0.50,
        "protocol": (
            "Within-pool C1 on posterior Top-N; paper M00 stored compat Acc=0.50 "
            "uses annotate-time joint (not persisted) — cite separately."
        ),
    }
    for arm, s in eval_summaries.items():
        metrics = (s or {}).get("metrics") or {}
        acc = metrics.get("diagnostic_accuracy_single_trajectory")
        report["evals"][arm] = {
            "metrics": metrics,
            "acc": acc,
            "out_name": f"official_eval_llm_c1_mcr_{arm.lower()}_pool{pool_n}",
        }

    # Lexical any-hit@K vs gold (secondary; not primary Acc)
    try:
        from mapper_bind_repair import leaf_match_score
        from transfer_eval import io_gold
        from transfer_eval.matching import DEFAULT_LEXICAL_THRESHOLD

        gold_map = io_gold.load_gold(
            "medcasereasoning", Path(args.subset_parquet), case_ids=ids
        )
        thr = float(DEFAULT_LEXICAL_THRESHOLD)
        for arm in args.arms:
            sub = annotate / f"eval_projection_c1_mcr_{arm.lower()}_pool{pool_n}"
            hits = 0
            top1 = 0
            rr_sum = 0.0
            n = 0
            for cid in ids:
                proj = _read_json(sub / f"{cid}.json")
                gold = gold_map.get(str(cid)) or {}
                gdx = str(gold.get("final_diagnosis") or "").strip()
                labels = [
                    str(r.get("label") or "").strip()
                    for r in (proj.get("pred_ddx") or [])
                    if str(r.get("label") or "").strip()
                ]
                if not gdx or not labels:
                    continue
                n += 1
                if float(leaf_match_score(labels[0], gdx)) >= thr:
                    top1 += 1
                first = next(
                    (
                        i
                        for i, lab in enumerate(labels[:k], start=1)
                        if float(leaf_match_score(lab, gdx)) >= thr
                    ),
                    None,
                )
                if first is not None:
                    hits += 1
                    rr_sum += 1.0 / first
            report.setdefault("lexical", {})[arm] = {
                "n": n,
                "lex_acc_at_1": round(top1 / n, 4) if n else None,
                "lex_any_hit_at_k": round(hits / n, 4) if n else None,
                "lex_rr_at_k": round(rr_sum / n, 4) if n else None,
            }
    except Exception as exc:  # noqa: BLE001
        report["lexical_error"] = f"{type(exc).__name__}: {exc}"

    out_json = (
        ROOT / "runs/paper_v1" / f"ablations_c1_mcr_pool{pool_n}_results.json"
    )
    tag = "live" if not dry_calib else "dry"
    out_json = (
        ROOT / "runs/paper_v1" / f"ablations_c1_mcr_pool{pool_n}_{tag}_results.json"
    )
    _write_json(out_json, report)
    print(json.dumps({
        "evals": {a: e.get("acc") for a, e in report["evals"].items()},
        "lexical": report.get("lexical"),
        "mask": report["mask"],
        "path": str(out_json),
    }, indent=2, ensure_ascii=False))
    print(f"[wrote] {out_json}", flush=True)


if __name__ == "__main__":
    main()
