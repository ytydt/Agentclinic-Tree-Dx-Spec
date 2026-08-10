#!/usr/bin/env bash
# Power run. Collapse3c holds the highest MCR task in the table (0.2900) but is
# only directionally ahead of MAC / Forest / Lite / B07 at n=200 (p=0.16-0.48).
# The 200b slices carry Forest, IMPC and Lite, so extending onto them doubles n
# for exactly the comparisons the claim rests on.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_collapse3c_200b_master.log"
: >"$MASTER"

run() {
  local ds="$1" logfile="$2"
  echo "### START $ds $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm aphhm_c_collapse3c_v1 \
      --mode c4_selector_candev_nomatrix --concept-contract evid_commit --axis-mode off \
      --unique-budget 10 --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm aphhm_c_collapse3c_v1 \
      --mode c4_selector_candev_nomatrix --concept-contract evid_commit --axis-mode off \
      --unique-budget 10 --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena_heldout200b "$LOG/aphhm_c_collapse3c_v1_da_200b.log" &
run medcasereasoning_200b      "$LOG/aphhm_c_collapse3c_v1_mcr_200b.log" &
wait
echo APHHM_C_COLLAPSE3C_200B_DONE | tee -a "$MASTER"
