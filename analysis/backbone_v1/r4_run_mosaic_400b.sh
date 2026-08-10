#!/usr/bin/env bash
# Wave 4: Forest + IMPC to DA400 / MCR400 (heldout200b + mcr_200b).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
mkdir -p "$LOG"
MASTER="$LOG/mosaic_400b_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm $mode $(date -Is)" | tee -a "$MASTER" | tee -a "$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score >>"$logfile" 2>&1
  fi
  local ec=$?
  echo "### DONE $ds $arm exit=$ec $(date -Is)" | tee -a "$MASTER" | tee -a "$logfile"
  return $ec
}

run diagnosisarena_heldout200b mosaic_forest_v1 forest "$LOG/mosaic_forest_200b.log" &
run diagnosisarena_heldout200b mosaic_impc_v1 impc "$LOG/mosaic_impc_200b.log" &
run medcasereasoning_200b mosaic_forest_v1 forest "$LOG/mosaic_forest_mcr_200b.log" &
run medcasereasoning_200b mosaic_impc_v1 impc "$LOG/mosaic_impc_mcr_200b.log" &
wait
echo WAVE4_FOREST_IMPC_400_DONE | tee -a "$MASTER"
echo ALL_MOSAIC_400B_DONE | tee -a "$MASTER"
