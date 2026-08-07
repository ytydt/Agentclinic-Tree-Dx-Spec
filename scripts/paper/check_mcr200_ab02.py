#!/usr/bin/env python3
"""Aggregate MCR200 AB02 (flat) vs M00 Prompt-7 Acc on both slices.

Writes analysis/mcr200_ab02_v1/{report.json,README.md}.
Zero new LLM calls — reads official_eval_llm_compat case_scores.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis/mcr200_ab02_v1"

PATHS = {
    "v1": {
        "m00": ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate/official_eval_llm_compat",
        "ab02": ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/annotate/official_eval_llm_compat",
    },
    "v2": {
        "m00": ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1/annotate/official_eval_llm_compat",
        "ab02": ROOT
        / "logs/medcasereasoning_mcr_val_seq100_v2/c3_ab02_v1/annotate/official_eval_llm_compat",
    },
}


def _load_hits(eval_dir: Path) -> dict[str, bool]:
    scores = eval_dir / "case_scores"
    out: dict[str, bool] = {}
    if not scores.is_dir():
        # try jsonl
        for name in ("case_scores.jsonl", "scores.jsonl"):
            p = eval_dir / name
            if p.is_file():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    cid = str(d.get("case_id") or d.get("source_id") or "")
                    hit = d.get("diagnostic_hit")
                    if hit is None:
                        hit = d.get("correct")
                    if cid and hit is not None:
                        out[cid] = bool(hit)
                return out
        return out
    for p in scores.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        cid = str(d.get("case_id") or p.stem)
        hit = d.get("diagnostic_hit")
        if hit is None:
            hit = (d.get("scores") or {}).get("diagnostic_hit")
        if hit is None:
            continue
        out[cid] = bool(hit)
    return out


def _acc(hits: dict[str, bool]) -> float | None:
    if not hits:
        return None
    return sum(hits.values()) / len(hits)


def _sign_test(b: int, c: int) -> float:
    """Two-sided exact binomial on discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    # P(X<=min) * 2, capped at 1
    k = min(b, c)
    # sum_{i=0..k} C(n,i) / 2^n
    total = 0.0
    for i in range(k + 1):
        total += math.comb(n, i)
    p = 2.0 * total / (2 ** n)
    return min(1.0, p)


def _slice_stats(tag: str) -> dict[str, Any]:
    m00 = _load_hits(PATHS[tag]["m00"])
    ab02 = _load_hits(PATHS[tag]["ab02"])
    common = sorted(set(m00) & set(ab02))
    b = c = 0  # b: M00 better, c: AB02 better
    for cid in common:
        if m00[cid] and not ab02[cid]:
            b += 1
        elif ab02[cid] and not m00[cid]:
            c += 1
    m00_acc = sum(m00[cid] for cid in common) / max(1, len(common))
    ab02_acc = sum(ab02[cid] for cid in common) / max(1, len(common))
    return {
        "slice": tag,
        "n_m00": len(m00),
        "n_ab02": len(ab02),
        "n_paired": len(common),
        "m00_acc": round(m00_acc, 4),
        "ab02_acc": round(ab02_acc, 4),
        "delta_m00_minus_ab02": round(m00_acc - ab02_acc, 4),
        "discordant_b_m00_better": b,
        "discordant_c_ab02_better": c,
        "sign_test_p": round(_sign_test(b, c), 4),
        "m00_only": sorted(set(m00) - set(ab02)),
        "ab02_only": sorted(set(ab02) - set(m00)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    slices = {}
    for tag in ("v1", "v2"):
        if PATHS[tag]["ab02"].is_dir() or (PATHS[tag]["ab02"] / "summary.json").is_file():
            # case_scores may be under the eval dir
            pass
        slices[tag] = _slice_stats(tag)

    # pooled
    m00_all: dict[str, bool] = {}
    ab02_all: dict[str, bool] = {}
    for tag in ("v1", "v2"):
        # prefix to avoid id collision across slices (ids may restart)
        m00 = _load_hits(PATHS[tag]["m00"])
        ab02 = _load_hits(PATHS[tag]["ab02"])
        for cid, h in m00.items():
            m00_all[f"{tag}:{cid}"] = h
        for cid, h in ab02.items():
            ab02_all[f"{tag}:{cid}"] = h
    common = sorted(set(m00_all) & set(ab02_all))
    b = c = 0
    for cid in common:
        if m00_all[cid] and not ab02_all[cid]:
            b += 1
        elif ab02_all[cid] and not m00_all[cid]:
            c += 1
    m00_acc = sum(m00_all[cid] for cid in common) / max(1, len(common))
    ab02_acc = sum(ab02_all[cid] for cid in common) / max(1, len(common))
    pooled = {
        "n_paired": len(common),
        "m00_acc": round(m00_acc, 4),
        "ab02_acc": round(ab02_acc, 4),
        "delta_m00_minus_ab02": round(m00_acc - ab02_acc, 4),
        "discordant_b_m00_better": b,
        "discordant_c_ab02_better": c,
        "sign_test_p": round(_sign_test(b, c), 4),
    }
    report = {
        "endpoint": "Prompt-7 diagnostic_accuracy_single_trajectory (official_eval_llm_compat)",
        "contrast": "M00 compat_synonym − AB02 flat",
        "slices": slices,
        "pooled": pooled,
        "note": (
            "AB02 = flat L1 axis on M00 trees + regenerate L2; "
            "same compat + synonym_bind + Prompt-7 stack as M00. "
            "Internal analysis for next paper cycle; do not enter locked main text."
        ),
    }
    (OUT / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# MCR200 × AB02（flat / no L1）",
        "",
        "口径：`official_eval_llm_compat` Prompt-7 Acc@1，与主文 MCR 头条同标度。",
        "干预：在 M00 树上施加 `l1_axis_mode=flat`（`keep_leaves=False`），annotate 重生 L2；",
        "其余与 M00 对齐（`granularity=compat` + synonym_bind）。",
        "",
        "## 结果",
        "",
        "| 切片 | n 配对 | M00 Acc | AB02 Acc | Δ (M00−AB02) | b/c | sign-test p |",
        "|---|---:|---:|---:|---:|---|---:|",
    ]
    for tag in ("v1", "v2"):
        s = slices[tag]
        lines.append(
            f"| 切片{'一' if tag=='v1' else '二'} ({tag}) | {s['n_paired']} | "
            f"{s['m00_acc']:.3f} | {s['ab02_acc']:.3f} | "
            f"{s['delta_m00_minus_ab02']:+.3f} | "
            f"{s['discordant_b_m00_better']}/{s['discordant_c_ab02_better']} | "
            f"{s['sign_test_p']:.3f} |"
        )
    lines.append(
        f"| **合并** | {pooled['n_paired']} | {pooled['m00_acc']:.3f} | "
        f"{pooled['ab02_acc']:.3f} | {pooled['delta_m00_minus_ab02']:+.3f} | "
        f"{pooled['discordant_b_m00_better']}/{pooled['discordant_c_ab02_better']} | "
        f"{pooled['sign_test_p']:.3f} |"
    )
    lines += [
        "",
        "b = M00 对、AB02 错；c = AB02 对、M00 错。",
        "",
        "## 产物",
        "",
        "- `logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/`",
        "- `logs/medcasereasoning_mcr_val_seq100_v2/c3_ab02_v1/`",
        "- 机器可读：`report.json`",
        "",
        "## 处置",
        "",
        "内部分析；主文已锁。是否入下一版取决于合并方向与效应量，",
        "不自动写入 `paper_aaai/`。",
        "",
    ]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
