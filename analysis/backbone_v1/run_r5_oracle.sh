#!/usr/bin/env bash
# R5 J1/J2/J3 selector-oracle interventions on collapse3c and forest (dev slices).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
LOG=logs/backbone_v1
MASTER=$LOG/r5_oracle_master.log
: >"$MASTER"

run() {
  local ds="$1" reuse="$2" out="$3" interv="$4" logfile="$5"
  echo "### START $ds $out $interv $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  python3 -u scripts/paper/run_r5_selector_oracle.py \
    --reuse-from "$reuse" --dataset "$ds" --out-arm "$out" \
    --intervention "$interv" --workers 32 >>"$logfile" 2>&1
  echo "### DONE $ds $out exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

# J1 bare inject on collapse3c + forest, DA+MCR dev
for ds in diagnosisarena diagnosisarena_heldout medcasereasoning medcasereasoning_v2; do
  run "$ds" "logs/backbone_v1/$ds/aphhm_c_collapse3c_v1" "r5_j1_collapse3c" j1 "$LOG/r5_j1_c3c_${ds}.log" &
  run "$ds" "logs/backbone_v1/$ds/mosaic_forest_v1" "r5_j1_forest" j1 "$LOG/r5_j1_forest_${ds}.log" &
done
wait
# J2 fair inject (more expensive: +1 call/case) on same arms, DA seq100 + MCR v1 only
for ds in diagnosisarena medcasereasoning; do
  run "$ds" "logs/backbone_v1/$ds/aphhm_c_collapse3c_v1" "r5_j2_collapse3c" j2 "$LOG/r5_j2_c3c_${ds}.log" &
  run "$ds" "logs/backbone_v1/$ds/mosaic_forest_v1" "r5_j2_forest" j2 "$LOG/r5_j2_forest_${ds}.log" &
done
wait
# J3 unmerge on multistance (where identity_loss exists), DA+MCR dev
for ds in diagnosisarena diagnosisarena_heldout medcasereasoning medcasereasoning_v2; do
  run "$ds" "logs/backbone_v1/$ds/aphhm_c_multistance_v1" "r5_j3_multistance" j3 "$LOG/r5_j3_ms_${ds}.log" &
done
wait
echo R5_ORACLE_DONE | tee -a "$MASTER"
