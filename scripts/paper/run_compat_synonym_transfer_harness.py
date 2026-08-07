#!/usr/bin/env python3
"""Launch compat_parallel annotate + synonym_bind mapper on a transfer subset.

Expects ``normalized_cases.json`` + ``case_ids.txt`` from
``extract_diagnosisarena_subset.py --dataset {open_xddx,medcasereasoning,rarearena}``.

Runs the staged DiagnosisArena harness:
  vp → trees → p5 → annotate (granularity=compat) → mapper (--synonym-bind-repair)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--subset-dir",
        type=Path,
        required=True,
        help="e.g. data/benchmarks/open_xddx/subsets/ox_seq100_v1",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Pipeline output root under logs/",
    )
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--from-stage", default="vp")
    ap.add_argument("--to-stage", default="mapper")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-print", action="store_true")
    ap.add_argument(
        "--targeted-l2-gapfill",
        action="store_true",
        help="Opt-in research overlay after Config A (default off)",
    )
    ap.add_argument(
        "--targeted-l2-gapfill-arm",
        default="ALL_B_b1",
        help="Arm for --targeted-l2-gapfill (default ALL_B_b1)",
    )
    args = ap.parse_args()

    subset = Path(args.subset_dir).expanduser().resolve()
    cases_json = subset / "normalized_cases.json"
    ids_path = subset / "case_ids.txt"
    if not cases_json.is_file() or not ids_path.is_file():
        print("missing normalized_cases.json or case_ids.txt under", subset, file=sys.stderr)
        return 2
    ids = [
        line.strip()
        for line in ids_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not ids:
        print("empty case_ids", file=sys.stderr)
        return 2

    out = Path(args.output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts" / "paper" / "run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(cases_json),
        "--cases", ",".join(ids),
        "--output-dir", str(out),
        "--workers", str(args.workers),
        "--model", args.model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--synonym-bind-repair",
        "--from-stage", args.from_stage,
        "--to-stage", args.to_stage,
    ]
    if args.targeted_l2_gapfill:
        cmd.append("--targeted-l2-gapfill")
        cmd.extend(["--targeted-l2-gapfill-arm", str(args.targeted_l2_gapfill_arm)])
    if args.resume:
        cmd.append("--resume")

    meta = {
        "subset_dir": str(subset),
        "n_cases": len(ids),
        "case_ids": ids,
        "output_dir": str(out),
        "cmd": cmd,
        "stack": "compat_parallel + synonym_bind_repair",
        "targeted_l2_gapfill": bool(args.targeted_l2_gapfill),
        "targeted_l2_gapfill_arm": (
            str(args.targeted_l2_gapfill_arm) if args.targeted_l2_gapfill else None
        ),
    }
    (out / "transfer_harness_launch.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Launching transfer harness n=%d → %s" % (len(ids), out), flush=True)
    print(" ".join(cmd), flush=True)
    if args.dry_print:
        return 0
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
