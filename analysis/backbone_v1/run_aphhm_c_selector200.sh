#!/usr/bin/env bash
# Ablation: identical C1-C4 (cache-seeded from aphhm_c_v1), only the final
# ordering differs. Isolates the cost of the deterministic-rank constraint.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_sel_master.log"
: >"$MASTER"

run() {
  local ds="$1" logfile="$2"
  echo "### START $ds aphhm_c_sel_v1 $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm aphhm_c_sel_v1 \
      --mode c4_selector --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm aphhm_c_sel_v1 \
      --mode c4_selector --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena         "$LOG/aphhm_c_sel_da_seq100.log" &
run diagnosisarena_heldout "$LOG/aphhm_c_sel_da_heldout.log" &
run medcasereasoning       "$LOG/aphhm_c_sel_mcr_v1.log" &
run medcasereasoning_v2    "$LOG/aphhm_c_sel_mcr_v2.log" &
wait
echo APHHM_C_SELECTOR200_DONE | tee -a "$MASTER"
