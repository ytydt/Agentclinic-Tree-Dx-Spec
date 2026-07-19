#!/usr/bin/env python3
"""Ordered, resumable clinical-baseline + research-only P5KG A/B ladder."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "scripts/eval_talp_discrimination.py"
P5_AUDIT = ROOT / "scripts/audit_p5_asset_integrity.py"
P5KG_AUDIT = ROOT / "scripts/audit_p5kg_asset_integrity.py"
DEFAULT_P5_MANIFEST = ROOT / "data/eval/p5_external_asset_manifest.json"
DEFAULT_EXTRA_DATASET = ROOT / "data/eval/talp_medxpert_expansion_cases_v2.json"
DEFAULT_CORPUS_METADATA = ROOT / "data/cpg/processed/cpg_chunks.jsonl"

ARM_FLAGS = [
    ("G0", ["--evidence-source=legacy"]),
    ("G1", ["--evidence-source=cpg_enhanced"]),
    ("G2PR", ["--evidence-lane=research",
              "--research-evidence-mode=pair_direct"]),
    ("G2UR", ["--evidence-lane=research",
              "--research-evidence-mode=unary"]),
    ("G2CR", ["--evidence-lane=research",
              "--research-evidence-mode=composed"]),
    ("G3R", ["--evidence-lane=research",
             "--research-evidence-mode=graph"]),
    ("G4R", ["--evidence-lane=research",
             "--research-evidence-mode=graph"]),
]
EXECUTION_ORDER = ["G0", "G1", "G2PR", "G2UR", "G2CR", "G3R", "G4R"]
RESEARCH_ARMS = frozenset({"G2PR", "G2UR", "G2CR", "G3R", "G4R"})
DEFERRED_ARMS = frozenset({"G5"})


def _expected_outputs(tag: str, seeds: str) -> list[Path]:
    return [
        ROOT / "logs" / f"talp_discrim_{tag}_s{seed}r0_dv2_p5.json"
        for seed in (part.strip() for part in seeds.split(","))
        if seed
    ]


def _rate(summary: dict, numerator: str, denominator: str) -> float:
    return float(summary.get(numerator, 0)) / max(1, int(summary.get(denominator, 0)))


def _claim_types(path: Path) -> set[str]:
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {str(row.get("claim_type") or "") for row in rows}


def _gate_passes(baseline_paths: list[Path], candidate_paths: list[Path]) -> bool:
    """Conservative no-regression gate used before spending on graph traversal."""
    if not baseline_paths or len(baseline_paths) != len(candidate_paths):
        return False
    improved_shared = False
    for baseline_path, candidate_path in zip(baseline_paths, candidate_paths):
        if not baseline_path.is_file() or not candidate_path.is_file():
            return False
        base = json.loads(baseline_path.read_text()).get("summary", {})
        cand = json.loads(candidate_path.read_text()).get("summary", {})
        for num, den in (
            ("dir_ok", "dir_n"), ("ruleout_ok", "ruleout_n"),
            ("sel_valid", "n_sel"),
        ):
            if _rate(cand, num, den) < _rate(base, num, den):
                return False
        improved_shared |= (
            _rate(cand, "shared_ok", "shared_n")
            > _rate(base, "shared_ok", "shared_n"))
    return improved_shared


def _audit_command(script: Path, manifest: Path,
                   required: list[Path] | None = None,
                   research: bool = False) -> list[str]:
    command = [
        sys.executable, str(script), "--verify", f"--manifest={manifest}"]
    for path in required or []:
        command.append(f"--require={path}")
    if research:
        command.append("--research")
    return command


def _run_audits(commands: list[list[str]], dry_run: bool) -> int:
    for command in commands:
        print(" ".join(command), flush=True)
        if dry_run:
            continue
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            return result.returncode
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="7,11,13")
    parser.add_argument(
        "--arms", default="G0,G1,G2PR,G2UR,G2CR,G3R,G4R")
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--pair-claims", type=Path)
    parser.add_argument("--unary-claims", type=Path)
    parser.add_argument("--composed-claims", type=Path)
    parser.add_argument("--adjacency", type=Path)
    parser.add_argument(
        "--corpus-metadata", type=Path, default=DEFAULT_CORPUS_METADATA)
    parser.add_argument("--p5-manifest", type=Path, default=DEFAULT_P5_MANIFEST)
    parser.add_argument("--extra-dataset", type=Path, default=DEFAULT_EXTRA_DATASET)
    parser.add_argument("--p5kg-research-manifest", type=Path)
    parser.add_argument("--max-hops", type=int, default=2)
    parser.add_argument("--cache-dir", type=Path,
                        default=ROOT / "logs/p5kg_research_disc_block_cache")
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "logs/talp_p5kg_research_ab_manifest.json")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="explicitly permit overwriting existing result tags")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    requested = {part.strip().upper() for part in args.arms.split(",") if part.strip()}
    known = {name for name, _ in ARM_FLAGS} | DEFERRED_ARMS
    if requested - known:
        parser.error(f"unknown arms: {sorted(requested - known)}")
    args.pair_claims = args.pair_claims or args.claims
    required_claims = {
        "G2PR": args.pair_claims,
        "G2UR": args.unary_claims,
        "G2CR": args.composed_claims,
        "G3R": args.composed_claims,
        "G4R": args.composed_claims,
    }
    missing_claims = [arm for arm in requested & RESEARCH_ARMS
                      if not required_claims[arm]]
    if missing_claims:
        parser.error(f"research claims missing for arms: {sorted(missing_claims)}")
    if requested & {"G3R", "G4R"} and not args.adjacency:
        parser.error("G3R/G4R require --adjacency")
    if requested & RESEARCH_ARMS and not args.p5kg_research_manifest:
        parser.error(
            "research arms require --p5kg-research-manifest")
    expected_types = {
        "G2PR": {"direction", "common", "test_recommendation"},
        "G2UR": {"candidate_effect"},
        "G2CR": {"derived_contrast"},
        "G3R": {"derived_contrast"},
        "G4R": {"derived_contrast"},
    }
    claim_types = {
        arm: (
            expected_types[arm]
            if args.dry_run and not path.is_file()
            else _claim_types(path)
        )
        for arm, path in required_claims.items()
        if arm in requested and path is not None
    }
    for arm, observed in claim_types.items():
        unexpected = observed - expected_types[arm]
        if unexpected:
            parser.error(
                f"{arm} received forbidden claim types: {sorted(unexpected)}")
    if args.max_hops not in (1, 2):
        parser.error("--max-hops must be 1 or 2")

    flags_by_arm = dict(ARM_FLAGS)
    records = []
    outputs_by_arm = {
        arm: _expected_outputs(
            (f"p5kg_research_{arm.lower()}" if arm in RESEARCH_ARMS
             else f"p5kg_{arm.lower()}"),
            args.seeds)
        for arm in known
    }
    if "G5" in requested:
        records.append({
            "arm": "G5", "status": "deferred",
            "condition": "human-complete oracle remains unavailable"})
    for arm in EXECUTION_ORDER:
        if arm not in requested:
            continue
        condition = None
        if arm in RESEARCH_ARMS and not claim_types.get(arm):
            records.append({
                "arm": arm,
                "status": "skipped_no_evidence",
                "condition": "no schema-valid claims for this research arm",
            })
            continue
        if arm in {"G3R", "G4R"}:
            condition = "G2CR passes no-regression/shared-headroom gate"
            allowed = (
                bool(claim_types.get("G2CR"))
                and (args.dry_run or _gate_passes(
                outputs_by_arm["G0"], outputs_by_arm["G2CR"])
                )
            )
        else:
            allowed = True
        if not allowed:
            records.append({"arm": arm, "status": "skipped_condition",
                            "condition": condition})
            continue

        tag = (f"p5kg_research_{arm.lower()}"
               if arm in RESEARCH_ARMS else f"p5kg_{arm.lower()}")
        expected = outputs_by_arm[arm]
        existing = (
            [] if args.dry_run
            else [str(path) for path in expected if path.exists()]
        )
        if arm in {"G0", "G1"} and len(existing) == len(expected):
            records.append({
                "arm": arm, "tag": tag, "status": "reused_complete",
                "outputs": existing, "condition": condition})
            continue
        if existing and args.resume and len(existing) == len(expected):
            records.append({"arm": arm, "status": "skipped_complete",
                            "outputs": existing, "condition": condition})
            continue
        if existing and not args.force:
            parser.error(f"refusing to overwrite {arm} results: {existing}")

        arm_flags = list(flags_by_arm[arm])
        claims = required_claims.get(arm)
        if arm in RESEARCH_ARMS:
            arm_flags.extend([
                f"--research-claims={claims}",
                f"--p5kg-research-manifest={args.p5kg_research_manifest}",
            ])
        if arm in {"G3R", "G4R"}:
            arm_flags.extend([
                f"--research-adjacency={args.adjacency}",
                f"--cceg-max-hops={args.max_hops}",
            ])
        if arm == "G4R":
            arm_flags.extend([
                f"--research-corpus-metadata={args.corpus_metadata}",
                "--research-hydrate",
            ])
        cache_path = (
            args.cache_dir / (arm.lower() + "_p5.json")
            if arm in RESEARCH_ARMS else
            ROOT / "logs/p5kg_disc_block_cache" / (arm.lower() + "_p5.json"))
        cmd = [
            sys.executable, str(EVAL), f"--model={args.model}",
            f"--seeds={args.seeds}", f"--tag={tag}",
            "--disc-stage=p5", "--stage-only",
            f"--disc-block-cache={cache_path}",
            f"--p5-asset-manifest={args.p5_manifest}",
            f"--extra-dataset={args.extra_dataset}",
            *arm_flags,
        ]
        audits = [_audit_command(P5_AUDIT, args.p5_manifest)]
        if arm in RESEARCH_ARMS:
            required = [claims]
            if arm in {"G3R", "G4R"}:
                required.append(args.adjacency)
            if arm == "G4R":
                required.append(args.corpus_metadata)
            audits.append(_audit_command(
                P5KG_AUDIT, args.p5kg_research_manifest, required,
                research=True))
        record = {
            "arm": arm, "tag": tag, "disc_stage": "p5",
            "evidence_lane": (
                "research" if arm in RESEARCH_ARMS else "clinical_baseline"),
            "condition": condition, "command": cmd,
            "expected_outputs": [str(path) for path in expected],
            "pre_audits": audits, "post_audits": audits,
            "status": "planned",
        }
        records.append(record)
        rc = _run_audits(audits, args.dry_run)
        if rc:
            record.update(status="failed_pre_asset_integrity", returncode=rc)
        else:
            print(" ".join(cmd), flush=True)
            if not args.dry_run:
                result = subprocess.run(cmd, cwd=ROOT)
                rc = result.returncode
                record["returncode"] = rc
                record["status"] = "completed" if rc == 0 else "failed"
                if rc == 0:
                    rc = _run_audits(audits, False)
                    record["post_asset_integrity_returncode"] = rc
                    if rc:
                        record["status"] = "failed_post_asset_integrity"
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        if rc and not args.continue_on_error:
            return rc

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
