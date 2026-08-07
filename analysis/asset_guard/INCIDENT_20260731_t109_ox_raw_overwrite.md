# Incident: `ablations_c2_ox_raw.json` overwritten by STF suite

**When:** 2026-07-31 ~16:44 (after T1-09 STF eval)

**Cause:** `run_c2_ox_state_suite.py --arms stf` fell through to the default
output path `runs/paper_v1/ablations_c2_ox_raw.json` because the T1-07
isolation branch only covered `{ab29,ab30,ab31}`.

**Impact:** Published C2 OX factorial JSON was replaced with a one-arm STF
document. Arm summaries on disk (`c2_ab13/14/17/19_v1/.../summary.json`)
were untouched.

**Recovery:**
1. Polluted content moved to `runs/paper_v1/ablations_c2_t109_stf.json`
2. `ablations_c2_ox_raw.json` restored by re-reading the four published arm
   summaries (AB13/14/17/19) + M00 readonly micro
3. Suite output routing patched so `stf` → `ablations_c2_t109_stf.json`

**Verify:** M00 / DA / C3 published summaries still matched the mid-campaign
snapshot; only ab29 cache churn + second-judge cache + this file had changed.
