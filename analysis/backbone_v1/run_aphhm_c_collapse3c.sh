#!/usr/bin/env bash
# The slot-efficiency diagnostic found that our extra slots go to generic
# differential entries (commonness 3.6-3.8, singleton share 0.40-0.44) while the
# baselines spend theirs on the case-specific rare entity (2.45-2.69, 0.47-0.50).
# This arm tests the commitment contract: candidates must be driven by findings
# that are unusual for them, generic completeness entries are banned, and at most
# 2 candidates may share a family. Same 3-call shape as Collapse3w.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_collapse3c_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm mode=$mode $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode "$mode" --concept-contract evid_commit --axis-mode off \
      --unique-budget 10 --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode "$mode" --concept-contract evid_commit --axis-mode off \
      --unique-budget 10 --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for spec in "aphhm_c_collapse3c_v1 c4_selector_candev_nomatrix"; do
  set -- $spec
  arm="$1"; mode="$2"
  run diagnosisarena         "$arm" "$mode" "$LOG/${arm}_da_seq100.log" &
  run diagnosisarena_heldout "$arm" "$mode" "$LOG/${arm}_da_heldout.log" &
  run medcasereasoning       "$arm" "$mode" "$LOG/${arm}_mcr_v1.log" &
  run medcasereasoning_v2    "$arm" "$mode" "$LOG/${arm}_mcr_v2.log" &
done
wait
echo APHHM_C_COLLAPSE3C_DONE | tee -a "$MASTER"
