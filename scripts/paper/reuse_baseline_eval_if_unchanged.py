#!/usr/bin/env python3
"""Reuse OX/MCR/DA eval artifacts when SC predictions match a reference arm.

Compares normalized ordered_diagnoses. For unchanged cases:
  - OX/MCR: copy case_scores/*.json (so --resume-scores skips judge)
  - optionally merge judge_cache.json
  - DA: copy matching mapper/records.json entries when present

Does NOT skip projection rebuild (cheap / no judge).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

import baseline_aggregate as bagg


def _names(row: dict[str, Any]) -> list[str]:
    top = row.get("ordered_diagnoses") or row.get("top2_diagnoses") or []
    out: list[str] = []
    for item in top:
        if isinstance(item, dict):
            out.append(str(item.get("diagnosis") or "").strip())
        else:
            out.append(str(item).strip())
    return [x for x in out if x]


def _key_list(names: list[str]) -> tuple[str, ...]:
    return tuple(bagg.normalize_disease_key(n) for n in names)


def load_preds(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[str(row["case_id"])] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--new-pred-dir", type=Path, required=True)
    ap.add_argument("--ref-pred-dir", type=Path, required=True)
    ap.add_argument(
        "--dataset",
        default="open_xddx",
        choices=("diagnosisarena", "open_xddx", "medcasereasoning", "ox", "mcr", "da"),
    )
    ap.add_argument("--out-manifest", type=Path, default=None)
    args = ap.parse_args()

    ds = args.dataset
    if ds in ("ox",):
        ds = "open_xddx"
    elif ds in ("mcr",):
        ds = "medcasereasoning"
    elif ds in ("da",):
        ds = "diagnosisarena"

    new_dir = args.new_pred_dir
    ref_dir = args.ref_pred_dir
    new_preds = load_preds(new_dir / "predictions.jsonl")
    ref_preds = load_preds(ref_dir / "predictions.jsonl")

    unchanged: list[str] = []
    changed: list[str] = []
    missing_ref: list[str] = []
    for cid, nrow in sorted(new_preds.items()):
        rrow = ref_preds.get(cid)
        if rrow is None:
            missing_ref.append(cid)
            changed.append(cid)
            continue
        if _key_list(_names(nrow)) == _key_list(_names(rrow)):
            unchanged.append(cid)
        else:
            changed.append(cid)

    copied_scores = 0
    if ds != "diagnosisarena":
        ref_scores = ref_dir / "annotate" / "official_eval_llm" / "case_scores"
        new_scores = new_dir / "annotate" / "official_eval_llm" / "case_scores"
        new_scores.mkdir(parents=True, exist_ok=True)
        # Prefer numeric stem used by OX/MCR (source_id) if present.
        for cid in unchanged:
            src_id = str((new_preds[cid].get("source_id") or "")).strip()
            # case_scores files are typically "{source_id}.json"
            for stem in (src_id, cid, cid.split("__")[-1].lstrip("0") or cid):
                if not stem:
                    continue
                src = ref_scores / f"{stem}.json"
                if src.is_file():
                    dst = new_scores / f"{stem}.json"
                    shutil.copy2(src, dst)
                    copied_scores += 1
                    break

        ref_cache = ref_dir / "annotate" / "official_eval_llm" / "judge_cache.json"
        new_cache = new_dir / "annotate" / "official_eval_llm" / "judge_cache.json"
        if ref_cache.is_file():
            new_cache.parent.mkdir(parents=True, exist_ok=True)
            if new_cache.is_file():
                base = json.loads(ref_cache.read_text(encoding="utf-8"))
                cur = json.loads(new_cache.read_text(encoding="utf-8"))
                if isinstance(base, dict) and isinstance(cur, dict):
                    merged = dict(base)
                    merged.update(cur)
                    new_cache.write_text(
                        json.dumps(merged, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                else:
                    shutil.copy2(ref_cache, new_cache)
            else:
                shutil.copy2(ref_cache, new_cache)
    else:
        # DA mapper records
        ref_rec = ref_dir / "mapper" / "records.json"
        new_rec_path = new_dir / "mapper" / "records.json"
        if ref_rec.is_file() and unchanged:
            ref_rows = json.loads(ref_rec.read_text(encoding="utf-8"))
            by_id = {
                str(r.get("case_id")): r
                for r in ref_rows
                if isinstance(r, dict) and r.get("case_id")
            }
            kept = [by_id[cid] for cid in unchanged if cid in by_id]
            new_rec_path.parent.mkdir(parents=True, exist_ok=True)
            # Only seed unchanged; scorer may overwrite/extend later.
            new_rec_path.write_text(
                json.dumps(kept, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Copy mapper LLM cache so identical top2 hits without API.
            ref_mcache = ref_dir / "cache" / "mapper_llm.json"
            new_mcache = new_dir / "cache" / "mapper_llm.json"
            if ref_mcache.is_file():
                new_mcache.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ref_mcache, new_mcache)

    manifest = {
        "new_pred_dir": str(new_dir),
        "ref_pred_dir": str(ref_dir),
        "dataset": ds,
        "n_new": len(new_preds),
        "n_unchanged": len(unchanged),
        "n_changed": len(changed),
        "n_missing_ref": len(missing_ref),
        "copied_case_scores": copied_scores,
        "unchanged_case_ids": unchanged,
        "changed_case_ids": changed,
    }
    out = args.out_manifest or (new_dir / "eval_reuse_vs_ref.json")
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in manifest if not k.endswith("_ids")}, indent=2))
    print(f"wrote {out}")
    print(f"changed={len(changed)} unchanged={len(unchanged)} copied_scores={copied_scores}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
