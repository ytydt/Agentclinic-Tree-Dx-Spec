#!/usr/bin/env python3
"""C2 DA selector suite (AB21/AB22) + AB28 typed-remap recheck.

Isolation: logs/diagnosisarena_d2_m01_v1/c2_<arm>_v1/
DA mapper: synonym_bind OFF (S1 main protocol).
Does not mutate pilot24 / remain76 frozen trees or at1_compat_v1.
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
PILOT = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
REMAIN = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate"
SUBSET = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1"
OUT_ROOT = ROOT / "logs/diagnosisarena_d2_m01_v1"
CASES_JSON = ROOT / "data/benchmarks/diagnosisarena/normalized_cases.json"

ARMS: dict[str, dict[str, Any]] = {
    "ab21": {
        "dir": "c2_ab21_v1",
        "label": "AB21 salience≈p5_contrastive_direct (proxy for plan salience)",
        "l1_bfs_preset": "p5_contrastive_direct",
        "no_inject_compiler": False,
    },
    "ab22": {
        "dir": "c2_ab22_v1",
        "label": "AB22 anti-anchor + no P5 compiler inject",
        "l1_bfs_preset": "p5_anti_anchor_direct",
        "no_inject_compiler": True,
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
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for cid in case_ids:
        for src_root in (PILOT / "shared_trees", REMAIN / "shared_trees"):
            sp = src_root / f"{cid}.json"
            if sp.is_file():
                shutil.copy2(sp, dst / sp.name)
                n += 1
                break
    return n


def _merge_normalized_cases(out: Path, case_ids: Sequence[str]) -> Path:
    by_id: dict[str, Any] = {}
    for src in (
        PILOT / "normalized_cases.json",
        REMAIN / "normalized_cases.json",
    ):
        if not src.is_file():
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        for c in doc.get("cases") or []:
            by_id[str(c.get("id"))] = c
    # Fallback: global cases json if present
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
    """Merge standard-pipeline vignette freezes (pilot v3 + remain76)."""
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
        "asset_kind": "vignette_parser_frozen_c2_merged",
        "note": "C2 merge of vignette_parser_probe_v3 + remain76 frozen",
        "cases": [by_id[cid] for cid in case_ids],
        "n_cases": len(case_ids),
    }
    path = out / "frozen" / "vignette_parser_frozen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"path": str(path), "n_cases": len(case_ids)}


def _merge_p5_headline(out: Path) -> dict[str, Any]:
    """Merge pilot+remain p5_headline_frozen.json (disc_audit keyed by case id)."""
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
        # Prefer non-empty rows if either side has them
        rows = doc.get("rows") or []
        if rows and not (merged.get("rows") or []):
            merged["rows"] = rows
    if merged is None:
        raise FileNotFoundError("missing p5_headline_frozen.json under pilot/remain")
    path = out / "frozen" / "p5_headline_frozen.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "n_disc_audit": len(merged.get("disc_audit") or {}),
    }


def _merge_p5_audit(out: Path, case_ids: Sequence[str]) -> int:
    """Copy standard-pipeline per-case p5_audit into out/frozen/p5_audit/."""
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
            "missing standard-pipeline p5_audit for %d cases (e.g. %s)"
            % (len(missing), missing[:8])
        )
    return n


def _prepare(out: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    n_trees = _merge_trees(out, case_ids)
    cases_path = _merge_normalized_cases(out, case_ids)
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    # Refresh annotate trees from frozen
    dst = ann / "shared_trees"
    dst.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = out / "frozen" / "shared_trees" / f"{cid}.json"
        if sp.is_file():
            shutil.copy2(sp, dst / sp.name)
    # Standard DA pipeline freezes (vignette + P5)
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
    # Seed caches from remain/pilot for speed
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
        "n_cases_json": len(json.loads(cases_path.read_text())["cases"]),
    }




def _run_annotate_mapper(
    out: Path,
    case_ids: Sequence[str],
    *,
    preset: str,
    no_inject: bool,
    workers: int,
    model: str,
) -> int:
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
        "--l2-candidate-max-per-live-family", "6",
        "--l1-bfs-preset", preset,
        "--mapper-mode", "typed_llm_disagreement_rag",
        "--resume",
        # NO --synonym-bind-repair
    ]
    if no_inject:
        cmd.append("--no-inject-compiler-rules")
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _run_ab28(*, workers: int, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_l1_gold_recall_typed_remap.py"),
        "--cohort", "all100",
        "--inject-mode", "full",
        "--mapper-mode", "typed_llm",
        "--workers", str(workers),
        "--out", str(out),
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
    if not p.is_file():
        # records.json may embed summary
        r = out / "annotate" / "mapper" / "records.json"
        if r.is_file():
            doc = json.loads(r.read_text(encoding="utf-8"))
            return doc.get("summary") if isinstance(doc, dict) else None
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", default="ab21,ab22", help="Live DA arms (AB28 = historical reuse)")
    ap.add_argument("--n-cases", type=int, default=100)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument(
        "--run-ab28-live",
        action="store_true",
        help="Override: actually re-run AB28 typed remap (discouraged)",
    )
    args = ap.parse_args()

    case_ids = _load_ids(args.n_cases)
    wanted = [a.strip().lower() for a in str(args.arms).split(",") if a.strip()]
    wanted = [k for k in wanted if k != "ab28"]
    results: dict[str, Any] = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "workers": int(args.workers),
        "synonym_bind": False,
        "slice_note": (
            "Block4 planned D1b-dev-freeze missing; AB21/AB22 run on DA d2_seq100 proxy; "
            "AB28 historical reuse (smoke_typed_remap all100)"
        ),
        "m00_da_compat": {"option_top1": 0.71, "option_top2": 0.78},
        "arms": {},
    }

    reuse_path = ROOT / "runs/paper_v1/ablations_c2_ab28_reused.json"
    if not args.run_ab28_live:
        if reuse_path.is_file():
            reused = json.loads(reuse_path.read_text(encoding="utf-8"))
            results["arms"]["ab28"] = {
                "label": reused.get("label"),
                "output_dir": reused.get("source_run_dir"),
                "exit_code": 0,
                "summary": reused.get("summary"),
                "reused": True,
                "R_compat": reused.get("R_compat"),
                "R_compat_inject_typed": reused.get("R_compat_inject_typed"),
                "delta_opt1": reused.get("delta_opt1"),
                "source_summary": reused.get("source_summary"),
                "note": reused.get("note"),
            }
            print("AB28 skipped (reuse archive):", reuse_path, flush=True)
        else:
            print(
                "AB28 archive missing; run scripts/paper/c2_record_ab28_reuse.py",
                flush=True,
            )

    for key in wanted:
        if key not in ARMS:
            print("unknown arm", key, file=sys.stderr)
            return 2
        spec = ARMS[key]
        out = OUT_ROOT / spec["dir"]
        out.mkdir(parents=True, exist_ok=True)
        prep = {}
        if not args.skip_annotate:
            prep = _prepare(out, case_ids)
        launch = {
            "arm": key,
            "label": spec["label"],
            "preset": spec["l1_bfs_preset"],
            "no_inject_compiler": spec["no_inject_compiler"],
            "prep": prep,
            "created_at": _utc(),
        }
        _write_json(out / "c2_launch.json", launch)
        code = 0
        if not args.skip_annotate:
            code = _run_annotate_mapper(
                out,
                case_ids,
                preset=str(spec["l1_bfs_preset"]),
                no_inject=bool(spec["no_inject_compiler"]),
                workers=int(args.workers),
                model=str(args.model),
            )
        metrics = _mapper_metrics(out)
        results["arms"][key] = {
            "label": spec["label"],
            "output_dir": str(out),
            "exit_code": code,
            "mapper": metrics,
            "synonym_bind": False,
        }
        print(json.dumps({key: results["arms"][key]}, indent=2, ensure_ascii=False), flush=True)

    if args.run_ab28_live:
        ab28_out = ROOT / "analysis/l1_gold_recall_v1/smoke_typed_remap_t110_live"
        code = _run_ab28(workers=int(args.workers), out=ab28_out)
        summary = ab28_out / "summary_typed_all100.json"
        if not summary.is_file():
            summary = ab28_out / "summary.json"
        metrics = None
        if summary.is_file():
            metrics = json.loads(summary.read_text(encoding="utf-8"))
        results["arms"]["ab28"] = {
            "label": "AB28 full leaf inject + typed remap recheck",
            "output_dir": str(ab28_out),
            "exit_code": code,
            "summary": metrics,
            "reused": False,
        }
        print(json.dumps({"ab28": results["arms"]["ab28"]}, indent=2, ensure_ascii=False), flush=True)

    out_json = ROOT / "runs/paper_v1/ablations_c2_da_raw.json"
    if args.run_ab28_live and not wanted:
        # Isolate T1-10 live recheck; never overwrite published C2 DA summary.
        out_json = ROOT / "runs/paper_v1/ablations_t110_ab28_live.json"
    _write_json(out_json, results)
    print("WROTE", out_json, flush=True)
    bad = [k for k, v in results["arms"].items() if int(v.get("exit_code") or 0) != 0]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
