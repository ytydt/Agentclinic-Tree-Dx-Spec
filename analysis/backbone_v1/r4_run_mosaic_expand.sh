#!/usr/bin/env bash
# Expand MOSAIC/IMPC evaluation across slices.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
mkdir -p "$LOG"

run() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm $mode $(date -Is)" | tee -a "$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm "$arm" --mode "$mode" \
      --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$logfile"
}

# Wave 1: Lite expand (parallel)
run diagnosisarena_heldout mosaic_lite_v1 lite "$LOG/mosaic_lite_heldout.log" &
run diagnosisarena_heldout200b mosaic_lite_v1 lite "$LOG/mosaic_lite_200b.log" &
run medcasereasoning_v2 mosaic_lite_v1 lite "$LOG/mosaic_lite_mcr_v2.log" &
run medcasereasoning_200b mosaic_lite_v1 lite "$LOG/mosaic_lite_mcr_200b.log" &
wait
echo WAVE1_LITE_DONE

# Wave 2: Adaptive4v2 + Forest + IMPC on seq100/v1 (parallel arms)
run diagnosisarena mosaic_adaptive4v2_v1 adaptive4v2 "$LOG/mosaic_a4v2_da.log" &
run medcasereasoning mosaic_adaptive4v2_v1 adaptive4v2 "$LOG/mosaic_a4v2_mcr.log" &
run diagnosisarena mosaic_forest_v1 forest "$LOG/mosaic_forest_da.log" &
run medcasereasoning mosaic_forest_v1 forest "$LOG/mosaic_forest_mcr.log" &
run diagnosisarena mosaic_impc_v1 impc "$LOG/mosaic_impc_da.log" &
run medcasereasoning mosaic_impc_v1 impc "$LOG/mosaic_impc_mcr.log" &
wait
echo WAVE2_NEW_ARMS_DONE

# Wave 3: heldout / mcr_v2 for new arms
run diagnosisarena_heldout mosaic_adaptive4v2_v1 adaptive4v2 "$LOG/mosaic_a4v2_heldout.log" &
run medcasereasoning_v2 mosaic_adaptive4v2_v1 adaptive4v2 "$LOG/mosaic_a4v2_mcr_v2.log" &
run diagnosisarena_heldout mosaic_forest_v1 forest "$LOG/mosaic_forest_heldout.log" &
run medcasereasoning_v2 mosaic_forest_v1 forest "$LOG/mosaic_forest_mcr_v2.log" &
run diagnosisarena_heldout mosaic_impc_v1 impc "$LOG/mosaic_impc_heldout.log" &
run medcasereasoning_v2 mosaic_impc_v1 impc "$LOG/mosaic_impc_mcr_v2.log" &
wait
echo WAVE3_EXPAND_DONE
echo ALL_MOSAIC_EXPAND_DONE
