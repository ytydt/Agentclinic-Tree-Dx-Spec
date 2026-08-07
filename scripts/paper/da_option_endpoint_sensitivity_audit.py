#!/usr/bin/env python3
"""DA option endpoint sensitivity: how much of option@1 is tie credit?

DiagnosisArena is a 4-way MCQ scored by projecting predicted leaves onto
options. When one leaf maps to several options at rank 1, option@1 credits the
hit even though the prediction never pinned a single option. This audit
recomputes three endpoints side by side so that granularity precision is
separable from raw option@1:

  option@1       official mapper metric (gold option ranked 1)
  strict@1       hit AND gold is the only option at rank 1
  forced_choice  expected accuracy when rank-1 ties are broken at random and a
                 total non-match is answered by guessing (1 / n_options)

Writes runs/paper_v1/da_option_endpoint_sensitivity.{json,md}.
"""
from __future__ import annotations

import collections
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

ROOT = Path(__file__).resolve().parents[2]
DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
RUNS = ROOT / "runs/paper_v1"
OUT_JSON = RUNS / "da_option_endpoint_sensitivity.json"
OUT_MD = RUNS / "da_option_endpoint_sensitivity.md"

# (label, kind, paths, note)
SOURCES: list[tuple[str, str, list[Path], str]] = [
    (
        "M00 compat (live)",
        "projections",
        [
            DA / "pilot24_compat_b12_live_v1/mapper/projections",
            DA / "remain76_compat_b12_live_v1/mapper/projections",
        ],
        "native compat+b12 mapper run; protocol-closest analogue of the C3 arms",
    ),
    (
        "M00 pre-compat",
        "projections",
        [
            DA / "downstream_top2_w12_v1/mapper/projections",
            DA / "pipeline_remaining76_v1/annotate/mapper/projections",
        ],
        "raw mapper before compat routing; source the 0.71 anchor rematches from",
    ),
    (
        "AB01 fixed_icd",
        "projections",
        [DA / "c3_ab01_v1/annotate/mapper/projections"],
        "C3 block 1",
    ),
    (
        "AB02 flat",
        "projections",
        [DA / "c3_ab02_v1/annotate/mapper/projections"],
        "C3 block 1; demoted to exploratory, see ablations_c3_results.md",
    ),
    (
        "AB03 random",
        "projections",
        [DA / "c3_ab03_v1/annotate/mapper/projections"],
        "C3 block 1",
    ),
    (
        "AB21 contrastive",
        "projections",
        [DA / "c2_ab21_v1/annotate/mapper/projections"],
        "C2",
    ),
    (
        "AB22 no-P5",
        "projections",
        [DA / "c2_ab22_v1/annotate/mapper/projections"],
        "C2",
    ),
    (
        "B02 matched-rerank",
        "records",
        [
            RUNS
            / "diagnosisarena_fixed_v1/B02-flat-matched-rerank/replicate_01/mapper/records.json"
        ],
        "flat baseline, native budget",
    ),
    (
        "B02 compute-matched",
        "records",
        [
            RUNS
            / "diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01/mapper/records.json"
        ],
        "flat baseline, compute matched (~9 calls/case)",
    ),
    (
        "B02 cm-sc10",
        "records",
        [
            RUNS
            / "diagnosisarena_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01/mapper/records.json"
        ],
        "flat baseline, 10-SC + RRF (~92 calls/case)",
    ),
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(kind: str, paths: Sequence[Path]) -> Iterator[dict[str, Any]]:
    if kind == "projections":
        for base in paths:
            if not base.is_dir():
                continue
            for path in sorted(base.glob("*.json")):
                yield json.loads(path.read_text(encoding="utf-8"))
        return
    for path in paths:
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        yield from (doc.get("records") or [])


def _score(label: str, kind: str, paths: Sequence[Path], note: str) -> dict[str, Any]:
    n = 0
    n_hit = 0
    n_strict = 0
    n_abstain = 0
    expected = 0.0
    tie_widths: list[int] = []
    relations: collections.Counter[str] = collections.Counter()

    for row in _rows(kind, paths):
        n += 1
        options = (row.get("projection") or {}).get("option_maps") or {}
        k = len(options) or int(row.get("n_options") or 4)
        matched_any = any((v or {}).get("matched") for v in options.values())
        rank1 = [a for a, v in options.items() if (v or {}).get("option_rank") == 1]
        hit = bool(row.get("option_top1"))
        if hit:
            n_hit += 1
        # A total non-match ranks every option 1 but scores as a miss; treat it
        # as an abstention that a forced-choice evaluation would have to guess.
        if not matched_any:
            n_abstain += 1
            expected += 1.0 / k
            continue
        tie_widths.append(len(rank1))
        if hit:
            expected += 1.0 / max(1, len(rank1))
            if len(rank1) == 1:
                n_strict += 1
            gold = options.get(str(row.get("gold_letter") or "").upper()) or {}
            relations[str(gold.get("relation_type"))] += 1

    if not n:
        return {"arm": label, "note": note, "n_cases": 0, "available": False}
    return {
        "arm": label,
        "note": note,
        "available": True,
        "n_cases": n,
        "option_at1": round(n_hit / n, 3),
        "strict_at1": round(n_strict / n, 3),
        "equivalent_at1": round(relations.get("equivalent", 0) / n, 3),
        "tie_rescued": round((n_hit - n_strict) / n, 3),
        "forced_choice": round(expected / n, 3),
        "n_abstain": n_abstain,
        "mean_tie_width_on_hit": (
            round(statistics.mean(tie_widths), 2) if tie_widths else None
        ),
        "gold_relation_on_hit": dict(relations.most_common()),
    }


def _md(doc: dict[str, Any]) -> str:
    lines = [
        "# DA option 端点敏感性审计（并列判定占比）",
        "",
        f"- 生成时间: `{doc['created_at']}`",
        f"- 脚本: `scripts/paper/da_option_endpoint_sensitivity_audit.py`",
        f"- 机器可读: [`da_option_endpoint_sensitivity.json`](da_option_endpoint_sensitivity.json)",
        "- 切片: DA `d2_seq100`，n=100，4 选项，随机基线 **0.250**",
        "",
        "> **不入论文主表。** `strict@1` 与 `forced_choice` 为事后定义端点，"
        "未经预注册，进入论文前需先写入 `paper_ablation_plan.md` 并补配对显著性检验。",
        "",
        "## 端点定义",
        "",
        "| 端点 | 定义 |",
        "|---|---|",
        "| `option@1` | 官方 mapper 指标：gold 选项排名第 1（并列也算命中） |",
        "| `strict@1` | 命中 **且** rank-1 集合只有 gold 一个选项 |",
        "| `equivalent@1` | 命中 **且** gold 选项与叶的关系判为 `equivalent`（非 `subtype_of` 等跨粒度关系） |",
        "| `forced_choice` | 并列随机打破的期望正确率；完全无匹配视为弃答，按 1/选项数 计 |",
        "",
        "## 结果",
        "",
        "| 臂 | option@1 | strict@1 | equivalent@1 | 并列救回 | forced-choice | 弃答 | 命中时并列宽度 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in doc["arms"]:
        if not row.get("available"):
            lines.append(f"| {row['arm']} | — | — | — | — | — | — | 缺资产 |")
            continue
        lines.append(
            "| {arm} | {o:.3f} | {s:.3f} | {e:.3f} | {t:.3f} | {f:.3f} | {a} | {w} |".format(
                arm=row["arm"],
                o=row["option_at1"],
                s=row["strict_at1"],
                e=row["equivalent_at1"],
                t=row["tie_rescued"],
                f=row["forced_choice"],
                a=row["n_abstain"],
                w=row["mean_tie_width_on_hit"],
            )
        )
    lines += [
        "",
        "## 读数",
        "",
        "1. **并列救回是 DA option 端点的系统性性质，不是某个臂的伪影。** "
        "M00 与 AB02 的命中里都有约一半来自并列，命中时平均并列宽度均在 2.1 左右。",
        "2. **AB02 与 M00 的差距对端点不敏感**：option@1 −0.02、strict@1 −0.04、"
        "forced-choice −0.025。换严格端点不能恢复「层级必要」的主张。",
        "3. **B02 的命中几乎全是并列 credit**：strict@1 仅 0.02–0.03，"
        "forced-choice 贴近随机基线 0.250。本方法栈与平面基线的差距在严格端点下"
        "远大于 option@1 所显示的。",
        "4. **反向代价**：AB03 的 47 次弃答在 option@1 下全记为错，在 forced-choice 下"
        "各得 0.25，其效应量从 −0.34 压到约 −0.085，接近 n=100 的功效阈值。"
        "严格端点不是无代价的替代，只能作敏感性分析。",
        "5. **compat 中间件的增益全部是并列 credit**：pre-compat → compat 使 option@1 "
        "由 0.59 升到 0.70（+0.11），但 `strict@1` 由 0.22 微降到 0.21，命中时并列宽度由 "
        "1.86 升到 2.08。合并等价类确实会拓宽 rank-1 并列集；当被并的选项是真同义时该 "
        "credit 合理，是 `subtype_of` 跨粒度关系时则是粒度损失。**须与贡献二的读数一并复核。**",
        "6. **关系类型分布**：M00 命中里 `subtype_of` 33 / `equivalent` 31；B02 则是 "
        "`subtype_of` 37–44 / `equivalent` 仅 6–8。平面基线几乎从不产出与 gold 同粒度的标签。",
        "",
        "## 锚点溯源（M00 0.71 的出处）",
        "",
        "| 数字 | 出处 | 性质 |",
        "|---|---|---|",
        "| **0.59 / 0.78** | `downstream_top2_w12_v1` + `pipeline_remaining76_v1` mapper | 原生 mapper，compat 路由前 |",
        "| **0.71 / 0.78** | `at1_c1_v1/per_case_compat_parallel_all100.tsv` 的 `opt1`/`opt2` 列 | **rematch**：对上一行的 `option_maps` 施加 compat_parallel 合并后重算（`run_at1_calibration_smoke.rematch_option_metrics`），非原生跑 |",
        "| **0.70 / 0.79** | `pilot24_compat_b12_live_v1` + `remain76_compat_b12_live_v1` mapper | 原生 compat+b12 live 跑 |",
        "",
        "同一 TSV 里 `official_opt1` = 0.59 与 `opt1` = 0.71 并存，可确认 0.71 是重算值。",
        "",
        "**影响**：C3/C2 各臂的 option@1 来自**原生 compat mapper 跑**，与之协议最接近的 M00 "
        "是 0.70（live），而现用锚点 0.71 是 rematch 值。两者仅差 1 例，不改变任何既有结论，"
        "但报数时应注明锚点与臂的打分路径不同源。",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    arms = [_score(label, kind, paths, note) for label, kind, paths, note in SOURCES]
    doc = {
        "schema_version": 1,
        "created_at": _utc(),
        "not_for_paper_main_table": True,
        "slice": "DA d2_seq100, n=100, 4 options, random baseline 0.250",
        "endpoints": {
            "option_at1": "official mapper metric; ties at rank 1 still count as a hit",
            "strict_at1": "hit AND gold is the sole option at rank 1",
            "forced_choice": (
                "expected accuracy with random tie-break; total non-match "
                "treated as abstention scored at 1/n_options"
            ),
        },
        "preregistration_status": (
            "strict_at1 and forced_choice are post-hoc endpoints; register in "
            "paper_ablation_plan.md and add paired significance tests before use."
        ),
        "anchor_provenance": {
            "0.59/0.78": "downstream_top2_w12_v1 + pipeline_remaining76_v1 native mapper (pre-compat)",
            "0.71/0.78": (
                "at1_c1_v1/per_case_compat_parallel_all100.tsv opt1/opt2 — a rematch of the "
                "pre-compat option_maps under compat_parallel, not a native run; the same "
                "file carries official_opt1=0.59"
            ),
            "0.70/0.79": "pilot24_compat_b12_live_v1 + remain76_compat_b12_live_v1 native compat+b12 run",
            "implication": (
                "C3/C2 arms are scored by native compat mapper runs, so their "
                "protocol-closest M00 is 0.70, while the published anchor 0.71 is a "
                "rematch value; the gap is one case and changes no conclusion."
            ),
        },
        "arms": arms,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    OUT_MD.write_text(_md(doc), encoding="utf-8")
    for row in arms:
        print(json.dumps(row, ensure_ascii=False))
    print("wrote", OUT_JSON)
    print("wrote", OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
