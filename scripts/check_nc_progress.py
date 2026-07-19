#!/usr/bin/env python3
"""Quick progress report for nc_ rematrix."""
import glob, json, os, re, statistics
from collections import defaultdict

CASES = 9
K = 5
ARMS = [
    "nc_bk_off", "nc_bk_on", "nc_rp_on_bk_off", "nc_rp_on_bk_on",
    "nc_rq_mg", "nc_rq_cc", "nc_rq_mg_cc",
    "nc_n5_detox", "nc_n5_mand", "nc_n5_phase", "nc_n5_full", "nc_n5_rp_full",
    "nc_nrq_mg", "nc_nrq_cc", "nc_nrq_mg_cc",
    "nc_u29_bk", "nc_u29_mand", "nc_u29_clean", "nc_u29_mand_clean", "nc_u29_full",
]

# sidecar progress per rep tag
sidecar = defaultdict(lambda: {"scored": 0, "files": 0})
for f in glob.glob("logs/_case_results/nc_*/case_*.json"):
    tag = os.path.basename(os.path.dirname(f))
    sidecar[tag]["files"] += 1
    try:
        st = json.load(open(f)).get("status")
        if st in ("OK", "XX"):
            sidecar[tag]["scored"] += 1
    except Exception:
        pass

# final JSON done (9/9)
done_reps = defaultdict(set)
for f in glob.glob("logs/medbullets_conc_nc_*.json"):
    m = re.match(r"medbullets_conc_(nc_.+?)_(\d+)_\d{8}_\d{6}\.json", os.path.basename(f))
    if not m:
        continue
    arm, rep = m.group(1), int(m.group(2))
    try:
        d = json.load(open(f))
    except Exception:
        continue
    scored = sum(1 for r in d if r.get("status") in ("OK", "XX"))
    if scored >= CASES and len(d) >= CASES:
        done_reps[arm].add(rep)

print(f"{'臂':<22} {'完成rep':>8} {'进行中(有sidecar)':>16} {'sidecar题':>10}")
total_done = 0
in_prog = 0
for arm in ARMS:
    dr = len(done_reps.get(arm, set()))
    total_done += dr
    # reps with sidecar but not done
    active = []
    sc_total = 0
    for rep in range(1, K + 1):
        tag = f"{arm}_{rep}"
        if rep in done_reps.get(arm, set()):
            continue
        s = sidecar.get(tag, {"scored": 0, "files": 0})
        if s["files"] > 0:
            active.append(f"{rep}({s['scored']}/9)")
            sc_total += s["scored"]
    if dr or active:
        in_prog += len(active)
        act_s = ",".join(active) if active else "-"
        print(f"{arm:<22} {dr:>3}/{K:<4} {act_s:>16} {sc_total:>10}")

print(f"\n总完成: {total_done}/100 rep ({total_done}%)")
print(f"进行中(有 sidecar 未完成): {in_prog} rep")

# timing by arm from sidecars
dts = []
for f in glob.glob("logs/_case_results/nc_*/case_*.json"):
    try:
        dt = json.load(open(f)).get("dt")
        if dt:
            dts.append(float(dt))
    except Exception:
        pass
if dts:
    dts.sort()
    print(f"\n单题耗时(n={len(dts)}): min={dts[0]:.0f}s med={statistics.median(dts):.0f}s "
          f"p90={dts[int(len(dts)*0.9)]:.0f}s max={dts[-1]:.0f}s")
