#!/usr/bin/env python3
"""C3 MCR dedupe-site suite (AB04/AB06) on mcr_val_seq100.

Shared no-semantic-dedupe trees under c3_shared_no_dedupe_v1/, then:
  AB04 — route off (granularity-mode=off)
  AB06 — route on  (granularity-mode=compat)

Isolation: logs/medcasereasoning_mcr_val_seq100_v1/c3_ab{04,06}_v1/
Does not mutate compat_synonym_v1. No synonym_bind on mapper.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_M00 = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1"
DEFAULT_OUT_ROOT = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1"
DEFAULT_RESULTS = ROOT / "runs/paper_v1/ablations_c3_mcr_raw.json"

# Mutated in main() from CLI (keep module-level names for helpers).
M00 = DEFAULT_M00
SUBSET = DEFAULT_SUBSET
OUT_ROOT = DEFAULT_OUT_ROOT
SHARED = OUT_ROOT / "c3_shared_no_dedupe_v1"

ARMS: dict[str, dict[str, Any]] = {
    "ab04": {
        "dir": "c3_ab04_v1",
        "label": "AB04 no tree semantic dedupe + route off",
        "granularity_mode": "off",
    },
    "ab06": {
        "dir": "c3_ab06_v1",
        "label": "AB06 no tree semantic dedupe + route on (compat)",
        "granularity_mode": "compat",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_ids(n: int | None) -> list[str]:
    ids = [
        ln.strip()
        for ln in (SUBSET / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if n is not None:
        ids = ids[: int(n)]
    return ids


def _env() -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }


def _copy_vp_freeze(dst_root: Path) -> None:
    src = M00 / "frozen" / "vignette_parser_frozen.json"
    if not src.is_file():
        raise FileNotFoundError(src)
    dst = dst_root / "frozen"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst / "vignette_parser_frozen.json")


def _trees_ready(tree_dir: Path, case_ids: Sequence[str]) -> bool:
    if not tree_dir.is_dir():
        return False
    return all((tree_dir / f"{cid}.json").is_file() for cid in case_ids)


def _build_shared_trees(
    case_ids: Sequence[str],
    *,
    workers: int,
    model: str,
    resume: bool,
) -> int:
    """Build / reuse shared no-dedupe trees + P5 (VP copied from M00)."""
    SHARED.mkdir(parents=True, exist_ok=True)
    cases_json = SUBSET / "normalized_cases.json"
    shutil.copy2(cases_json, SHARED / "normalized_cases.json")
    _copy_vp_freeze(SHARED)
    tree_dir = SHARED / "frozen" / "shared_trees"
    if resume and _trees_ready(tree_dir, case_ids) and (
        SHARED / "frozen" / "p5_headline_frozen.json"
    ).is_file():
        print("[c3/mcr] SHARED trees+P5 HIT →", SHARED, flush=True)
        return 0
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(cases_json),
        "--cases", ",".join(case_ids),
        "--output-dir", str(SHARED),
        "--workers", str(workers),
        "--model", model,
        "--no-tree-semantic-dedupe",
        "--l1-axis-mode", "adaptive",
        "--from-stage", "trees",
        "--to-stage", "p5",
        "--resume",
    ]
    print("RUN shared trees/p5:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=_env())


def _seed_arm_from_shared(out: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    # VP
    shutil.copy2(
        SHARED / "frozen" / "vignette_parser_frozen.json",
        frozen / "vignette_parser_frozen.json",
    )
    # trees
    src_trees = SHARED / "frozen" / "shared_trees"
    dst_trees = frozen / "shared_trees"
    dst_trees.mkdir(parents=True, exist_ok=True)
    n_trees = 0
    for cid in case_ids:
        sp = src_trees / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, dst_trees / sp.name)
            n_trees += 1
    # p5
    for name in ("p5_headline_frozen.json",):
        sp = SHARED / "frozen" / name
        if sp.is_file():
            shutil.copy2(sp, frozen / name)
    src_audit = SHARED / "frozen" / "p5_audit"
    dst_audit = frozen / "p5_audit"
    dst_audit.mkdir(parents=True, exist_ok=True)
    n_audit = 0
    if src_audit.is_dir():
        for cid in case_ids:
            sp = src_audit / f"{cid}.json"
            if sp.is_file():
                shutil.copy2(sp, dst_audit / sp.name)
                n_audit += 1
    shutil.copy2(SUBSET / "normalized_cases.json", out / "normalized_cases.json")
    # Clear annotate resume so arms don't collide
    ann = out / "annotate"
    if ann.exists():
        man = ann / "stage_manifest.json"
        if man.is_file():
            man.unlink()
    return {"n_trees": n_trees, "n_p5_audit": n_audit}


def _run_arm(
    out: Path,
    case_ids: Sequence[str],
    *,
    granularity_mode: str,
    workers: int,
    model: str,
) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(out / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", granularity_mode,
        "--l1-calib", "off",
        "--no-tree-semantic-dedupe",
        "--l1-axis-mode", "adaptive",
        "--from-stage", "annotate",
        "--to-stage", "mapper",
        "--fixed-l1-budget", "6",
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", "6",
        "--mapper-mode", "typed_llm_disagreement_rag",
        "--resume",
        # NO --synonym-bind-repair
    ]
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=_env())


def _open_eval(out: Path, *, workers: int) -> dict[str, Any] | None:
    """Run MCR open Acc eval (compat ddx source); non-fatal on failure."""
    eval_script = ROOT / "scripts/paper/run_ox_mcr_official_eval.py"
    parquet = SUBSET / "cases.parquet"
    if not eval_script.is_file() or not parquet.is_file():
        return None
    cmd = [
        sys.executable, "-u",
        str(eval_script),
        "--dataset", "medcasereasoning",
        "--run-dir", str(out),
        "--subset-parquet", str(parquet),
        "--judge", "llm",
        "--ddx-source", "compat",
        "--build-projection",
        "--skip-reasoning-recall",
        "--out-name", "official_eval_llm_compat",
        "--workers", str(min(12, max(1, int(workers)))),
        "--resume",
        "--resume-scores",
    ]
    print("EVAL:", " ".join(cmd), flush=True)
    code = subprocess.call(cmd, cwd=str(ROOT), env=_env())
    # summary may live under annotate/<out-name>/
    candidates = [
        out / "annotate" / "official_eval_llm_compat" / "summary.json",
        out / "official_eval_llm_compat" / "summary.json",
    ]
    for summary in candidates:
        if summary.is_file():
            return {
                "exit_code": code,
                "summary_path": str(summary),
                "summary": json.loads(summary.read_text(encoding="utf-8")),
            }
    ds = out / "annotate" / "downstream_summary.json"
    if ds.is_file():
        return {
            "exit_code": code,
            "downstream_summary": json.loads(ds.read_text(encoding="utf-8")),
        }
    return {"exit_code": code}


def _mapper_or_down(out: Path) -> dict[str, Any]:
    out_d: dict[str, Any] = {}
    for rel in (
        "annotate/mapper/summary.json",
        "annotate/downstream_summary.json",
    ):
        p = out / rel
        if p.is_file():
            out_d[rel] = json.loads(p.read_text(encoding="utf-8"))
    return out_d


def main() -> int:
    global M00, SUBSET, OUT_ROOT, SHARED

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="ab04,ab06")
    ap.add_argument("--n-cases", type=int, default=100)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument(
        "--m00",
        type=Path,
        default=DEFAULT_M00,
        help="main-method run root (VP freeze source); default v1 compat_synonym_v1",
    )
    ap.add_argument(
        "--subset",
        type=Path,
        default=DEFAULT_SUBSET,
        help="subset dir with case_ids.txt + normalized_cases.json + cases.parquet",
    )
    ap.add_argument(
        "--out-root",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help="parent for c3_shared_no_dedupe_v1/ and c3_ab{04,06}_v1/",
    )
    ap.add_argument(
        "--results-json",
        type=Path,
        default=DEFAULT_RESULTS,
        help="aggregate JSON output (do not overwrite paper v1 unless intended)",
    )
    ap.add_argument("--skip-shared-trees", action="store_true")
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    args = ap.parse_args()

    M00 = Path(args.m00).resolve()
    SUBSET = Path(args.subset).resolve()
    OUT_ROOT = Path(args.out_root).resolve()
    SHARED = OUT_ROOT / "c3_shared_no_dedupe_v1"
    results_json = Path(args.results_json).resolve()

    case_ids = _load_ids(args.n_cases)
    wanted = [a.strip().lower() for a in str(args.arms).split(",") if a.strip()]
    results: dict[str, Any] = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "workers": int(args.workers),
        "synonym_bind": False,
        "m00": str(M00),
        "subset": str(SUBSET),
        "out_root": str(OUT_ROOT),
        "shared_trees": str(SHARED),
        "m00_mcr_acc": None,
        "note_ab04_vs_plan059": (
            "Plan historical ~0.59 was AB05 (dedupe on + route off), not AB04"
        ),
        "not_for_paper": "mcr_val_seq100_v2" in str(OUT_ROOT),
        "arms": {},
    }

    code_shared = 0
    if not args.skip_shared_trees and not args.skip_annotate:
        code_shared = _build_shared_trees(
            case_ids,
            workers=int(args.workers),
            model=str(args.model),
            resume=True,
        )
        if code_shared != 0:
            print("shared trees failed", code_shared, file=sys.stderr)
            return code_shared

    for key in wanted:
        if key not in ARMS:
            print("unknown arm", key, file=sys.stderr)
            return 2
        spec = ARMS[key]
        out = OUT_ROOT / spec["dir"]
        prep = {}
        if not args.skip_annotate:
            prep = _seed_arm_from_shared(out, case_ids)
        launch = {
            "arm": key,
            "label": spec["label"],
            "granularity_mode": spec["granularity_mode"],
            "no_tree_semantic_dedupe": True,
            "prep": prep,
            "created_at": _utc(),
        }
        _write_json(out / "c3_launch.json", launch)
        code = 0
        if not args.skip_annotate:
            code = _run_arm(
                out,
                case_ids,
                granularity_mode=str(spec["granularity_mode"]),
                workers=int(args.workers),
                model=str(args.model),
            )
        metrics = _mapper_or_down(out)
        eval_meta = None
        if not args.skip_eval and code == 0:
            try:
                eval_meta = _open_eval(out, workers=int(args.workers))
            except Exception as exc:  # noqa: BLE001
                eval_meta = {"error": "%s: %s" % (type(exc).__name__, exc)}
        results["arms"][key] = {
            "label": spec["label"],
            "output_dir": str(out),
            "exit_code": code,
            "granularity_mode": spec["granularity_mode"],
            "metrics": metrics,
            "open_eval": eval_meta,
            "synonym_bind": False,
        }
        print(json.dumps({key: results["arms"][key]}, indent=2, ensure_ascii=False), flush=True)

    _write_json(results_json, results)
    print("WROTE", results_json, flush=True)
    bad = [k for k, v in results["arms"].items() if int(v.get("exit_code") or 0) != 0]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
