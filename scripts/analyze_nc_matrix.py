#!/usr/bin/env python3
"""NC rematrix accuracy table with llama-fallback rep exclusion.

Contamination signature (OpenRouter error JSON → silent llama-3.3 fallback):
  run log contains "Failed to unpack choices" or "no attribute 'choices'"

Any rep with ≥1 hit is excluded from comparison aggregates (even if 9/9 scored).

Usage:
  python scripts/analyze_nc_matrix.py                  # report
  python scripts/analyze_nc_matrix.py --isolate        # move poisoned JSON → logs/_billing_poisoned/
  python scripts/analyze_nc_matrix.py --out logs/nc_matrix_comparison_clean.txt
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import statistics
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
POISON_DIR = os.path.join(LOGS, "_billing_poisoned")
CASES = 9

FALLBACK_SIG = re.compile(
    r"no attribute 'choices'|Failed to unpack choices", re.I
)

ARMS = [
    "nc_bk_off", "nc_bk_on", "nc_rp_on_bk_off", "nc_rp_on_bk_on",
    "nc_rq_mg", "nc_rq_cc", "nc_rq_mg_cc",
    "nc_n5_detox", "nc_n5_mand", "nc_n5_phase", "nc_n5_full", "nc_n5_rp_full",
    "nc_nrq_mg", "nc_nrq_cc", "nc_nrq_mg_cc",
    "nc_u29_bk", "nc_u29_mand", "nc_u29_clean", "nc_u29_mand_clean", "nc_u29_full",
]

K10_ARMS = {
    "nc_bk_on", "nc_u29_full", "nc_n5_detox", "nc_n5_phase", "nc_rp_on_bk_on",
    "nc_nrq_cc", "nc_u29_mand", "nc_nrq_mg_cc",
}


def _fallback_hits(tag: str) -> int:
    rf = os.path.join(LOGS, f"run_{tag}.out")
    if not os.path.isfile(rf):
        return 0
    n = 0
    with open(rf, encoding="utf-8", errors="replace") as f:
        for line in f:
            if FALLBACK_SIG.search(line):
                n += 1
    return n


def _latest_json(tag: str) -> tuple[str | None, list | None]:
    js = sorted(
        glob.glob(os.path.join(LOGS, f"medbullets_conc_{tag}_*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not js:
        return None, None
    try:
        return js[0], json.load(open(js[0], encoding="utf-8"))
    except Exception:
        return js[0], None


def _rep_acc(recs: list) -> tuple[float | None, int, int]:
    ok = sum(1 for r in recs if r.get("status") == "OK")
    sc = sum(1 for r in recs if r.get("status") in ("OK", "XX"))
    return (ok / sc if sc else None, ok, sc)


def scan_contaminated(prefix: str = "nc_") -> list[dict]:
    tags: set[str] = set()
    for f in glob.glob(os.path.join(LOGS, f"run_{prefix}*.out")):
        tag = os.path.basename(f).replace("run_", "").replace(".out", "")
        if _fallback_hits(tag):
            tags.add(tag)
    rows = []
    for tag in sorted(tags):
        parts = tag.rsplit("_", 1)
        arm = parts[0] if len(parts) == 2 and parts[1].isdigit() else tag
        rep = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
        hits = _fallback_hits(tag)
        jpath, recs = _latest_json(tag)
        acc, ok, sc = _rep_acc(recs) if recs else (None, 0, 0)
        rows.append(
            {
                "tag": tag,
                "arm": arm,
                "rep": rep,
                "hits": hits,
                "acc": acc,
                "ok": ok,
                "scored": sc,
                "json_path": jpath,
                "complete": sc >= CASES,
            }
        )
    return rows


def isolate_contaminated(rows: list[dict]) -> list[str]:
    os.makedirs(POISON_DIR, exist_ok=True)
    actions: list[str] = []
    for r in rows:
        tag = r["tag"]
        for f in glob.glob(os.path.join(LOGS, f"medbullets_conc_{tag}_*.json")):
            dst = os.path.join(POISON_DIR, os.path.basename(f))
            if os.path.abspath(f) == os.path.abspath(dst):
                continue
            shutil.move(f, dst)
            actions.append(f"MOVED {os.path.basename(f)} → _billing_poisoned/")
        sd = os.path.join(LOGS, "_case_results", tag)
        if os.path.isdir(sd):
            for f in glob.glob(os.path.join(sd, "case_*.json")):
                dst = os.path.join(POISON_DIR, f"{tag}_{os.path.basename(f)}")
                shutil.move(f, dst)
                actions.append(f"MOVED sidecar {tag}/{os.path.basename(f)}")
    return actions


def _arm_stats(arm: str, max_rep: int = 10) -> dict:
    byrep: dict[int, dict] = {}
    for rep in range(1, max_rep + 1):
        tag = f"{arm}_{rep}"
        hits = _fallback_hits(tag)
        _, recs = _latest_json(tag)
        if not recs:
            continue
        acc, ok, sc = _rep_acc(recs)
        if sc < CASES:
            continue
        byrep[rep] = {"acc": acc, "hits": hits, "ok": ok, "scored": sc}
    excluded = sorted(r for r, v in byrep.items() if v["hits"] > 0)
    clean = {r: v for r, v in byrep.items() if v["hits"] == 0}
    all_accs = [v["acc"] for v in byrep.values()]
    clean_accs = [v["acc"] for v in clean.values()]

    def _agg(accs: list[float]) -> tuple[str, str]:
        if not accs:
            return "n/a", "n/a"
        m = statistics.mean(accs) * 100
        sd = statistics.pstdev(accs) * 100 if len(accs) > 1 else 0.0
        return f"{m:.1f}%", f"{sd:.1f}"

    ma, sd = _agg(clean_accs)
    ma_all, sd_all = _agg(all_accs)
    return {
        "arm": arm,
        "n_clean": len(clean_accs),
        "n_all": len(all_accs),
        "mean_clean": ma,
        "sd_clean": sd,
        "mean_all": ma_all,
        "sd_all": sd_all,
        "per_rep_clean": [
            f"{int(v['acc'] * 100)}" for _, v in sorted(clean.items())
        ],
        "excluded": excluded,
        "incomplete_excluded": excluded,  # alias
    }


def build_report(arms: list[str] | None = None) -> str:
    arms = arms or ARMS
    contam = scan_contaminated("nc_")
    lines: list[str] = []
    w = lines.append
    w(f"=== NC 配置对比（排除 llama fallback 污染 rep） @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    w("")
    w("污染判定：run_*.out 含 Failed to unpack / no attribute 'choices'（API 错误 → llama-3.3 静默兜底）")
    w(f"污染 rep 数：{len(contam)}")
    w("")
    w(f"{'tag':28} {'hits':>5} {'acc':>7} {'scored':>8} {'complete':>8}")
    for r in contam:
        accs = f"{r['acc'] * 100:.0f}%" if r["acc"] is not None else "n/a"
        w(
            f"{r['tag']:28} {r['hits']:5} {accs:>7} "
            f"{r['scored']}/9{'':>4} {'yes' if r['complete'] else 'no':>8}"
        )
    w("")
    w("--- 全矩阵（clean reps only）---")
    w(f"{'arm':22} {'K':>3} {'acc':>7} {'sd':>5}  perRep%  excluded")
    for arm in arms:
        st = _arm_stats(arm)
        ex = ",".join(map(str, st["excluded"])) if st["excluded"] else "-"
        if st["n_clean"]:
            w(
                f"{st['arm']:22} {st['n_clean']:3} {st['mean_clean']:>7} "
                f"{st['sd_clean']:5}  {st['per_rep_clean']}  ex={ex}"
            )
        elif st["n_all"]:
            w(f"{st['arm']:22}  ALL CONTAMINATED (n={st['n_all']})  ex={ex}")
        else:
            w(f"{st['arm']:22}  (no complete reps)")
    w("")
    w("--- 对照：含污染 rep（deprecated，勿用于判读）---")
    w(f"{'arm':22} {'K':>3} {'acc':>7} {'sd':>5}  excluded")
    for arm in arms:
        st = _arm_stats(arm)
        ex = ",".join(map(str, st["excluded"])) if st["excluded"] else "-"
        if st["n_all"]:
            w(
                f"{st['arm']:22} {st['n_all']:3} {st['mean_all']:>7} "
                f"{st['sd_all']:5}  ex={ex}"
            )
    w("")
    w("--- K5 vs K6-10（K10 扩展臂，clean only）---")
    w(f"{'arm':22} {'K5 acc':>8} {'K610 acc':>9} {'Δ pp':>6}  ex_K5  ex_K610")
    for arm in sorted(K10_ARMS):
        st = _arm_stats(arm)
        k5 = []
        k610 = []
        ex5, ex610 = [], []
        for rep in range(1, 6):
            tag = f"{arm}_{rep}"
            hits = _fallback_hits(tag)
            _, recs = _latest_json(tag)
            if not recs:
                continue
            acc, _, sc = _rep_acc(recs)
            if sc < CASES:
                continue
            if hits:
                ex5.append(rep)
                continue
            k5.append(acc)
        for rep in range(6, 11):
            tag = f"{arm}_{rep}"
            hits = _fallback_hits(tag)
            _, recs = _latest_json(tag)
            if not recs:
                continue
            acc, _, sc = _rep_acc(recs)
            if sc < CASES:
                continue
            if hits:
                ex610.append(rep)
                continue
            k610.append(acc)
        m5 = statistics.mean(k5) * 100 if k5 else float("nan")
        m6 = statistics.mean(k610) * 100 if k610 else float("nan")
        delta = m6 - m5 if k5 and k610 else float("nan")
        w(
            f"{arm:22} {m5:7.1f}%({len(k5)}) {m6:8.1f}%({len(k610)}) "
            f"{delta:+5.1f}  ex5={ex5 or '-'} ex610={ex610 or '-'}"
        )
    w("")
    w("需重跑 tag（污染或未完成）：")
    rerun = set(r["tag"] for r in contam)
    for arm in arms:
        for rep in range(1, 11):
            tag = f"{arm}_{rep}"
            _, recs = _latest_json(tag)
            sc = sum(1 for x in (recs or []) if x.get("status") in ("OK", "XX"))
            if sc < CASES and _fallback_hits(tag) == 0:
                # incomplete but not fallback — gap fill handles separately
                pass
            if tag in rerun or (recs and sc < CASES and _fallback_hits(tag)):
                rerun.add(tag)
    for arm in arms:
        for rep in range(1, 11):
            tag = f"{arm}_{rep}"
            if _fallback_hits(tag):
                rerun.add(tag)
    for tag in sorted(rerun):
        w(f"  {tag}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--isolate", action="store_true", help="move poisoned JSON/sidecars")
    ap.add_argument("--out", default="", help="write report to file")
    ap.add_argument("--manifest", default="", help="JSON manifest path")
    args = ap.parse_args()

    contam = scan_contaminated("nc_")
    actions: list[str] = []
    if args.isolate:
        actions = isolate_contaminated(contam)

    report = build_report()
    print(report)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nreport → {args.out}")

    manifest_path = args.manifest or os.path.join(
        POISON_DIR, f"fallback_exclude_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    os.makedirs(POISON_DIR, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(
            {
                "scanned_at": datetime.now().isoformat(),
                "signature": "Failed to unpack choices / no attribute 'choices'",
                "contaminated": contam,
                "exclude_tags": [r["tag"] for r in contam],
                "isolate_actions": actions,
            },
            mf,
            indent=2,
            ensure_ascii=False,
        )
    print(f"manifest → {manifest_path}")


if __name__ == "__main__":
    main()
