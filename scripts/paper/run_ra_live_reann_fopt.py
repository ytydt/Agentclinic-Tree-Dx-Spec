#!/usr/bin/env python3
"""RareArena live re-annotate under locked F budgets (Acc side-run).

Copies frozen VP/trees/P5 from the F6 transfer run, re-runs annotate with the
Stage-2 locked budgets, then LLM Acc @ compat/ddx_k=5.

Default locked combo = formal_combo from audit_ra_budget_recalib.py
(L1=4, local=4, between=2, cand=6) — same integers OX locked when Acc-flat.
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
DEFAULT_SRC = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1"
DEFAULT_OUT = (
    ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_noemit_fopt_live_v1"
)
DEFAULT_RECALIB = ROOT / "analysis/transfer_metrics_v1/ra_budget_recalib.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _load_ids(subset: Path) -> list[str]:
    return [
        ln.strip()
        for ln in (subset / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]


def _locked_from_recalib(path: Path | None) -> dict[str, int]:
    default = {
        "l1_evidence_budget": 4,
        "l2_local_evidence_budget": 4,
        "l2_between_evidence_budget": 2,
        "l2_candidate_max_per_live_family": 6,
    }
    if path is None or not path.is_file():
        return default
    doc = _read_json(path)
    fc = doc.get("formal_combo") or {}
    return {
        "l1_evidence_budget": int(fc.get("l1_evidence_budget", 4)),
        "l2_local_evidence_budget": int(fc.get("l2_local_evidence_budget", 4)),
        "l2_between_evidence_budget": int(fc.get("l2_between_evidence_budget", 2)),
        "l2_candidate_max_per_live_family": int(
            fc.get("l2_candidate_max_per_live_family", 6)
        ),
    }


def _copy_frozen(src: Path, out: Path, case_ids: Sequence[str]) -> None:
    src_f = src / "frozen"
    dst_f = out / "frozen"
    dst_f.mkdir(parents=True, exist_ok=True)
    for name in ("vignette_parser_frozen.json", "p5_headline_frozen.json"):
        p = src_f / name
        if p.is_file():
            shutil.copy2(p, dst_f / name)
    for sub in ("shared_trees", "p5_audit"):
        s = src_f / sub
        d = dst_f / sub
        d.mkdir(parents=True, exist_ok=True)
        if not s.is_dir():
            continue
        for cid in case_ids:
            sp = s / ("%s.json" % cid)
            if sp.is_file():
                shutil.copy2(sp, d / sp.name)


def _prepare_annotate(out: Path, case_ids: Sequence[str], src: Path, subset: Path) -> None:
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    src_trees = out / "frozen" / "shared_trees"
    dst_trees = ann / "shared_trees"
    dst_trees.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = src_trees / ("%s.json" % cid)
        if sp.is_file():
            shutil.copy2(sp, dst_trees / sp.name)
    p5 = out / "frozen" / "p5_headline_frozen.json"
    if p5.is_file():
        shutil.copy2(p5, ann / "p5_headline_frozen.json")
    man = ann / "stage_manifest.json"
    if man.is_file():
        man.unlink()
    for nc_src in (
        src / "annotate" / "normalized_cases.json",
        subset / "normalized_cases.json",
    ):
        if nc_src.is_file():
            shutil.copy2(nc_src, out / "normalized_cases.json")
            shutil.copy2(nc_src, ann / "normalized_cases.json")
            break
    for name in ("finding_fixture_v1.json",):
        s = src / "annotate" / name
        if s.is_file():
            shutil.copy2(s, ann / name)


def _seed_caches(src: Path, out: Path, case_ids: Sequence[str]) -> int:
    n = 0
    src_c = src / "annotate" / "cache"
    if not src_c.is_dir():
        return 0
    for cid in case_ids:
        s = src_c / cid
        if not s.is_dir():
            continue
        d = out / "annotate" / "cache" / cid
        if d.exists():
            continue
        shutil.copytree(s, d)
        n += 1
    return n


def _run_annotate(
    out: Path,
    case_ids: Sequence[str],
    subset: Path,
    locked: Mapping[str, int],
    *,
    workers: int,
    model: str,
) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(subset / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--synonym-bind-repair",
        "--from-stage", "annotate",
        "--to-stage", "annotate",
        "--fixed-l1-budget", str(locked["l1_evidence_budget"]),
        "--l2-local-evidence-budget", str(locked["l2_local_evidence_budget"]),
        "--l2-between-evidence-budget", str(locked["l2_between_evidence_budget"]),
        "--l2-candidate-max-per-live-family", str(
            locked["l2_candidate_max_per_live_family"]
        ),
        "--resume",
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        # Cap at 4096 so a 2× bump on truncated posts stays ≤8192 (Google hard max).
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "4096",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _run_llm_acc(out: Path, subset: Path, *, workers: int) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "rarearena",
        "--run-dir", str(out),
        "--subset-parquet", str(subset / "cases.parquet"),
        "--judge", "llm",
        "--skip-reasoning-recall",
        "--ddx-k", "5",
        "--workers", str(workers),
        "--ddx-source", "compat",
        "--build-projection",
        "--projection-subdir", "eval_projection_compat",
        "--out-name", "official_eval_llm_compat",
    ]
    env = {**os.environ, "PYTHONPATH": "src:scripts/paper:scripts"}
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--recalib-json", type=Path, default=DEFAULT_RECALIB)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument("--skip-eval", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    src = Path(args.source_run)
    out = Path(args.out_dir)
    subset = Path(args.subset_dir)
    case_ids = _load_ids(subset)
    locked = _locked_from_recalib(Path(args.recalib_json))
    out.mkdir(parents=True, exist_ok=True)

    meta = {
        "created_at": _utc(),
        "source_run": str(src),
        "out_dir": str(out),
        "n_cases": len(case_ids),
        "locked_budget": locked,
        "protocol": "ra_live_reann_noemit_fopt_v1",
    }
    _write_json(out / "live_reann_launch.json", meta)
    print(json.dumps(meta, indent=2, ensure_ascii=False), flush=True)

    if not args.skip_annotate:
        _copy_frozen(src, out, case_ids)
        _prepare_annotate(out, case_ids, src, subset)
        n_cache = _seed_caches(src, out, case_ids)
        print("seeded_caches=%d" % n_cache, flush=True)
        rc = _run_annotate(
            out, case_ids, subset, locked,
            workers=int(args.workers), model=str(args.model),
        )
        if rc != 0:
            return rc

    if not args.skip_eval:
        if Path("/home/wanghongyi/clashctl/clashon.sh").is_file():
            subprocess.call(
                ["bash", "/home/wanghongyi/clashctl/clashon.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        rc = _run_llm_acc(out, subset, workers=int(args.judge_workers))
        if rc != 0:
            return rc

    summary_path = (
        out / "annotate" / "official_eval_llm_compat" / "summary.json"
    )
    if summary_path.is_file():
        m = (_read_json(summary_path).get("metrics") or {})
        print(
            json.dumps(
                {
                    "fopt_acc": m.get("diagnostic_accuracy_single_trajectory"),
                    "hits": m.get("n_diagnostic_hits"),
                    "summary": str(summary_path),
                    "locked_budget": locked,
                },
                indent=2,
                ensure_ascii=False,
            ),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
