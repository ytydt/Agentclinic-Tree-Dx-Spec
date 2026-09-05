#!/usr/bin/env python3
"""Build the manual pack for the discrimination audit.

Scope: cases where at least one target method actually entertained the gold
diagnosis (strong or near match in its hypothesis set) *and* at least one method
that entertained it still failed to select it.  Those are the cases where the
question "were the findings that separate gold from its competitors present in
the vignette, and did the method use them" is answerable.

For each such case the pack prints the full vignette, the gold, the D0-D3 grade
from the expanded-corpus audit, and per method: the champion, the runner-up, the
selector rationale, every registry candidate with the model's own support and
contradiction spans, and the discarded candidates with the reason given.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
RECALL = LEDGER_DIR / "method_hypothesis_recall_48.jsonl"
BENCH = ROOT / "data/benchmarks"

METHODS = ("collapse3c", "multistance", "impc", "forest")
SUBSETS = {
    "DA_d2_seq100": "diagnosisarena/subsets/d2_seq100_v1",
    "DA_d2_heldout100": "diagnosisarena/subsets/d2_heldout100_v1",
    "DA_d2_heldout200b": "diagnosisarena/subsets/d2_heldout200b_v1",
    "MCR_v1_seq100": "medcasereasoning/subsets/mcr_val_seq100_v1",
    "MCR_v2_seq100": "medcasereasoning/subsets/mcr_val_seq100_v2",
    "MCR_seq200b": "medcasereasoning/subsets/mcr_val_seq200b_v1",
}
RECALLED = {"champion_strong", "top2_strong", "set_strong", "set_near"}


def load_cases(subset: str) -> dict[str, dict[str, Any]]:
    path = BENCH / subset / "normalized_cases.json"
    blob = json.loads(path.read_text(encoding="utf-8"))
    rows = blob.get("cases", blob) if isinstance(blob, dict) else blob
    return {str(r.get("id", r.get("case_id", ""))): r for r in rows}


def spans(items: list[str], limit: int = 6) -> str:
    if not items:
        return "—"
    return " / ".join(s.strip()[:110] for s in items[:limit])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "discrimination_pack.md")
    parser.add_argument("--index", type=Path, default=LEDGER_DIR / "discrimination_scope.csv")
    args = parser.parse_args()

    rows = [json.loads(l) for l in RECALL.read_text(encoding="utf-8").splitlines() if l.strip()]
    cache: dict[str, dict[str, Any]] = {}

    selected = []
    for row in rows:
        entertained = [m for m in METHODS if row["methods"][m].get("recall_status") in RECALLED]
        if not entertained:
            continue
        failed = [m for m in entertained if row["methods"][m]["correct"].get("top1") is not True]
        if not failed:
            continue
        selected.append((row, entertained, failed))

    out: list[str] = [
        "# 鉴别能力审查证据包",
        "",
        f"入选标准：至少一个目标方法把金标纳入假设集（strong 或 near），且其中至少一个方法未选中。共 {len(selected)} 例。",
        "",
    ]
    index_rows = ["case_key,family,gold,d0d3_local,entertained,failed,n_failed"]

    for row, entertained, failed in selected:
        slice_id, source_id = row["case_key"].split("/", 1)
        subset = SUBSETS[slice_id]
        if subset not in cache:
            cache[subset] = load_cases(subset)
        case = cache[subset].get(source_id, {})
        text = case.get("case_text", "") or ""

        index_rows.append(
            f'{row["case_key"]},{row["family"]},"{row["gold"]}",{row["diagnostic_support_local"][:2]},'
            f'{";".join(entertained)},{";".join(failed)},{len(failed)}'
        )

        out += [
            "---",
            "",
            f'## {row["case_key"]} — {row["gold"]}',
            "",
            f'- 家族 {row["family"]} / 层 {row["sampling_stratum"]} / 权重 {row["sampling_weight"]}',
            f'- 指南能力：本地扩展 {row["diagnostic_support_local"]}（上游三源 {row["diagnostic_support_upstream"]}）',
            f'- 纳入金标的方法：{", ".join(entertained)}；其中未选中：{", ".join(failed)}',
            "",
            "### vignette 全文",
            "",
            "```",
            text.strip(),
            "```",
            "",
        ]

        for method in METHODS:
            data = row["methods"][method]
            if not data.get("present"):
                out.append(f"### {method}：无轨迹\n")
                continue
            corr = data["correct"]
            verdict = corr.get("top1")
            extra = ""
            if corr.get("metric") == "option_top1":
                extra = (
                    f'，映射命中 {corr.get("n_options_matched")}/{corr.get("n_options")} 个选项'
                    f'，金标关系 {corr.get("gold_relation_type")}'
                )
            out += [
                f"### {method}（召回 {data['recall_status']}，判分 {verdict}{extra}）",
                "",
                f"- champion：**{data['champion']}**　runner-up：{data['runner_up']}　margin：{data['selector_margin']}",
                f"- selector 理由：{(data['selector_why'] or '—')[:600]}",
                "",
                "| 候选 | 与金标 | 分数 | 支持 span | 反对 span |",
                "|---|---|---|---|---|",
            ]
            for entry in data["gold_registry_entries"] + data["competitor_registry_entries"]:
                sup = entry["support_spans"] or entry.get("support_evidence") or []
                con = entry["contradict_spans"] or entry.get("contradict_evidence") or []
                out.append(
                    f'| {entry["label"]} | {entry.get("gold_match","-")} | {entry.get("score")} '
                    f'| {spans([str(s) for s in sup], 4)} | {spans([str(s) for s in con], 4)} |'
                )
            out.append("")
            gen = data["generator_candidates"]
            if gen:
                out += ["<details><summary>生成器逐视角候选与理由</summary>", ""]
                for g in gen:
                    out.append(
                        f'- `{g["view"]}` **{g["label"]}** — why: {(g["why"] or "")[:260]}'
                    )
                    if g["support_spans"]:
                        out.append(f'    - 支持：{spans(g["support_spans"], 5)}')
                    if g["contradict_spans"]:
                        out.append(f'    - 反对：{spans(g["contradict_spans"], 5)}')
                out += ["", "</details>", ""]
            if data["selector_rejected"]:
                out += ["<details><summary>selector 淘汰理由</summary>", ""]
                for rej in data["selector_rejected"]:
                    out.append(f'- **{rej["name"]}** — {(rej["why"] or "")[:260]}')
                out += ["", "</details>", ""]

    args.out.write_text("\n".join(out) + "\n", encoding="utf-8")
    args.index.write_text("\n".join(index_rows) + "\n", encoding="utf-8")
    print(f"{len(selected)} cases -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
