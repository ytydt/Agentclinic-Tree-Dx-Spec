#!/usr/bin/env python3
"""C3 DA hierarchy suite (AB01/AB02/AB03) on d2_seq100 proxy.

Isolation: logs/diagnosisarena_d2_m01_v1/c3_ab{01,02,03}_v1/
DA mapper: synonym_bind OFF. Does not mutate pilot24 / remain76.
Order (plan): AB01 → AB03 → AB02.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import c3_l1_axis  # noqa: E402

PILOT = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
REMAIN = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate"
SUBSET = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1"
OUT_ROOT = ROOT / "logs/diagnosisarena_d2_m01_v1"
CASES_JSON = ROOT / "data/benchmarks/diagnosisarena/normalized_cases.json"

ARMS: dict[str, dict[str, Any]] = {
    "ab01": {
        "dir": "c3_ab01_v1",
        "label": "AB01 fixed ICD/specialty L1",
        "l1_axis_mode": "fixed_icd",
    },
    "ab03": {
        "dir": "c3_ab03_v1",
        "label": "AB03 case-independent random L1",
        "l1_axis_mode": "random",
    },
    "ab02": {
        "dir": "c3_ab02_v1",
        "label": "AB02 flat / no L1",
        "l1_axis_mode": "flat",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_ids(n: int | None) -> list[str]:
    ids = [
        ln.strip()
        for ln in (SUBSET / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if n is not None:
        ids = ids[: int(n)]
    return ids


def _merge_trees(out: Path, case_ids: Sequence[str]) -> int:
    dst = out / "frozen" / "shared_trees"
    # Drop stale trees from prior n-case prepares (stage_assets scans the dir).
    if dst.is_dir():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    wanted = {str(cid) for cid in case_ids}
    n = 0
    for cid in case_ids:
        for src_root in (PILOT / "shared_trees", REMAIN / "shared_trees"):
            sp = src_root / f"{cid}.json"
            if sp.is_file():
                shutil.copy2(sp, dst / sp.name)
                n += 1
                break
    # Belt-and-suspenders: remove any non-requested json left behind.
    for path in dst.glob("*.json"):
        if path.stem != "summary" and path.stem not in wanted:
            path.unlink()
    return n


def _merge_normalized_cases(out: Path, case_ids: Sequence[str]) -> Path:
    by_id: dict[str, Any] = {}
    for src in (PILOT / "normalized_cases.json", REMAIN / "normalized_cases.json"):
        if not src.is_file():
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        for c in doc.get("cases") or []:
            by_id[str(c.get("id"))] = c
    if CASES_JSON.is_file():
        doc = json.loads(CASES_JSON.read_text(encoding="utf-8"))
        for c in doc.get("cases") or []:
            cid = str(c.get("id"))
            if cid in set(case_ids) and cid not in by_id:
                by_id[cid] = c
    cases = [by_id[cid] for cid in case_ids if cid in by_id]
    path = out / "normalized_cases.json"
    _write_json(path, {"schema_version": 1, "cases": cases})
    return path


def _merge_vignette_freeze(out: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    sources = (
        ROOT / "logs/diagnosisarena_d2_m01_v1/vignette_parser_probe_v3/vignette_parser_frozen_v3.json",
        ROOT
        / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/frozen/vignette_parser_frozen.json",
    )
    by_id: dict[str, Any] = {}
    base_meta: dict[str, Any] = {}
    for sp in sources:
        if not sp.is_file():
            continue
        doc = json.loads(sp.read_text(encoding="utf-8"))
        if not base_meta:
            base_meta = {k: v for k, v in doc.items() if k != "cases"}
        for row in doc.get("cases") or []:
            cid = str(row.get("case_id") or "").strip()
            if cid:
                by_id[cid] = row
    missing = [cid for cid in case_ids if cid not in by_id]
    if missing:
        raise FileNotFoundError(
            "vignette freeze missing %d cases (e.g. %s)" % (len(missing), missing[:8])
        )
    merged = {
        **base_meta,
        "human_signed_off": True,
        "asset_kind": "vignette_parser_frozen_c3_merged",
        "note": "C3 merge of vignette_parser_probe_v3 + remain76 frozen",
        "cases": [by_id[cid] for cid in case_ids],
        "n_cases": len(case_ids),
    }
    path = out / "frozen" / "vignette_parser_frozen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(path), "n_cases": len(case_ids)}


def _merge_p5_headline(out: Path) -> dict[str, Any]:
    merged: dict[str, Any] | None = None
    dict_keys = (
        "disc_audit",
        "case_normalized",
        "entry_audit",
        "key_audit",
        "audit_summary",
    )
    for src_root in (PILOT, REMAIN):
        sp = src_root / "p5_headline_frozen.json"
        if not sp.is_file():
            continue
        doc = json.loads(sp.read_text(encoding="utf-8"))
        if merged is None:
            merged = dict(doc)
            for k in dict_keys:
                merged[k] = dict(doc.get(k) or {})
            continue
        for k in dict_keys:
            bucket = dict(merged.get(k) or {})
            bucket.update(dict(doc.get(k) or {}))
            merged[k] = bucket
        rows = doc.get("rows") or []
        if rows and not (merged.get("rows") or []):
            merged["rows"] = rows
    if merged is None:
        raise FileNotFoundError("missing p5_headline_frozen.json under pilot/remain")
    path = out / "frozen" / "p5_headline_frozen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(path), "n_disc_audit": len(merged.get("disc_audit") or {})}


def _merge_p5_audit(out: Path, case_ids: Sequence[str]) -> int:
    dst = out / "frozen" / "p5_audit"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    missing: list[str] = []
    for cid in case_ids:
        found = False
        for src_root in (PILOT / "p5_audit", REMAIN / "p5_audit"):
            sp = src_root / f"{cid}.json"
            if sp.is_file():
                shutil.copy2(sp, dst / sp.name)
                n += 1
                found = True
                break
        if not found:
            missing.append(str(cid))
    if missing:
        raise FileNotFoundError(
            "missing p5_audit for %d cases (e.g. %s)" % (len(missing), missing[:8])
        )
    return n


def _prepare(out: Path, case_ids: Sequence[str], *, axis_mode: str) -> dict[str, Any]:
    n_trees = _merge_trees(out, case_ids)
    # Materialize L1 axis on frozen trees (Config A will strip/regen L2).
    axis_meta = c3_l1_axis.rewrite_tree_dir(
        out / "frozen" / "shared_trees",
        axis_mode,
        case_ids=case_ids,
        max_l1=6,
        keep_leaves=False,
    )
    cases_path = _merge_normalized_cases(out, case_ids)
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    dst = ann / "shared_trees"
    dst.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = out / "frozen" / "shared_trees" / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, dst / sp.name)
    (out / "frozen").mkdir(parents=True, exist_ok=True)
    vign = _merge_vignette_freeze(out, case_ids)
    p5_head = _merge_p5_headline(out)
    n_audit = _merge_p5_audit(out, case_ids)
    shutil.copy2(out / "frozen" / "p5_headline_frozen.json", ann / "p5_headline_frozen.json")
    audit_ann = ann / "p5_audit"
    audit_ann.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = out / "frozen" / "p5_audit" / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, audit_ann / sp.name)
    for name in ("finding_fixture_v1.json",):
        for src_root in (PILOT, REMAIN):
            sp = src_root / name
            if sp.is_file():
                shutil.copy2(sp, out / name)
                shutil.copy2(sp, ann / name)
                break
    shutil.copy2(cases_path, ann / "normalized_cases.json")
    man = ann / "stage_manifest.json"
    if man.is_file():
        man.unlink()
    n_cache = 0
    for cid in case_ids:
        for src_root in (REMAIN / "cache", PILOT / "cache"):
            s = src_root / cid
            if s.is_dir():
                d = ann / "cache" / cid
                if not d.exists():
                    shutil.copytree(s, d)
                    n_cache += 1
                break
    return {
        "n_trees": n_trees,
        "n_cache": n_cache,
        "n_p5_audit": n_audit,
        "p5_headline": p5_head,
        "vignette": vign,
        "axis": axis_meta,
        "n_cases_json": len(json.loads(cases_path.read_text())["cases"]),
    }


def _run_annotate_mapper(
    out: Path,
    case_ids: Sequence[str],
    *,
    axis_mode: str,
    workers: int,
    model: str,
) -> int:
    per_family = 6
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(out / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--from-stage", "annotate",
        "--to-stage", "mapper",
        "--fixed-l1-budget", "6",
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", str(per_family),
        "--l1-bfs-preset", "p5_anti_anchor_direct",
        "--l1-axis-mode", axis_mode,
        "--mapper-mode", "typed_llm_disagreement_rag",
        "--resume",
        # NO --synonym-bind-repair
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _mapper_metrics(out: Path) -> dict[str, Any] | None:
    p = out / "annotate" / "mapper" / "summary.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    r = out / "annotate" / "mapper" / "records.json"
    if r.is_file():
        doc = json.loads(r.read_text(encoding="utf-8"))
        return doc.get("summary") if isinstance(doc, dict) else None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="ab01,ab03,ab02")
    ap.add_argument("--n-cases", type=int, default=100)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--skip-annotate", action="store_true")
    args = ap.parse_args()

    case_ids = _load_ids(args.n_cases)
    wanted = [a.strip().lower() for a in str(args.arms).split(",") if a.strip()]
    results: dict[str, Any] = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "workers": int(args.workers),
        "synonym_bind": False,
        "slice_note": (
            "Block1 planned D1b-dev-freeze missing; AB01–AB03 on DA d2_seq100 proxy"
        ),
        "m00_da_compat": {"option_top1": 0.71, "option_top2": 0.78},
        "arms": {},
    }

    for key in wanted:
        if key not in ARMS:
            print("unknown arm", key, file=sys.stderr)
            return 2
        spec = ARMS[key]
        out = OUT_ROOT / spec["dir"]
        out.mkdir(parents=True, exist_ok=True)
        prep: dict[str, Any] = {}
        if not args.skip_annotate:
            prep = _prepare(out, case_ids, axis_mode=str(spec["l1_axis_mode"]))
        launch = {
            "arm": key,
            "label": spec["label"],
            "l1_axis_mode": spec["l1_axis_mode"],
            "prep": prep,
            "created_at": _utc(),
            "synonym_bind": False,
        }
        _write_json(out / "c3_launch.json", launch)
        code = 0
        if not args.skip_annotate:
            code = _run_annotate_mapper(
                out,
                case_ids,
                axis_mode=str(spec["l1_axis_mode"]),
                workers=int(args.workers),
                model=str(args.model),
            )
        metrics = _mapper_metrics(out)
        results["arms"][key] = {
            "label": spec["label"],
            "output_dir": str(out),
            "exit_code": code,
            "l1_axis_mode": spec["l1_axis_mode"],
            "mapper": metrics,
            "synonym_bind": False,
        }
        print(json.dumps({key: results["arms"][key]}, indent=2, ensure_ascii=False), flush=True)

    out_json = ROOT / "runs/paper_v1/ablations_c3_da_raw.json"
    _write_json(out_json, results)
    print("WROTE", out_json, flush=True)
    bad = [k for k, v in results["arms"].items() if int(v.get("exit_code") or 0) != 0]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
