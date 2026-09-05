#!/usr/bin/env python3
"""Compact per-case worksheet for hand-building a discrimination flow.

The full adjudication pack carries every method's spans and rationales, which is
the right material for judging *why a method failed* but too diffuse for the
different question of whether a clinician could separate the gold at all.  That
question needs only three things per case: the vignette, the gold, and the union
of hypotheses the four methods actually put on the table.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
RECALL = LEDGER_DIR / "method_hypothesis_recall_48.jsonl"
LEDGER = LEDGER_DIR / "manual_source_coverage_48_local_expanded.jsonl"
SCOPE = LEDGER_DIR / "discrimination_scope.csv"
FINDINGS = LEDGER_DIR / "discrimination_findings_22.csv"
PACK = LEDGER_DIR / "discrimination_pack.md"
METHODS = ("collapse3c", "multistance", "impc", "forest")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def vignettes_from_pack() -> dict[str, str]:
    """The pack already carries the frozen vignette text for the scoped cases."""
    out: dict[str, str] = {}
    key = None
    buf: list[str] = []
    grabbing = False
    for line in PACK.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if key and buf:
                out[key] = "\n".join(buf).strip()
            key = line[3:].split(" — ")[0].strip()
            buf, grabbing = [], False
        elif line.startswith("### vignette"):
            grabbing = True
        elif line.startswith("###"):
            if grabbing and key:
                out[key] = "\n".join(buf).strip()
            grabbing = False
        elif grabbing:
            buf.append(line)
    if key and buf and key not in out:
        out[key] = "\n".join(buf).strip()
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "manual_tree_worksheet.md")
    args = parser.parse_args()

    recall = {r["case_key"]: r for r in read_jsonl(RECALL)}
    ledger = {r["case_key"]: r for r in read_jsonl(LEDGER)}
    with SCOPE.open(encoding="utf-8") as fh:
        scope = [r["case_key"] for r in csv.DictReader(fh)]
    findings = {}
    if FINDINGS.exists():
        with FINDINGS.open(encoding="utf-8") as fh:
            findings = {r["case_key"]: r for r in csv.DictReader(fh)}
    vignettes = vignettes_from_pack()

    lines: list[str] = ["# 手工判别流程工作底稿（深审 22 例）", ""]
    for key in scope:
        row, led = recall[key], ledger[key]
        lines += [
            f"## {key} — {row['gold']}",
            "",
            f"- 语料判级：{led['diagnostic_support']}　家族：{row['family']}",
            f"- vignette 决定性线索（账本）：{'；'.join(led.get('matched_vignette_clues', []))}",
            f"- 缺失限定词（账本）：{'；'.join(led.get('missing_qualifiers', []))}",
        ]
        f = findings.get(key)
        if f:
            lines += [
                f"- 前轮鉴别点：{f['discriminator']}",
                f"- 指南中有：{f['in_guideline']}　vignette 中有：{f['in_vignette']}　"
                f"方法抽取到：{f['extracted_by_methods']}　用对：{f['used_correctly']}　"
                f"失败模式：{f['failure_mode']}",
            ]

        by_label: dict[str, set[str]] = defaultdict(set)
        champions: dict[str, str] = {}
        for m in METHODS:
            d = row["methods"][m]
            if not d.get("present"):
                continue
            champions[m] = d.get("champion") or "(无)"
            for e in d["gold_registry_entries"] + d["competitor_registry_entries"]:
                by_label[e["label"]].add(m)
            for g in d["generator_candidates"]:
                by_label[g["label"]].add(m)
        lines += [
            "",
            "### 四方法最终答案",
            "",
            *[f"- {m}：{champions.get(m, '(缺)')}"
              f"（召回 {row['methods'][m]['recall_status']}）" for m in METHODS
              if row["methods"][m].get("present")],
            "",
            f"### 待分离的假设集（{len(by_label)} 个）",
            "",
        ]
        for label in sorted(by_label, key=lambda x: (-len(by_label[x]), x)):
            lines.append(f"- {label} ← {','.join(sorted(by_label[label]))}")
        lines += ["", "### vignette", "", vignettes.get(key, "(未取到)"), "", "---", ""]

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(lines)} lines, {len(scope)} cases, "
          f"{sum(1 for k in scope if k in vignettes)} vignettes recovered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
