#!/usr/bin/env python3
"""AB02 re-run with the MCQ options stripped from ``state.case_summary``.

The pipeline builds trees from ``case_text``, which still carries the MCQ stem
and the Options block (the gold answer verbatim). Baselines, the backbone and
the option mapper all read ``da.vignette_body()`` instead, so the published DA
comparison is an unequal-input one: 100/100 AB02 case summaries contain the gold
string, and 63.8% of its final L2 leaves are verbatim copies of an option.

AB02 is the cheap place to measure the cost of that leak. It is the flat arm --
``keep_leaves=False`` means annotate regenerates every L2 leaf and every score
from ``case_summary`` -- so stripping the summary and re-annotating yields a
fully clean run without rebuilding L1 (~50 calls/case instead of ~300).

Clones the prepared c3_ab02_v1 state, rewrites the summaries, drops the L2
caches that were produced under the leak, then re-runs annotate + mapper.
Reads c3_ab02_v1; writes only c3_ab02_clean_v1.
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
        "base": ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1",
        "dest": ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_clean_v1",
        "to_stage": "mapper",
    },
    # MCR Prompt-7 Acc reads compat final_ranking straight from annotate; the
    # DA-style option mapper is not part of that metric.
    "mcr": {
        "base": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1",
        "dest": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_clean_v1",
        "to_stage": "annotate",
    },
}
BASE = DATASETS["da"]["base"]
DEST = DATASETS["da"]["dest"]


def clone_and_strip(base: Path, dest: Path) -> dict:
    if dest.exists():
        raise SystemExit(f"{dest} already exists; remove it or pick another dest")
    dest.mkdir(parents=True)
    ann_dst = dest / "annotate"
    ann_dst.mkdir(parents=True)
    for name in ("normalized_cases.json", "finding_fixture_v1.json", "case_ids.json"):
        if (base / name).is_file():
            shutil.copy2(base / name, dest / name)
    for name in ("normalized_cases.json", "finding_fixture_v1.json"):
        if (base / "annotate" / name).is_file():
            shutil.copy2(base / "annotate" / name, ann_dst / name)

    # stage_annotate re-copies shared_trees + p5_audit from ``frozen`` on every
    # run, so the summaries have to be stripped there, not under ``annotate``.
    frz_src, frz_dst = base / "frozen", dest / "frozen"
    frz_dst.mkdir(parents=True)
    for name in ("p5_headline_frozen.json", "vignette_parser_frozen.json"):
        if (frz_src / name).is_file():
            shutil.copy2(frz_src / name, frz_dst / name)
    if (frz_src / "p5_audit").is_dir():
        shutil.copytree(frz_src / "p5_audit", frz_dst / "p5_audit")
    if (base / "annotate" / "p5_headline_frozen.json").is_file():
        shutil.copy2(base / "annotate" / "p5_headline_frozen.json", ann_dst / "p5_headline_frozen.json")

    trees_dst = frz_dst / "shared_trees"
    trees_dst.mkdir(parents=True)
    n = stripped = 0
    for src in sorted((frz_src / "shared_trees").glob("*.json")):
        doc = json.loads(src.read_text(encoding="utf-8"))
        state = doc.get("state") or {}
        summary = str(state.get("case_summary") or "")
        body = da.vignette_body(summary)
        if body and body != summary:
            state["case_summary"] = body
            stripped += 1
        n += 1
        (trees_dst / src.name).write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

    # normalized_cases.json feeds the runtime case text; strip it there too.
    ncp = ann_dst / "normalized_cases.json"
    n_cases = 0
    if ncp.is_file():
        doc = json.loads(ncp.read_text(encoding="utf-8"))
        for case in doc.get("cases") or []:
            for key in ("case_text", "vignette", "case_summary"):
                if case.get(key):
                    body = da.vignette_body(str(case[key]))
                    if body:
                        case[key] = body
            n_cases += 1
        ncp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        shutil.copy2(ncp, dest / "normalized_cases.json")

    # The L2 caches hold differentials generated while the options were visible.
    # Reusing them would carry the leak straight into the "clean" run.
    return {"n_trees": n, "n_stripped": stripped, "n_cases": n_cases, "cache_copied": 0}


def run_annotate(
    dest: Path, case_ids: list[str], *, workers: int, model: str, to_stage: str = "mapper"
) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(dest / "annotate" / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(dest),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--from-stage", "annotate",
        "--to-stage", to_stage,
        "--fixed-l1-budget", "6",
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", "6",
        "--l1-bfs-preset", "p5_anti_anchor_direct",
        "--l1-axis-mode", "flat",
        "--mapper-mode", "typed_llm_disagreement_rag",
        "--resume",
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="da", choices=sorted(DATASETS))
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    spec = DATASETS[args.dataset]
    base, dest = Path(spec["base"]), Path(spec["dest"])
    meta = clone_and_strip(base, dest)
    print(json.dumps(meta, indent=2), flush=True)
    case_ids = sorted(p.stem for p in (dest / "frozen" / "shared_trees").glob("*.json"))
    if args.prepare_only:
        return 0
    return run_annotate(
        dest, case_ids, workers=args.workers, model=args.model, to_stage=spec["to_stage"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
