#!/usr/bin/env python3
"""C1 ablation suite: DA projection rematch + OX AB15 posterior-pool decode.

Safety:
  - Writes only to at1_c1_v1 / eval_projection_c1_* / runs/paper_v1/ablations_c1_*
  - Does NOT enable synonym_bind
  - Does NOT overwrite at1_compat_v1 or eval_projection_closed_live_mac
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
WS = ROOT / "logs/c1_ablation_workspace_v1"
DA_OUT = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_c1_v1"
OX_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_noemit_fopt_live_v1"
OX_SUBSET = ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet"
RESULTS_MD = ROOT / "runs/paper_v1/ablations_c1_results.md"
RESULTS_JSON = ROOT / "runs/paper_v1/ablations_c1_results.json"

ARM_MAP = {
    "ours": "AB05",
    "merge": "AB07",
    "both_l1fallback": "AB08",
    "compat_serial_safe": "AB09",
    "compat_parallel": "M00_recheck",
    "compat_random_route": "AB10",
    "concept_id_merge": "AB11",
    "compat_parallel_no_l1_prior": "AB20",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print("[run]", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=str(cwd or ROOT))


def verify_backup() -> dict[str, Any]:
    meta = WS / "meta" / "backup_path.txt"
    info: dict[str, Any] = {"workspace": str(WS)}
    if meta.is_file():
        bak = Path(meta.read_text(encoding="utf-8").strip())
        info["backup_path"] = str(bak)
        info["sha256sums"] = str(bak / "sha256sums.txt")
        info["backup_ok"] = bak.is_dir() and (bak / "sha256sums.txt").is_file()
    else:
        info["backup_ok"] = False
        info["backup_path"] = None
    return info


def run_da(
    *,
    cohort: str,
    workers: int,
    dry_run: bool,
) -> Path:
    DA_OUT.mkdir(parents=True, exist_ok=True)
    # Refuse to write into historical main rematch dir
    if DA_OUT.resolve() == (
        ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1"
    ).resolve():
        raise SystemExit("refusing to overwrite at1_compat_v1")
    cmd = [
        PY,
        str(ROOT / "scripts/paper/run_at1_calibration_smoke.py"),
        "--preset", "c1",
        "--cohort", cohort,
        "--workers", str(workers),
        "--out-dir", str(DA_OUT),
        "--no-gold-g2",
    ]
    if dry_run:
        cmd.append("--dry-run")
    env_prefix = {
        "PYTHONPATH": f"{ROOT / 'src'}:{ROOT / 'scripts'}:{ROOT / 'scripts' / 'paper'}",
    }
    print("[env]", env_prefix, flush=True)
    import os
    os.environ["PYTHONPATH"] = env_prefix["PYTHONPATH"]
    _run(cmd)
    return DA_OUT / f"summary_{cohort}.json"


def run_ox_ab15(*, workers: int, pool_n: int = 7) -> dict[str, Path]:
    """AB15: posterior Top-K / post_n_mcr on hot writeback trees."""
    if not OX_RUN.is_dir():
        raise SystemExit(f"missing OX hot run: {OX_RUN}")
    outs: dict[str, Path] = {}
    for src, sub, out_name in (
        ("posterior", "eval_projection_c1_ab15_posterior", "official_eval_llm_c1_ab15_posterior"),
        ("post_n_mcr", "eval_projection_c1_ab15_post_n_mcr", "official_eval_llm_c1_ab15_post_n_mcr"),
    ):
        target = OX_RUN / "annotate" / sub
        if target.exists():
            print(f"[skip-exists] {target} (will resume)", flush=True)
        import os
        os.environ["PYTHONPATH"] = (
            f"{ROOT / 'src'}:{ROOT / 'scripts'}:{ROOT / 'scripts' / 'paper'}"
        )
        cmd = [
            PY,
            str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
            "--dataset", "open_xddx",
            "--run-dir", str(OX_RUN),
            "--subset-parquet", str(OX_SUBSET),
            "--judge", "llm",
            "--ddx-k", "5",
            "--workers", str(workers),
            "--build-projection",
            "--resume",
            "--resume-scores",
            "--ddx-source", src,
            "--pool-n", str(pool_n),
            "--projection-subdir", sub,
            "--out-name", out_name,
        ]
        _run(cmd)
        outs[src] = OX_RUN / "annotate" / out_name / "summary.json"
    return outs


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_ox_closed_live_baseline() -> dict[str, Any] | None:
    p = OX_RUN / "annotate" / "official_eval_llm_closed_live_mac" / "summary.json"
    if p.is_file():
        return _load_json(p)
    return None


def build_results(
    *,
    backup_info: Mapping[str, Any],
    da_summary_path: Path | None,
    ox_paths: Mapping[str, Path],
    workers: int,
) -> tuple[dict[str, Any], str]:
    da = _load_json(da_summary_path) if da_summary_path and da_summary_path.is_file() else None
    ox_closed = load_ox_closed_live_baseline()
    ox_arms: dict[str, Any] = {}
    for k, p in ox_paths.items():
        if p.is_file():
            ox_arms[k] = _load_json(p)

    payload: dict[str, Any] = {
        "created_at": _utc(),
        "workers": workers,
        "synonym_bind": False,
        "backup": dict(backup_info),
        "da_out": str(DA_OUT),
        "ox_run": str(OX_RUN),
        "da": da,
        "ox_closed_live_baseline": ox_closed,
        "ox_ab15": ox_arms,
        "ab12_deferred": True,
    }

    lines: list[str] = []
    lines.append("# C1 消融实验结果（独立收录，不入论文）")
    lines.append("")
    lines.append(f"- generated: {payload['created_at']}")
    lines.append(f"- workers: {workers}")
    lines.append("- DA mapper / rematch: **synonym_bind = OFF**（主口径）")
    lines.append(f"- backup: `{backup_info.get('backup_path')}` (ok={backup_info.get('backup_ok')})")
    lines.append(f"- DA out: `{DA_OUT}`")
    lines.append(f"- OX run (hot writeback, read-only trees): `{OX_RUN}`")
    lines.append("")
    lines.append("## 1. 预飞行")
    lines.append("")
    lines.append("- 主实验冻结资产已在跑前备份并写 sha256。")
    lines.append("- 消融写出隔离至 `at1_c1_v1` 与 `eval_projection_c1_*`；未覆盖 `at1_compat_v1` / `eval_projection_closed_live_mac`。")
    lines.append("- AB12（医生裁定等价类上界）本轮 **defer**（需人工）。")
    lines.append("")

    lines.append("## 2. 块 2｜DA 等价类压缩（C1）")
    lines.append("")
    if da:
        lines.append(f"- cohort: `{da.get('cohort')}` n={da.get('n')} elapsed_s={da.get('elapsed_s')}")
        lines.append(f"- use_gold_g2: {da.get('use_gold_g2')} (harness 口径)")
        lines.append("")
        lines.append("| AB | arm | @1 | @2 | MRR | Δ@1 vs ours | gate_rate | mean_|π(Top-k)| | status |")
        lines.append("|---|---|---:|---:|----:|---:|---:|---:|---|")
        summaries = da.get("summaries") or {}
        for arm, ab in ARM_MAP.items():
            s = summaries.get(arm) or {}
            if not s:
                continue
            lines.append(
                f"| {ab} | `{arm}` | {s.get('opt1', float('nan')):.4f} | "
                f"{s.get('opt2', float('nan')):.4f} | {s.get('mrr', float('nan')):.4f} | "
                f"{s.get('delta_opt1')} | {s.get('gate_trigger_rate', '—')} | "
                f"{s.get('mean_pi_topk', '—')} | {s.get('status')} |"
            )
        lines.append("")
        m00 = summaries.get("compat_parallel") or {}
        ab10 = summaries.get("compat_random_route") or {}
        ab11 = summaries.get("concept_id_merge") or {}
        ab05 = summaries.get("ours") or {}
        ab07 = summaries.get("merge") or {}
        lines.append("### 预注册否证解读（描述性；100 例功效约 ≥0.10 @1）")
        lines.append("")
        if m00 and ab10:
            d = round(float(m00.get("opt1", 0) - ab10.get("opt1", 0)), 4)
            lines.append(
                f"- **AB10 vs 主方法**：compat_parallel @1={m00.get('opt1')} vs "
                f"random_route @1={ab10.get('opt1')}（Δ={d}）。"
                + (
                    " 门控携带信息的方向性成立。"
                    if d >= 0.05
                    else " 差异未达可解释阈值；不得据此撤下贡献二，亦不得宣称门控已证伪。"
                )
            )
        if m00 and ab11:
            d = round(float(m00.get("opt1", 0) - ab11.get("opt1", 0)), 4)
            cov = ab11.get("mean_concept_key_coverage")
            lines.append(
                f"- **AB11 vs 主方法**：concept_id_merge @1={ab11.get('opt1')} "
                f"(coverage={cov}) vs compat @1={m00.get('opt1')}（Δ={d}）。"
            )
        if ab07 and ab11:
            lines.append(
                f"- **AB11 vs AB07**：concept_id @1={ab11.get('opt1')} vs "
                f"heuristic merge @1={ab07.get('opt1')}。"
            )
        if m00 and ab05:
            d = round(float(m00.get("opt1", 0) - ab05.get("opt1", 0)), 4)
            lines.append(
                f"- **AB05 vs 主方法（决策期路由增量）**：ours @1={ab05.get('opt1')} → "
                f"compat @1={m00.get('opt1')}（Δ={d}）。"
            )
        ab20 = summaries.get("compat_parallel_no_l1_prior") or {}
        if m00 and ab20:
            d = round(float(m00.get("opt1", 0) - ab20.get("opt1", 0)), 4)
            lines.append(
                f"- **AB20（关 L1 soft prior）**：no_l1_prior @1={ab20.get('opt1')} vs "
                f"compat @1={m00.get('opt1')}（Δ={d}）。"
            )
    else:
        lines.append("_DA summary missing._")
    lines.append("")

    lines.append("## 3. 块 3｜OX AB15 后验池解码")
    lines.append("")
    if ox_closed:
        micro = (ox_closed.get("micro") or ox_closed.get("metrics") or ox_closed)
        lines.append(
            f"- **主方法 closed_live_mac（只读）**：summary keys={list(ox_closed.keys())[:12]}"
        )
        # try common fields
        f1 = None
        for path in (
            ("micro", "f1"),
            ("metrics", "micro_f1"),
            ("micro_f1",),
            ("f1",),
        ):
            cur: Any = ox_closed
            ok = True
            for k in path:
                if isinstance(cur, dict) and k in cur:
                    cur = cur[k]
                else:
                    ok = False
                    break
            if ok:
                f1 = cur
                break
        if f1 is not None:
            lines.append(f"- closed_live micro-F1 (ref): **{f1}**")
    for name, doc in ox_arms.items():
        lines.append(f"- **AB15 `{name}`**：`summary` loaded from `{ox_paths.get(name)}`")
        # dump a few metric fields if present
        for key in ("micro", "metrics", "summary"):
            if key in doc and isinstance(doc[key], dict):
                lines.append(f"  - `{key}`: `{json.dumps(doc[key], ensure_ascii=False)[:500]}`")
                break
        else:
            # flatten top-level numeric-ish
            slim = {
                k: v for k, v in doc.items()
                if isinstance(v, (int, float, str, bool)) and k != "created_at"
            }
            if slim:
                lines.append(f"  - scalars: `{json.dumps(slim, ensure_ascii=False)[:500]}`")
    lines.append("")

    lines.append("## 4. AB12 defer")
    lines.append("")
    lines.append("- 需盲法医生裁定等价类（不看 gold），再驱动投影。本轮未跑。")
    lines.append("")

    lines.append("## 5. 功效与限制")
    lines.append("")
    lines.append("- 100 例配对设计对 option @1 的可解释差大约 ≥0.10；更小差异只作方向性描述。")
    lines.append("- 机制归因优先看门控触发率、`|π(Top-k)|`、簇数与路由分支，而非单点 @1。")
    lines.append("- 本文件**不写入论文**；论文数字须另经冻结协议重核。")
    lines.append("")

    return payload, "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-da", action="store_true")
    ap.add_argument("--skip-ox", action="store_true")
    ap.add_argument("--da-cohort", default="all100", choices=["pilot24", "remain76", "all100"])
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pool-n", type=int, default=7)
    args = ap.parse_args()

    WS.mkdir(parents=True, exist_ok=True)
    (ROOT / "runs/paper_v1").mkdir(parents=True, exist_ok=True)

    backup_info = verify_backup()
    print("[backup]", json.dumps(backup_info, indent=2), flush=True)
    if not backup_info.get("backup_ok"):
        print("[warn] backup meta missing; continuing but assets may be unprotected", flush=True)

    da_path: Path | None = None
    if not args.skip_da:
        da_path = run_da(
            cohort=args.da_cohort,
            workers=int(args.workers),
            dry_run=bool(args.dry_run),
        )
    else:
        cand = DA_OUT / f"summary_{args.da_cohort}.json"
        da_path = cand if cand.is_file() else None

    ox_paths: dict[str, Path] = {}
    if not args.skip_ox and not args.dry_run:
        ox_paths = run_ox_ab15(workers=int(args.workers), pool_n=int(args.pool_n))
    elif args.skip_ox:
        for src, name in (
            ("posterior", "official_eval_llm_c1_ab15_posterior"),
            ("post_n_mcr", "official_eval_llm_c1_ab15_post_n_mcr"),
        ):
            p = OX_RUN / "annotate" / name / "summary.json"
            if p.is_file():
                ox_paths[src] = p

    payload, md = build_results(
        backup_info=backup_info,
        da_summary_path=da_path,
        ox_paths=ox_paths,
        workers=int(args.workers),
    )
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    RESULTS_MD.write_text(md, encoding="utf-8")
    print(f"[wrote] {RESULTS_MD}")
    print(f"[wrote] {RESULTS_JSON}")


if __name__ == "__main__":
    main()
