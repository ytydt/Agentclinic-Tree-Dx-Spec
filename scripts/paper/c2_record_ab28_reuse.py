#!/usr/bin/env python3
"""Record AB28 as historical reuse (smoke_typed_remap all100: 0.72→0.42).

Does not re-run typed remap. Writes archival JSON for C2 aggregation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "analysis/l1_gold_recall_v1/smoke_typed_remap"
SRC_SUMMARY = SRC / "summary_typed_all100.json"
OUT = ROOT / "runs/paper_v1/ablations_c2_ab28_reused.json"
NOTE = ROOT / "logs/c2_ablation_workspace_v1/meta/ab28_reuse.txt"
NOTE_MD = ROOT / "runs/paper_v1/ablations_c2_ab28_reuse_note.md"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    if not SRC_SUMMARY.is_file():
        raise SystemExit(f"missing historical summary: {SRC_SUMMARY}")
    summary = json.loads(SRC_SUMMARY.read_text(encoding="utf-8"))
    arms = summary.get("arms") or {}
    r0 = arms.get("R_compat") or {}
    r1 = arms.get("R_compat_inject_typed") or {}
    opt1_0 = float(r0.get("opt1"))
    opt1_1 = float(r1.get("opt1"))
    if abs(opt1_0 - 0.72) > 0.02 or abs(opt1_1 - 0.42) > 0.02:
        raise SystemExit(
            f"AB28 reuse aborted: unexpected rates compat@1={opt1_0} inject@1={opt1_1}"
        )
    gate = summary.get("gate") or {}
    doc: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _utc(),
        "arm": "ab28",
        "label": "AB28 full leaf inject + typed remap (historical reuse)",
        "reused": True,
        "not_scheduled_in_c2_live": True,
        "source_run_dir": str(SRC),
        "source_summary": str(SRC_SUMMARY),
        "cohort": summary.get("cohort"),
        "mapper_mode": summary.get("mapper_mode"),
        "inject_mode": "full",
        "R_compat": r0,
        "R_compat_inject_typed": r1,
        "delta_opt1": opt1_1 - opt1_0,
        "delta_opt2": float(r1.get("opt2", 0)) - float(r0.get("opt2", 0)),
        "mean_extra_leaves": r1.get("mean_extra_leaves"),
        "gate": gate,
        "claim_allowed": gate.get("claim_allowed"),
        "exit_code": 0,
        "summary": summary,
        "note": (
            "C2 AB28 maps to historical smoke_typed_remap all100 "
            "(full leaf inject + typed_llm remap). Plan cites @1 0.72→0.42; "
            "gate REJECT / claim_allowed=false. Not re-run in this C2 round."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    NOTE.parent.mkdir(parents=True, exist_ok=True)
    NOTE.write_text(
        f"AB28 reused from {SRC}\n"
        f"summary={SRC_SUMMARY}\n"
        f"R_compat@1={opt1_0} R_inject@1={opt1_1} Δ={opt1_1-opt1_0}\n"
        f"archive={OUT}\n"
        f"created_at={doc['created_at']}\n",
        encoding="utf-8",
    )
    NOTE_MD.write_text(
        "\n".join(
            [
                "# AB28（C2 块6）— 历史复用档案（不入论文主表）",
                "",
                f"- recorded: 见 `{OUT.relative_to(ROOT)}`",
                "- 策略: **不再 live 排期**；复用 `analysis/l1_gold_recall_v1/smoke_typed_remap/`",
                "- 干预: 全树叶注入（mean_extra≈16.1）+ typed_llm 重映射",
                f"- 端点: R_compat @1/@2 = **{r0.get('opt1')}/{r0.get('opt2')}** → "
                f"inject_typed **{r1.get('opt1')}/{r1.get('opt2')}**（Δ@1={opt1_1-opt1_0:+.2f}）",
                f"- gate: `{gate.get('decision')}`；claim_allowed=`{gate.get('claim_allowed')}`",
                "- 说明: 与计划「已测 0.72→0.42」一致；有害干预反事实成立方向不变",
                "",
                "完整 C2 汇总将在其余臂完成后写入 `ablations_c2_results.md`，并自动并入本复用记录。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps({k: doc[k] for k in doc if k != "summary"}, indent=2, ensure_ascii=False))
    print("WROTE", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
