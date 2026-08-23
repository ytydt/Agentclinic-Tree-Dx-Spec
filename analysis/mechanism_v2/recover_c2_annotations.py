"""Quarantine validator-invalid C2 annotation caches before an exact retry."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.mechanism_v2.online_runner import (
    atomic_json,
    read_jsonl,
    write_jsonl,
)


STAGES = ("factorizer_parser", "modifier_binder")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _archive(path: Path, quarantine: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    digest = file_sha256(path)
    destination = quarantine / f"{path.name}.before-recovery.{digest}"
    if not destination.exists():
        shutil.copy2(path, destination)
    return {"path": str(destination), "sha256": digest}


def prepare(root: Path) -> dict[str, Any]:
    root = Path(root)
    prepared: list[dict[str, Any]] = []
    for stage in STAGES:
        directory = root / stage
        raw_path = directory / "raw_results.jsonl"
        rows = read_jsonl(raw_path)
        failed = [row for row in rows if not bool(row.get("success"))]
        quarantine = directory / "quarantine"
        quarantine.mkdir(parents=True, exist_ok=True)
        archives = [
            item
            for item in (
                _archive(raw_path, quarantine),
                _archive(directory / "manifest.json", quarantine),
                _archive(directory / "telemetry_summary.json", quarantine),
            )
            if item is not None
        ]
        ledger_path = quarantine / "invalid_cache_ledger.jsonl"
        ledger = read_jsonl(ledger_path)
        known = {
            (str(row.get("cache_key")), str(row.get("raw_cache_sha256")))
            for row in ledger
        }
        moved = 0
        for row in failed:
            cache_key = str(row.get("cache_key") or "")
            cache_path = directory / "cache" / f"{cache_key}.json"
            if not cache_key or not cache_path.is_file():
                raise RuntimeError(f"missing failed cache for {stage}: {row.get('task_id')}")
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if bool(cache.get("success")):
                raise RuntimeError(f"refusing to quarantine successful cache: {cache_key}")
            for key in ("model", "prompt_sha256", "payload_sha256"):
                if str(cache.get(key) or "") != str(row.get(key) or ""):
                    raise RuntimeError(f"cache identity drift for {stage}/{cache_key}: {key}")
            digest = file_sha256(cache_path)
            destination = quarantine / f"{cache_key}.{digest}.invalid.json"
            if destination.exists():
                if file_sha256(destination) != digest:
                    raise RuntimeError(f"quarantine collision: {destination}")
                cache_path.unlink()
            else:
                cache_path.replace(destination)
            identity = (cache_key, digest)
            if identity not in known:
                ledger.append(
                    {
                        "cache_key": cache_key,
                        "error": str(row.get("error") or ""),
                        "model": str(row.get("model") or ""),
                        "payload_sha256": str(row.get("payload_sha256") or ""),
                        "prompt_sha256": str(row.get("prompt_sha256") or ""),
                        "quarantined_at_utc": utcnow(),
                        "quarantine_path": str(destination),
                        "raw_cache_sha256": digest,
                        "schema": "c2-annotation-invalid-cache-quarantine-v1",
                        "stage": stage,
                        "task_id": str(row.get("task_id") or ""),
                    }
                )
                known.add(identity)
            moved += 1
        write_jsonl(ledger_path, ledger)
        prepared.append(
            {
                "archived_products": archives,
                "failed_cache_n": len(failed),
                "moved_cache_n": moved,
                "stage": stage,
            }
        )
    summary = {
        "created_at_utc": utcnow(),
        "root": str(root),
        "schema": "c2-annotation-recovery-preparation-v1",
        "stages": prepared,
    }
    atomic_json(root / "recovery_preparation.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
