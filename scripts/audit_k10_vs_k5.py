#!/usr/bin/env python3
"""Audit K6-10 vs K5 for config drift and cross-run contamination."""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
from collections import Counter, defaultdict

CASES = 9
CASE_IDX = [1, 9, 13, 14, 17, 18, 22, 23, 24]

K10_ARMS = {
    "nc_bk_on": "--fix-a2 --fix-b --branch-knowledge",
    "nc_u29_full": (
        "--fix-a2 --fix-b --branch-knowledge --mandatory-kb-branches "
        "--lr-clean --phase-subaxis"
    ),
    "nc_n5_detox": "--fix-a2 --fix-b --branch-knowledge --lr-detox",
    "nc_n5_phase": "--fix-a2 --fix-b --branch-knowledge --phase-subaxis",
    "nc_rp_on_bk_on": "--fix-a2 --fix-b --branch-knowledge --retrieval-priority",
}

CFG_RE = re.compile(r"CFG tag='([^']+)'(.+)")
LAUNCH_RE = re.compile(r"launch (\S+) on .+ flags='([^']+)'")
RESUME_RE = re.compile(r"resume.*from|inheriting|sidecars\+final|re-running", re.I)


def _latest_json(tag: str) -> dict | None:
    js = sorted(
        glob.glob(f"logs/medbullets_conc_{tag}_*.json"),
        key=os.path.getmtime,
        reverse=True,
    )
    if not js:
        return None
    return json.load(open(js[0], encoding="utf-8"))


def _acc(d: list) -> float | None:
    sc = sum(1 for r in d if r.get("status") in ("OK", "XX"))
    if sc < CASES or len(d) < CASES:
        return None
    return sum(1 for r in d if r.get("status") == "OK") / CASES


def _parse_run_log(tag: str) -> dict:
    path = f"logs/run_{tag}.out"
    info: dict = {"launch_flags": [], "cfg_lines": [], "no_secondary_cache": None}
    if not os.path.isfile(path):
        return info
    text = open(path, encoding="utf-8", errors="replace").read()
    for m in LAUNCH_RE.finditer(text):
        if m.group(1) == tag:
            info["launch_flags"].append(m.group(2))
    info["no_secondary_cache"] = all(
        "--no-secondary-cache" in f for f in info["launch_flags"]
    ) if info["launch_flags"] else None
    for line in text.splitlines():
        m = CFG_RE.search(line)
        if m and m.group(1) == tag:
            info["cfg_lines"].append(m.group(2).strip())
    info["unique_cfg"] = list(dict.fromkeys(info["cfg_lines"]))
    return info


