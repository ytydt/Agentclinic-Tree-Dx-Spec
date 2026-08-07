#!/usr/bin/env python3
"""Aggregate Pilot24+Remain76 B12+compat typed option → all100 gate vs compat_parallel."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1"
REMAIN_DIR = ROOT / "logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1"
AT1 = ROOT / "logs/diagnosisarena_d2_m01_v1/at1_compat_v1"
ANALYSIS = ROOT / "analysis/l1_gold_recall_v1/smoke_live_option"

# Gate vs formal compat_parallel rematch
BASE_OPT1 = 0.72
BASE_OPT2 = 0.78
DELTA_AT1 = 0.04
DELTA_AT2_FLOOR = -0.01


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def typed_stats(down: Path) -> dict:
    proj = down / "mapper" / "projections"
    rows = []
    for p in sorted(proj.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        rows.append({
            "case_id": p.stem,
            "option_top1": int(bool(r.get("option_top1"))),
            "option_top2": int(bool(r.get("option_top2"))),
            "option_rr": float(r.get("option_rr") or 0.0),
        })
    n = len(rows)
    if not n:
        return {"n": 0, "opt1": None, "opt2": None, "mrr": None, "rows": []}
    return {
        "n": n,
        "opt1": sum(r["option_top1"] for r in rows) / n,
        "opt2": sum(r["option_top2"] for r in rows) / n,
        "mrr": sum(r["option_rr"] for r in rows) / n,
        "rows": rows,
    }


def merge_only_rate(down: Path) -> dict:
    n = mo = 0
    for p in (down / "case_results").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("error") or not (r.get("l2") or {}).get("final_ranking_labels"):
            continue
        n += 1
        g = (r.get("l2") or {}).get("granularity") or {}
        if (g.get("path") or g.get("branch")) == "merge_only":
            mo += 1
    return {"n": n, "merge_only_n": mo, "rate": (mo / n) if n else None}


def main() -> int:
    pilot = typed_stats(PILOT_DIR)
    remain = typed_stats(REMAIN_DIR)
    if pilot["n"] != 24:
        print(json.dumps({"error": "pilot incomplete", "pilot": pilot["n"]}))
        return 2
    if remain["n"] != 76:
        print(json.dumps({"error": "remain incomplete", "remain": remain["n"]}))
        return 2

    all_rows = pilot["rows"] + remain["rows"]
    n = len(all_rows)
    all100 = {
        "n": n,
        "opt1": sum(r["option_top1"] for r in all_rows) / n,
        "opt2": sum(r["option_top2"] for r in all_rows) / n,
        "mrr": sum(r["option_rr"] for r in all_rows) / n,
    }
    d1 = all100["opt1"] - BASE_OPT1
    d2 = all100["opt2"] - BASE_OPT2
    pass_gate = (d1 >= DELTA_AT1) and (d2 >= DELTA_AT2_FLOOR)
    # Extra honesty: if merge_only dominates, flag
    mo_p = merge_only_rate(PILOT_DIR)
    mo_r = merge_only_rate(REMAIN_DIR)
    mo_all = {
        "n": mo_p["n"] + mo_r["n"],
        "merge_only_n": mo_p["merge_only_n"] + mo_r["merge_only_n"],
    }
    mo_all["rate"] = (
        mo_all["merge_only_n"] / mo_all["n"] if mo_all["n"] else None
    )

    verdict = {
        "pass": bool(pass_gate),
        "set_default_l1_calib_b12": bool(pass_gate),
        "delta_opt1_vs_compat_rematch": round(d1, 4),
        "delta_opt2_vs_compat_rematch": round(d2, 4),
        "gate": f"Δ@1≥{DELTA_AT1} and Δ@2≥{DELTA_AT2_FLOOR} vs compat rematch {BASE_OPT1}/{BASE_OPT2}",
        "reason": (
            f"all100 B12 typed {all100['opt1']:.3f}/{all100['opt2']:.3f} vs "
            f"compat_parallel rematch {BASE_OPT1:.2f}/{BASE_OPT2:.2f}; "
            f"merge_only_rate={mo_all['rate']}"
        ),
        "claim_allowed": bool(pass_gate),
    }

    payload = {
        "generated_at": _utc(),
        "protocol": "b12_compat_typed_all100_v1",
        "baseline_compat_rematch_all100": {"opt1": BASE_OPT1, "opt2": BASE_OPT2},
        "pilot24": {k: pilot[k] for k in ("n", "opt1", "opt2", "mrr")},
        "remain76": {k: remain[k] for k in ("n", "opt1", "opt2", "mrr")},
        "all100": all100,
        "merge_only": {"pilot24": mo_p, "remain76": mo_r, "all100": mo_all},
        "verdict": verdict,
    }
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS / "b12_compat_all100_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# B12+compat all100 live option gate",
        "",
        f"- generated: `{payload['generated_at']}`",
        f"- baseline: compat_parallel rematch **{BASE_OPT1:.2f}/{BASE_OPT2:.2f}**",
        "",
        "| cohort | n | typed @1 | typed @2 | MRR |",
        "|--------|--:|---------:|---------:|----:|",
        f"| Pilot24 | {pilot['n']} | {pilot['opt1']:.3f} | {pilot['opt2']:.3f} | {pilot['mrr']:.3f} |",
        f"| Remain76 | {remain['n']} | {remain['opt1']:.3f} | {remain['opt2']:.3f} | {remain['mrr']:.3f} |",
        f"| **all100** | {all100['n']} | **{all100['opt1']:.3f}** | **{all100['opt2']:.3f}** | {all100['mrr']:.3f} |",
        "",
        f"- Δ@1={d1:+.4f} Δ@2={d2:+.4f}",
        f"- merge_only all100: {mo_all['merge_only_n']}/{mo_all['n']} ({mo_all['rate']:.2%})",
        f"- **GATE: {'PASS' if pass_gate else 'REJECT'}** — {verdict['reason']}",
        f"- set_default_l1_calib_b12=`{verdict['set_default_l1_calib_b12']}`",
        "",
    ]
    (ANALYSIS / "b12_compat_all100_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if remain["n"] == 76 else 1


if __name__ == "__main__":
    raise SystemExit(main())
