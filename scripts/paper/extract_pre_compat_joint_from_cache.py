#!/usr/bin/env python3
"""Rebuild ``annotate/pre_compat_joint/`` middleware from l2 LLM cache.

C2-level recovery for subsequent ablations (AB07/AB10 on stored-compat config).

Does NOT modify frozen/, case_results/, or shared_trees/.

Example:
  PYTHONPATH=src:scripts:scripts/paper \\
  python3 scripts/paper/extract_pre_compat_joint_from_cache.py \\
    --run-dir logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1 \\
    --verify-replay
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import pre_compat_joint as pcj  # noqa: E402


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--run-dir",
        type=Path,
        required=True,
        help="run root (…/compat_synonym_v1) or annotate dir",
    )
    ap.add_argument(
        "--out-subdir",
        default=pcj.DEFAULT_SUBDIR,
        help="under annotate/ (default: pre_compat_joint)",
    )
    ap.add_argument(
        "--verify-replay",
        action="store_true",
        help="replay compat_parallel (dry) and compare to stored final_ranking",
    )
    ap.add_argument(
        "--live-calib",
        action="store_true",
        help="with --verify-replay: live both_l1fallback for calib branch",
    )
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--case-id", action="append", default=[])
    args = ap.parse_args()

    annotate = pcj.resolve_annotate_dir(Path(args.run_dir))
    out_dir = annotate / str(args.out_subdir)
    if out_dir.resolve() == (annotate / "frozen").resolve():
        raise SystemExit("refusing to write into frozen/")

    case_dir = annotate / "case_results"
    if args.case_id:
        ids = [str(x) for x in args.case_id]
    else:
        ids = sorted(p.stem for p in case_dir.glob("*.json"))

    print(f"[pre_compat] annotate={annotate} n={len(ids)} out={out_dir}", flush=True)

    method_counts: dict[str, int] = {}
    failed: list[str] = []
    empty_joint: list[str] = []
    verify_rows: list[dict[str, Any]] = []

    calib_cache = None
    if args.verify_replay and args.live_calib:
        import baseline_common as bc
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        cache_path = out_dir / "cache" / "verify_replay_topk_calib.json"
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

    for cid in ids:
        art = pcj.recover_case(annotate, cid)
        pcj.save_artifact(annotate, art, subdir=str(args.out_subdir))
        method = str((art.get("recovery") or {}).get("method") or "?")
        selected = str((art.get("recovery") or {}).get("selected_by") or "")
        method_counts[f"{method}:{selected}"] = method_counts.get(f"{method}:{selected}", 0) + 1
        n_pre = int((art.get("pre_compat") or {}).get("n_leaves") or 0)
        if (art.get("recovery") or {}).get("method") == "failed":
            failed.append(cid)
        if n_pre == 0:
            empty_joint.append(cid)

        if args.verify_replay:
            case = {}
            cp = annotate / "case_results" / f"{cid}.json"
            if cp.is_file():
                case = json.loads(cp.read_text(encoding="utf-8"))
            vignette = str(case.get("case_text") or "")
            if "\nOptions:" in vignette:
                vignette = vignette.split("\nOptions:", 1)[0].strip()
            # findings optional
            routed = pcj.replay_compat_parallel(
                art,
                case_doc=case,
                vignette=vignette,
                findings=[],
                cache=calib_cache,
                dry_run=not bool(args.live_calib),
                k=int(args.k),
            )
            ver = pcj.verify_replay_against_stored(art, routed)
            ver["case_id"] = cid
            ver["n_pre"] = n_pre
            verify_rows.append(ver)

    manifest = {
        "schema_version": pcj.SCHEMA_VERSION,
        "artifact": pcj.ARTIFACT_NAME,
        "created_at": _utc(),
        "annotate_dir": str(annotate),
        "out_subdir": str(args.out_subdir),
        "n_cases": len(ids),
        "method_counts": method_counts,
        "n_failed": len(failed),
        "failed_case_ids": failed,
        "n_empty_joint": len(empty_joint),
        "empty_joint_case_ids": empty_joint,
        "verify_replay": bool(args.verify_replay),
        "live_calib": bool(args.live_calib),
    }
    if verify_rows:
        n_exact = sum(1 for r in verify_rows if r.get("exact_match"))
        n_top1 = sum(1 for r in verify_rows if r.get("top1_match"))
        nonempty = [r for r in verify_rows if r.get("stored") or r.get("replayed")]
        by_path: dict[str, dict[str, int]] = {}
        for r in verify_rows:
            key = str(r.get("stored_path") or r.get("branch") or "unknown")
            bucket = by_path.setdefault(key, {"n": 0, "n_exact": 0, "n_top1": 0})
            bucket["n"] += 1
            if r.get("exact_match"):
                bucket["n_exact"] += 1
            if r.get("top1_match"):
                bucket["n_top1"] += 1
        manifest["verify"] = {
            "n": len(verify_rows),
            "n_exact_match": n_exact,
            "n_top1_match": n_top1,
            "exact_rate": round(n_exact / max(1, len(verify_rows)), 4),
            "top1_rate": round(n_top1 / max(1, len(verify_rows)), 4),
            "n_nonempty": len(nonempty),
            "by_stored_path": {
                k: {
                    **v,
                    "exact_rate": round(v["n_exact"] / max(1, v["n"]), 4),
                    "top1_rate": round(v["n_top1"] / max(1, v["n"]), 4),
                }
                for k, v in sorted(by_path.items())
            },
            "mismatches": [
                {
                    "case_id": r["case_id"],
                    "stored": r["stored"],
                    "replayed": r["replayed"],
                    "branch": r.get("branch"),
                    "stored_path": r.get("stored_path"),
                }
                for r in verify_rows
                if not r.get("exact_match")
            ][:30],
        }

    # label quality on recovered artifacts
    n_empty_lab = 0
    n_lab_rows = 0
    for cid in ids:
        art = pcj.load_artifact(annotate, cid, subdir=str(args.out_subdir))
        for row in (art.get("pre_compat") or {}).get("final_ranking_labels") or []:
            n_lab_rows += 1
            if not str(row.get("label") or "").strip():
                n_empty_lab += 1
    manifest["label_quality"] = {
        "n_label_rows": n_lab_rows,
        "n_empty_label": n_empty_lab,
        "empty_label_rate": round(n_empty_lab / max(1, n_lab_rows), 4),
    }
    pcj._write_json(out_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"[wrote] {out_dir}/manifest.json + {len(ids)} case artifacts", flush=True)
    if failed:
        raise SystemExit(f"failed recovery for {len(failed)} cases: {failed}")


if __name__ == "__main__":
    main()
