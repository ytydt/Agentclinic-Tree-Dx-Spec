#!/usr/bin/env bash
# APHHM-C pilot: DA200 (seq100 + heldout100) and MCR200 (v1 + v2).
# The 200b slices are deliberately held back for confirmation.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
mkdir -p "$LOG"
MASTER="$LOG/aphhm_c_pilot_master.log"
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
  local ec=$?
  echo "### DONE $ds $arm exit=$ec $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena          aphhm_c_v1 c4 "$LOG/aphhm_c_da_seq100.log" &
run diagnosisarena_heldout  aphhm_c_v1 c4 "$LOG/aphhm_c_da_heldout.log" &
run medcasereasoning        aphhm_c_v1 c4 "$LOG/aphhm_c_mcr_v1.log" &
run medcasereasoning_v2     aphhm_c_v1 c4 "$LOG/aphhm_c_mcr_v2.log" &
wait
echo APHHM_C_PILOT200_DONE | tee -a "$MASTER"
