#!/usr/bin/env bash
# R6: same-config replicates for msplit / adaptive4v2 / aphhm_c_v1 / e7 / v0 (dev 400).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER=$LOG/r6_replicates_master.log
: >"$MASTER"
DS_LIST=(diagnosisarena diagnosisarena_heldout medcasereasoning medcasereasoning_v2)

run_aphhm() {
  local ds="$1" arm="$2" logfile="$3"; shift 3
  echo "### START $ds $arm $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
  python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
    --workers 32 --score "${extra[@]}" "$@" >>"$logfile" 2>&1
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}
run_mosaic() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
  python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm "$arm" --mode "$mode" \
    --workers 32 --score "${extra[@]}" >>"$logfile" 2>&1
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}
run_bb() {
  local ds="$1" arm="$2" logfile="$3"; shift 3
  echo "### START $ds $arm $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
  python3 -u scripts/paper/run_backbone_v1.py --dataset "$ds" --arm "$arm" \
    --workers 32 --score "${extra[@]}" "$@" >>"$logfile" 2>&1
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for ds in "${DS_LIST[@]}"; do
  run_aphhm "$ds" aphhm_c_msplit_r2 "$LOG/aphhm_c_msplit_r2_${ds}.log" \
    --mode multistance_split --stances commit,coverage,mechanism --axis-mode off --unique-budget 10 &
  run_aphhm "$ds" aphhm_c_v1_r2 "$LOG/aphhm_c_v1_r2_${ds}.log" --mode c4 &
  run_mosaic "$ds" mosaic_adaptive4v2_r2 adaptive4v2 "$LOG/mosaic_adaptive4v2_r2_${ds}.log" &
  run_bb "$ds" e7_k3_comp_k5_r2 "$LOG/e7_r2_${ds}.log" --select b --max-k 5 --s2-k 3 --s2-mode complement &
  run_bb "$ds" v0_s4b_k5_r2 "$LOG/v0_r2_${ds}.log" --select b --max-k 5 &
done
echo "launched $(jobs -r | wc -l) jobs" | tee -a "$MASTER"
wait
echo R6_REPLICATES_DONE | tee -a "$MASTER"
