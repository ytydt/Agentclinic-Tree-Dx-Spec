#!/usr/bin/env bash
# Backbone batch 2: E7 (breadth by repetition), E8 (partition conditioning),
# E9 (per-fact decorrelated selection), E10 (strict-subset S3 -> correct KB ablation),
# E11 (E7 + E9 combined).
#
# Writes only logs/backbone_v1/.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
LOG=logs/backbone_v1/batch2
mkdir -p "$LOG"

step () {  # step <name> <args...>
  local name="$1"; shift
  echo "=== [$(date +%H:%M:%S)] $name ==="
  $R "$@" >"$LOG/$name.log" 2>&1
  echo "    exit=$? $(tail -c 400 "$LOG/$name.log" | tr '\n' ' ' | tail -c 200)"
}

# --- E7: breadth by repeated, differently-conditioned S2 calls (DA) ---
step e7_k2_comp  --dataset diagnosisarena --arm e7_k2_comp_k5 --select b --max-k 5 \
    --s2-k 2 --s2-mode complement --workers 25 --score
step e7_k3_comp  --dataset diagnosisarena --arm e7_k3_comp_k5 --select b --max-k 5 \
    --s2-k 3 --s2-mode complement --workers 25 --score

# --- E8: structured partition conditioning at the same k=3 budget (DA) ---
step e8_k3_part  --dataset diagnosisarena --arm e8_k3_part_k5 --select b --max-k 5 \
    --s2-k 3 --s2-mode partition --workers 25 --score

# --- E9: per-fact decorrelated selection, S1-S3 held fixed (paired vs v0_s4b_k5) ---
step e9_perfact  --dataset diagnosisarena --arm e9_perfact_k5 --select d --max-k 5 \
    --reuse-from "$DA/v0_s4b_k5" --workers 25 --score
step e9_perfact8 --dataset diagnosisarena --arm e9_perfact_k8 --select d --max-k 8 \
    --reuse-from "$DA/v0_s4b_k8" --workers 25 --score

# --- E11: both fixes combined (reuses E7 S1-S3, only S4 is new) ---
step e11_combo   --dataset diagnosisarena --arm e11_k3comp_perfact_k5 --select d --max-k 5 \
    --reuse-from "$DA/e7_k3_comp_k5" --workers 25 --score

# --- E10: correct version of the KB-only ablation (strict subset S3) ---
step e10_kb_strict --dataset diagnosisarena --arm e10_kb_strict_k5 --select b --max-k 5 \
    --entrance kb_only --s3-strict --workers 12 --score
step e10_llm_strict --dataset diagnosisarena --arm e10_llm_strict_k5 --select b --max-k 5 \
    --s3-strict --workers 25 --score

# --- MCR slice 1: the two winning mechanisms, same protocol ---
step mcr_e7_k3   --dataset medcasereasoning --arm e7_k3_comp_k5 --select b --max-k 5 \
    --s2-k 3 --s2-mode complement --workers 25 --score
step mcr_e9      --dataset medcasereasoning --arm e9_perfact_k5 --select d --max-k 5 \
    --reuse-from logs/backbone_v1/medcasereasoning/v0_s4b_k5 --workers 25 --score
step mcr_e11     --dataset medcasereasoning --arm e11_k3comp_perfact_k5 --select d --max-k 5 \
    --reuse-from logs/backbone_v1/medcasereasoning/e7_k3_comp_k5 --workers 25 --score

echo "=== [$(date +%H:%M:%S)] BATCH2 DONE ==="
