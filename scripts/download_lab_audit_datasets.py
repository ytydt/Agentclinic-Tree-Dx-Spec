#!/usr/bin/env python3
"""Restore or verify the pinned diagnostic benchmark artifacts used by the lab audit.

The benchmark snapshots are committed under ``data/eval/lab_reference_datasets``.
Every artifact is pinned by revision, byte size, and SHA-256 in
``lab_reference_dataset_manifest.json`` so a missing or damaged snapshot can be
restored deterministically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data" / "eval" / "lab_reference_dataset_manifest.json"
DEFAULT_OUTPUT = ROOT / "data" / "eval" / "lab_reference_datasets"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(path: Path, record: dict) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    actual_bytes = path.stat().st_size
    if actual_bytes != record["bytes"]:
        return False, f"size {actual_bytes} != {record['bytes']}"
    actual_hash = sha256(path)
    if actual_hash != record["sha256"]:
        return False, f"sha256 {actual_hash} != {record['sha256']}"
    return True, "verified"


def safe_target(output: Path, relative: str) -> Path:
    candidate = (output / relative).resolve()
    root = output.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"unsafe manifest path: {relative!r}")
    return candidate


def download(record: dict, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    request = urllib.request.Request(
        record["download_url"],
        headers={"User-Agent": "Agentclinic-Tree-Dx-Spec lab audit/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        ok, reason = validate(partial, record)
        if not ok:
            raise ValueError(f"download verification failed for {record['id']}: {reason}")
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--datasets",
        nargs="*",
        help="optional dataset ids (default: all manifest records)",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    requested = set(args.datasets or [])
    records = [
        record
        for record in manifest["datasets"]
        if not requested or record["id"] in requested
    ]
    missing_ids = requested - {record["id"] for record in records}
    if missing_ids:
        parser.error("unknown dataset ids: " + ", ".join(sorted(missing_ids)))

    failures = 0
    for record in records:
        target = safe_target(args.output_dir, record["relative_path"])
        ok, reason = validate(target, record)
        if ok:
            print(f"OK       {record['id']}: {target}")
            continue
        if args.verify_only:
            failures += 1
            print(f"MISSING  {record['id']}: {reason}", file=sys.stderr)
            continue
        print(f"DOWNLOAD {record['id']} -> {target}")
        download(record, target)
        print(f"VERIFIED {record['id']}: sha256={record['sha256']}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
