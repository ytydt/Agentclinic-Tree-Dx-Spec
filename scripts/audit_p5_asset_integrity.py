#!/usr/bin/env python3
"""Create or verify an immutable-content manifest for P5 input assets."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/eval/p5_external_asset_manifest.json"
P5_ASSETS = [
    "data/knowledge_raw/phenotype.hpoa",
    "data/knowledge_raw/hp.obo",
    "data/knowledge_raw/Guideline_common.json",
    "data/knowledge_raw/Guideline_rare.json",
    "data/knowledge_raw/kg.csv",
    "data/knowledge_raw/lab_reference_ranges.json",
    "data/knowledge_raw/loinc2hpo_annotations.json",
    "data/knowledge_raw/unit_conversions.json",
    "data/corpus/cpg_index/config.json",
    "data/corpus/cpg_index/metadata.jsonl",
    "data/corpus/case_report_index/config.json",
    "data/corpus/case_report_index/metadata.jsonl",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot() -> dict:
    assets = {}
    missing = []
    for relative in P5_ASSETS:
        path = ROOT / relative
        if not path.is_file():
            missing.append(relative)
            continue
        stat = path.stat()
        assets[relative] = {
            "size": stat.st_size,
            "sha256": _sha256(path),
        }
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "purpose": "P5 read-only fallback inputs; experiment outputs forbidden",
        "assets": assets,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    current = snapshot()
    if args.create:
        if args.manifest.exists():
            parser.error(f"refusing to overwrite {args.manifest}")
        if current["missing"]:
            parser.error(f"missing P5 assets: {current['missing']}")
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(current, ensure_ascii=False, indent=2))
        print(f"created immutable P5 asset manifest: {args.manifest}")
        print(f"assets={len(current['assets'])}")
        return 0
    if not args.manifest.exists():
        parser.error(
            f"missing manifest {args.manifest}; create it explicitly first")
    expected = json.loads(args.manifest.read_text())
    failures = []
    for relative, record in expected.get("assets", {}).items():
        actual = current["assets"].get(relative)
        if actual is None:
            failures.append(f"missing: {relative}")
        elif actual != record:
            failures.append(
                f"changed: {relative} expected={record} actual={actual}")
    extras = sorted(set(current["assets"]) - set(expected.get("assets", {})))
    report = {
        "verified": not failures,
        "assets": len(expected.get("assets", {})),
        "failures": failures,
        "untracked_p5_inputs": extras,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
