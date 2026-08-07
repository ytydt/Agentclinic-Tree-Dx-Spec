#!/usr/bin/env python3
"""Aggregate C3 AB01–AB03 / AB04 / AB06 into runs/paper_v1/ablations_c3_results.*"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT_MD = ROOT / "runs/paper_v1/ablations_c3_results.md"
OUT_JSON = ROOT / "runs/paper_v1/ablations_c3_results.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> Any | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _opt_rates(mapper: dict[str, Any] | None) -> dict[str, Any]:
    if not mapper:
        return {}
    # common shapes
    for key in ("option_top1", "opt1", "top1_rate"):
        if key in mapper:
            pass
    perf = mapper.get("performance") if isinstance(mapper.get("performance"), dict) else {}
    # typed mapper summaries often nest rates
    rates = mapper.get("rates") if isinstance(mapper.get("rates"), dict) else {}
    out = {
        "option_top1": (
            mapper.get("option_top1")
            or rates.get("option_top1")
            or perf.get("option_top1")
            or mapper.get("at1_rate")
            or perf.get("at1_rate")
        ),
        "option_top2": (
            mapper.get("option_top2")
            or rates.get("option_top2")
            or perf.get("option_top2")
            or mapper.get("at2_rate")
            or perf.get("at2_rate")
        ),
        "n": mapper.get("n_cases") or mapper.get("n") or perf.get("n"),
        "raw_keys": sorted(mapper.keys())[:40],
    }
    # dig records-style
    if out["option_top1"] is None and "metrics" in mapper:
        m = mapper["metrics"]
        if isinstance(m, dict):
            out["option_top1"] = m.get("option_top1") or m.get("at1_rate")
            out["option_top2"] = m.get("option_top2") or m.get("at2_rate")
    return out


def _mapper_summary(arm_dir: Path) -> dict[str, Any] | None:
    for rel in (
        "annotate/mapper/summary.json",
        "annotate/mapper/records.json",
    ):
        p = arm_dir / rel
        doc = _load(p)
        if doc is None:
            continue
        if rel.endswith("records.json") and isinstance(doc, dict):
            return doc.get("summary") or doc
        return doc
    return None


def _down_summary(arm_dir: Path) -> dict[str, Any] | None:
    return _load(arm_dir / "annotate" / "downstream_summary.json")


def _open_acc(arm_dir: Path) -> dict[str, Any] | None:
    for rel in (
        "annotate/official_eval_llm_compat/summary.json",
        "official_eval_llm_compat/summary.json",
    ):
        doc = _load(arm_dir / rel)
        if doc:
            return doc
    return None


def _extract_acc(summary: dict[str, Any] | None) -> float | None:
    if not summary:
        return None
    for path in (
        ("metrics", "diagnostic_accuracy_single_trajectory"),
        ("diagnostic_accuracy_single_trajectory",),
        ("diagnostic_accuracy",),
        ("metrics", "diagnostic_accuracy"),
        ("metrics", "acc"),
        ("acc",),
        ("accuracy",),
        ("macro", "diagnostic_accuracy"),
    ):
        cur: Any = summary
        ok = True
        for k in path:
            if not isinstance(cur, dict) or k not in cur:
                ok = False
                break
            cur = cur[k]
        if ok and isinstance(cur, (int, float)):
            return float(cur)
    # nested common for this repo
    if isinstance(summary.get("prompt7"), dict):
        v = summary["prompt7"].get("accuracy") or summary["prompt7"].get("acc")
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(float(a) - float(b), 4)


def main() -> int:
    bak = ""
    bp = ROOT / "logs/c3_ablation_workspace_v1/meta/backup_path.txt"
    if bp.is_file():
        bak = bp.read_text(encoding="utf-8").strip()

    da_raw = _load(ROOT / "runs/paper_v1/ablations_c3_da_raw.json") or {}
    mcr_raw = _load(ROOT / "runs/paper_v1/ablations_c3_mcr_raw.json") or {}

    block1: dict[str, Any] = {}
    for key, dirname in (
        ("ab01", "c3_ab01_v1"),
        ("ab02", "c3_ab02_v1"),
        ("ab03", "c3_ab03_v1"),
    ):
        arm_dir = ROOT / "logs/diagnosisarena_d2_m01_v1" / dirname
        mapper = _mapper_summary(arm_dir)
        rates = _opt_rates(mapper)
        block1[key] = {
            "dir": str(arm_dir),
            "mapper": rates,
            "exit_code": ((da_raw.get("arms") or {}).get(key) or {}).get("exit_code"),
            "l1_axis_mode": ((da_raw.get("arms") or {}).get(key) or {}).get("l1_axis_mode"),
        }

    m00_da = {"option_top1": 0.71, "option_top2": 0.78}
    for key, row in block1.items():
        r = row["mapper"]
        row["delta_vs_m00_at1"] = _delta(r.get("option_top1"), m00_da["option_top1"])
        row["delta_vs_m00_at2"] = _delta(r.get("option_top2"), m00_da["option_top2"])

    block2: dict[str, Any] = {}
    for key, dirname in (
        ("ab04", "c3_ab04_v1"),
        ("ab06", "c3_ab06_v1"),
    ):
        arm_dir = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1" / dirname
        down = _down_summary(arm_dir)
        open_sum = _open_acc(arm_dir)
        # No cross-metric fallback. A previous version fell back to
        # downstream at1_rate when the open-Acc summary was unreadable, which
        # silently reported arm values in one caliber against an M00 anchor in
        # another (AB04 0.39 / AB06 0.47 against open-Acc 0.50, when the true
        # open Acc is 0.42 / 0.50 and the downstream anchor is 0.46).
        acc = _extract_acc(open_sum)
        block2[key] = {
            "dir": str(arm_dir),
            "open_acc": acc,
            "open_acc_missing": acc is None,
            "open_summary_keys": sorted(open_sum.keys())[:30] if open_sum else [],
            "downstream_at1": (down or {}).get("performance", {}).get("at1_rate")
            if isinstance(down, dict)
            else None,
            "exit_code": ((mcr_raw.get("arms") or {}).get(key) or {}).get("exit_code"),
            "granularity_mode": ((mcr_raw.get("arms") or {}).get(key) or {}).get(
                "granularity_mode"
            ),
        }

    m00_mcr = _extract_acc(_open_acc(ROOT / "logs/medcasereasoning_mcr_val_seq100_v1" / "compat_synonym_v1")) or 0.50
    m00_down = (
        (_down_summary(ROOT / "logs/medcasereasoning_mcr_val_seq100_v1" / "compat_synonym_v1") or {})
        .get("performance", {})
        .get("at1_rate")
    )
    for key, row in block2.items():
        row["delta_vs_m00_acc"] = _delta(row.get("open_acc"), m00_mcr)
        # Each caliber gets its own anchor; the two deltas are not interchangeable.
        row["delta_vs_m00_downstream_at1"] = _delta(row.get("downstream_at1"), m00_down)

    ab03 = block1.get("ab03", {}).get("mapper", {})
    ab03_delta = block1.get("ab03", {}).get("delta_vs_m00_at1")
    falsify_adaptive = (
        ab03_delta is not None and abs(float(ab03_delta)) < 0.10
    )

    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "not_for_paper_main_table": True,
        "backup_path": bak,
        "slice": {
            "block1": "DA d2_seq100 proxy (D1b-dev-freeze missing)",
            "block2": "MCR mcr_val_seq100",
        },
        "protocol": {
            "da_synonym_bind": False,
            "workers_default": 25,
            "p0_c3_cap_note": (
                "Breakthrough of plan P0 C3≤4: ran five arms AB01/02/03/04/06 "
                "because AB04 cannot downgrade-reuse historical 0.59 (that was AB05)."
            ),
            "ab04_vs_plan059": (
                "Plan 'AB04 already 0.59' was actually AB05 (dedupe on + route off)."
            ),
        },
        "anchors": {
            "da_m00_option": m00_da,
            "mcr_m00_acc": m00_mcr,
            "mcr_m00_downstream_at1": m00_down,
        },
        "block1_hierarchy": block1,
        "block2_dedupe_site": block2,
        "interpretation": {
            "ab03_falsifies_adaptive_axis": falsify_adaptive,
            "ab03_delta_at1": ab03_delta,
            "note": (
                "If AB03≈M00 (Δ@1<0.10), rewrite contribution-1 as "
                "'equipartition buckets suffice'."
            ),
        },
        "raw": {
            "da": str(ROOT / "runs/paper_v1/ablations_c3_da_raw.json"),
            "mcr": str(ROOT / "runs/paper_v1/ablations_c3_mcr_raw.json"),
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _fmt(x: Any) -> str:
        if x is None:
            return "—"
        if isinstance(x, float):
            return f"{x:.3f}"
        return str(x)

    lines = [
        "# C3 P0 消融结果（不入论文主表）",
        "",
        f"- 生成时间: `{doc['created_at']}`",
        f"- 备份: `{bak}`",
        "- **切片代理**: 块1 = DA `d2_seq100`（D1b 未物化）；块2 = MCR `mcr_val_seq100`",
        "- **DA mapper**: 无 `--synonym-bind-repair`",
        "- **P0 C3 帽突破**: 计划「P0 C3≤4」，本轮跑满 AB01/02/03/04/06（AB04 无法降档复用历史 0.59）",
        "- **口径纠正**: 计划「AB04≈0.59」实为 **AB05**（去重开 + 路由关）",
        "",
        "## 锚点（只读）",
        "",
        f"- DA M00 option @1/@2 = **{m00_da['option_top1']:.2f}/{m00_da['option_top2']:.2f}**（无 bind）",
        f"- MCR M00 开放 Acc = **{m00_mcr:.2f}**（`compat_synonym_v1`，Prompt7 judge）",
        f"- MCR M00 downstream @1 = **{_fmt(m00_down)}**（另一口径，勿与上行混比）",
        "",
        "## 块 1｜层级轴（DA d2_seq100 代理）",
        "",
        "| 臂 | L1 轴 | option@1 | option@2 | Δ@1 vs M00 | Δ@2 vs M00 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    labels = {"ab01": "fixed_icd", "ab02": "flat", "ab03": "random"}
    for key in ("ab01", "ab02", "ab03"):
        row = block1.get(key) or {}
        m = row.get("mapper") or {}
        lines.append(
            "| {arm} | {axis} | {a1} | {a2} | {d1} | {d2} |".format(
                arm=key.upper(),
                axis=labels[key],
                a1=_fmt(m.get("option_top1")),
                a2=_fmt(m.get("option_top2")),
                d1=_fmt(row.get("delta_vs_m00_at1")),
                d2=_fmt(row.get("delta_vs_m00_at2")),
            )
        )
    lines += [
        "",
        "### 否证读数（贡献一）",
        "",
        (
            f"- AB03 Δ@1 = `{_fmt(ab03_delta)}` → "
            + (
                "**自适应轴不成立**（|Δ|<0.10）：等势分桶即可"
                if falsify_adaptive
                else "保留「病例自适应轴」主张（|Δ|≥0.10 或缺失）"
            )
        ),
        "- AB01/AB02：若 |Δ|<0.10 只报方向；功效阈值约 ≥0.10（n=100）",
        "",
        "## 块 2｜执行位点（MCR seq100）",
        "",
        "两列是**两个不同口径**，各自对各自的 M00 锚做 Δ，禁止交叉相减。",
        "",
        "| 臂 | 建树语义去重 | 路由 | 开放 Acc | Δ vs M00(开放) | downstream@1 | Δ vs M00(downstream) |",
        "|---|---|---|---:|---:|---:|---:|",
        "| M00 | 开 | 开 | {a} | — | {b} | — |".format(
            a=_fmt(m00_mcr), b=_fmt(m00_down)
        ),
    ]
    for key, dedupe, route in (
        ("ab04", "关", "关"),
        ("ab06", "关", "开"),
    ):
        row = block2.get(key) or {}
        lines.append(
            "| {arm} | {d} | {r} | {acc} | {delta} | {dat1} | {ddelta} |".format(
                arm=key.upper(),
                d=dedupe,
                r=route,
                acc=_fmt(row.get("open_acc")),
                delta=_fmt(row.get("delta_vs_m00_acc")),
                dat1=_fmt(row.get("downstream_at1")),
                ddelta=_fmt(row.get("delta_vs_m00_downstream_at1")),
            )
        )
    lines += [
        "",
        "### 位点读数",
        "",
        "- AB04 vs M00：同时关掉建树去重与路由 → 联合损失上界",
        "- AB06 vs M00：仅关建树去重、保留路由 → 建树去重边际",
        "- AB04 vs AB06：路由在「无建树去重」树上的边际",
        "- **完整 2×2（含 AB05）＋ any-hit@5 / open-MRR ＋ 配对 McNemar ＋ Holm**："
        "见 `ablations_c1_results.md` §2.10；机器可读 "
        "`ablations_block2_site_rank_metrics.json`。本表仅保留 Acc@1 口径。",
        "- 主口径：MCR 开放 Acc / any-hit@k / open-MRR（对齐 R1b/R1c）；闭集 rematch 不敏感时注明",
        "- ⚠️ **口径纪律**：`downstream@1` 与开放 Acc 是两套判分，M00 分别为 "
        f"{_fmt(m00_down)} 与 {_fmt(m00_mcr)}。历史版本曾把臂的 downstream@1 "
        "与开放 Acc 的 M00 锚相减（得 AB04 −0.11 / AB06 −0.03），该数已作废。",
        "",
        "## 产物路径",
        "",
        "- DA: `logs/diagnosisarena_d2_m01_v1/c3_ab0{1,2,3}_v1/`",
        "- MCR: `logs/medcasereasoning_mcr_val_seq100_v1/c3_ab0{4,6}_v1/`",
        "- 共享无去重树: `logs/medcasereasoning_mcr_val_seq100_v1/c3_shared_no_dedupe_v1/`",
        f"- JSON: `{OUT_JSON}`",
        "",
        "> 本文仅供消融工作区；**不得**写入论文主表。",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("WROTE", OUT_MD)
    print("WROTE", OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
