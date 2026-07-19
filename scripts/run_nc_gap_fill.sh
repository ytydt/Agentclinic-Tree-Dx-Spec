#!/usr/bin/env bash
# Watcher: fill incomplete nc_ reps abandoned by other drivers (PERSISTENT FAIL /
# ACCEPT PARTIAL / post-driver leftovers). Skips reps still queued or auto-REQUEUE'd
# by an active k10/rematrix/gap_fill driver. Uses --resume; --no-secondary-cache.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

export EXTRA_FLAGS="--no-secondary-cache"
export CPU_SLOTS="${CPU_SLOTS:-3}"
source scripts/run_lib.sh

POLL="${GAP_FILL_POLL:-60}"
ONCE=0
[[ "${1:-}" == "--once" ]] && ONCE=1

_collect_jobs() {
  JOBS=()
  while IFS='|' read -r tag flags reason; do
    [[ "$tag" == \#* ]] && continue
    [ -z "$tag" ] && continue
    JOBS+=("${tag}|${flags}")
    echo "  gap: ${tag}  (${reason})"
  done < <(python3 scripts/scan_nc_gaps.py 2>&1 | rg -v '^# ')
}

while :; do
  JOBS=()
  _collect_jobs

  if [ "${#JOBS[@]}" -eq 0 ]; then
    active=$(python3 scripts/scan_nc_gaps.py --drivers-active)
    if [ "$ONCE" -eq 1 ] || [ "$active" -eq 0 ]; then
      echo "[$(date +%H:%M:%S)] no fillable gaps (drivers_active=${active}) — exit."
      break
    fi
    echo "[$(date +%H:%M:%S)] no fillable gaps; ${active} rep(s) still owned by active drivers — poll ${POLL}s"
    sleep "$POLL"
    continue
  fi

  echo "[$(date +%H:%M:%S)] ===== nc_ gap fill batch: ${#JOBS[@]} rep(s) ====="
  run_reps "${JOBS[@]}"
  echo "[$(date +%H:%M:%S)] ===== nc_ gap fill batch done ====="

  if [ "$ONCE" -eq 1 ]; then
    break
  fi
  sleep 5
done

echo "[$(date +%H:%M:%S)] ===== nc_ gap fill watcher exit ====="
