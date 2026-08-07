#!/usr/bin/env python3
"""MCR C1 route ablation on recovered pre-compat joint (stored-compat config).

Uses ``annotate/pre_compat_joint/`` middleware — NOT posterior pools and NOT
post-compat ``final_ranking_*``.

Arms (same operators as DA C1 / paper stored-compat dialect):
  M00   — compat_parallel (FineCrowdGate → merge XOR both_l1fallback)
  AB05  — raw joint (no decision-time route)
  AB07  — always-merge (force merge branch; heuristic synonymish)
  AB08  — calib-only (force both_l1fallback)
  AB09  — compat_serial_safe (merge→support_rerank XOR calib)
  AB10  — frequency-matched random route (seed=20260727)
  AB10b — count-matched semantics-blind merge (same gate, same |pi|, random members)
  AB10c — AB10b + rank-1 cluster size also matched
  AB11  — concept_id always-merge
  AB20  — compat_parallel with calib arm ``both`` (no L1 soft prior)

Example:
  PYTHONPATH=src:scripts:scripts/paper \\
  python3 scripts/paper/run_mcr_c1_precompat_ablation.py --live-calib --workers 50 \\
    --arms AB05 AB08 AB09 AB11 AB20
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")

import baseline_common as bc  # noqa: E402
import merge_calib_compat as mcc  # noqa: E402
import pre_compat_joint as pcj  # noqa: E402
from build_eval_projection import load_fixture_findings, resolve_annotate_dir  # noqa: E402
from run_ox_mcr_official_eval import run_eval  # noqa: E402

DEFAULT_RUN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
DEFAULT_PARQUET = (
    ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
)
SEED = 20260727
ARMS = (
    "M00", "AB05", "AB07", "AB08", "AB09", "AB10", "AB10b", "AB10c", "AB11", "AB20",
)
BLIND_SEED = 20260728
TAG = "precompat"


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


def _findings_list(fmap: Mapping[str, str] | None) -> list[dict[str, str]]:
    if not fmap:
        return []
    return [{"id": k, "text": v} for k, v in fmap.items()]


def _labels_to_pred_ddx(
    labels: Sequence[Mapping[str, Any]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(labels[:k], start=1):
        out.append({
            "rank": i,
            "id": str(row.get("id") or ""),
            "label": str(row.get("label") or ""),
            "posterior": float(row.get("posterior") or 0.0),
            "parent_id": str(row.get("parent") or row.get("parent_id") or ""),
        })
    return out


def route_on_precompat(
    *,
    arm: str,
    case_doc: Mapping[str, Any],
    ranking_labels: Sequence[Mapping[str, Any]],
    k: int,
    dry_calib: bool,
    calib_cache: Any,
    force_merge: Optional[bool],
    vignette: str,
    findings: Sequence[Mapping[str, Any]],
    blind_seed: Optional[int] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels = [dict(r) for r in ranking_labels]
    gate = mcc.fine_crowd_gate(labels)
    meta: dict[str, Any] = {
        "arm": arm,
        "input": "pre_compat_joint",
        "n_pre": len(labels),
        "k": k,
        "gate_empirical": bool(gate.get("triggered")),
    }
    if not labels:
        return [], {**meta, "branch": "empty_joint", "fallback": "empty_pre_compat"}

    live = (not dry_calib) and calib_cache is not None
    dry_run = not live
    common = dict(
        case=case_doc,
        ranking_labels=labels,
        vignette=vignette,
        findings=list(findings),
        option_maps=None,
        gold_leaf_ids=[],
        cache=calib_cache,
        dry_run=dry_run,
        k=k,
    )

    if arm == "AB05":
        # Raw joint: no merge / no calib (DA ``ours`` / 关决策期路由).
        ordered = [str(r.get("id")) for r in labels if r.get("id")]
        pred = _labels_to_pred_ddx(labels, k=k)
        meta.update({
            "branch": "raw_joint",
            "mode": "ours",
            "gate_applied": False,
            "ordered_ids": ordered[:k],
            "calib_mode": None,
        })
        return pred, meta

    if arm == "AB07":
        routed = mcc.run_compat_parallel(
            **common, force_merge=True, mode_name="always_merge"
        )
    elif arm == "AB08":
        routed = mcc.run_compat_parallel(
            **common, force_merge=False, mode_name="calib_only_force"
        )
    elif arm == "AB09":
        routed = mcc.run_compat_serial_safe(**common)
    elif arm == "AB10":
        if force_merge is None:
            raise ValueError("AB10 requires force_merge")
        routed = mcc.run_compat_random_route(**common, force_merge=bool(force_merge))
        meta["gate_random"] = bool(force_merge)
    elif arm in {"AB10b", "AB10c"}:
        if blind_seed is None:
            raise ValueError(f"{arm} requires blind_seed")
        routed = mcc.run_count_matched_blind_merge(
            **common,
            seed=int(blind_seed),
            match_top1=(arm == "AB10c"),
        )
        meta["blind_partition"] = routed.get("blind_partition")
    elif arm == "AB11":
        routed = mcc.run_concept_id_merge(**common)
    elif arm == "AB20":
        routed = mcc.run_compat_parallel_no_l1_prior(**common)
    elif arm == "M00":
        routed = mcc.run_compat_parallel(**common)
    else:
        raise ValueError(f"unknown arm: {arm}")

    out_labels = list(routed.get("ranking_labels") or [])
    pred = _labels_to_pred_ddx(out_labels, k=k)
    if not pred and routed.get("ordered_ids"):
        by_id = {str(r.get("id")): r for r in labels}
        rebuilt = []
        for i, lid in enumerate(routed.get("ordered_ids") or [], start=1):
            src = by_id.get(str(lid)) or {"id": lid, "label": lid, "parent": ""}
            rebuilt.append({**dict(src), "rank": i})
            if len(rebuilt) >= k:
                break
        pred = _labels_to_pred_ddx(rebuilt, k=k)

    branch = str(routed.get("branch") or routed.get("mode") or "")
    meta.update({
        "branch": branch,
        "mode": routed.get("mode"),
        "gate_applied": routed.get("gate_applied"),
        "ordered_ids": list(routed.get("ordered_ids") or []),
        "concept_key_coverage": routed.get("concept_key_coverage"),
        "calib_mode": (
            "live_both_l1fallback"
            if live and branch in {"calib_only", "merge_then_support"}
            else (
                "dry_both_l1fallback"
                if (not live) and branch in {"calib_only", "merge_then_support"}
                else None
            )
        ),
    })
    return pred, meta


def _is_merge_like(branch: str) -> bool:
    return branch in {
        "merge_only",
        "always_merge",
        "concept_id_merge",
        "merge_then_support",
    }


def _is_calib_like(branch: str) -> bool:
    return branch in {"calib_only", "merge_then_support"}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument(
        "--blind-seed",
        type=int,
        default=BLIND_SEED,
        help="base seed for AB10b/AB10c count-matched random partitions",
    )
    ap.add_argument("--live-calib", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--skip-reasoning-recall", action="store_true", default=True)
    ap.add_argument("--arms", nargs="+", default=list(ARMS))
    ap.add_argument("--precompat-subdir", default=pcj.DEFAULT_SUBDIR)
    ap.add_argument(
        "--merge-prior-results",
        type=Path,
        default=None,
        help="merge evals/lexical from a prior results JSON (e.g. earlier M00/AB07/AB10 run)",
    )
    ap.add_argument(
        "--report-arms",
        nargs="+",
        default=None,
        help="arms to include in lexical/top1 report (default: --arms ∪ prior)",
    )
    ap.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="results JSON path (default: runs/paper_v1/ablations_c1_mcr_{TAG}_{live|dry}_results.json)",
    )
    args = ap.parse_args()

    annotate = resolve_annotate_dir(Path(args.run_dir))
    pre_dir = annotate / str(args.precompat_subdir)
    if not pre_dir.is_dir():
        raise SystemExit(
            f"missing pre_compat middleware at {pre_dir}; "
            "run extract_pre_compat_joint_from_cache.py first"
        )

    dry_calib = not bool(args.live_calib)
    # Artifact namespace must separate dry from live: the two differ only in the calib
    # branch, so sharing a directory would silently overwrite the archived live run.
    # The AB10 mask and calib cache stay on the shared TAG so both modes route
    # identically and only the calib branch differs.
    art_tag = TAG if not dry_calib else f"{TAG}_dry"
    k = int(args.ddx_k)
    ids = sorted(p.stem for p in (annotate / "case_results").glob("*.json"))

    bak = ROOT / "backups" / f"c1_mcr_precompat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    bak.mkdir(parents=True, exist_ok=True)
    (bak / "note.txt").write_text(
        f"MCR C1 precompat ablation\nrun_dir={args.run_dir}\nk={k}\nlive={not dry_calib}\n",
        encoding="utf-8",
    )
    hashes = []
    for cid in ids:
        tp = pre_dir / f"{cid}.json"
        if tp.is_file():
            h = hashlib.sha256(tp.read_bytes()).hexdigest()
            hashes.append(f"{h}  pre_compat_joint/{cid}.json")
    (bak / "sha256sums_precompat.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    print(f"[backup] {bak} n_precompat={len(hashes)}", flush=True)

    fixture = annotate / "finding_fixture_v1.json"
    findings_by_case = load_fixture_findings(fixture if fixture.is_file() else None)
    text_by_id: dict[str, str] = {}
    norm = annotate / "normalized_cases.json"
    if norm.is_file():
        doc = _read_json(norm)
        for c in doc.get("cases") or ():
            text_by_id[str(c.get("id"))] = str(c.get("case_text") or "")

    # AB10 mask from empirical FineCrowdGate on pre-compat labels
    empirical: list[bool] = []
    cids: list[str] = []
    for cid in ids:
        _, labels, _ = pcj.load_pre_compat_inputs(
            annotate, cid, subdir=str(args.precompat_subdir)
        )
        gate = mcc.fine_crowd_gate(labels)
        empirical.append(bool(gate.get("triggered")))
        cids.append(cid)
    random_mask = mcc.assign_random_route_mask(empirical, seed=int(args.seed))
    force_by_cid = {cid: bool(m) for cid, m in zip(cids, random_mask)}
    mask_doc = {
        "seed": int(args.seed),
        "input": "pre_compat_joint",
        "n": len(cids),
        "n_empirical_true": int(sum(empirical)),
        "n_random_true": int(sum(random_mask)),
        "cases": [
            {"case_id": cid, "gate_empirical": bool(e), "gate_random": bool(r)}
            for cid, e, r in zip(cids, empirical, random_mask)
        ],
    }
    mask_path = annotate / f"c1_mcr_random_route_mask_{TAG}.json"
    _write_json(mask_path, mask_doc)
    print(
        f"[AB10] empirical_true={mask_doc['n_empirical_true']} "
        f"random_true={mask_doc['n_random_true']} (precompat)",
        flush=True,
    )

    cache_path = annotate / "cache" / f"c1_mcr_topk_calib_{TAG}.json"
    # Seed from open_acc ablation cache if present (annotate-time calib prompts)
    seed_cache = annotate / "cache" / "open_acc_ablation_topk_calib.json"
    if not dry_calib and seed_cache.is_file() and not cache_path.is_file():
        cache_path.write_bytes(seed_cache.read_bytes())
        print(f"[cache] seeded from {seed_cache.name}", flush=True)

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

    proj_summaries: list[dict[str, Any]] = []
    for arm in args.arms:
        sub = f"eval_projection_c1_mcr_{arm.lower()}_{art_tag}"
        out_dir = annotate / sub
        out_dir.mkdir(parents=True, exist_ok=True)
        n_gate = 0
        n_merge = 0
        n_calib = 0
        n_ok = 0
        n_match_stored = 0
        for cid in ids:
            case_doc = _read_json(annotate / "case_results" / f"{cid}.json")
            if text_by_id.get(cid):
                case_doc = {**case_doc, "case_text": text_by_id[cid]}
            _, labels, art = pcj.load_pre_compat_inputs(
                annotate, cid, subdir=str(args.precompat_subdir)
            )
            pred, meta = route_on_precompat(
                arm=arm,
                case_doc=case_doc,
                ranking_labels=labels,
                k=k,
                dry_calib=dry_calib,
                calib_cache=calib_cache,
                force_merge=force_by_cid.get(cid) if arm == "AB10" else None,
                vignette=_vignette(case_doc),
                findings=_findings_list(findings_by_case.get(cid)),
                blind_seed=(
                    (int(args.blind_seed) * 1_000_003 + int(hashlib.sha256(
                        cid.encode("utf-8")
                    ).hexdigest()[:8], 16)) % (2**31)
                    if arm in {"AB10b", "AB10c"}
                    else None
                ),
            )
            if meta.get("gate_empirical"):
                n_gate += 1
            br = str(meta.get("branch") or "")
            if _is_merge_like(br):
                n_merge += 1
            if br == "calib_only":
                n_calib += 1
            stored = list(
                ((art.get("post_compat_ref") or {}).get("final_ranking_ids") or [])
            )
            replayed = list(meta.get("ordered_ids") or [])
            if arm == "M00" and stored == replayed:
                n_match_stored += 1
            _write_json(
                out_dir / f"{cid}.json",
                {
                    "case_id": cid,
                    "ddx_source": f"c1_{arm.lower()}_{art_tag}",
                    "pred_ddx": pred,
                    "meta": meta,
                    "created_at": _utc(),
                },
            )
            n_ok += 1
        covs = []
        blind_rows: list[dict[str, Any]] = []
        for cid in ids:
            doc = _read_json(out_dir / f"{cid}.json")
            c = (doc.get("meta") or {}).get("concept_key_coverage")
            if c is not None:
                covs.append(float(c))
            bp = (doc.get("meta") or {}).get("blind_partition")
            if bp and bp.get("applied"):
                blind_rows.append({"case_id": cid, **bp})
        summary = {
            "arm": arm,
            "n": n_ok,
            "k": k,
            "dry_calib": dry_calib,
            "input": "pre_compat_joint",
            "gate_empirical_rate": round(n_gate / max(1, n_ok), 4),
            "n_merge_branch": n_merge,
            "n_calib_branch": n_calib,
            "out_subdir": sub,
            "created_at": _utc(),
        }
        if covs:
            summary["mean_concept_key_coverage"] = round(sum(covs) / len(covs), 4)
        if blind_rows:
            free = [r for r in blind_rows if int(r.get("dof") or 1) > 1]
            differ = [r for r in blind_rows if not r.get("identical_to_synonym")]
            summary["blind_partition_power"] = {
                "n_merge_branch": len(blind_rows),
                "n_dof_gt1_perturbable": len(free),
                "n_forced_identical": len(blind_rows) - len(free),
                "n_partition_differs": len(differ),
                "perturbable_case_ids": [r["case_id"] for r in free],
                "note": (
                    "Cases with dof<=1 are byte-identical to the main method by "
                    "construction; full-cohort deltas are diluted by them."
                ),
            }
        if arm == "M00":
            summary["n_exact_match_stored_final_ranking"] = n_match_stored
            summary["exact_match_stored_rate"] = round(n_match_stored / max(1, n_ok), 4)
        _write_json(out_dir / "_summary.json", summary)
        proj_summaries.append(summary)
        print(f"[proj] {arm}: {summary}", flush=True)

    eval_summaries: dict[str, Any] = {}
    if not args.skip_eval:
        for arm in args.arms:
            sub = f"eval_projection_c1_mcr_{arm.lower()}_{art_tag}"
            out_name = f"official_eval_llm_c1_mcr_{arm.lower()}_{art_tag}"
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
                pool_n=0,
                projection_subdir=sub,
                dry_calib=True,
                mac_predictions=None,
                mac_trace=None,
                live_closed_mac=False,
            )
            eval_summaries[arm] = summary

    prior: dict[str, Any] = {}
    if args.merge_prior_results and Path(args.merge_prior_results).is_file():
        prior = _read_json(Path(args.merge_prior_results))
        print(f"[merge] prior={args.merge_prior_results}", flush=True)

    report_arms = list(args.report_arms or [])
    if not report_arms:
        report_arms = list(dict.fromkeys(list(args.arms) + list((prior.get("evals") or {}))))
    # Prefer canonical order
    order = [a for a in ARMS if a in report_arms]
    order += [a for a in report_arms if a not in order]
    report_arms = order

    report: dict[str, Any] = {
        "created_at": _utc(),
        "run_dir": str(args.run_dir),
        "backup": str(bak),
        "input": "pre_compat_joint",
        "ddx_k": k,
        "dry_calib": dry_calib,
        "seed": int(args.seed),
        "workers": int(args.workers),
        "arms_run": list(args.arms),
        "arms_reported": list(report_arms),
        "mask": {
            "n_empirical_true": mask_doc["n_empirical_true"],
            "n_random_true": mask_doc["n_random_true"],
            "path": str(mask_path),
        },
        "projections": list((prior.get("projections") or [])) + proj_summaries,
        "evals": dict(prior.get("evals") or {}),
        "paper_m00_stored_compat_acc": 0.50,
        "protocol": (
            "Full C1 operator suite on recovered annotate-time pre-compat joint "
            "(stored-compat config). Fair within-joint comparison vs M00."
        ),
    }
    for arm, s in eval_summaries.items():
        metrics = (s or {}).get("metrics") or {}
        acc = metrics.get("diagnostic_accuracy_single_trajectory")
        report["evals"][arm] = {
            "metrics": metrics,
            "acc": acc,
            "out_name": f"official_eval_llm_c1_mcr_{arm.lower()}_{art_tag}",
        }

    # Lexical secondary + Top-1 agreement vs M00 (all reported arms with projections)
    try:
        from mapper_bind_repair import leaf_match_score
        from transfer_eval import io_gold
        from transfer_eval.matching import DEFAULT_LEXICAL_THRESHOLD

        gold_map = io_gold.load_gold(
            "medcasereasoning", Path(args.subset_parquet), case_ids=ids
        )
        thr = float(DEFAULT_LEXICAL_THRESHOLD)
        m00_top1: dict[str, str] = {}
        m00_sub = annotate / f"eval_projection_c1_mcr_m00_{art_tag}"
        if m00_sub.is_dir():
            for cid in ids:
                fp = m00_sub / f"{cid}.json"
                if not fp.is_file():
                    continue
                proj = _read_json(fp)
                labs = proj.get("pred_ddx") or []
                m00_top1[cid] = str((labs[0] or {}).get("id") or "") if labs else ""

        lexical = dict(prior.get("lexical") or {})
        top1_agree = dict(prior.get("top1_agree_m00") or {})
        for arm in report_arms:
            sub = annotate / f"eval_projection_c1_mcr_{arm.lower()}_{art_tag}"
            if not sub.is_dir():
                continue
            hits = 0
            top1 = 0
            rr_sum = 0.0
            n = 0
            agree = 0
            n_agree = 0
            for cid in ids:
                fp = sub / f"{cid}.json"
                if not fp.is_file():
                    continue
                proj = _read_json(fp)
                gold = gold_map.get(str(cid)) or {}
                gdx = str(gold.get("final_diagnosis") or "").strip()
                labels = [
                    str(r.get("label") or "").strip()
                    for r in (proj.get("pred_ddx") or [])
                    if str(r.get("label") or "").strip()
                ]
                ids_pred = [
                    str(r.get("id") or "").strip()
                    for r in (proj.get("pred_ddx") or [])
                    if str(r.get("id") or "").strip()
                ]
                if gdx and labels:
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
                if arm != "M00" and m00_top1:
                    n_agree += 1
                    if (ids_pred[0] if ids_pred else "") == m00_top1.get(cid, ""):
                        agree += 1
            lexical[arm] = {
                "n": n,
                "lex_acc_at_1": round(top1 / n, 4) if n else None,
                "lex_any_hit_at_k": round(hits / n, 4) if n else None,
                "lex_rr_at_k": round(rr_sum / n, 4) if n else None,
            }
            if arm != "M00" and n_agree:
                top1_agree[arm] = round(agree / n_agree, 4)
        report["lexical"] = lexical
        report["top1_agree_m00"] = top1_agree
        # deltas vs M00 Acc
        m00_acc = (report["evals"].get("M00") or {}).get("acc")
        if m00_acc is not None:
            report["delta_vs_m00"] = {
                arm: (
                    None
                    if (report["evals"].get(arm) or {}).get("acc") is None
                    else round(float((report["evals"][arm]["acc"])) - float(m00_acc), 4)
                )
                for arm in report_arms
                if arm != "M00"
            }
    except Exception as exc:  # noqa: BLE001
        report["lexical_error"] = f"{type(exc).__name__}: {exc}"

    tag = "live" if not dry_calib else "dry"
    out_json = (
        Path(args.out_json)
        if args.out_json is not None
        else ROOT / "runs/paper_v1" / f"ablations_c1_mcr_{TAG}_{tag}_results.json"
    )
    report["not_for_paper"] = "mcr_val_seq100_v2" in str(args.run_dir)
    _write_json(out_json, report)
    print(
        json.dumps(
            {
                "evals": {a: (report["evals"].get(a) or {}).get("acc") for a in report_arms},
                "delta_vs_m00": report.get("delta_vs_m00"),
                "lexical": report.get("lexical"),
                "top1_agree_m00": report.get("top1_agree_m00"),
                "mask": report["mask"],
                "path": str(out_json),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"[wrote] {out_json}", flush=True)


if __name__ == "__main__":
    main()
