#!/usr/bin/env python3
"""C3 preflight: sha256 backup of DA/MCR frozen assets (no source mutation)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = {
    "da_pilot24": ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1",
    "da_remain76": ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate",
    "da_remain76_frozen": ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/frozen",
    "mcr_compat_synonym": ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1",
    "mcr_compat_frozen": ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/frozen",
    "mcr_compat_annotate": ROOT
    / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate",
}

SUBS = (
    "shared_trees",
    "case_results",
    "mapper",
    "p5_headline_frozen.json",
    "vignette_parser_frozen.json",
    "freeze_manifest.json",
    "stage_manifest.json",
    "downstream_summary.json",
    "pipeline_summary.json",
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
    bak = ROOT / "backups" / f"c3_preflight_{ts}"
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
        "C3 preflight backup (sha256 only; sources untouched)\n"
        f"n_files={len(lines)}\n"
        "arms=AB01,AB02,AB03,AB04,AB06\n"
        "da_mapper=no_synonym_bind\n"
        "slice_block1=DA_d2_seq100_proxy\n"
        "slice_block2=MCR_mcr_val_seq100\n"
        "p0_c3_cap_breach=five_arms_AB01_02_03_04_06\n",
        encoding="utf-8",
    )
    (bak / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    ws = ROOT / "logs/c3_ablation_workspace_v1/meta"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "backup_path.txt").write_text(str(bak) + "\n", encoding="utf-8")
    print(json.dumps({"backup": str(bak), **meta}, indent=2))
    return 0 if meta["backup_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
