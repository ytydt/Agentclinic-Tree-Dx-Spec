#!/usr/bin/env bash
# MultiStance was defined on the dev slices (DA200/MCR200), so the only claim in
# §16.3 that still needs out-of-sample support is the one that matters: DA
# concept +5.5pp over Collapse3c (3-14, p=0.013). §16.4 showed roughly half of
# that gain comes from the coverage stance manufacturing under-specified labels
# the DA matcher rewards, so the holdout is what decides whether the rest is real.
# d2_heldout200b and mcr_200b are the reserved slices; nothing was tuned on them.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
ARM=aphhm_c_multistance_v1
MASTER="$LOG/aphhm_c_multistance_200b_master.log"
: >"$MASTER"

run() {
  local ds="$1" logfile="$2"
  echo "### START $ds $ARM $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
  python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$ARM" \
    --mode multistance --stances commit,coverage,mechanism --axis-mode off \
    --unique-budget 10 --workers 32 --score "${extra[@]}" >>"$logfile" 2>&1
  echo "### DONE $ds $ARM exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena_heldout200b "$LOG/${ARM}_da_200b.log" &
run medcasereasoning_200b      "$LOG/${ARM}_mcr_200b.log" &
wait
echo APHHM_C_MULTISTANCE_200B_DONE | tee -a "$MASTER"
