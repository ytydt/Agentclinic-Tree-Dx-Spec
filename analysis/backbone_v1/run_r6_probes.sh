#!/usr/bin/env bash
# R6 causal probes X1–X5 on forest × collapse3c (dev 400).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
LOG=logs/backbone_v1
MASTER=$LOG/r6_probes_master.log
: >"$MASTER"
DS_LIST=(diagnosisarena diagnosisarena_heldout medcasereasoning medcasereasoning_v2)

run() {
  local ds="$1" probe="$2" pool="$3" sel="$4" out="$5" logfile="$6"
  shift 6 || true
  echo "### START $ds $out $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  python3 -u scripts/paper/run_r6_probe.py \
    --dataset "$ds" --probe "$probe" --pool-from "$pool" \
    --selector-family "$sel" --out-arm "$out" --workers 32 "$@" \
    >>"$logfile" 2>&1
  echo "### DONE $ds $out exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

# ---- X1 2×2 cross: {forest,collapse3c} pool × {mosaic,aphhm_c} selector ----
for ds in "${DS_LIST[@]}"; do
  run "$ds" x1_cross \
    "logs/backbone_v1/$ds/mosaic_forest_v1" mosaic \
    r6_x1_forest_pool_mosaic_sel "$LOG/r6_x1_fm_${ds}.log" &
  run "$ds" x1_cross \
    "logs/backbone_v1/$ds/mosaic_forest_v1" aphhm_c \
    r6_x1_forest_pool_aphhm_sel "$LOG/r6_x1_fa_${ds}.log" &
  run "$ds" x1_cross \
    "logs/backbone_v1/$ds/aphhm_c_collapse3c_v1" mosaic \
    r6_x1_c3c_pool_mosaic_sel "$LOG/r6_x1_cm_${ds}.log" &
  run "$ds" x1_cross \
    "logs/backbone_v1/$ds/aphhm_c_collapse3c_v1" aphhm_c \
    r6_x1_c3c_pool_aphhm_sel "$LOG/r6_x1_ca_${ds}.log" &
done
wait

# ---- X2 disc strip / X3 siblings / X5 quota on forest + collapse3c ----
for ds in "${DS_LIST[@]}"; do
  for pair in \
    "x2_disc:mosaic_forest_v1:mosaic:r6_x2_forest" \
    "x2_disc:aphhm_c_collapse3c_v1:aphhm_c:r6_x2_c3c" \
    "x3_siblings:mosaic_forest_v1:mosaic:r6_x3_forest" \
    "x3_siblings:aphhm_c_collapse3c_v1:aphhm_c:r6_x3_c3c" \
    "x5_quota:mosaic_forest_v1:mosaic:r6_x5_forest" \
    "x5_quota:aphhm_c_collapse3c_v1:aphhm_c:r6_x5_c3c"
  do
    IFS=: read -r probe poolarm selfam out <<<"$pair"
    run "$ds" "$probe" "logs/backbone_v1/$ds/$poolarm" "$selfam" "$out" \
      "$LOG/${out}_${ds}.log" &
  done
done
wait

# ---- X4 order permutations (3 seeds) on forest ----
for seed in 0 1 2; do
  for ds in "${DS_LIST[@]}"; do
    run "$ds" "x4_order_s${seed}" \
      "logs/backbone_v1/$ds/mosaic_forest_v1" mosaic \
      "r6_x4_forest_s${seed}" "$LOG/r6_x4_forest_s${seed}_${ds}.log" \
      --order-seed "$seed" &
    run "$ds" "x4_order_s${seed}" \
      "logs/backbone_v1/$ds/aphhm_c_collapse3c_v1" aphhm_c \
      "r6_x4_c3c_s${seed}" "$LOG/r6_x4_c3c_s${seed}_${ds}.log" \
      --order-seed "$seed" &
  done
  wait
done

echo R6_PROBES_DONE | tee -a "$MASTER"
