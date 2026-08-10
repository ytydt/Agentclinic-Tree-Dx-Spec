#!/usr/bin/env bash
# Two attribution arms over the SAME cache-seeded C1-C4 state as aphhm_c_v1:
#   wide = shortlist is every active concept (score no longer prunes)
#   rich = wide + generation-support evidence in the selector notes
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_selrank_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm $mode $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for spec in "aphhm_c_wide_v1 c4_selector_wide wide" "aphhm_c_rich_v1 c4_selector_rich rich"; do
  set -- $spec
  arm="$1"; mode="$2"; tag="$3"
  run diagnosisarena         "$arm" "$mode" "$LOG/aphhm_c_${tag}_da_seq100.log" &
  run diagnosisarena_heldout "$arm" "$mode" "$LOG/aphhm_c_${tag}_da_heldout.log" &
  run medcasereasoning       "$arm" "$mode" "$LOG/aphhm_c_${tag}_mcr_v1.log" &
  run medcasereasoning_v2    "$arm" "$mode" "$LOG/aphhm_c_${tag}_mcr_v2.log" &
done
wait
echo APHHM_C_SELRANK_DONE | tee -a "$MASTER"
