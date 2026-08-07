#!/usr/bin/env python3
"""C2 preflight: sha256 backup of OX/DA frozen assets (no source mutation)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = {
    "ox_frozen": ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1/frozen",
    "ox_hot_annotate": ROOT
    / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1/annotate",
    "da_pilot24": ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1",
    "da_remain76": ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate",
}

# Only hash these subtrees (avoid giant caches)
SUBS = (
    "shared_trees",
    "case_results",
    "mapper",
    "p5_headline_frozen.json",
    "vignette_parser_frozen.json",
    "freeze_manifest.json",
    "stage_manifest.json",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    if not root.exists():
        return out
    for name in SUBS:
        p = root / name
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(p.rglob("*.json")))
    return out


def main() -> int:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / "backups" / f"c2_preflight_{ts}"
    bak.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    meta: dict = {"created": ts, "targets": {}, "n_files": 0}
    for label, root in TARGETS.items():
        files = _iter_files(root)
        meta["targets"][label] = {
            "path": str(root),
            "exists": root.exists(),
            "n_files": len(files),
        }
        for fp in files:
            rel = f"{label}/{fp.relative_to(root)}"
            digest = _sha256(fp)
            lines.append(f"{digest}  {rel}")
    (bak / "sha256sums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta["n_files"] = len(lines)
    meta["backup_ok"] = len(lines) > 0
    (bak / "note.txt").write_text(
        "C2 preflight backup (sha256 only; sources untouched)\n"
        f"n_files={len(lines)}\n"
        "arms=AB13,AB14,AB16,AB17,AB19,AB21,AB22,AB28\n"
        "da_mapper=no_synonym_bind\n",
        encoding="utf-8",
    )
    (bak / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    ws = ROOT / "logs/c2_ablation_workspace_v1/meta"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "backup_path.txt").write_text(str(bak) + "\n", encoding="utf-8")
    print(json.dumps({"backup": str(bak), **meta}, indent=2))
    return 0 if meta["backup_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
