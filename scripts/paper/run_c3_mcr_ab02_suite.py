#!/usr/bin/env python3
"""C3 MCR AB02 (flat / no L1) on mcr_val_seq100_v1 and/or v2.

Mirrors DA ``run_c3_hierarchy_suite.py`` AB02: rewrite M00 trees to a single FLAT
L1 parent (keep_leaves=False so annotate regenerates L2), then annotate only
with ``--l1-axis-mode flat``. MCR Prompt-7 Acc reads compat ``final_ranking``
from annotate (``--ddx-source compat``); DA-style option mapper is skipped.

Isolation (does not mutate M00):
  logs/medcasereasoning_mcr_val_seq100_v{1,2}/c3_ab02_v1/

Example:
  PYTHONPATH=src:scripts:scripts/paper python3 -u \\
    scripts/paper/run_c3_mcr_ab02_suite.py --slices v1,v2 --workers 25
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
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import c3_l1_axis  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
ARM_DIR = "c3_ab02_v1"

SLICE_CFG = {
    "v1": {
        "subset": ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
        "m00": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
        "out_root": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1",
    },
    "v2": {
        "subset": ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2",
        "m00": ROOT / "logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1",
        "out_root": ROOT / "logs/medcasereasoning_mcr_val_seq100_v2",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src:scripts:scripts/paper"
    return env


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_ids(subset: Path, n: int | None) -> list[str]:
    ids = [
        ln.strip()
        for ln in (subset / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if n is not None:
        ids = ids[: int(n)]
    return ids


def _resolve_tree_src(m00: Path) -> Path:
    for cand in (
        m00 / "annotate" / "shared_trees",
        m00 / "frozen" / "shared_trees",
    ):
        if cand.is_dir() and any(cand.glob("*.json")):
            return cand
    raise FileNotFoundError(f"no shared_trees under {m00}")


def _seed_from_m00(out: Path, m00: Path, subset: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    """Copy VP/P5/fixtures from M00; copy trees then rewrite to flat."""
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen"
    ann = out / "annotate"
    frozen.mkdir(parents=True, exist_ok=True)
    ann.mkdir(parents=True, exist_ok=True)

    # normalized cases
    shutil.copy2(subset / "normalized_cases.json", out / "normalized_cases.json")
    shutil.copy2(subset / "normalized_cases.json", ann / "normalized_cases.json")

    # vignette parser freeze
    for name in ("vignette_parser_frozen.json",):
        for src_root in (m00 / "frozen", m00 / "annotate", m00):
            sp = src_root / name
            if sp.is_file():
                shutil.copy2(sp, frozen / name)
                break

    # p5
    for name in ("p5_headline_frozen.json",):
        for src_root in (m00 / "frozen", m00 / "annotate", m00):
            sp = src_root / name
            if sp.is_file():
                shutil.copy2(sp, frozen / name)
                shutil.copy2(sp, ann / name)
                break
    for src_audit in (m00 / "frozen" / "p5_audit", m00 / "annotate" / "p5_audit"):
        if not src_audit.is_dir():
            continue
        for dst in (frozen / "p5_audit", ann / "p5_audit"):
            dst.mkdir(parents=True, exist_ok=True)
            n_audit = 0
            for cid in case_ids:
                sp = src_audit / f"{cid}.json"
                if sp.is_file():
                    shutil.copy2(sp, dst / sp.name)
                    n_audit += 1
        break
    else:
        n_audit = 0

    # fixtures
    for name in ("finding_fixture_v1.json",):
        for src_root in (m00 / "annotate", m00, m00 / "frozen"):
            sp = src_root / name
            if sp.is_file():
                shutil.copy2(sp, out / name)
                shutil.copy2(sp, ann / name)
                break

    # trees → flat rewrite
    src_trees = _resolve_tree_src(m00)
    dst_frozen = frozen / "shared_trees"
    if dst_frozen.is_dir():
        shutil.rmtree(dst_frozen)
    dst_frozen.mkdir(parents=True, exist_ok=True)
    n_trees = 0
    for cid in case_ids:
        sp = src_trees / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, dst_frozen / sp.name)
            n_trees += 1
    axis_meta = c3_l1_axis.rewrite_tree_dir(
        dst_frozen,
        "flat",
        case_ids=case_ids,
        max_l1=6,
        keep_leaves=False,
    )
    dst_ann = ann / "shared_trees"
    if dst_ann.is_dir():
        shutil.rmtree(dst_ann)
    dst_ann.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = dst_frozen / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, dst_ann / sp.name)

    # optional: seed annotate caches from M00 (BFS/VP reusable; L2 will miss)
    n_cache = 0
    for cid in case_ids:
        for src_root in (m00 / "annotate" / "cache", m00 / "cache"):
            s = src_root / cid
            if s.is_dir():
                d = ann / "cache" / cid
                if not d.exists():
                    shutil.copytree(s, d)
                    n_cache += 1
                break

    man = ann / "stage_manifest.json"
    if man.is_file():
        man.unlink()

    return {
        "n_trees": n_trees,
        "n_p5_audit": n_audit,
        "n_cache": n_cache,
        "tree_src": str(src_trees),
        "axis": axis_meta,
    }


def _run_annotate(
    out: Path,
    case_ids: Sequence[str],
    *,
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
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--from-stage", "annotate",
        # MCR Prompt-7 Acc reads compat final_ranking from annotate; DA-style
        # option mapper is unnecessary and was stalling behind the local proxy.
        "--to-stage", "annotate",
        "--fixed-l1-budget", "6",
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", "6",
        "--l1-bfs-preset", "p5_anti_anchor_direct",
        "--l1-axis-mode", "flat",
        "--resume",
    ]
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=_env())


def _open_eval(out: Path, subset: Path, *, workers: int) -> dict[str, Any]:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "medcasereasoning",
        "--run-dir", str(out),
        "--subset-parquet", str(subset / "cases.parquet"),
        "--judge", "llm",
        "--ddx-source", "compat",
        "--build-projection",
        "--skip-reasoning-recall",
        "--out-name", "official_eval_llm_compat",
        "--workers", str(min(25, max(1, int(workers)))),
        "--resume",
        "--resume-scores",
    ]
    print("EVAL:", " ".join(cmd), flush=True)
    code = subprocess.call(cmd, cwd=str(ROOT), env=_env())
    summary_path = out / "annotate" / "official_eval_llm_compat" / "summary.json"
    meta: dict[str, Any] = {"exit_code": code, "summary_path": str(summary_path)}
    if summary_path.is_file():
        meta["summary"] = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = meta["summary"].get("metrics") or {}
        meta["acc"] = metrics.get("diagnostic_accuracy_single_trajectory")
        meta["n_hits"] = metrics.get("n_diagnostic_hits")
        meta["n_scored"] = metrics.get("n_cases") or meta["summary"].get("n_cases_scored")
    return meta


def _m00_acc(m00: Path) -> dict[str, Any]:
    summary = m00 / "annotate" / "official_eval_llm_compat" / "summary.json"
    if not summary.is_file():
        return {}
    doc = json.loads(summary.read_text(encoding="utf-8"))
    metrics = doc.get("metrics") or {}
    return {
        "acc": metrics.get("diagnostic_accuracy_single_trajectory"),
        "n_hits": metrics.get("n_diagnostic_hits"),
        "n_scored": metrics.get("n_cases") or doc.get("n_cases_scored"),
        "summary_path": str(summary),
    }


def run_slice(
    tag: str,
    *,
    workers: int,
    model: str,
    n_cases: int | None,
    skip_annotate: bool,
    skip_eval: bool,
) -> dict[str, Any]:
    cfg = SLICE_CFG[tag]
    subset = cfg["subset"]
    m00 = cfg["m00"]
    out = cfg["out_root"] / ARM_DIR
    case_ids = _load_ids(subset, n_cases)
    result: dict[str, Any] = {
        "slice": tag,
        "label": "AB02 flat / no L1",
        "l1_axis_mode": "flat",
        "output_dir": str(out),
        "m00": str(m00),
        "subset": str(subset),
        "n_cases": len(case_ids),
        "m00_eval": _m00_acc(m00),
        "created_at": _utc(),
    }
    prep = {}
    if not skip_annotate:
        prep = _seed_from_m00(out, m00, subset, case_ids)
        result["prep"] = prep
        _write_json(out / "c3_launch.json", {
            "arm": "ab02",
            "label": "AB02 flat / no L1",
            "l1_axis_mode": "flat",
            "granularity_mode": "compat",
            "synonym_bind": True,
            "prep": prep,
            "created_at": _utc(),
        })
        code = _run_annotate(out, case_ids, workers=workers, model=model)
        result["annotate_exit"] = code
        if code != 0:
            return result
    if not skip_eval:
        result["open_eval"] = _open_eval(out, subset, workers=workers)
    _write_json(out / "ab02_suite_summary.json", result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slices", default="v1,v2", help="comma list: v1,v2")
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--n-cases", type=int, default=None)
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument(
        "--results-json",
        type=Path,
        default=ROOT / "analysis/mcr200_ab02_v1/suite_results.json",
    )
    args = ap.parse_args()

    wanted = [s.strip().lower() for s in str(args.slices).split(",") if s.strip()]
    for tag in wanted:
        if tag not in SLICE_CFG:
            print("unknown slice", tag, file=sys.stderr)
            return 2

    results: dict[str, Any] = {
        "created_at": _utc(),
        "arm": "ab02",
        "label": "AB02 flat / no L1",
        "workers": int(args.workers),
        "model": args.model,
        "slices": {},
    }
    for tag in wanted:
        print(f"\n===== SLICE {tag} =====", flush=True)
        results["slices"][tag] = run_slice(
            tag,
            workers=int(args.workers),
            model=str(args.model),
            n_cases=args.n_cases,
            skip_annotate=bool(args.skip_annotate),
            skip_eval=bool(args.skip_eval),
        )
        acc = (results["slices"][tag].get("open_eval") or {}).get("acc")
        m00 = (results["slices"][tag].get("m00_eval") or {}).get("acc")
        print(f"[slice {tag}] AB02 Acc={acc}  M00 Acc={m00}", flush=True)

    out_json = Path(args.results_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    _write_json(out_json, results)
    print("wrote", out_json, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
