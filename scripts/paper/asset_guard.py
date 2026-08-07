#!/usr/bin/env python3
"""SHA256 snapshot / verify for paper-bearing artifacts.

Prevents accidental overwrite of frozen main-paper assets while Tier-1
experiments write into *new* directories.

  snapshot  — write recursive sha256 manifest under analysis/asset_guard/<ts>/
  verify    — compare against latest (or --manifest) snapshot;
              any modified or deleted protected file → nonzero exit.
              New files under protected roots are allowed.

Protected roots (relative to repo root):
  logs/medcasereasoning_mcr_val_seq100_v1
  logs/medcasereasoning_mcr_val_seq100_v2
  logs/open_xddx_ox_seq100_v1
  logs/diagnosisarena_d2_m01_v1
  logs/rarearena_ra_rdc_seq100_v1
  runs/paper_v1
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARD_DIR = ROOT / "analysis" / "asset_guard"

PROTECTED = (
    "logs/medcasereasoning_mcr_val_seq100_v1",
    "logs/medcasereasoning_mcr_val_seq100_v2",
    "logs/open_xddx_ox_seq100_v1",
    "logs/diagnosisarena_d2_m01_v1",
    "logs/rarearena_ra_rdc_seq100_v1",
    "runs/paper_v1",
)

# Skip bulky / regenerable caches that churn without changing paper claims.
SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
}
SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".out",
    ".tmp",
}


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _iter_files(root: Path):
    if not root.is_dir():
        return
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        # Judge / LLM caches under annotate/cache grow during legitimate
        # append-only reuses; still hash them so *mutations* of existing
        # entries are caught (hash of whole file). Callers writing *new*
        # cache files only produce "added" which verify allows.
        yield p


def build_manifest(roots: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in roots:
        base = ROOT / rel
        if not base.exists():
            print(f"[warn] missing root: {rel}", flush=True)
            continue
        for p in _iter_files(base):
            key = str(p.relative_to(ROOT)).replace("\\", "/")
            out[key] = _sha256_file(p)
    return out


def write_manifest(manifest: dict[str, str], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.tsv"
    lines = ["relpath\tsha256"]
    for k in sorted(manifest):
        lines.append(f"{k}\t{manifest[k]}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = out_dir / "meta.txt"
    meta.write_text(
        f"utc={datetime.now(timezone.utc).isoformat()}\n"
        f"n_files={len(manifest)}\n"
        f"roots={','.join(PROTECTED)}\n",
        encoding="utf-8",
    )
    return path


def load_manifest(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if i == 0 and line.startswith("relpath"):
            continue
        if not line.strip():
            continue
        rel, digest = line.split("\t", 1)
        out[rel] = digest
    return out


def latest_manifest() -> Path | None:
    if not GUARD_DIR.is_dir():
        return None
    cands = sorted(
        (p for p in GUARD_DIR.iterdir() if p.is_dir() and (p / "manifest.tsv").is_file()),
        key=lambda p: p.name,
    )
    return (cands[-1] / "manifest.tsv") if cands else None


def cmd_snapshot(args: argparse.Namespace) -> int:
    roots = list(PROTECTED)
    print(f"[snapshot] hashing {len(roots)} roots under {ROOT}", flush=True)
    manifest = build_manifest(roots)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = GUARD_DIR / ts
    path = write_manifest(manifest, out_dir)
    print(f"[snapshot] wrote {path} ({len(manifest)} files)", flush=True)
    # Pointer for convenience.
    (GUARD_DIR / "LATEST").write_text(str(out_dir.relative_to(ROOT)) + "\n", encoding="utf-8")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    man_path = Path(args.manifest) if args.manifest else latest_manifest()
    if man_path is None or not man_path.is_file():
        print("[verify] FAIL: no snapshot found; run snapshot first", flush=True)
        return 2
    if not man_path.is_absolute():
        man_path = ROOT / man_path
    old = load_manifest(man_path)
    print(f"[verify] baseline={man_path} n={len(old)}", flush=True)
    # Only re-hash files that were in the baseline (fast path for modified/deleted).
    # Also walk to detect nothing for "deleted" — missing file is enough.
    modified: list[str] = []
    deleted: list[str] = []
    for rel, digest in old.items():
        p = ROOT / rel
        if not p.is_file():
            deleted.append(rel)
            continue
        now = _sha256_file(p)
        if now != digest:
            modified.append(rel)
    # Count additions under protected roots (informational).
    current = build_manifest(list(PROTECTED))
    added = sorted(set(current) - set(old))
    print(
        f"[verify] modified={len(modified)} deleted={len(deleted)} added={len(added)}",
        flush=True,
    )
    if modified:
        print("[verify] MODIFIED (first 30):", flush=True)
        for r in modified[:30]:
            print(f"  M {r}", flush=True)
    if deleted:
        print("[verify] DELETED (first 30):", flush=True)
        for r in deleted[:30]:
            print(f"  D {r}", flush=True)
    if added and args.verbose:
        print("[verify] ADDED (first 30, allowed):", flush=True)
        for r in added[:30]:
            print(f"  A {r}", flush=True)
    if modified or deleted:
        print("[verify] FAIL: protected assets changed", flush=True)
        return 1
    print("[verify] OK", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser("snapshot", help="Write sha256 manifest")
    p_snap.set_defaults(func=cmd_snapshot)

    p_ver = sub.add_parser("verify", help="Verify against snapshot")
    p_ver.add_argument(
        "--manifest",
        type=str,
        default="",
        help="Path to manifest.tsv (default: latest under analysis/asset_guard)",
    )
    p_ver.add_argument("-v", "--verbose", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
