#!/usr/bin/env python3
"""Live option @1/@2 for test arms on compat_parallel.

B12: rematch frozen option_maps onto Pilot24 annotate(--l1-calib b12 --granularity-mode compat)
     rankings; also read typed_llm mapper projections if present.

R3: frozen trees already gap_fill ON → option equals existing compat baseline.

R4/R5: ABSENT inject failed TPP → report ABSENT official mapper option (0/0).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import run_at1_calibration_smoke as at1  # noqa: E402

PILOT = list(at1.PILOT) if hasattr(at1, "PILOT") else [
    "3", "4", "5", "7", "11", "12", "15", "19", "21", "22", "27", "28",
    "29", "33", "36", "39", "40", "45", "57", "59", "60", "62", "63", "67",
]
# at1 may not export PILOT - hardcode
PILOT = [
    "3", "4", "5", "7", "11", "12", "15", "19", "21", "22", "27", "28",
    "29", "33", "36", "39", "40", "45", "57", "59", "60", "62", "63", "67",
]
ABSENT = ("67", "231")
ANALYSIS = ROOT / "analysis" / "l1_gold_recall_v1"
AT1 = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1"
W12 = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1"
REMAIN = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mapper_row(cid: str) -> dict[str, Any] | None:
    for base in (W12, REMAIN):
        p = base / "mapper" / "projections" / f"{cid}.json"
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def rematch_downstream(downstream_dir: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing_case: list[str] = []
    missing_maps: list[str] = []
    for cid in case_ids:
        cp = downstream_dir / "case_results" / f"{cid}.json"
        if not cp.is_file():
            missing_case.append(cid)
            continue
        case = json.loads(cp.read_text(encoding="utf-8"))
        mapper = _mapper_row(cid)
        if not mapper:
            missing_maps.append(cid)
            continue
        labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
        ordered = [str(r.get("id") or "") for r in labels if r.get("id")]
        metrics = at1.rematch_option_metrics(
            mapper_row=mapper,
            ordered_ids=ordered,
            ranking_labels=labels,
        )
        rows.append({
            "case_id": cid,
            "option_top1": int(bool(metrics["option_top1"])),
            "option_top2": int(bool(metrics["option_top2"])),
            "option_rr": float(metrics.get("option_rr") or 0.0),
            "option_rank": metrics.get("option_rank") or "",
            "n_leaves": len(ordered),
            "granularity_mode": (case.get("granularity") or {}).get("mode")
            or (case.get("meta") or {}).get("granularity_mode")
            or "",
            "l1_calib": str(
                ((case.get("l1_calib") or {}) if isinstance(case.get("l1_calib"), dict)
                 else {}).get("arm")
                or case.get("l1_calib")
                or ""
            ),
        })
    n = len(rows)
    summary = {
        "n": n,
        "opt1": (sum(r["option_top1"] for r in rows) / n) if n else None,
        "opt2": (sum(r["option_top2"] for r in rows) / n) if n else None,
        "mrr": (sum(r["option_rr"] for r in rows) / n) if n else None,
    }
    return {
        "rows": rows,
        "summary": summary,
        "missing_case": missing_case,
        "missing_maps": missing_maps,
    }


def typed_summary(downstream_dir: Path, case_ids: Sequence[str]) -> dict[str, Any]:
    rows = []
    for cid in case_ids:
        p = downstream_dir / "mapper" / "projections" / f"{cid}.json"
        if not p.is_file():
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        rows.append({
            "case_id": cid,
            "option_top1": int(bool(r.get("option_top1"))),
            "option_top2": int(bool(r.get("option_top2"))),
            "option_rr": float(r.get("option_rr") or 0.0),
            "gold_option_rank": r.get("gold_option_rank") or "",
        })
    n = len(rows)
    return {
        "rows": rows,
        "summary": {
            "n": n,
            "opt1": (sum(r["option_top1"] for r in rows) / n) if n else None,
            "opt2": (sum(r["option_top2"] for r in rows) / n) if n else None,
            "mrr": (sum(r["option_rr"] for r in rows) / n) if n else None,
        },
    }


def baselines() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cohort, path in [
        ("pilot24", AT1 / "summary_pilot24.json"),
        ("all100", AT1 / "summary_all100.json"),
    ]:
        doc = json.loads(path.read_text(encoding="utf-8"))
        arm = (doc.get("summaries") or {}).get("compat_parallel") or {}
        out[cohort] = {
            "opt1": arm.get("opt1"),
            "opt2": arm.get("opt2"),
            "mrr": arm.get("mrr"),
            "source": str(path.relative_to(ROOT)),
            "protocol": "rematch_onto_compat_leaf_order",
        }
    # Pilot typed from w12
    rows = []
    for cid in PILOT:
        r = _mapper_row(cid)
        if not r:
            continue
        rows.append({
            "option_top1": int(bool(r.get("option_top1"))),
            "option_top2": int(bool(r.get("option_top2"))),
        })
    n = len(rows)
    out["pilot24_w12_typed"] = {
        "n": n,
        "opt1": sum(r["option_top1"] for r in rows) / n if n else None,
        "opt2": sum(r["option_top2"] for r in rows) / n if n else None,
    }
    absent = []
    for cid in ABSENT:
        r = _mapper_row(cid)
        if r:
            absent.append({
                "case_id": cid,
                "option_top1": int(bool(r.get("option_top1"))),
                "option_top2": int(bool(r.get("option_top2"))),
                "gold_option_rank": r.get("gold_option_rank"),
            })
    out["absent_official_mapper"] = absent
    return out


def write_report(payload: Mapping[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary_live_option.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    b = payload["baselines"]
    lines = [
        "# Live option @1/@2（compat_parallel 基线 × 测试臂）",
        "",
        f"- generated: `{payload['generated_at']}`",
        "",
        "## 基线",
        "",
        f"| 队列 | 协议 | @1 | @2 |",
        f"|------|------|---:|---:|",
        f"| all100 | compat rematch | **{b['all100']['opt1']:.2f}** | **{b['all100']['opt2']:.2f}** |",
        f"| Pilot24 | compat rematch | **{b['pilot24']['opt1']:.2f}** | **{b['pilot24']['opt2']:.2f}** |",
        f"| Pilot24 | w12 typed mapper | {b['pilot24_w12_typed']['opt1']:.3f} | {b['pilot24_w12_typed']['opt2']:.3f} |",
        "",
        "## R3 gap-fill",
        "",
        "冻结树已是 `recall_hints_gap` → **live option = compat 基线** "
        f"(all100 **{b['all100']['opt1']:.2f}/{b['all100']['opt2']:.2f}**)。无独立增量。",
        "",
        "## R4/R5 Track C（ABSENT）",
        "",
        "Live inject 未修好 TreeParentPresent。官方 mapper：",
        "",
    ]
    for r in b["absent_official_mapper"]:
        lines.append(
            f"- case {r['case_id']}: @1={r['option_top1']} @2={r['option_top2']} "
            f"(rank={r.get('gold_option_rank')})"
        )
    lines += [
        "",
        "**判定**：ABSENT live option 仍为 **0/0**；REJECT 全表宣称。",
        "",
        "## B12 + compat（Pilot24 live annotate）",
        "",
    ]
    b12 = payload.get("b12") or {}
    if b12.get("status") == "ANNOTATE_PENDING":
        lines.append("- 状态：**ANNOTATE_PENDING**（等待 case_results）")
    else:
        if b12.get("annotate_note"):
            an = b12["annotate_note"]
            lines.append(
                f"- annotate 注意：merge_only={an.get('merge_only_n')}/{an.get('n')}；"
                f"rematch 正式口径可比性=`{an.get('rematch_protocol_valid')}`"
            )
        if b12.get("rematch"):
            s = b12["rematch"]["summary"]
            lines.append(
                f"- rematch（参考，可能无效）: @1={s.get('opt1')} / @2={s.get('opt2')} "
                f"(n={s.get('n')})"
            )
        if b12.get("typed") and (b12["typed"]["summary"] or {}).get("n"):
            s = b12["typed"]["summary"]
            lines.append(
                f"- **typed_llm（主 live）**: **@1={s.get('opt1'):.3f} / "
                f"@2={s.get('opt2'):.3f}** (n={s.get('n')})"
            )
        elif b12.get("typed"):
            lines.append("- typed_llm: 尚未跑 mapper projections")
        v = b12.get("verdict") or {}
        if v:
            lines += [
                "",
                f"- 相对 Pilot24 compat rematch ({b['pilot24']['opt1']:.2f}/"
                f"{b['pilot24']['opt2']:.2f}): "
                f"Δ@1={v.get('delta_opt1_typed_vs_pilot_compat_rematch')} "
                f"Δ@2={v.get('delta_opt2_typed_vs_pilot_compat_rematch')}",
                f"- **{v.get('gate')}** — {v.get('reason')}",
                f"- claim_allowed=`{v.get('claim_allowed')}`；all100=`{v.get('all100')}`",
            ]
    lines += [
        "",
        "## 总表（L2 mapping / rematch 后 option）",
        "",
        "| 臂 | 队列 | @1 | @2 | 备注 |",
        "|----|------|---:|---:|------|",
        f"| compat_parallel | all100 | {b['all100']['opt1']:.2f} | {b['all100']['opt2']:.2f} | 正式主表 |",
        f"| R3 | all100 | {b['all100']['opt1']:.2f} | {b['all100']['opt2']:.2f} | =compat（gap_fill已开） |",
        f"| R4/R5 ABSENT | 2 | 0.00 | 0.00 | inject 未修 TPP |",
    ]
    rem = (b12.get("rematch") or {}).get("summary") or {}
    typ = (b12.get("typed") or {}).get("summary") or {}
    if typ.get("n"):
        lines.append(
            f"| B12+compat | Pilot24 | {typ['opt1']:.3f} | {typ['opt2']:.3f} | typed_llm 主 live |"
        )
    if rem.get("n"):
        lines.append(
            f"| B12+compat | Pilot24 | {rem['opt1']:.3f} | {rem['opt2']:.3f} | rematch（merge坍缩，不可比） |"
        )
    lines.append("")
    (out_dir / "report_live_option.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--b12-downstream",
        type=Path,
        default=ROOT / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1",
    )
    args = ap.parse_args()
    base = baselines()
    down = Path(args.b12_downstream).expanduser().resolve()
    try:
        down_rel = str(down.relative_to(ROOT.resolve()))
    except ValueError:
        down_rel = str(down)
    b12: dict[str, Any] = {"downstream": down_rel}
    n_ready = len(list((down / "case_results").glob("*.json"))) if (down / "case_results").is_dir() else 0
    if n_ready >= len(PILOT):
        rem = rematch_downstream(down, PILOT)
        b12["rematch"] = rem
        out = ANALYSIS / "smoke_live_option"
        out.mkdir(parents=True, exist_ok=True)
        if rem["rows"]:
            with (out / "b12_pilot24_rematch.tsv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rem["rows"][0].keys()), delimiter="\t")
                w.writeheader()
                w.writerows(rem["rows"])
        typ = typed_summary(down, PILOT)
        b12["typed"] = typ
        # Note annotate path: all merge_only collapses leaf set — rematch vs
        # frozen option_maps is NOT comparable to formal compat rematch.
        branches = {}
        for row in rem.get("rows") or ():
            # re-read granularity from case
            pass
        merge_only_n = 0
        for cid in PILOT:
            cp = down / "case_results" / f"{cid}.json"
            if not cp.is_file():
                continue
            case = json.loads(cp.read_text(encoding="utf-8"))
            g = (case.get("l2") or {}).get("granularity") or {}
            if (g.get("path") or g.get("branch")) == "merge_only":
                merge_only_n += 1
        b12["annotate_note"] = {
            "merge_only_n": merge_only_n,
            "n": len(PILOT),
            "rematch_protocol_valid": merge_only_n == 0,
            "warning": (
                "All/most cases took compat merge_only → ranking collapsed to "
                "1–3 representatives; rematch onto frozen option_maps is invalid "
                "as formal-compat comparator. Prefer typed_llm live numbers."
            ),
        }
        s_t = typ["summary"]
        base_o1 = float(base["pilot24"]["opt1"])
        base_o2 = float(base["pilot24"]["opt2"])
        d1_t = float(s_t["opt1"]) - base_o1
        d2_t = float(s_t["opt2"]) - base_o2
        # Gate on typed vs Pilot24 formal rematch baseline
        gate = "PASS" if (d1_t >= 0.04 and d2_t >= -0.01) else "REJECT"
        if d2_t < -0.01:
            gate = "REJECT"
        b12["verdict"] = {
            "gate": gate,
            "primary_protocol": "typed_llm",
            "delta_opt1_typed_vs_pilot_compat_rematch": round(d1_t, 4),
            "delta_opt2_typed_vs_pilot_compat_rematch": round(d2_t, 4),
            "delta_opt1_rematch_invalid": round(
                float(rem["summary"]["opt1"]) - base_o1, 4
            ),
            "delta_opt2_rematch_invalid": round(
                float(rem["summary"]["opt2"]) - base_o2, 4
            ),
            "reason": (
                f"typed_llm {s_t['opt1']:.3f}/{s_t['opt2']:.3f} vs Pilot24 compat "
                f"rematch {base_o1:.2f}/{base_o2:.2f}; "
                f"merge_only={merge_only_n}/{len(PILOT)} → rematch comparator invalid"
            ),
            "claim_allowed": gate == "PASS",
            "all100": "not_run",
        }
    else:
        b12["status"] = "ANNOTATE_PENDING"
        b12["n_case_results"] = n_ready

    payload = {
        "generated_at": _utc(),
        "protocol": "live_option_compat_test_arms_v1",
        "baselines": base,
        "b12": b12,
        "r3": {
            "live_opt_all100": {"opt1": base["all100"]["opt1"], "opt2": base["all100"]["opt2"]},
            "note": "gap_fill already ON in frozen trees",
        },
        "r4_r5": {
            "absent_option": base["absent_official_mapper"],
            "verdict": "REJECT",
        },
    }
    write_report(payload, ANALYSIS / "smoke_live_option")
    print(json.dumps({
        "b12": b12.get("verdict") or b12.get("status"),
        "rematch": (b12.get("rematch") or {}).get("summary"),
        "typed": (b12.get("typed") or {}).get("summary"),
        "n_ready": b12.get("n_case_results"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
