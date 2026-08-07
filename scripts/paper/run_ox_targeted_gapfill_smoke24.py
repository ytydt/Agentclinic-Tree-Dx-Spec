#!/usr/bin/env python3
"""OX seq24 live smoke: standard compat+synonym stack + targeted L2 gapfill.

Convention mirrors DA pilot24 (first live smoke before escalate): take the first
24 ids from ``ox_seq100_v1``, reuse frozen VP/trees/P5 from the seq100 transfer
run, re-annotate with ``--targeted-l2-gapfill``, then mapper synonym_bind.

Default arm: hybrid ``ALL_B_b1`` (research_only overlay; production_promote=false).
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

DEFAULT_SUBSET = ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1"
DEFAULT_SRC = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_OUT = ROOT / "logs/open_xddx_ox_seq24_smoke_v1/compat_synonym_gapfill_v1"
DEFAULT_ARM = "ALL_B_b1"
DEFAULT_N = 24


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_case_ids(subset_dir: Path, n: int) -> list[str]:
    ids_path = subset_dir / "case_ids.txt"
    if not ids_path.is_file():
        raise FileNotFoundError(ids_path)
    ids = [
        line.strip()
        for line in ids_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(ids) < n:
        raise ValueError("subset has only %d ids; need %d" % (len(ids), n))
    return ids[:n]


def _copy_frozen(src_run: Path, out: Path, case_ids: Sequence[str]) -> None:
    src_frozen = src_run / "frozen"
    if not src_frozen.is_dir():
        raise FileNotFoundError("missing source frozen dir: %s" % src_frozen)
    dst_frozen = out / "frozen"
    dst_frozen.mkdir(parents=True, exist_ok=True)

    vp = src_frozen / "vignette_parser_frozen.json"
    if not vp.is_file():
        raise FileNotFoundError(vp)
    shutil.copy2(vp, dst_frozen / vp.name)

    for name in ("p5_headline_frozen.json",):
        src = src_frozen / name
        if src.is_file():
            shutil.copy2(src, dst_frozen / name)

    tree_src = src_frozen / "shared_trees"
    tree_dst = dst_frozen / "shared_trees"
    tree_dst.mkdir(parents=True, exist_ok=True)
    audit_src = src_frozen / "p5_audit"
    audit_dst = dst_frozen / "p5_audit"
    audit_dst.mkdir(parents=True, exist_ok=True)
    missing = []
    for cid in case_ids:
        t = tree_src / ("%s.json" % cid)
        a = audit_src / ("%s.json" % cid)
        if not t.is_file():
            missing.append(cid)
            continue
        shutil.copy2(t, tree_dst / t.name)
        if a.is_file():
            shutil.copy2(a, audit_dst / a.name)
    if missing:
        raise FileNotFoundError("missing frozen trees for: %s" % missing)


def _seed_annotate_caches(
    src_run: Path, out: Path, case_ids: Sequence[str],
) -> int:
    """Copy per-case annotate LLM caches so Config A / joint can hit resume."""
    n = 0
    src_cache = src_run / "annotate" / "cache"
    if not src_cache.is_dir():
        return 0
    dst_root = out / "annotate" / "cache"
    for cid in case_ids:
        src = src_cache / cid
        if not src.is_dir():
            continue
        dst = dst_root / cid
        if dst.exists():
            continue
        shutil.copytree(src, dst)
        n += 1
    return n


def _baseline_proxy(src_run: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    """Lightweight proxy from existing seq100 case_results for the same 24 ids."""
    cr = src_run / "annotate" / "case_results"
    proj_dir = src_run / "annotate" / "mapper" / "projections"
    rows = []
    for cid in case_ids:
        path = cr / ("%s.json" % cid)
        if not path.is_file():
            continue
        doc = _read_json(path)
        mpath = proj_dir / ("%s.json" % cid)
        mdoc = _read_json(mpath) if mpath.is_file() else {}
        rows.append({
            "case_id": cid,
            "status": doc.get("status"),
            "human_at1": (doc.get("human_adjudication") or {}).get("at1"),
            "human_at2": (doc.get("human_adjudication") or {}).get("at2"),
            "mapper_option_top1": mdoc.get("option_top1"),
            "mapper_option_top2": mdoc.get("option_top2"),
            "gapfill_enabled": bool(
                ((doc.get("l2") or {}).get("targeted_l2_gapfill") or {}).get(
                    "enabled"
                )
            ),
        })
    n = len(rows)

    def rate(key: str) -> float | None:
        usable = []
        for r in rows:
            v = r.get(key)
            if v is None:
                continue
            usable.append(1.0 if bool(v) else 0.0)
        return round(sum(usable) / len(usable), 4) if usable else None

    return {
        "n": n,
        "human_at1_rate": rate("human_at1"),
        "human_at2_rate": rate("human_at2"),
        "mapper_option_top1_rate": rate("mapper_option_top1"),
        "mapper_option_top2_rate": rate("mapper_option_top2"),
        "source": str(src_run),
        "note": "baseline without targeted gapfill (seq100 compat_synonym)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subset-dir", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--n-cases", type=int, default=DEFAULT_N)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--gapfill-arm", default=DEFAULT_ARM)
    ap.add_argument("--from-stage", default="annotate", choices=("annotate", "mapper"))
    ap.add_argument("--to-stage", default="mapper", choices=("annotate", "mapper"))
    ap.add_argument("--resume", action="store_true", default=True)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--skip-setup", action="store_true")
    ap.add_argument("--dry-print", action="store_true")
    ap.add_argument(
        "--run-official-eval",
        action="store_true",
        help="After mapper, run lexical OX official eval on this smoke dir",
    )
    args = ap.parse_args()

    subset = Path(args.subset_dir).expanduser().resolve()
    src = Path(args.source_run).expanduser().resolve()
    out = Path(args.output_dir).expanduser().resolve()
    case_ids = _load_case_ids(subset, int(args.n_cases))
    resume = bool(args.resume) and not bool(args.no_resume)

    out.mkdir(parents=True, exist_ok=True)
    if not args.skip_setup:
        _copy_frozen(src, out, case_ids)
        n_cache = _seed_annotate_caches(src, out, case_ids)
    else:
        n_cache = 0

    baseline = _baseline_proxy(src, case_ids)
    launch = {
        "created_at": _utc(),
        "dataset": "open_xddx",
        "smoke": "ox_seq24_targeted_gapfill_live",
        "n_cases": len(case_ids),
        "case_ids": case_ids,
        "subset_dir": str(subset),
        "source_run": str(src),
        "output_dir": str(out),
        "stack": "compat_parallel + synonym_bind + targeted_l2_gapfill",
        "gapfill_arm": args.gapfill_arm,
        "research_only": True,
        "seeded_annotate_caches": n_cache,
        "baseline_proxy_seq100": baseline,
    }
    _write_json(out / "smoke_launch.json", launch)

    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(subset / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(args.workers),
        "--model", args.model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--synonym-bind-repair",
        "--targeted-l2-gapfill",
        "--targeted-l2-gapfill-arm", str(args.gapfill_arm),
        "--from-stage", args.from_stage,
        "--to-stage", args.to_stage,
    ]
    if resume:
        cmd.append("--resume")

    launch["cmd"] = cmd
    _write_json(out / "smoke_launch.json", launch)
    print("OX seq24 gapfill smoke n=%d → %s" % (len(case_ids), out), flush=True)
    print("baseline proxy: %s" % json.dumps(baseline, ensure_ascii=False), flush=True)
    print(" ".join(cmd), flush=True)
    if args.dry_print:
        return 0

    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    code = subprocess.call(cmd, cwd=str(ROOT), env=env)
    if code != 0:
        return code

    # Post-hoc: summarize gapfill adds vs baseline proxy.
    cr = out / "annotate" / "case_results"
    smoke_rows = []
    for cid in case_ids:
        path = cr / ("%s.json" % cid)
        if not path.is_file():
            continue
        doc = _read_json(path)
        gf = (doc.get("l2") or {}).get("targeted_l2_gapfill") or {}
        smoke_rows.append({
            "case_id": cid,
            "status": doc.get("status"),
            "human_at1": (doc.get("human_adjudication") or {}).get("at1"),
            "human_at2": (doc.get("human_adjudication") or {}).get("at2"),
            "gapfill_enabled": bool(gf.get("enabled")),
            "n_added": gf.get("n_added"),
            "arm": gf.get("arm"),
        })
    n_ok = sum(1 for r in smoke_rows if r.get("status") == "OK")
    summary = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "n_ok": n_ok,
        "n_error": len(case_ids) - n_ok,
        "mean_n_added": (
            round(
                sum(int(r.get("n_added") or 0) for r in smoke_rows if r.get("status") == "OK")
                / max(n_ok, 1),
                3,
            )
            if n_ok else None
        ),
        "human_at1_rate": (
            round(sum(1 for r in smoke_rows if r.get("human_at1")) / n_ok, 4)
            if n_ok else None
        ),
        "human_at2_rate": (
            round(sum(1 for r in smoke_rows if r.get("human_at2")) / n_ok, 4)
            if n_ok else None
        ),
        "baseline_proxy_seq100": baseline,
        "research_only": True,
        "rows": smoke_rows,
    }
    _write_json(out / "smoke_summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2), flush=True)

    if args.run_official_eval:
        eval_cmd = [
            sys.executable, "-u",
            str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
            "--dataset", "open_xddx",
            "--run-dir", str(out),
            "--subset-parquet", str(subset / "cases.parquet"),
            "--judge", "lexical",
            "--ddx-k", "5",
            "--workers", "8",
            "--build-projection",
            "--ddx-source", "compat_then_pad_posterior",
        ]
        print(" ".join(eval_cmd), flush=True)
        return subprocess.call(eval_cmd, cwd=str(ROOT), env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
