#!/usr/bin/env python3
"""Refresh C2 results docs from live AB21/AB22 mapper artifacts (idempotent)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DA = ROOT / "logs/diagnosisarena_d2_m01_v1"
RES_MD = ROOT / "runs/paper_v1/ablations_c2_results.md"
RES_JSON = ROOT / "runs/paper_v1/ablations_c2_results.json"
DA_RAW = ROOT / "runs/paper_v1/ablations_c2_da_raw.json"
M00 = {"option_top1": 0.71, "option_top2": 0.78}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapper(arm: str) -> dict | None:
    p = DA / arm / "annotate/mapper/summary.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _proj_n(arm: str) -> int:
    d = DA / arm / "annotate/mapper/projections"
    if not d.is_dir():
        return 0
    return len(list(d.glob("*.json")))


def _case_ok(arm: str) -> int:
    d = DA / arm / "annotate/case_results"
    if not d.is_dir():
        return 0
    n = 0
    for p in d.glob("*.json"):
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("status") == "OK":
                n += 1
        except Exception:  # noqa: BLE001
            pass
    return n


def main() -> int:
    ab21 = _mapper("c2_ab21_v1")
    ab22 = _mapper("c2_ab22_v1")
    ab22_proj = _proj_n("c2_ab22_v1")
    ab21_ok = _case_ok("c2_ab21_v1")
    ab22_ok = _case_ok("c2_ab22_v1")

    da_raw = json.loads(DA_RAW.read_text(encoding="utf-8")) if DA_RAW.is_file() else {"arms": {}}
    da_raw["updated_at"] = _utc()
    da_raw["synonym_bind"] = False
    da_raw.setdefault("arms", {})

    def _pack(label: str, out: Path, summary: dict | None, *, annotate_ok: int, proj: int) -> dict:
        if summary:
            return {
                "label": label,
                "output_dir": str(out),
                "exit_code": 0,
                "synonym_bind": False,
                "status": "COMPLETE",
                "annotate": {"n_ok": annotate_ok},
                "mapper": {
                    "option_top1": summary.get("option_top1"),
                    "option_top2": summary.get("option_top2"),
                    "option_top1_count": summary.get("option_top1_count"),
                    "option_top2_count": summary.get("option_top2_count"),
                    "mean_option_rr": summary.get("mean_option_rr"),
                    "n_ok": summary.get("n_ok"),
                    "n_error": summary.get("n_error"),
                    "synonym_bind_repair": summary.get("synonym_bind_repair"),
                    "mapper_mode": summary.get("mapper_mode"),
                },
                "delta_vs_m00": {
                    "option_top1": round(float(summary["option_top1"]) - M00["option_top1"], 4),
                    "option_top2": round(float(summary["option_top2"]) - M00["option_top2"], 4),
                },
            }
        return {
            "label": label,
            "output_dir": str(out),
            "exit_code": None,
            "synonym_bind": False,
            "status": "MAPPER_IN_PROGRESS" if annotate_ok >= 100 else "ANNOTATE_IN_PROGRESS",
            "annotate": {"n_ok": annotate_ok},
            "mapper_progress": {"n_projections": proj, "n_target": 100},
            "mapper": None,
        }

    da_raw["arms"]["ab21"] = _pack(
        "AB21 salience≈p5_contrastive_direct (proxy for plan salience)",
        DA / "c2_ab21_v1",
        ab21,
        annotate_ok=ab21_ok,
        proj=_proj_n("c2_ab21_v1"),
    )
    da_raw["arms"]["ab22"] = _pack(
        "AB22 anti-anchor + no P5 compiler inject",
        DA / "c2_ab22_v1",
        ab22,
        annotate_ok=ab22_ok,
        proj=ab22_proj,
    )
    DA_RAW.write_text(json.dumps(da_raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    res = json.loads(RES_JSON.read_text(encoding="utf-8"))
    res["updated_at"] = _utc()
    if ab21 and ab22:
        res["status_note"] = "AB21+AB22 complete"
    elif ab21:
        res["status_note"] = "AB21 complete; AB22 mapper in progress"
    else:
        res["status_note"] = "DA block4 in progress"
    block4 = []
    for key, arm_id in (("ab21", "AB21"), ("ab22", "AB22")):
        row = da_raw["arms"][key]
        block4.append(
            {
                "id": arm_id,
                "label": row["label"],
                "mapper": row.get("mapper") or {},
                "delta_vs_m00": row.get("delta_vs_m00"),
                "status": row.get("status"),
                "mapper_progress": row.get("mapper_progress"),
                "output_dir": row["output_dir"],
                "exit_code": row.get("exit_code"),
                "synonym_bind": False,
            }
        )
    res["block4_da_proxy"] = block4
    interps = list(res.get("interpretations") or [])
    if ab21:
        note = (
            "AB21 option@1/@2=%.2f/%.2f vs M00 0.71/0.78 "
            "(Δ@1=%+.2f; |Δ|<0.10 → direction only: contrastive salience slightly worse)"
            % (
                ab21["option_top1"],
                ab21["option_top2"],
                float(ab21["option_top1"]) - 0.71,
            )
        )
        interps = [x for x in interps if not x.startswith("AB21 ")]
        interps.append(note)
    if ab22:
        note = (
            "AB22 option@1/@2=%.2f/%.2f vs M00 0.71/0.78 (Δ@1=%+.2f)"
            % (
                ab22["option_top1"],
                ab22["option_top2"],
                float(ab22["option_top1"]) - 0.71,
            )
        )
        interps = [x for x in interps if not x.startswith("AB22 ")]
        interps.append(note)
    res["interpretations"] = interps
    RES_JSON.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # md
    lines = [
        "# C2 计算档消融结果（不入论文主表）",
        "",
        f"- created_at: `{res.get('created_at')}`",
        f"- updated_at: `{res['updated_at']}`",
        "- tier: **C2**（复用冻结树 T，从 E/W live；非 confirmatory AB10b）",
        f"- backup: `{res.get('backup_path')}`",
        "- OX workers: `12`；DA workers: `12`",
        "- DA scoring: **无 synonym_bind**",
        "- 块4切片: **DA `d2_seq100` 代理**（计划 D1b-dev-freeze 未物化）",
        f"- AB16: **历史复用**；档案 `{res.get('ab16_reuse_archive')}`",
        f"- AB28: **历史复用**；档案 `{res.get('ab28_reuse_archive')}`",
        f"- **进度**: {res['status_note']}",
        "",
        "## 锚点（只读）",
        "",
        (
            f"- OX M00 closed_live_mac: F1={res['m00_ox_readonly']['micro_f1']} "
            f"P={res['m00_ox_readonly']['micro_precision']} "
            f"R={res['m00_ox_readonly']['micro_recall']} "
            f"Interp={res['m00_ox_readonly']['interpretation_accuracy']}"
        ),
        f"- DA compat 名义 option@1/@2: {M00}",
        "",
        "## 块3 OX（预算 / 写回 / cap）",
        "",
        "| ID | 设置 | micro | live_trees | exits |",
        "|---|---|---|---|---|",
    ]
    for row in res["block3_ox"]:
        m = row["micro"]
        tag = " **[reuse]**" if row.get("reused") else ""
        lines.append(
            f"| {row['id']}{tag} | L1={row['l1']} wb={row['writeback']} cap={row['cap']} | "
            f"F1={m['micro_f1']} P={m['micro_precision']} R={m['micro_recall']} "
            f"Interp={m['interpretation_accuracy']} | {row.get('n_live_trees')} | "
            f"ann={row.get('annotate_exit')} llm={row.get('llm_exit')} |"
        )
    lines += [
        "",
        "## 块4 DA 选择器（代理切片）",
        "",
        "| ID | 设置 | option@1 | option@2 | Δ@1 vs M00 | Δ@2 vs M00 | 状态 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for key, title in (
        ("ab21", "salience≈p5_contrastive_direct"),
        ("ab22", "anti-anchor + no P5 compiler inject"),
    ):
        row = da_raw["arms"][key]
        m = row.get("mapper") or {}
        d = row.get("delta_vs_m00") or {}
        if m:
            lines.append(
                f"| {key.upper()} | {title} | {m['option_top1']:.2f} | {m['option_top2']:.2f} | "
                f"{d.get('option_top1', 0):+.2f} | {d.get('option_top2', 0):+.2f} | COMPLETE |"
            )
        else:
            prog = row.get("mapper_progress") or {}
            lines.append(
                f"| {key.upper()} | {title} | — | — | — | — | "
                f"{row.get('status')} proj {prog.get('n_projections', 0)}/100 |"
            )
    ab28 = res["block6_ab28"]
    lines += [
        "",
        "## 块6 AB28 重核",
        "",
        f"- **reused**: `{ab28.get('reused')}`",
        f"- out: `{ab28.get('output_dir')}`",
        f"- R_compat @1/@2: `{ab28.get('R_compat')}`",
        f"- inject_typed @1/@2: `{ab28.get('R_compat_inject_typed')}`",
        f"- Δ@1: `{ab28.get('delta_opt1')}`",
        f"- note: {ab28.get('note')}",
        "",
        "## 预注册解读（草稿）",
        "",
    ]
    for x in res["interpretations"]:
        lines.append(f"- {x}")
    lines += [
        "",
        "## 路径索引",
        "",
        f"- `{res.get('ox_raw')}`",
        f"- `{DA_RAW}`",
        f"- `{RES_JSON}`",
        "",
        "> 本文件仅供内部消融归档；勿写入论文主结果表。",
        "",
    ]
    RES_MD.write_text("\n".join(lines), encoding="utf-8")
    print(
        json.dumps(
            {
                "ab21": da_raw["arms"]["ab21"]["status"],
                "ab22": da_raw["arms"]["ab22"]["status"],
                "ab22_proj": ab22_proj,
                "md": str(RES_MD),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
