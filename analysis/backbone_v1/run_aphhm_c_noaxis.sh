#!/usr/bin/env bash
# Axis factor. Both arms keep the structural base (registry, ledger, append-only
# lifecycle) and the clean selector, and both use K=10 like the best conditioned
# arm (aphhm_c_k10_v1), so the only variable is axis conditioning.
#   nocond = C2 still runs; C3 is simply not told about families/quotas
#   noaxis = C2 is dropped entirely, removing one fixed call
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_noaxis_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" am="$3" logfile="$4"
  echo "### START $ds $arm axis=$am $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode c4_selector_clean --concept-contract noaxis --axis-mode "$am" \
      --unique-budget 10 --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode c4_selector_clean --concept-contract noaxis --axis-mode "$am" \
      --unique-budget 10 --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for spec in "aphhm_c_nocond_v1 unconditioned" "aphhm_c_noaxis_v1 off"; do
  set -- $spec
  arm="$1"; am="$2"
  run diagnosisarena         "$arm" "$am" "$LOG/${arm}_da_seq100.log" &
  run diagnosisarena_heldout "$arm" "$am" "$LOG/${arm}_da_heldout.log" &
  run medcasereasoning       "$arm" "$am" "$LOG/${arm}_mcr_v1.log" &
  run medcasereasoning_v2    "$arm" "$am" "$LOG/${arm}_mcr_v2.log" &
done
wait
echo APHHM_C_NOAXIS_DONE | tee -a "$MASTER"
