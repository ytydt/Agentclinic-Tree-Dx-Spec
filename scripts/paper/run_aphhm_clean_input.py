#!/usr/bin/env python3
"""Full APHHM (M00) re-run on the options-stripped vignette, DA and MCR.

Why a full rebuild rather than the cheap re-annotate used for AB02: M00's frozen
trees already carry both levels built under the leak (|L1|=4.6 with 14% of labels
matching an MCQ option and gold already inside L1 for 22% of cases; |L2|=17.6 with
30% option matches), and annotate keeps those leaves rather than regenerating
them. So the candidate set is fixed at tree-build time and the whole
vp -> trees -> p5 -> annotate -> mapper chain has to be re-run.

Both datasets go through the same ``run_diagnosisarena_pipeline_staged.py``, so
one stripped ``normalized_cases.json`` per dataset is enough. The option mapper
reads ``annotation.source_options``, not ``case_text``, so scoring is unaffected.

Reads the published run dirs; writes only ``<dataset>_aphhm_clean_v1``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import diagnosisarena_adapter as da  # noqa: E402

DATASETS = {
    "da": {
        "cases_json": ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/normalized_cases.json",
        "out": ROOT / "logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1",
        "vp_freeze": ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/frozen/vignette_parser_frozen.json",
        "extra": [],
    },
    # Held-out DA slice has no published run to freeze the parser from, so this
    # entry must be driven with --from-stage vp.
    "da_heldout": {
        "cases_json": ROOT
        / "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1/normalized_cases.json",
        "out": ROOT / "logs/diagnosisarena_heldout_v1/aphhm_clean_v1",
        "vp_freeze": None,
        "extra": [],
    },
    "da_heldout200b": {
        "cases_json": ROOT
        / "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1/normalized_cases.json",
        "out": ROOT / "logs/diagnosisarena_heldout200b_v1/aphhm_clean_v1",
        "vp_freeze": None,
        "extra": [],
    },
    "mcr": {
        "cases_json": ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
        "out": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1",
        "vp_freeze": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/frozen/vignette_parser_frozen.json",
        "extra": ["--synonym-bind-repair"],
    },
}


def write_stripped_cases(src: Path, dest: Path) -> dict:
    doc = json.loads(src.read_text(encoding="utf-8"))
    n = stripped = 0
    for case in doc.get("cases") or []:
        n += 1
        text = str(case.get("case_text") or "")
        body = da.vignette_body(text)
        if body and body != text:
            case["case_text"] = body
            stripped += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    remaining = sum(
        1 for c in doc.get("cases") or [] if "Options:" in str(c.get("case_text") or "")
    )
    if remaining:
        raise SystemExit(f"{remaining} cases still carry an Options block in {dest}")
    return {"n": n, "stripped": stripped, "dest": str(dest)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, choices=sorted(DATASETS))
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--from-stage", default="trees")
    ap.add_argument("--to-stage", default="mapper")
    ap.add_argument("--prepare-only", action="store_true")
    ap.add_argument(
        "--l1-calib",
        default="off",
        choices=["off", "ours", "support", "pair", "b12"],
        help=(
            "Match the published run's L1 calib. The DA headline (0.71) was "
            "produced with b12 while every ablation arm used off, so the "
            "leak effect is only readable against a same-calib control."
        ),
    )
    ap.add_argument(
        "--out-suffix",
        default="",
        help="Appended to the output dir, for same-input/different-calib controls",
    )
    args = ap.parse_args()

    spec = DATASETS[args.dataset]
    out = Path(str(spec["out"]) + args.out_suffix)
    out.mkdir(parents=True, exist_ok=True)
    cases_json = out / "normalized_cases_clean.json"
    meta = write_stripped_cases(Path(spec["cases_json"]), cases_json)

    # VignetteParser evidence is verifiably free of option text (DA 1/100 with
    # gold, MCR 3/100 -- the same coincidence rate the options-stripped backbone
    # shows), so reusing the published freeze holds the evidence catalog fixed
    # and leaves trees/L2 as the only thing the strip can change.
    if args.from_stage == "trees":
        if spec["vp_freeze"] is None:
            raise SystemExit(
                f"{args.dataset} has no published parser freeze; use --from-stage vp"
            )
        frozen = out / "frozen"
        frozen.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(spec["vp_freeze"]), frozen / "vignette_parser_frozen.json")
        meta["vp_freeze_reused_from"] = str(spec["vp_freeze"])
    print(json.dumps(meta, indent=2), flush=True)

    case_ids = [
        str(c["id"]) for c in json.loads(cases_json.read_text(encoding="utf-8"))["cases"]
    ]
    if args.prepare_only:
        return 0

    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(cases_json),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(args.workers),
        "--model", args.model,
        "--granularity-mode", "compat",
        "--l1-calib", args.l1_calib,
        "--from-stage", args.from_stage,
        "--to-stage", args.to_stage,
        "--strip-mcq-options",
        "--resume",
        *spec["extra"],
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
