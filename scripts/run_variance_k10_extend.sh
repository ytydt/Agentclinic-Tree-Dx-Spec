#!/usr/bin/env bash
# §31.9 Variance-reduction extension: +5 reps (rep 6–10), ALL no-cache.
#
# All arms use --no-secondary-cache and nc_ tags so rep 6–10 join the §30
# no-cache family and never mix cache regimes with cached rep 1–5.
#
# Arms (original selection criteria unchanged):
#   nc_bk_on        (was bk_on ≥40% cached)
#   nc_u29_full     (was u29_full ≥40% cached)
#   nc_n5_detox     (nc rematrix ≥40%)
#   nc_n5_phase     (nominated)
#   nc_rp_on_bk_on  (nominated)
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

if pgrep -f "run_nocache_rematrix.sh" >/dev/null 2>&1; then
  echo "[$(date +%H:%M:%S)] waiting for run_nocache_rematrix.sh to finish…"
  for _ in $(seq 1 5760); do
    if grep -q "NO-CACHE rematrix COMPLETE" logs/run_nocache_rematrix_driver.out 2>/dev/null; then
      echo "[$(date +%H:%M:%S)] nc rematrix done — starting K=10 extension."
      break
    fi
    if ! pgrep -f "run_nocache_rematrix.sh" >/dev/null 2>&1; then
      echo "[$(date +%H:%M:%S)] rematrix driver exited (check logs); proceeding."
      break
    fi
    sleep 30
  done
fi

export EXTRA_FLAGS="--no-secondary-cache"
export CPU_SLOTS="${CPU_SLOTS:-3}"
source scripts/run_lib.sh

BK="--fix-a2 --fix-b --branch-knowledge"
expand () {
  local base="$1" flags="$2"
  for k in $(seq 6 10); do echo "${base}_${k}|${flags}"; done
}

JOBS=()
while IFS= read -r j; do JOBS+=("$j"); done < <(
  expand nc_bk_on        "$BK"
  expand nc_u29_full     "$BK --mandatory-kb-branches --lr-clean --phase-subaxis"
  expand nc_n5_detox     "$BK --lr-detox"
  expand nc_n5_phase     "$BK --phase-subaxis"
  expand nc_rp_on_bk_on  "$BK --retrieval-priority"
)

echo "[$(date +%H:%M:%S)] ===== §31.9 variance K=10 extension (ALL no-cache): ${#JOBS[@]} reps ====="
run_reps "${JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== §31.9 variance K=10 extension COMPLETE ====="
