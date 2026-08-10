#!/usr/bin/env bash
# R7 large-scale backlog: compact_forest 800+r2, near-dedup 800, 200b r2, specialty.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
LOG=logs/backbone_v1
MASTER=$LOG/r7_scale_master.log
: >"$MASTER"
DS800=(diagnosisarena diagnosisarena_heldout diagnosisarena_heldout200b medcasereasoning medcasereasoning_v2 medcasereasoning_200b)
DS200B=(diagnosisarena_heldout200b medcasereasoning_200b)

echo "### R7_SCALE START $(date -Is)" | tee -a "$MASTER"

# --- Wave A: specialty labels (independent) ---
(
  echo "### START specialty $(date -Is)" | tee -a "$MASTER"
  python3 -u analysis/backbone_v1/r7_specialty_label.py >"$LOG/r7_specialty.log" 2>&1
  echo "### DONE specialty exit=$? $(date -Is)" | tee -a "$MASTER"
) &

# --- Wave A: compact_forest_v0 (reuse forest pool, near-dedup on) ---
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/r7_compact_${ds}.log"
    echo "### START compact $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_compact_forest_aphhm.py \
      --dataset "$ds" --arm compact_forest_v0 \
      --reuse-from mosaic_forest_v1 --near-dedup-shortlist --workers 32 \
      >>"$lf" 2>&1
    echo "### DONE compact $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done

# --- Wave A: compact_forest_v0_r2 ---
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/r7_compact_r2_${ds}.log"
    echo "### START compact_r2 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_compact_forest_aphhm.py \
      --dataset "$ds" --arm compact_forest_v0_r2 \
      --reuse-from mosaic_forest_v1 --near-dedup-shortlist --workers 32 \
      >>"$lf" 2>&1
    echo "### DONE compact_r2 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done

# --- Wave A: near-dedup on collapse3c (flat) ---
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/r7_nd_c3c_${ds}.log"
    echo "### START nd_c3c $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_near_dedup_sel.py \
      --dataset "$ds" --arm aphhm_c_collapse3c_neardedup \
      --pool-from aphhm_c_collapse3c_v1 --mode flat --workers 32 \
      >>"$lf" 2>&1
    echo "### DONE nd_c3c $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done

# --- Wave A: near-dedup on multistance (tournament + group dedup) ---
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/r7_nd_ms_${ds}.log"
    echo "### START nd_ms $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_near_dedup_sel.py \
      --dataset "$ds" --arm aphhm_c_multistance_neardedup \
      --pool-from aphhm_c_multistance_v1 --mode tournament --group-near-dedup --workers 32 \
      >>"$lf" 2>&1
    echo "### DONE nd_ms $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done

echo "### Wave A launched jobs=$(jobs -r | wc -l) $(date -Is)" | tee -a "$MASTER"
wait
echo "### Wave A DONE $(date -Is)" | tee -a "$MASTER"

# --- Wave B: 200b full replicates for forest + collapse3c ---
for ds in "${DS200B[@]}"; do
  (
    lf="$LOG/r7_forest_r2_${ds}.log"
    echo "### START forest_r2 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    extra=()
    [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
    python3 -u scripts/paper/run_mosaic.py --dataset "$ds" --arm mosaic_forest_r2 \
      --mode forest --workers 32 --score "${extra[@]}" >>"$lf" 2>&1
    echo "### DONE forest_r2 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
  (
    lf="$LOG/r7_c3c_r2_${ds}.log"
    echo "### START c3c_r2 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    extra=()
    [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm aphhm_c_collapse3c_r2 \
      --mode c4_selector_candev_nomatrix --concept-contract evid_commit --axis-mode off \
      --unique-budget 10 --workers 32 --score "${extra[@]}" >>"$lf" 2>&1
    echo "### DONE c3c_r2 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done

echo "### Wave B launched jobs=$(jobs -r | wc -l) $(date -Is)" | tee -a "$MASTER"
wait
echo "### Wave B DONE $(date -Is)" | tee -a "$MASTER"

# --- Summarize ---
python3 -u analysis/backbone_v1/r7_scale_summarize.py >"$LOG/r7_scale_summarize.log" 2>&1
echo "### R7_SCALE ALL DONE $(date -Is)" | tee -a "$MASTER"
