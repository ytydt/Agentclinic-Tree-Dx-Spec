#!/usr/bin/env python3
"""Download raw paper-experiment benchmark datasets (Phase 1, PAPER plan §5).

Outputs under ``data/benchmarks/<dataset>/raw/`` plus a pinned
``data/benchmarks/download_manifest.json`` with revision, byte size, and SHA-256.

Usage:
    clashon   # enable local proxy if needed
    conda activate gnn-llm
    python scripts/paper/download_benchmark_datasets.py
    python scripts/paper/download_benchmark_datasets.py --datasets diagnosisarena ddxplus
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARKS = ROOT / "data" / "benchmarks"
MANIFEST_PATH = BENCHMARKS / "download_manifest.json"

USER_AGENT = "Agentclinic-Tree-Dx-Spec paper-benchmark-downloader/1.0"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hf_revision(repo: str) -> str:
    from huggingface_hub import dataset_info

    return dataset_info(repo).sha


def hf_download(repo: str, remote: str, target: Path, revision: str | None = None) -> None:
    """Download via huggingface.co resolve URL (avoids flaky HF_ENDPOINT mirrors)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    rev = revision or "main"
    url = f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{remote}"
    partial = target.with_suffix(target.suffix + ".part")
    print(f"  GET {url}")
    result = subprocess.run(
        ["curl", "-sSL", "--fail", "-o", str(partial), url],
        check=False,
    )
    if result.returncode != 0 or not partial.exists() or partial.stat().st_size == 0:
        if partial.exists():
            partial.unlink()
        raise RuntimeError(f"download failed: {repo}/{remote}")
    os.replace(partial, target)


def url_download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response, partial.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    os.replace(partial, target)


def record_file(
    dataset_id: str,
    relative: str,
    target: Path,
    *,
    source_page: str,
    revision: str,
    license_note: str,
    extra: dict | None = None,
) -> dict:
    payload = {
        "dataset_id": dataset_id,
        "relative_path": relative,
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
        "source_page": source_page,
        "revision": revision,
        "license_note": license_note,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def download_diagnosisarena(raw: Path) -> list[dict]:
    repo = "shzyk/DiagnosisArena"
    revision = hf_revision(repo)
    rel = "data/test-00000-of-00001.parquet"
    target = raw / "test.parquet"
    if not target.exists():
        print(f"[diagnosisarena] HF {repo}@{revision[:12]} -> {target.name}")
        hf_download(repo, rel, target, revision=revision)
    else:
        print(f"[diagnosisarena] SKIP existing {target.name}")
    return [
        record_file(
            "diagnosisarena",
            "raw/test.parquet",
            target,
            source_page=f"https://huggingface.co/datasets/{repo}",
            revision=revision,
            license_note="Pinned public HF snapshot; record revision and row count in flow report.",
            extra={"hf_repo": repo, "hf_file": rel},
        )
    ]


def download_medcasereasoning(raw: Path) -> list[dict]:
    repo = "zou-lab/MedCaseReasoning"
    revision = hf_revision(repo)
    files = [
        "data/val-00000-of-00001.parquet",
        "data/test-00000-of-00001.parquet",
        "data/train-00000-of-00001.parquet",
        "medcasereasoning_core.csv",
        "medcasereasoning_core.pqt",
    ]
    records: list[dict] = []
    for rel in files:
        local_name = Path(rel).name
        target = raw / local_name
        if not target.exists():
            print(f"[medcasereasoning] HF {repo}@{revision[:12]} -> {local_name}")
            hf_download(repo, rel, target, revision=revision)
        else:
            print(f"[medcasereasoning] SKIP existing {local_name}")
        records.append(
            record_file(
                "medcasereasoning",
                f"raw/{local_name}",
                target,
                source_page=f"https://huggingface.co/datasets/{repo}",
                revision=revision,
                license_note="HF card declares MIT; D1 uses validation split only.",
                extra={"hf_repo": repo, "hf_file": rel},
            )
        )
    return records


def download_open_xddx(raw: Path) -> list[dict]:
    revision = "a8ea4a954479e38f318ae8a871192c4daa2b26ec"
    url = (
        "https://raw.githubusercontent.com/betterzhou/Dual-Inf/"
        f"{revision}/Open-XDDx.xlsx"
    )
    target = raw / "Open-XDDx.xlsx"
    if not target.exists():
        print(f"[open_xddx] GitHub Dual-Inf@{revision[:12]} -> Open-XDDx.xlsx")
        url_download(url, target)
    else:
        print("[open_xddx] SKIP existing Open-XDDx.xlsx")
    return [
        record_file(
            "open_xddx",
            "raw/Open-XDDx.xlsx",
            target,
            source_page="https://github.com/betterzhou/Dual-Inf",
            revision=revision,
            license_note="No explicit LICENSE at pinned revision; local use only.",
            extra={"download_url": url},
        )
    ]


def download_rarebench(raw: Path) -> list[dict]:
    repo = "chenxz/RareBench"
    revision = hf_revision(repo)
    records: list[dict] = []

    zip_rel = "data.zip"
    zip_target = raw / "data.zip"
    if not zip_target.exists():
        print(f"[rarebench] HF {repo}@{revision[:12]} -> data.zip")
        hf_download(repo, zip_rel, zip_target, revision=revision)
    else:
        print("[rarebench] SKIP existing data.zip")

    extract_dir = raw / "data"
    if not extract_dir.exists() or not any(extract_dir.glob("*.jsonl")):
        print("[rarebench] extracting data.zip -> raw/data/")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_target) as archive:
            archive.extractall(raw)
    else:
        print("[rarebench] SKIP extract (jsonl present)")

    records.append(
        record_file(
            "rarebench",
            "raw/data.zip",
            zip_target,
            source_page=f"https://huggingface.co/datasets/{repo}",
            revision=revision,
            license_note="HF card declares Apache-2.0; Task 4 uses MME/HMS/LIRICAL jsonl.",
            extra={"hf_repo": repo, "hf_file": zip_rel},
        )
    )

    mapping_files = [
        "mapping/disease_mapping.json",
        "mapping/phenotype_mapping.json",
        "mapping/ic_dict.json",
    ]
    for rel in mapping_files:
        local_name = Path(rel).name
        target = raw / "mapping" / local_name
        if not target.exists():
            print(f"[rarebench] HF mapping -> {local_name}")
            hf_download(repo, rel, target, revision=revision)
        records.append(
            record_file(
                "rarebench",
                f"raw/mapping/{local_name}",
                target,
                source_page=f"https://huggingface.co/datasets/{repo}",
                revision=revision,
                license_note="RareBench mapping artifact.",
                extra={"hf_repo": repo, "hf_file": rel},
            )
        )
    return records