def _sidecar_tag_check(tag: str) -> list[str]:
    issues = []
    sd = f"logs/_case_results/{tag}"
    if not os.path.isdir(sd):
        return issues
    for f in glob.glob(os.path.join(sd, "case_*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            issues.append(f"{os.path.basename(f)}: unreadable")
            continue
        st = d.get("tag") or d.get("run_tag")
        if st and st != tag:
            issues.append(f"{os.path.basename(f)}: tag={st}!={tag}")
    return issues


def _case_ok_matrix(arm: str) -> dict[int, dict[str, int]]:
    """case_id -> {'k5_ok': n, 'k5_n': n, 'k610_ok': n, 'k610_n': n}"""
    mat: dict[int, dict[str, int]] = {
        c: {"k5_ok": 0, "k5_n": 0, "k610_ok": 0, "k610_n": 0} for c in CASE_IDX
    }
    for rep in range(1, 11):
        tag = f"{arm}_{rep}"
        d = _latest_json(tag)
        if not d:
            continue
        bucket = "k5" if rep <= 5 else "k610"
        for row in d:
            cid = row.get("idx")
            if cid is None:
                continue
            cid = int(cid)
            if cid not in mat:
                continue
            mat[cid][f"{bucket}_n"] += 1
            if row.get("status") == "OK":
                mat[cid][f"{bucket}_ok"] += 1
    return mat


def main() -> None:
    print("=" * 72)
    print("K6-10 vs K5 审计：配置一致性 + 跨运行污染")
    print("=" * 72)

    config_issues: list[str] = []
    sidecar_issues: list[str] = []
    status_issues: list[str] = []

    for arm, expected_flags in K10_ARMS.items():
        print(f"\n── {arm} ──")
        k5_accs, k610_accs = [], []
        flag_sets_k5, flag_sets_k610 = set(), set()
        cfg_sets_k5, cfg_sets_k610 = set(), set()
        nc_k5, nc_k610 = [], []

        for rep in range(1, 11):
            tag = f"{arm}_{rep}"
            d = _latest_json(tag)
            acc = _acc(d) if d else None
            if acc is not None:
                (k5_accs if rep <= 5 else k610_accs).append(acc)
            if d:
                bad = [r.get("status") for r in d if r.get("status") not in ("OK", "XX")]
                if bad:
                    status_issues.append(f"{tag}: non-scored statuses {Counter(bad)}")
            ri = _parse_run_log(tag)
            fs = tuple(ri.get("launch_flags") or [])
            if fs:
                (flag_sets_k5 if rep <= 5 else flag_sets_k610).add(fs[-1])
            if ri.get("no_secondary_cache") is False:
                config_issues.append(f"{tag}: launch missing --no-secondary-cache")
            elif ri.get("no_secondary_cache") is None and d:
                config_issues.append(f"{tag}: no launch line in run log (orphan?)")
            cfgs = ri.get("unique_cfg") or []
            if cfgs:
                (cfg_sets_k5 if rep <= 5 else cfg_sets_k610).add(cfgs[-1])
            if ri.get("no_secondary_cache") is not None:
                (nc_k5 if rep <= 5 else nc_k610).append(ri["no_secondary_cache"])
            sc = _sidecar_tag_check(tag)
            sidecar_issues.extend(f"{tag}: {x}" for x in sc)

        if k5_accs:
            m5 = statistics.mean(k5_accs) * 100
        else:
            m5 = float("nan")
        if k610_accs:
            m6 = statistics.mean(k610_accs) * 100
        else:
            m6 = float("nan")
        print(f"  准确率  K5={m5:.1f}% (n={len(k5_accs)})  K6-10={m6:.1f}% (n={len(k610_accs)})  Δ={m6-m5:+.1f}pp")

        if len(flag_sets_k5) > 1:
            config_issues.append(f"{arm}: K5 launch flags differ across reps: {len(flag_sets_k5)} variants")
        if len(flag_sets_k610) > 1:
            config_issues.append(f"{arm}: K6-10 launch flags differ: {len(flag_sets_k610)} variants")
        if flag_sets_k5 and flag_sets_k610 and flag_sets_k5 != flag_sets_k610:
            config_issues.append(f"{arm}: K5 vs K6-10 launch flags MISMATCH")
            print(f"  ⚠ K5 flags sample:   {next(iter(flag_sets_k5))[:80]}…")
            print(f"  ⚠ K610 flags sample: {next(iter(flag_sets_k610))[:80]}…")
        else:
            print(f"  ✓ launch flags 一致 ({len(flag_sets_k5 | flag_sets_k610)} variant)")

        if cfg_sets_k5 != cfg_sets_k610 and cfg_sets_k5 and cfg_sets_k610:
            config_issues.append(f"{arm}: CFG dict differs K5 vs K6-10")
            print(f"  ⚠ CFG K5:   {next(iter(cfg_sets_k5))[:90]}")
            print(f"  ⚠ CFG K610: {next(iter(cfg_sets_k610))[:90]}")
        elif len(cfg_sets_k5 | cfg_sets_k610) == 1:
            print(f"  ✓ CFG 一致")
        else:
            print(f"  CFG variants: K5={len(cfg_sets_k5)} K610={len(cfg_sets_k610)}")

        # per-case OK rate shift
        mat = _case_ok_matrix(arm)
        print("  逐题 OK 率 (K5 → K6-10):")
        shifts = []
        for cid in CASE_IDX:
            k5n, k5ok = mat[cid]["k5_n"], mat[cid]["k5_ok"]
            k6n, k6ok = mat[cid]["k610_n"], mat[cid]["k610_ok"]
            if k5n and k6n:
                r5, r6 = k5ok / k5n, k6ok / k6n
                shifts.append((cid, r5, r6, r6 - r5))
        shifts.sort(key=lambda x: x[3])
        for cid, r5, r6, d in shifts:
            mark = " ↓" if d < -0.2 else (" ↑" if d > 0.2 else "")
            print(f"    case {cid:2d}: {r5*100:4.0f}% ({mat[cid]['k5_ok']}/{mat[cid]['k5_n']}) → "
                  f"{r6*100:4.0f}% ({mat[cid]['k610_ok']}/{mat[cid]['k610_n']}){mark}")

    print("\n" + "=" * 72)
    print("汇总")
    print("=" * 72)
    if config_issues:
        print(f"\n配置问题 ({len(config_issues)}):")
        for x in config_issues:
            print(f"  • {x}")
    else:
        print("\n✓ 未发现 K5 vs K6-10 launch flags / no-secondary-cache 不一致")

    if sidecar_issues:
        print(f"\nSidecar 污染 ({len(sidecar_issues)}):")
        for x in sidecar_issues[:20]:
            print(f"  • {x}")
    else:
        print("\n✓ sidecar tag 无跨 rep 污染")

    if status_issues:
        print(f"\n非 OK/XX 状态 ({len(status_issues)}):")
        for x in status_issues:
            print(f"  • {x}")
    else:
        print("\n✓ 所有完成 rep 均为 OK/XX 打分（无 PROTO/欠费残留）")

    # Statistical null: binomial SE for 9-case accuracy
    print("\n统计注：9 题/rep、K=5 vs K=5 的均值差 ~7pp 可在随机波动内；")
    print("      若配置一致且无 PROTO，K6-10 偏低更可能为方差而非系统性降级。")


if __name__ == "__main__":
    main()
