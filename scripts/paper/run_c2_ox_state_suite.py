#!/usr/bin/env python3
"""C2 OX state-propagation suite (AB13/14/16/17/19).

Reuses frozen trees from compat_synonym_v1; isolates all writes under
logs/open_xddx_ox_seq100_v1/c2_<arm>_v1/. Does not touch the main
compat_synonym_noemit_fopt_live_v1 hot tree or its closed_live eval dirs.

Decode: closed_live_mac @15/K5 for all arms.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
SRC_FROZEN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
HOT_SEED = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1"
SUBSET = ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1"
OUT_ROOT = ROOT / "logs/open_xddx_ox_seq100_v1"
M00_SUMMARY = (
    HOT_SEED / "annotate/official_eval_llm_closed_live_mac/summary.json"
)

# Budget / writeback / cap factor grid (closed_live decode fixed).
ARMS: dict[str, dict[str, Any]] = {
    "ab13": {
        "dir": "c2_ab13_v1",
        "label": "AB13 locked F4 + cold (no writeback)",
        "l1": 4,
        "cap": 6,
        "writeback": False,
        "seed_cache_from": "hot",
    },
    "ab14": {
        "dir": "c2_ab14_v1",
        "label": "AB14 default F6 + writeback",
        "l1": 6,
        "cap": 6,
        "writeback": True,
        "seed_cache_from": "cold",
    },
    "ab16": {
        "dir": "c2_ab16_v1",
        "label": "AB16 default F6 + cold (historical reuse; do not live-run)",
        "l1": 6,
        "cap": 6,
        "writeback": False,
        "seed_cache_from": "cold",
        "reuse_only": True,
    },
    "ab17": {
        "dir": "c2_ab17_v1",
        "label": "AB17 locked F4 + writeback + cap=1 (single champion)",
        "l1": 4,
        "cap": 1,
        "writeback": True,
        "seed_cache_from": "hot",
    },
    "ab19": {
        "dir": "c2_ab19_v1",
        "label": "AB19 locked F4 + writeback + cap=999 (loose)",
        "l1": 4,
        "cap": 999,
        "writeback": True,
        "seed_cache_from": "hot",
    },
    # T1-07 writeback controls (locked F4/local4/between2/cap6)
    "ab29": {
        "dir": "c2_ab29_v1",
        "label": "AB29 locked F4 + placebo_refresh writeback",
        "l1": 4,
        "cap": 6,
        "writeback": True,
        "writeback_mode": "placebo_refresh",
        "score_scope_mode": "per_family",
        "seed_cache_from": "hot",
    },
    "ab30": {
        "dir": "c2_ab30_v1",
        "label": "AB30 locked F4 + shuffled writeback",
        "l1": 4,
        "cap": 6,
        "writeback": True,
        "writeback_mode": "shuffled",
        "score_scope_mode": "per_family",
        "seed_cache_from": "hot",
    },
    "ab31": {
        "dir": "c2_ab31_v1",
        "label": "AB31 locked F4 + flat recomputation (global scope)",
        "l1": 4,
        "cap": 6,
        "writeback": True,
        "writeback_mode": "normal",
        "score_scope_mode": "global",
        "seed_cache_from": "hot",
    },
    "stf": {
        "dir": "c2_stf_v1",
        "label": "T1-09 STF fidelity re-run (normal writeback + leaf pre/post)",
        "l1": 4,
        "cap": 6,
        "writeback": True,
        "writeback_mode": "normal",
        "score_scope_mode": "per_family",
        "seed_cache_from": "hot",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _copy_frozen(out: Path, case_ids: Sequence[str]) -> None:
    src_f = SRC_FROZEN / "frozen"
    dst_f = out / "frozen"
    dst_f.mkdir(parents=True, exist_ok=True)
    for name in ("vignette_parser_frozen.json", "p5_headline_frozen.json", "freeze_manifest.json"):
        p = src_f / name
        if p.is_file():
            shutil.copy2(p, dst_f / name)
    for sub in ("shared_trees", "p5_audit"):
        s = src_f / sub
        d = dst_f / sub
        if not s.is_dir():
            continue
        d.mkdir(parents=True, exist_ok=True)
        for cid in case_ids:
            sp = s / ("%s.json" % cid)
            if not sp.is_file():
                continue
            dp = d / sp.name
            if sub == "shared_trees" and dp.is_file():
                try:
                    import json as _json
                    if _json.loads(dp.read_text(encoding="utf-8")).get("live_reannotated"):
                        continue
                except Exception:
                    pass
            shutil.copy2(sp, dp)


def _prepare_annotate(
    out: Path, case_ids: Sequence[str], *, tree_seed: str = "frozen"
) -> None:
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    # Prefer hot live trees when the arm seeds caches from hot (T1-07/09),
    # so BFS/L2 prompts align with the seeded LLM cache.
    if tree_seed == "hot":
        src_trees = HOT_SEED / "annotate" / "shared_trees"
    elif tree_seed == "ab29":
        src_trees = OUT_ROOT / "c2_ab29_v1" / "annotate" / "shared_trees"
    else:
        src_trees = out / "frozen" / "shared_trees"
    if not src_trees.is_dir():
        src_trees = out / "frozen" / "shared_trees"
    dst_trees = ann / "shared_trees"
    dst_trees.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = src_trees / ("%s.json" % cid)
        if sp.is_file():
            shutil.copy2(sp, dst_trees / sp.name)
            if tree_seed in ("hot", "ab29"):
                fr_trees = out / "frozen" / "shared_trees"
                fr_trees.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sp, fr_trees / sp.name)
    p5 = out / "frozen" / "p5_headline_frozen.json"
    if p5.is_file():
        shutil.copy2(p5, ann / "p5_headline_frozen.json")
    man = ann / "stage_manifest.json"
    if man.is_file():
        man.unlink()
    src_nc = SRC_FROZEN / "annotate" / "normalized_cases.json"
    if not src_nc.is_file():
        src_nc = SUBSET / "normalized_cases.json"
    if src_nc.is_file():
        shutil.copy2(src_nc, out / "normalized_cases.json")
        shutil.copy2(src_nc, ann / "normalized_cases.json")
    for name in ("finding_fixture_v1.json",):
        s = SRC_FROZEN / "annotate" / name
        if s.is_file():
            shutil.copy2(s, ann / name)
            shutil.copy2(s, out / name)


def _seed_caches(out: Path, case_ids: Sequence[str], *, from_hot: bool) -> int:
    """Seed per-case LLM caches. Prefer enriched ab29 caches when present."""
    primary = (HOT_SEED if from_hot else SRC_FROZEN) / "annotate" / "cache"
    enriched = OUT_ROOT / "c2_ab29_v1" / "annotate" / "cache"
    sources = []
    if enriched.is_dir() and enriched.resolve() != (out / "annotate" / "cache").resolve():
        sources.append(enriched)
    if primary.is_dir():
        sources.append(primary)
    if not sources:
        return 0
    n = 0
    for cid in case_ids:
        d = out / "annotate" / "cache" / cid
        if d.exists():
            # Upgrade individual files from enriched source when larger.
            if enriched.is_dir():
                s = enriched / cid
                if s.is_dir():
                    for name in (
                        "bfs_llm_cache.json",
                        "l2_llm_cache.json",
                        "granularity_llm_cache.json",
                    ):
                        sf, df = s / name, d / name
                        if sf.is_file() and (
                            (not df.is_file()) or sf.stat().st_size > df.stat().st_size
                        ):
                            shutil.copy2(sf, df)
            continue
        for src in sources:
            s = src / cid
            if s.is_dir():
                shutil.copytree(s, d)
                n += 1
                break
    return n


def _run_annotate(
    out: Path,
    case_ids: Sequence[str],
    *,
    l1: int,
    cap: int,
    writeback: bool,
    workers: int,
    model: str,
    writeback_mode: str = "normal",
    score_scope_mode: str = "per_family",
) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(SUBSET / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--from-stage", "annotate",
        "--to-stage", "annotate",
        "--fixed-l1-budget", str(int(l1)),
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", str(int(cap)),
        "--writeback-mode", str(writeback_mode or "normal"),
        "--score-scope-mode", str(score_scope_mode or "per_family"),
        "--resume",
    ]
    if not writeback:
        cmd.append("--no-write-annotated-trees")
    # Intentionally NO --synonym-bind-repair (OX annotate-only; keep off).
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _run_llm(out: Path, arm_key: str, *, workers: int) -> int:
    proj = f"eval_projection_c2_{arm_key}"
    name = f"official_eval_llm_c2_{arm_key}"
    # Fresh live-mac cache for this arm
    cache = out / "annotate" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    live_cache = cache / "closed_live_mac_supervisor.json"
    if live_cache.is_file():
        live_cache.unlink()
    pdir = out / "annotate" / proj
    if pdir.is_dir():
        shutil.rmtree(pdir)
    edir = out / "annotate" / name
    if edir.is_dir():
        shutil.rmtree(edir)
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "open_xddx",
        "--run-dir", str(out),
        "--subset-parquet", str(SUBSET / "cases.parquet"),
        "--judge", "llm",
        "--ddx-k", "5",
        "--workers", str(workers),
        "--ddx-source", "closed_live_mac",
        "--live-closed-mac",
        "--pool-n", "15",
        "--build-projection",
        "--projection-subdir", proj,
        "--out-name", name,
    ]
    env = {**os.environ, "PYTHONPATH": "src:scripts/paper:scripts"}
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _micro_from_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    doc = _read_json(path)
    m = (doc.get("metrics") or {})
    dm = m.get("diagnostic_micro") or {}
    return {
        "micro_precision": dm.get("micro_precision"),
        "micro_recall": dm.get("micro_recall"),
        "micro_f1": dm.get("micro_f1"),
        "interpretation_accuracy": m.get("interpretation_accuracy"),
        "n_cases": m.get("n_cases") or doc.get("n_cases_scored"),
    }


def _cpu_load() -> float:
    try:
        return os.getloadavg()[0]
    except OSError:
        return -1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--arms",
        default="ab13,ab14,ab17,ab19",
        help="Comma-separated arm keys (AB16 excluded: historical reuse only)",
    )
    ap.add_argument("--n-cases", type=int, default=100)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--judge-workers", type=int, default=25)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument(
        "--max-load",
        type=float,
        default=0.0,
        help="If >0 and 1-min loadavg exceeds this before an arm, sleep/retry",
    )
    args = ap.parse_args()

    case_ids = _load_ids(args.n_cases)
    wanted = [a.strip().lower() for a in str(args.arms).split(",") if a.strip()]
    results: dict[str, Any] = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "workers": int(args.workers),
        "judge_workers": int(args.judge_workers),
        "m00_readonly": _micro_from_summary(M00_SUMMARY),
        "arms": {},
    }

    # AB16 is archival reuse only — never live-schedule.
    skipped_reuse = [k for k in wanted if k == "ab16"]
    wanted = [k for k in wanted if k != "ab16"]
    if skipped_reuse:
        reuse_path = ROOT / "runs/paper_v1/ablations_c2_ab16_reused.json"
        if reuse_path.is_file():
            results["arms"]["ab16"] = {
                **_read_json(reuse_path),
                "skipped_live": True,
            }
            print("AB16 skipped (reuse archive):", reuse_path, flush=True)
        else:
            print(
                "AB16 skipped from live schedule; run scripts/paper/c2_record_ab16_reuse.py",
                flush=True,
            )

    for key in wanted:
        if key not in ARMS:
            print("unknown arm", key, file=sys.stderr)
            return 2
        if ARMS[key].get("reuse_only"):
            print(f"skip reuse_only arm {key}", flush=True)
            continue
        if args.max_load > 0:
            for _ in range(60):
                load = _cpu_load()
                if load < 0 or load < args.max_load:
                    break
                print(f"[load] {load:.1f} >= {args.max_load}; sleep 30s", flush=True)
                time.sleep(30)
        spec = ARMS[key]
        out = OUT_ROOT / spec["dir"]
        out.mkdir(parents=True, exist_ok=True)
        n_cache = 0
        if not args.skip_annotate:
            _copy_frozen(out, case_ids)
            tree_seed = "frozen"
            if spec.get("seed_cache_from") == "hot":
                # STF / writeback arms: align starting trees with hot cache.
                tree_seed = "hot" if key == "stf" else "hot"
            _prepare_annotate(out, case_ids, tree_seed=tree_seed)
            n_cache = _seed_caches(
                out, case_ids, from_hot=(spec["seed_cache_from"] == "hot")
            )
        launch = {
            "arm": key,
            "label": spec["label"],
            "l1": spec["l1"],
            "cap": spec["cap"],
            "writeback": spec["writeback"],
            "writeback_mode": spec.get("writeback_mode", "normal"),
            "score_scope_mode": spec.get("score_scope_mode", "per_family"),
            "output_dir": str(out),
            "seeded_caches": n_cache,
            "created_at": _utc(),
            "loadavg_start": _cpu_load(),
        }
        _write_json(out / "c2_launch.json", launch)

        code_ann = 0
        if not args.skip_annotate:
            code_ann = _run_annotate(
                out,
                case_ids,
                l1=int(spec["l1"]),
                cap=int(spec["cap"]),
                writeback=bool(spec["writeback"]),
                workers=int(args.workers),
                model=str(args.model),
                writeback_mode=str(spec.get("writeback_mode") or "normal"),
                score_scope_mode=str(spec.get("score_scope_mode") or "per_family"),
            )
        code_llm = 0
        if code_ann == 0 and not args.skip_llm:
            code_llm = _run_llm(out, key, workers=int(args.judge_workers))

        micro = _micro_from_summary(
            out / "annotate" / f"official_eval_llm_c2_{key}" / "summary.json"
        )
        n_live = 0
        tree_dir = out / "annotate" / "shared_trees"
        if tree_dir.is_dir():
            for p in tree_dir.glob("*.json"):
                if _read_json(p).get("live_reannotated"):
                    n_live += 1
        results["arms"][key] = {
            "label": spec["label"],
            "output_dir": str(out),
            "annotate_exit": code_ann,
            "llm_exit": code_llm,
            "micro": micro,
            "n_live_trees": n_live,
            "loadavg_end": _cpu_load(),
            **{k: spec[k] for k in ("l1", "cap", "writeback")},
        }
        print(json.dumps({key: results["arms"][key]}, indent=2, ensure_ascii=False), flush=True)

    out_json = ROOT / "runs/paper_v1/ablations_c2_ox_raw.json"
    # Never overwrite the published C2 OX factorial summary with Tier-1 arms.
    arm_keys = set(results["arms"])
    if arm_keys <= {"ab29", "ab30", "ab31"}:
        out_json = ROOT / "runs/paper_v1/ablations_c2_t107_writeback.json"
    elif arm_keys <= {"stf"}:
        out_json = ROOT / "runs/paper_v1/ablations_c2_t109_stf.json"
    elif arm_keys & {"ab29", "ab30", "ab31", "stf"}:
        out_json = ROOT / "runs/paper_v1/ablations_c2_ox_raw_with_t107.json"
    _write_json(out_json, results)
    print("WROTE", out_json, flush=True)
    bad = [
        k
        for k, v in results["arms"].items()
        if int(v.get("annotate_exit") or 0) != 0 or int(v.get("llm_exit") or 0) != 0
    ]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
