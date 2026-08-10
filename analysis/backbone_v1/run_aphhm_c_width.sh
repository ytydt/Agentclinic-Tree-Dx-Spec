#!/usr/bin/env bash
# Candidate-width curve. All three arms share the v2 (budget-relative) C3
# contract and the clean selector, so the only thing that varies is how many
# unique concepts the pool is allowed to hold. C1/C2 come from the seeded cache.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_width_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" k="$3" logfile="$4"
  echo "### START $ds $arm K=$k $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode c4_selector_clean --concept-contract v2 --unique-budget "$k" \
      --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode c4_selector_clean --concept-contract v2 --unique-budget "$k" \
      --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for spec in "aphhm_c_k10_v1 10" "aphhm_c_k6_v1 6" "aphhm_c_k4_v1 4"; do
  set -- $spec
  arm="$1"; k="$2"
  run diagnosisarena         "$arm" "$k" "$LOG/${arm}_da_seq100.log" &
  run diagnosisarena_heldout "$arm" "$k" "$LOG/${arm}_da_heldout.log" &
  run medcasereasoning       "$arm" "$k" "$LOG/${arm}_mcr_v1.log" &
  run medcasereasoning_v2    "$arm" "$k" "$LOG/${arm}_mcr_v2.log" &
done
wait
echo APHHM_C_WIDTH_DONE | tee -a "$MASTER"
