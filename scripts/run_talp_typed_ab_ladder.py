#!/usr/bin/env python3
"""Ordered, resumable TALP typed-evidence A/B ladder.

Each arm is parameterized and default-OFF. The script records commands/status;
it never changes production defaults or overwrites historical result files.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "scripts/eval_talp_discrimination.py"
ASSET_AUDIT = ROOT / "scripts/audit_p5_asset_integrity.py"
V1 = ROOT / "data/eval/talp_medxpert_expansion_cases.json"
V2 = ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json"

ARM_FLAGS = [
    ("legacy", [f"--extra-dataset={V1}"]),
    ("fixture_v2", [f"--extra-dataset={V2}"]),
    ("scoring_aligned", [f"--extra-dataset={V2}",
                         "--select-gold-pool=typed_effect",
                         "--candidate-order=rotations"]),
    ("multi_ontology", [f"--extra-dataset={V2}", "--concept-router=multi"]),
    ("atomic", [f"--extra-dataset={V2}", "--compound-mode=atomic"]),
    ("syndrome", [f"--extra-dataset={V2}", "--compound-mode=syndrome"]),
    ("dual", [f"--extra-dataset={V2}", "--compound-mode=dual"]),
    ("typed_entry", [f"--extra-dataset={V2}", "--concept-router=multi",
                     "--entry-gate=typed_uncertain"]),
    ("pathogen_corpus", [f"--extra-dataset={V2}", "--pathogen-source=corpus"]),
    ("pathogen_fused", [f"--extra-dataset={V2}", "--pathogen-source=fused"]),
]


def _expected_outputs(tag: str, seeds: str, stage: str | None) -> list[Path]:
    suffix = f"_dv2_{stage}" if stage else ""
    return [
        ROOT / "logs" / f"talp_discrim_{tag}_s{seed}r0{suffix}.json"
        for seed in (part.strip() for part in seeds.split(","))
        if seed
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="7,11,13")
    parser.add_argument("--arms", default=None)
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--baseline-family", default="llm_only",
                        choices=["llm_only", "p5"],
                        help="p5 layers every typed arm onto DISC-v2 P5")
    parser.add_argument("--pathogen-open-kb", type=Path,
                        help="append a pathogen_openkb arm using this new cache")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="skip an arm only when all expected outputs exist")
    parser.add_argument("--force-results", action="store_true",
                        help="explicitly permit overwriting existing result tags")
    parser.add_argument(
        "--asset-manifest", type=Path,
        default=ROOT / "data/eval/p5_external_asset_manifest.json")
    parser.add_argument(
        "--disc-cache-dir", type=Path,
        default=ROOT / "logs/p5_disc_block_cache")
    parser.add_argument("--manifest", type=Path,
                        default=None)
    args = parser.parse_args()
    arms = list(ARM_FLAGS)
    if args.pathogen_open_kb:
        arms.append((
            "pathogen_openkb",
            [f"--extra-dataset={V2}", "--pathogen-source=open_kb",
             f"--pathogen-open-kb={args.pathogen_open_kb}"]))
    default_names = [
        name for name, _ in arms
        if args.baseline_family == "llm_only" or name != "legacy"
    ]
    requested = {
        x.strip() for x in (args.arms or ",".join(default_names)).split(",")
        if x.strip()
    }
    args.manifest = args.manifest or (
        ROOT / "logs" / (
            "talp_p5_typed_ab_manifest.json"
            if args.baseline_family == "p5"
            else "talp_typed_ab_manifest.json"))
    unknown = requested - {name for name, _ in arms}
    if unknown:
        parser.error(f"unknown arms: {sorted(unknown)}")
    if args.baseline_family == "p5" and not args.dry_run:
        verified = subprocess.run([
            sys.executable, str(ASSET_AUDIT), "--verify",
            f"--manifest={args.asset_manifest}"], cwd=ROOT)
        if verified.returncode:
            return verified.returncode
    records = []
    for name, flags in arms:
        if name not in requested:
            continue
        if args.baseline_family == "p5":
            stage, prefix = "p5", "p5typed"
            cache_key = (
                name if name in {"atomic", "syndrome", "dual", "typed_entry"}
                else "fixture_v2_legacy_entry")
            cache_path = args.disc_cache_dir / f"{cache_key}_p5.json"
            stage_flags = [
                "--disc-stage=p5", "--stage-only",
                f"--disc-block-cache={cache_path}",
                f"--p5-asset-manifest={args.asset_manifest}",
            ]
        elif name == "typed_entry":
            stage, prefix = "p5ccv", "typed"
            stage_flags = ["--disc-stage=p5ccv", "--stage-only"]
        else:
            stage, prefix = None, "typed"
            stage_flags = []
        tag = f"{prefix}_{name}"
        expected = _expected_outputs(tag, args.seeds, stage)
        existing = [str(path) for path in expected if path.exists()]
        if existing and args.resume and len(existing) == len(expected):
            records.append({
                "arm": name, "baseline_family": args.baseline_family,
                "status": "skipped_complete", "outputs": existing})
            continue
        if existing and not args.force_results:
            parser.error(
                f"refusing to overwrite existing results for {name}: {existing}")
        cmd = [
            sys.executable, str(EVAL), f"--model={args.model}",
            f"--seeds={args.seeds}", f"--tag={tag}", *stage_flags, *flags,
        ]
        record = {
            "arm": name, "baseline_family": args.baseline_family,
            "command": cmd, "expected_outputs": [str(p) for p in expected],
            "status": "planned"}
        records.append(record)
        print(" ".join(cmd), flush=True)
        if args.dry_run:
            continue
        completed = subprocess.run(cmd, cwd=ROOT)
        record["returncode"] = completed.returncode
        record["status"] = "completed" if completed.returncode == 0 else "failed"
        args.manifest.parent.mkdir(exist_ok=True)
        args.manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        if args.baseline_family == "p5":
            verified = subprocess.run([
                sys.executable, str(ASSET_AUDIT), "--verify",
                f"--manifest={args.asset_manifest}"], cwd=ROOT)
            record["asset_integrity_returncode"] = verified.returncode
            if verified.returncode:
                record["status"] = "failed_asset_integrity"
                args.manifest.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2))
                return verified.returncode
        if completed.returncode and not args.continue_on_error:
            return completed.returncode
    args.manifest.parent.mkdir(exist_ok=True)
    args.manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
