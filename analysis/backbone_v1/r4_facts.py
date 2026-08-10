#!/usr/bin/env python3
"""Build R4 dual-metric fact tables and reconcile R2/R3 prune numbers.

Usage:
  PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1 \\
    python3 analysis/backbone_v1/r4_facts.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import r4_lib as r4

OUT = r4.R4


def summarize(rows: list[dict]) -> dict:
    arms = r4.CORE_ARMS
    n = len(rows)
    scored_acc = {a: r4.rate(r.get(f"{a}_scored_correct") for r in rows) for a in arms}
    chain_acc = {a: r4.rate(r.get(f"{a}_chain_correct") for r in rows) for a in arms}
    rescue = {
        a: {
            "n": sum(1 for r in rows if r.get(f"{a}_mapper_rescue") is True),
            "rate_among_scored": (
                sum(1 for r in rows if r.get(f"{a}_mapper_rescue") is True)
                / max(sum(1 for r in rows if r.get(f"{a}_scored_correct") is True), 1)
            ),
        }
        for a in list(arms) + ["B01", "APHHM"]
    }
    layers_scored = Counter(r.get("layer_scored") for r in rows)
    layers_chain = Counter(r.get("layer_chain") for r in rows)

    # exclusives under chain
    exclusive_chain = Counter()
    for r in rows:
        hits = [a for a in arms if r.get(f"{a}_chain_correct") is True]
        if len(hits) == 1:
            exclusive_chain[hits[0]] += 1

    e7_win_base = sum(
        1
        for r in rows
        if r.get("e7_chain_correct") is True
        and not (r.get("B06_chain_correct") or r.get("B07_chain_correct"))
    )
    base_win_e7 = sum(
        1
        for r in rows
        if r.get("e7_chain_correct") is False
        and (r.get("B06_chain_correct") or r.get("B07_chain_correct"))
    )

    # APHHM subset
    aph = [r for r in rows if r.get("APHHM_scored_correct") is not None]
    prune = [r for r in aph if (r.get("APHHM_locus") or "") == "tree_hit_final_drop"]
    prune_e7_scored = sum(1 for r in prune if r.get("e7_scored_correct") is True)
    prune_e7_chain = sum(1 for r in prune if r.get("e7_chain_correct") is True)
    prune_e7_locus_ok = sum(1 for r in prune if (r.get("e7_locus") or "") == "ok")
    prune_gap = []
    for r in prune:
        if r.get("e7_scored_correct") is True and (r.get("e7_locus") or "") != "ok":
            prune_gap.append(
                {
                    "dataset": r.get("dataset"),
                    "slice": r.get("slice"),
                    "case_id": r.get("case_id"),
                    "gold": r.get("gold"),
                    "e7_locus": r.get("e7_locus"),
                    "e7_mapper_rescue": r.get("e7_mapper_rescue"),
                    "e7_s4_hit": r.get("e7_s4_hit"),
                    "e7_pred": r.get("e7_pred"),
                }
            )

    return {
        "n": n,
        "scored_acc": scored_acc,
        "chain_acc": chain_acc,
        "mapper_rescue": rescue,
        "layers_scored": dict(layers_scored),
        "layers_chain": dict(layers_chain),
        "exclusive_chain": dict(exclusive_chain),
        "e7_win_vs_base_chain": e7_win_base,
        "base_win_vs_e7_chain": base_win_e7,
        "e7_win_vs_base_scored": sum(
            1
            for r in rows
            if r.get("e7_scored_correct") is True
            and not (r.get("B06_scored_correct") or r.get("B07_scored_correct"))
        ),
        "base_win_vs_e7_scored": sum(
            1
            for r in rows
            if r.get("e7_scored_correct") is False
            and (r.get("B06_scored_correct") or r.get("B07_scored_correct"))
        ),
        "aphhm": {
            "n": len(aph),
            "prune_n": len(prune),
            "r2_e7_correct_when_pruned": prune_e7_scored,
            "r2_rate": prune_e7_scored / len(prune) if prune else None,
            "r3_e7_locus_ok_when_pruned": prune_e7_locus_ok,
            "r3_rate": prune_e7_locus_ok / len(prune) if prune else None,
            "r4_e7_chain_when_pruned": prune_e7_chain,
            "r4_rate": prune_e7_chain / len(prune) if prune else None,
            "gap_n": len(prune_gap),
            "gap_mapper_rescue_n": sum(1 for g in prune_gap if g["e7_mapper_rescue"]),
            "gap_by_dataset": dict(Counter(g["dataset"] for g in prune_gap)),
            "gap_by_locus": dict(Counter(g["e7_locus"] for g in prune_gap)),
            "gap_rows": prune_gap,
        },
    }


def write_reconciliation(summary: dict) -> None:
    aph = summary["aphhm"]
    lines = [
        "# R4 口径对账（R2 34/77 vs R3 10/77）",
        "",
        "> 由 `r4_facts.py` 自动生成。零新增 LLM 调用。",
        "",
        "## 1. 两个数字用了同一批 77 例",
        "",
        f"- prune cohort：`APHHM_locus == tree_hit_final_drop`，n={aph['prune_n']}",
        f"- R2（`aphhm_funnel`）用 `e7_scored_correct`（终值分数）→ **{aph['r2_e7_correct_when_pruned']}/{aph['prune_n']} = {aph['r2_rate']:.2%}**",
        f"- R3（`failure_taxonomy`）用 `e7_correct ∧ e7_locus==ok` → **{aph['r3_e7_locus_ok_when_pruned']}/{aph['prune_n']} = {aph['r3_rate']:.2%}**",
        f"- R4（本表）用 `e7_chain_correct`（champion 硬匹配金标）→ **{aph['r4_e7_chain_when_pruned']}/{aph['prune_n']} = {aph['r4_rate']:.2%}**",
        "",
        "## 2. 差额分解",
        "",
        f"- 差额 n = R2 − R3 = **{aph['gap_n']}**",
        f"- 其中 `e7_mapper_rescue=True`：**{aph['gap_mapper_rescue_n']}/{aph['gap_n']}**",
        f"- 按数据集：{json.dumps(aph['gap_by_dataset'], ensure_ascii=False)}",
        f"- 按 e7_locus：{json.dumps(aph['gap_by_locus'], ensure_ascii=False)}",
        "",
        "**结论：** 不是不同交集、不是不同 mapper 版本。同一 77 例、同一 `e7_correct` 列；",
        "R3 加了全链路门控，把 DA 上的 mapper 捡漏从「救回」里剔掉了。",
        "R4 主叙事一律用 `chain_correct`；`scored_correct` 与 `mapper_rescue` 并列保留。",
        "",
        "## 3. 双口径下的 800 题主表（core4）",
        "",
        f"- n = {summary['n']}",
        f"- scored Acc：{json.dumps(summary['scored_acc'])}",
        f"- chain Acc：{json.dumps(summary['chain_acc'])}",
        f"- scored：e7 独占 vs base = {summary['e7_win_vs_base_scored']} : {summary['base_win_vs_e7_scored']}",
        f"- chain：e7 独占 vs base = {summary['e7_win_vs_base_chain']} : {summary['base_win_vs_e7_chain']}",
        f"- chain 独占臂：{json.dumps(summary['exclusive_chain'])}",
        "",
        "### layer（scored）",
        "",
        "```",
        json.dumps(summary["layers_scored"], indent=2, ensure_ascii=False),
        "```",
        "",
        "### layer（chain）",
        "",
        "```",
        json.dumps(summary["layers_chain"], indent=2, ensure_ascii=False),
        "```",
        "",
        "### mapper_rescue（占该臂 scored 命中的比例）",
        "",
    ]
    for arm, info in summary["mapper_rescue"].items():
        lines.append(
            f"- {arm}: n={info['n']}，占 scored 命中 {info['rate_among_scored']:.1%}"
        )
    lines.extend(
        [
            "",
            "## 4. 可写 / 不可写",
            "",
            "- **可写：** R2 的 44%「剪枝后 e7 仍对」被 DA mapper 捡漏灌水；全链路口径约为 13%。",
            "- **不可写：** 把 R2 的 34/77 直接当作「扁平骨干救回了层次剪枝损失」。",
            "- **不可写：** 在未剥离 mapper_rescue 的 scored 口径上比较 DA 臂序优势。",
            "",
        ]
    )
    (OUT / "RECONCILIATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = r4.load_joined()
    rows = []
    for r in raw:
        a = r4.annotate_metrics(r)
        a["layer_scored"] = r4.layer_scored(a)
        a["layer_chain"] = r4.layer_from_chain(a)
        # keep original census layer for reference
        a["layer_census"] = r.get("layer") or ""
        rows.append(a)

    r4.write_tsv(OUT / "pooled.tsv", rows)
    da = [r for r in rows if r.get("dataset") == "da"]
    mcr = [r for r in rows if r.get("dataset") == "mcr"]
    r4.write_tsv(OUT / "da.tsv", da)
    r4.write_tsv(OUT / "mcr.tsv", mcr)

    pooled = summarize(rows)
    da_s = summarize(da)
    mcr_s = summarize(mcr)
    # strip gap_rows from da/mcr nested to keep summary small; keep in pooled
    def _strip_gaps(s: dict) -> dict:
        out = {k: v for k, v in s.items() if k != "aphhm"}
        out["aphhm"] = {
            kk: vv for kk, vv in s["aphhm"].items() if kk != "gap_rows"
        }
        return out

    summary = {
        "pooled": {k: v for k, v in pooled.items()},
        "da": _strip_gaps(da_s),
        "mcr": _strip_gaps(mcr_s),
    }
    # keep gap_rows only in reconciliation / prune_gap_cases.tsv
    summary["pooled"]["aphhm"] = {
        k: v for k, v in pooled["aphhm"].items() if k != "gap_rows"
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_reconciliation(pooled)
    # also dump gap cases
    r4.write_tsv(OUT / "prune_gap_cases.tsv", pooled["aphhm"]["gap_rows"])

    print("=== R4 facts ===")
    print(f"n={pooled['n']} da={len(da)} mcr={len(mcr)}")
    print("scored Acc", pooled["scored_acc"])
    print("chain Acc ", pooled["chain_acc"])
    print(
        "layers_chain base_win_rank/recall:",
        pooled["layers_chain"].get("base_win_rank"),
        pooled["layers_chain"].get("base_win_recall"),
    )
    print(
        "APHHM prune R2/R3/R4:",
        pooled["aphhm"]["r2_e7_correct_when_pruned"],
        pooled["aphhm"]["r3_e7_locus_ok_when_pruned"],
        pooled["aphhm"]["r4_e7_chain_when_pruned"],
        "gap",
        pooled["aphhm"]["gap_n"],
        "rescue_in_gap",
        pooled["aphhm"]["gap_mapper_rescue_n"],
    )
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
