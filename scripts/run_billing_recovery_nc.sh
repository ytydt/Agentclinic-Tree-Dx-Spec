#!/usr/bin/env bash
# Re-run nc_ reps contaminated by OpenRouter billing outage (§26.10 / §30).
# 1) scan + isolate poison JSON / PROTO sidecars → logs/_billing_poisoned/
# 2) resume only missing/contaminated cases (--no-secondary-cache)
# Skips reps still owned by an active driver (k10/batch2/rematrix/gap_fill).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

export EXTRA_FLAGS="--no-secondary-cache"
export CPU_SLOTS="${CPU_SLOTS:-2}"
source scripts/run_lib.sh

DRIVER_LOG="logs/run_billing_recovery_nc_driver.out"

_skip_tag() {
  local tag="$1"
  python3 - "$tag" <<'PY'
import subprocess, re, sys
tag = sys.argv[1]
# running eval
out = subprocess.run(["pgrep", "-af", "eval_pipeline_medbullets"], capture_output=True, text=True).stdout
for line in out.splitlines():
    m = re.search(r"--tag\s+(\S+)", line)
    if m and m.group(1) == tag:
        print("running")
        sys.exit(0)
# driver-owned (same logic as scan_nc_gaps driver_pending)
import importlib.util
spec = importlib.util.spec_from_file_location("sg", "scripts/scan_nc_gaps.py")
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)
running = sg._running_tags()
pending = sg._driver_pending_tags(running)
if tag in pending:
    print(f"driver_pending:{pending[tag]}")
    sys.exit(0)
sys.exit(1)
PY
}

echo "[$(date +%H:%M:%S)] ===== billing recovery nc_: scan + isolate =====" | tee -a "$DRIVER_LOG"
python3 scripts/scan_billing_pollution.py --prefix nc_ --isolate 2>&1 | tee -a "$DRIVER_LOG"

JOBS=()
while IFS='|' read -r tag flags; do
  [ -z "$tag" ] && continue
  if reason=$(_skip_tag "$tag"); then
    echo "[$(date +%H:%M:%S)] SKIP ${tag} (${reason})" | tee -a "$DRIVER_LOG"
    continue
  fi
  JOBS+=("${tag}|${flags}")
  echo "[$(date +%H:%M:%S)] billing job: ${tag}" | tee -a "$DRIVER_LOG"
done < <(python3 scripts/scan_billing_pollution.py --prefix nc_ --jobs)

if [ "${#JOBS[@]}" -eq 0 ]; then
  echo "[$(date +%H:%M:%S)] no billable nc_ reps to recover (all clean or driver-owned)" | tee -a "$DRIVER_LOG"
  exit 0
fi

echo "[$(date +%H:%M:%S)] ===== billing recovery nc_: ${#JOBS[@]} rep(s) =====" | tee -a "$DRIVER_LOG"
run_reps "${JOBS[@]}" 2>&1 | tee -a "$DRIVER_LOG"
echo "[$(date +%H:%M:%S)] ===== billing recovery nc_ COMPLETE =====" | tee -a "$DRIVER_LOG"
