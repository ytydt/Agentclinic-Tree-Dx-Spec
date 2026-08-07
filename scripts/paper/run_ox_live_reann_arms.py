#!/usr/bin/env python3
"""OX live re-annotate arms: emit+locked F, and no-emit+locked F; then LLM eval.

Arm A: emit_v1 ON + L1=4 / L2local=4 / cand=6 + write annotated trees
Arm B: emit OFF + same F budgets + write annotated trees

Both reuse frozen VP/trees/P5 from compat_synonym_v1, re-run annotate with
online local posterior writeback (affects emitted-leaf pool order), then
closed_live_mac @15/K5 + paper_aligned LLM judge.
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
DEFAULT_SRC = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1"
DEFAULT_OUT_ROOT = ROOT / "logs/open_xddx_ox_seq100_v1"
DEFAULT_REPORT = ROOT / "analysis/transfer_metrics_v1/ox_live_reann_emit_vs_fopt.md"
DEFAULT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_live_reann_emit_vs_fopt.json"

ARMS = {
    "emit_locked_live": {
        "dir": "compat_synonym_emit_locked_live_v1",
        "force_emit": True,
        "label": "emit_v1 + locked F (live reann)",
    },
    "noemit_fopt_live": {
        "dir": "compat_synonym_noemit_fopt_live_v1",
        "force_emit": False,
        "label": "no-emit + locked F (live reann)",
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load_ids(subset: Path, n: int | None) -> list[str]:
    ids = [
        ln.strip()
        for ln in (subset / "case_ids.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if n is not None:
        ids = ids[: int(n)]
    return ids


def _copy_frozen(src: Path, out: Path, case_ids: Sequence[str]) -> None:
    src_f = src / "frozen"
    dst_f = out / "frozen"
    dst_f.mkdir(parents=True, exist_ok=True)
    for name in ("vignette_parser_frozen.json", "p5_headline_frozen.json"):
        p = src_f / name
        if p.is_file():
            shutil.copy2(p, dst_f / name)
    for sub in ("shared_trees", "p5_audit"):
        s = src_f / sub
        d = dst_f / sub
        d.mkdir(parents=True, exist_ok=True)
        for cid in case_ids:
            sp = s / ("%s.json" % cid)
            if sp.is_file():
                shutil.copy2(sp, d / sp.name)


def _prepare_annotate_stage(out: Path, case_ids: Sequence[str], src: Path) -> None:
    """Ensure annotate/stage_manifest covers all case_ids (smoke may have left a 2-case stub)."""
    ann = out / "annotate"
    ann.mkdir(parents=True, exist_ok=True)
    # Refresh trees from frozen for all ids
    src_trees = out / "frozen" / "shared_trees"
    dst_trees = ann / "shared_trees"
    dst_trees.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        sp = src_trees / ("%s.json" % cid)
        if sp.is_file():
            shutil.copy2(sp, dst_trees / sp.name)
    p5 = out / "frozen" / "p5_headline_frozen.json"
    if p5.is_file():
        shutil.copy2(p5, ann / "p5_headline_frozen.json")
    # Drop stub manifest so stage_assets rebuilds for full cohort
    man = ann / "stage_manifest.json"
    if man.is_file():
        try:
            doc = _read_json(man)
            have = set(doc.get("case_ids") or [])
            if have != set(case_ids):
                man.unlink()
        except Exception:
            man.unlink()
    # normalized_cases for downstream
    src_nc = src / "annotate" / "normalized_cases.json"
    if not src_nc.is_file():
        src_nc = DEFAULT_SUBSET / "normalized_cases.json"
    if src_nc.is_file() and not (out / "normalized_cases.json").is_file():
        shutil.copy2(src_nc, out / "normalized_cases.json")
    if src_nc.is_file():
        shutil.copy2(src_nc, ann / "normalized_cases.json")
    # finding fixture
    for name in ("finding_fixture_v1.json",):
        s = src / "annotate" / name
        if s.is_file():
            shutil.copy2(s, ann / name)
            shutil.copy2(s, out / name)


def _seed_caches(src: Path, out: Path, case_ids: Sequence[str]) -> int:
    """Seed per-case annotate caches for speed (force-emit is post-LLM deterministic)."""
    n = 0
    src_c = src / "annotate" / "cache"
    if not src_c.is_dir():
        return 0
    for cid in case_ids:
        s = src_c / cid
        if not s.is_dir():
            continue
        d = out / "annotate" / "cache" / cid
        if d.exists():
            continue
        shutil.copytree(s, d)
        n += 1
    return n


def _run_annotate(out: Path, case_ids: Sequence[str], *, force_emit: bool, workers: int, model: str) -> int:
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_diagnosisarena_pipeline_staged.py"),
        "--cases-json", str(DEFAULT_SUBSET / "normalized_cases.json"),
        "--cases", ",".join(case_ids),
        "--output-dir", str(out),
        "--workers", str(workers),
        "--model", model,
        "--granularity-mode", "compat",
        "--l1-calib", "off",
        "--synonym-bind-repair",
        "--from-stage", "annotate",
        "--to-stage", "annotate",
        "--fixed-l1-budget", "4",
        "--l2-local-evidence-budget", "4",
        "--l2-between-evidence-budget", "2",
        "--l2-candidate-max-per-live-family", "6",
        "--l2-gap-force-emit-max", "3",
        "--resume",
    ]
    if force_emit:
        cmd.append("--l2-gap-force-emit-uncovered")
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
        "TREE_DX_DIRECT_POST_OUTPUT_CAP": "8192",
        "TREE_DX_USE_PROXY": "1",
        "TREE_DX_EMBED_DEVICE": "cpu",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _run_llm_closed_live(out: Path, *, workers: int) -> int:
    # Fresh live-mac cache for this arm
    cache = out / "annotate" / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    live_cache = cache / "closed_live_mac_supervisor.json"
    if not live_cache.is_file():
        live_cache.write_text("{}\n", encoding="utf-8")
    cmd = [
        sys.executable, "-u",
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "open_xddx",
        "--run-dir", str(out),
        "--subset-parquet", str(DEFAULT_SUBSET / "cases.parquet"),
        "--judge", "llm",
        "--ddx-k", "5",
        "--workers", str(workers),
        "--ddx-source", "closed_live_mac",
        "--live-closed-mac",
        "--pool-n", "15",
        "--build-projection",
        "--projection-subdir", "eval_projection_closed_live_mac",
        "--out-name", "official_eval_llm_closed_live_mac",
    ]
    env = {
        **os.environ,
        "PYTHONPATH": "src:scripts/paper:scripts",
    }
    print("RUN:", " ".join(cmd), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def _micro(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    m = ((_read_json(path).get("metrics") or {}).get("diagnostic_micro") or {})
    if not m:
        return None
    return {
        "micro_precision": m.get("micro_precision"),
        "micro_recall": m.get("micro_recall"),
        "micro_f1": m.get("micro_f1"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--n-cases", type=int, default=100)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--judge-workers", type=int, default=50)
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--arms", default="emit_locked_live,noemit_fopt_live")
    ap.add_argument("--skip-annotate", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--out-md", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_JSON)
    args = ap.parse_args(list(argv) if argv is not None else None)

    case_ids = _load_ids(DEFAULT_SUBSET, args.n_cases)
    wanted = [a.strip() for a in str(args.arms).split(",") if a.strip()]
    results: dict[str, Any] = {
        "created_at": _utc(),
        "n_cases": len(case_ids),
        "locked_budget": {
            "l1_evidence_budget": 4,
            "l2_local_evidence_budget": 4,
            "l2_between_evidence_budget": 2,
            "l2_candidate_max_per_live_family": 6,
        },
        "arms": {},
    }

    for key in wanted:
        if key not in ARMS:
            print("unknown arm", key, file=sys.stderr)
            return 2
        spec = ARMS[key]
        out = Path(args.out_root) / spec["dir"]
        out.mkdir(parents=True, exist_ok=True)
        n_cache = 0
        if not args.skip_annotate:
            # Only refresh frozen→annotate trees when we are about to re-annotate.
            # skip-annotate must NOT clobber live_reannotated shared_trees.
            _copy_frozen(args.source_run, out, case_ids)
            _prepare_annotate_stage(out, case_ids, args.source_run)
            n_cache = _seed_caches(args.source_run, out, case_ids)
        launch = {
            "arm": key,
            "label": spec["label"],
            "force_emit": spec["force_emit"],
            "output_dir": str(out),
            "seeded_caches": n_cache,
            "skip_annotate": bool(args.skip_annotate),
            "created_at": _utc(),
        }
        _write_json(out / "live_reann_launch.json", launch)

        code_ann = 0
        if not args.skip_annotate:
            code_ann = _run_annotate(
                out,
                case_ids,
                force_emit=bool(spec["force_emit"]),
                workers=int(args.workers),
                model=str(args.model),
            )
        code_llm = 0
        if code_ann == 0 and not args.skip_llm:
            # Ensure closed_live LLM cache is fresh for this arm's trees.
            live_cache = out / "annotate" / "cache" / "closed_live_mac_supervisor.json"
            if live_cache.is_file():
                live_cache.unlink()
            proj = out / "annotate" / "eval_projection_closed_live_mac"
            if proj.is_dir():
                shutil.rmtree(proj)
            eval_out = out / "annotate" / "official_eval_llm_closed_live_mac"
            if eval_out.is_dir():
                shutil.rmtree(eval_out)
            code_llm = _run_llm_closed_live(out, workers=int(args.judge_workers))

        micro = _micro(
            out / "annotate/official_eval_llm_closed_live_mac/summary.json"
        )
        # Count force-emitted / tree writebacks
        n_tree_live = 0
        n_force_cases = 0
        tree_dir = out / "annotate" / "shared_trees"
        if tree_dir.is_dir():
            for p in tree_dir.glob("*.json"):
                doc = _read_json(p)
                if doc.get("live_reannotated"):
                    n_tree_live += 1
                if doc.get("l2_gap_force_emit_uncovered"):
                    n_force_cases += 1
        # Fallback: case_results confirm writeback if trees were later overwritten
        if n_tree_live == 0:
            cr = out / "annotate" / "case_results"
            if cr.is_dir():
                for p in cr.glob("*.json"):
                    l2 = (_read_json(p).get("l2") or {})
                    tw = l2.get("annotated_tree_write") or {}
                    if tw.get("written"):
                        n_tree_live += 1
                    ca = ((l2.get("generation") or {}).get("config_a") or {})
                    if ca.get("force_emit_uncovered"):
                        n_force_cases += 1
        results["arms"][key] = {
            "label": spec["label"],
            "output_dir": str(out),
            "annotate_exit": code_ann,
            "llm_exit": code_llm,
            "micro": micro,
            "n_live_trees": n_tree_live,
            "n_force_emit_flag_trees": n_force_cases,
        }

    # Baselines
    base_ann = args.source_run / "annotate"
    ox = ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1"
    results["baselines"] = {
        "live_no_emit_orig": _micro(
            base_ann / "official_eval_llm_closed_live_mac/summary.json"
        ),
        "b00": _micro(
            ox / "B00-direct-cot/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "mac": _micro(
            ox
            / "B06-mac-single-vendor/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "emit_offline_fresh_live": _micro(
            ROOT
            / "logs/open_xddx_ox_seq100_v1/compat_synonym_emit_v1/annotate"
            / "official_eval_llm_emit_v1_live/summary.json"
        ),
    }
    _write_json(args.out_json, results)

    lines = [
        "# OX live 重标注：emit+锁定F vs 无emit+锁定F",
        "",
        "日期：%s" % _utc()[:10],
        "锁定预算：L1=4 / L2local=4 / between=2 / cand_max=6",
        "短列表：fresh `closed_live_mac_supervisor` @ pool15/K5 + LLM judge",
        "机器表：[`ox_live_reann_emit_vs_fopt.json`](ox_live_reann_emit_vs_fopt.json)",
        "",
        "## 结果",
        "",
        "| 臂 | P | R | F1 | live树写回 |",
        "|----|---|---|-----|-----------|",
    ]
    for key, name in (
        ("live_no_emit_orig", "原 closed_live（无重标）"),
        ("b00", "B00"),
        ("mac", "MAC"),
        ("emit_offline_fresh_live", "emit离线inject+fresh live（旧）"),
    ):
        m = results["baselines"].get(key) or {}
        if not m:
            lines.append("| %s | — | — | — | — |" % name)
            continue
        lines.append(
            "| %s | %.4f | %.4f | %.4f | — |"
            % (
                name,
                float(m.get("micro_precision") or 0),
                float(m.get("micro_recall") or 0),
                float(m.get("micro_f1") or 0),
            )
        )
    for key in wanted:
        arm = results["arms"].get(key) or {}
        m = arm.get("micro") or {}
        if not m:
            lines.append(
                "| %s | — | — | — | %s |"
                % (arm.get("label") or key, arm.get("n_live_trees"))
            )
            continue
        lines.append(
            "| **%s** | %.4f | %.4f | %.4f | %s |"
            % (
                arm.get("label") or key,
                float(m.get("micro_precision") or 0),
                float(m.get("micro_recall") or 0),
                float(m.get("micro_f1") or 0),
                arm.get("n_live_trees"),
            )
        )
    lines += [
        "",
        "## 说明",
        "",
        "- live 重标注会跑 Config A（可选 force-emit）+ joint 局部证据标注，"
        "把局部后验写回叶并按 cand_max 截断，再覆盖 `annotate/shared_trees`。",
        "- 因此补入叶会进入后验池并参与 closed_live 排序（不再是极低后验 inject）。",
        "- 无 emit 臂隔离「仅改 F 预算」的效果。",
        "",
    ]
    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    args.out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
