#!/usr/bin/env bash
# R4 interventions I2/I3/I4 launcher. Uses --keep-s2 to freeze S1-S3.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
MODEL=meta-llama/llama-3.3-70b-instruct
IDS=analysis/backbone_v1/r4_interventions

case_args() {
  local f="$1"
  local args=()
  while IFS= read -r id; do
    [ -n "$id" ] || continue
    args+=(--case-id "$id")
  done < "$f"
  printf '%q ' "${args[@]}"
}

run_da_select() {
  local ds="$1" reuse="$2" arm="$3" select="$4" idfile="$5"
  echo "### I2 DA $ds $arm select=$select"
  mapfile -t CASES < <(grep -v '^$' "$idfile" | sed 's/^/--case-id /')
  # shellcheck disable=SC2068
  python3 -u scripts/paper/run_backbone_v1.py --dataset "$ds" \
    --arm "$arm" --select "$select" --max-k 5 --entrance llm_ddx \
    --s2-k 3 --s2-mode complement --keep-s2 \
    --reuse-from "$reuse" \
    --model "$MODEL" --workers 32 --score \
    $(while read -r id; do echo --case-id "$id"; done < "$idfile")
}

run_mcr_select() {
  local ds="$1" reuse="$2" arm="$3" select="$4" idfile="$5"
  echo "### I2 MCR $ds $arm select=$select"
  python3 -u scripts/paper/run_backbone_v1.py --dataset "$ds" \
    --arm "$arm" --select "$select" --max-k 5 --entrance llm_ddx \
    --s2-k 3 --s2-mode complement --keep-s2 \
    --reuse-from "$reuse" \
    --model "$MODEL" --workers 32 --score --mcr-judge-workers 50 \
    $(while read -r id; do echo --case-id "$id"; done < "$idfile")
}

# ---- I2: select c and d on s3_hit_s4_miss + ok controls ----
run_da_select diagnosisarena logs/backbone_v1/diagnosisarena/e7_k3_comp_k5 r4_i2_s4c_e7 c "$IDS/i2_ids_da_d2_seq100.txt"
run_da_select diagnosisarena logs/backbone_v1/diagnosisarena/e7_k3_comp_k5 r4_i2_s4d_e7 d "$IDS/i2_ids_da_d2_seq100.txt"
run_da_select diagnosisarena_heldout logs/backbone_v1/diagnosisarena_heldout/e7_k3_comp_k5 r4_i2_s4c_e7 c "$IDS/i2_ids_da_d2_heldout100.txt"
run_da_select diagnosisarena_heldout logs/backbone_v1/diagnosisarena_heldout/e7_k3_comp_k5 r4_i2_s4d_e7 d "$IDS/i2_ids_da_d2_heldout100.txt"
run_da_select diagnosisarena_heldout200b logs/backbone_v1/diagnosisarena_heldout200b/e7_k3_comp_k5 r4_i2_s4c_e7 c "$IDS/i2_ids_da_d2_heldout200b.txt"
run_da_select diagnosisarena_heldout200b logs/backbone_v1/diagnosisarena_heldout200b/e7_k3_comp_k5 r4_i2_s4d_e7 d "$IDS/i2_ids_da_d2_heldout200b.txt"

run_mcr_select medcasereasoning logs/backbone_v1/medcasereasoning/e7_k3_comp_k5 r4_i2_s4c_e7 c "$IDS/i2_ids_mcr_mcr_v1.txt"
run_mcr_select medcasereasoning logs/backbone_v1/medcasereasoning/e7_k3_comp_k5 r4_i2_s4d_e7 d "$IDS/i2_ids_mcr_mcr_v1.txt"
run_mcr_select medcasereasoning_v2 logs/backbone_v1/medcasereasoning_v2/e7_k3_comp_k5_v2 r4_i2_s4c_e7 c "$IDS/i2_ids_mcr_mcr_v2.txt"
run_mcr_select medcasereasoning_v2 logs/backbone_v1/medcasereasoning_v2/e7_k3_comp_k5_v2 r4_i2_s4d_e7 d "$IDS/i2_ids_mcr_mcr_v2.txt"
run_mcr_select medcasereasoning_200b logs/backbone_v1/medcasereasoning_200b/e7_k3_comp_k5 r4_i2_s4c_e7 c "$IDS/i2_ids_mcr_mcr_200b.txt"
run_mcr_select medcasereasoning_200b logs/backbone_v1/medcasereasoning_200b/e7_k3_comp_k5 r4_i2_s4d_e7 d "$IDS/i2_ids_mcr_mcr_200b.txt"

echo R4_I2_DONE

# ---- I3: force-s3 on same I2 id set (S3 necessity) ----
run_da_select_i3() {
  local ds="$1" reuse="$2" arm="$3" idfile="$4"
  echo "### I3 DA $ds $arm force-s3"
  python3 -u scripts/paper/run_backbone_v1.py --dataset "$ds" \
    --arm "$arm" --select b --max-k 5 --entrance llm_ddx \
    --s2-k 3 --s2-mode complement --keep-s2 --force-s3 \
    --reuse-from "$reuse" \
    --model "$MODEL" --workers 32 --score \
    $(while read -r id; do echo --case-id "$id"; done < "$idfile")
}
run_mcr_select_i3() {
  local ds="$1" reuse="$2" arm="$3" idfile="$4"
  echo "### I3 MCR $ds $arm force-s3"
  python3 -u scripts/paper/run_backbone_v1.py --dataset "$ds" \
    --arm "$arm" --select b --max-k 5 --entrance llm_ddx \
    --s2-k 3 --s2-mode complement --keep-s2 --force-s3 \
    --reuse-from "$reuse" \
    --model "$MODEL" --workers 32 --score --mcr-judge-workers 50 \
    $(while read -r id; do echo --case-id "$id"; done < "$idfile")
}

run_da_select_i3 diagnosisarena logs/backbone_v1/diagnosisarena/e7_k3_comp_k5 r4_i3_force_s3 "$IDS/i2_ids_da_d2_seq100.txt"
run_da_select_i3 diagnosisarena_heldout logs/backbone_v1/diagnosisarena_heldout/e7_k3_comp_k5 r4_i3_force_s3 "$IDS/i2_ids_da_d2_heldout100.txt"
run_da_select_i3 diagnosisarena_heldout200b logs/backbone_v1/diagnosisarena_heldout200b/e7_k3_comp_k5 r4_i3_force_s3 "$IDS/i2_ids_da_d2_heldout200b.txt"
run_mcr_select_i3 medcasereasoning logs/backbone_v1/medcasereasoning/e7_k3_comp_k5 r4_i3_force_s3 "$IDS/i2_ids_mcr_mcr_v1.txt"
run_mcr_select_i3 medcasereasoning_v2 logs/backbone_v1/medcasereasoning_v2/e7_k3_comp_k5_v2 r4_i3_force_s3 "$IDS/i2_ids_mcr_mcr_v2.txt"
run_mcr_select_i3 medcasereasoning_200b logs/backbone_v1/medcasereasoning_200b/e7_k3_comp_k5 r4_i3_force_s3 "$IDS/i2_ids_mcr_mcr_200b.txt"

echo R4_I3_DONE