def download_ddxplus(raw: Path) -> list[dict]:
    repo = "aai530-group6/ddxplus"
    revision = hf_revision(repo)
    files = [
        "test.csv",
        "train.csv",
        "validate.csv",
        "release_conditions.json",
        "release_evidences.json",
    ]
    records: list[dict] = []
    for rel in files:
        target = raw / rel
        if not target.exists():
            print(f"[ddxplus] HF {repo}@{revision[:12]} -> {rel}")
            hf_download(repo, rel, target, revision=revision)
        else:
            print(f"[ddxplus] SKIP existing {rel}")
        records.append(
            record_file(
                "ddxplus",
                f"raw/{rel}",
                target,
                source_page=f"https://huggingface.co/datasets/{repo}",
                revision=revision,
                license_note="English DDXPlus mirror (CC-BY); D5 subsamples 980 from test.csv.",
                extra={"hf_repo": repo, "hf_file": rel},
            )
        )
    return records


def download_rarearena(raw: Path) -> list[dict]:
    repo = "THUMedInfo/RareArena"
    revision = hf_revision(repo)
    files = [
        ("RDC.json", "RDC.json"),
        ("RDS.json", "RDS.json"),
    ]
    records: list[dict] = []
    for remote, local in files:
        target = raw / local
        if not target.exists():
            print(f"[rarearena] HF {repo}@{revision[:12]} -> {local}")
            hf_download(repo, remote, target, revision=revision)
        else:
            print(f"[rarearena] SKIP existing {local}")
        records.append(
            record_file(
                "rarearena",
                f"raw/{local}",
                target,
                source_page=f"https://huggingface.co/datasets/{repo}",
                revision=revision,
                license_note="CC BY-NC-SA 4.0; D6 requires custom REP-v1 manifest.",
                extra={"hf_repo": repo, "hf_file": remote},
            )
        )
    return records


DOWNLOADERS = {
    "diagnosisarena": download_diagnosisarena,
    "medcasereasoning": download_medcasereasoning,
    "open_xddx": download_open_xddx,
    "rarebench": download_rarebench,
    "ddxplus": download_ddxplus,
    "rarearena": download_rarearena,
}


def summarize(records: list[dict]) -> None:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        pq = None

    for rec in records:
        path = BENCHMARKS / rec["dataset_id"] / rec["relative_path"]
        if path.suffix == ".parquet" and pq is not None:
            try:
                n = pq.read_metadata(path).num_rows
                rec["rows"] = n
                print(f"  rows={n}  {rec['dataset_id']}/{rec['relative_path']}")
            except Exception as exc:  # noqa: BLE001
                print(f"  WARN row count failed for {path}: {exc}")
        elif path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                rec["rows"] = sum(1 for _ in handle)
            print(f"  rows={rec['rows']}  {rec['dataset_id']}/{rec['relative_path']}")


def main() -> int:
    # Local HF mirrors often break when combined with clash; force direct hub access.
    os.environ.pop("HF_ENDPOINT", None)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasets",
        nargs="*",
        choices=sorted(DOWNLOADERS),
        help="subset to download (default: all P0 + optional rarearena)",
    )
    parser.add_argument(
        "--include-rarearena",
        action="store_true",
        help="also download P1 RareArena raw files",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=BENCHMARKS,
        help="benchmark root (default: data/benchmarks)",
    )
    args = parser.parse_args()

    selected = list(args.datasets or ["diagnosisarena", "medcasereasoning", "open_xddx", "rarebench", "ddxplus"])
    if args.include_rarearena and "rarearena" not in selected:
        selected.append("rarearena")

    all_records: list[dict] = []
    for dataset_id in selected:
        raw = args.output_root / dataset_id / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        print(f"\n=== {dataset_id} -> {raw} ===")
        all_records.extend(DOWNLOADERS[dataset_id](raw))

    print("\n=== row counts ===")
    summarize(all_records)

    manifest = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plan_reference": "PAPER_EXPERIMENT_EXECUTION_PLAN.md §5 (D1-D6 raw download)",
        "artifacts": all_records,
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote manifest: {MANIFEST_PATH}")
    print(f"Downloaded/verified {len(all_records)} artifacts across {len(selected)} datasets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
