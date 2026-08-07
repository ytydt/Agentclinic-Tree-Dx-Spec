#!/usr/bin/env bash
# Backbone batch 3: isolate WHICH structural property of AB02's evidence
# adjudication carries the weight.
#
# Ablation ladder over the selection stage, S1-S3 held fixed (paired):
#   S4-b  free select        1 call   global gestalt over shortlist
#   S4-d  per-fact matrix    1 call   + per-fact decomposition (globally visible)
#   S4-f  joint rule in/out  m calls  + one-fact-at-a-time myopia
#   S4-e  separated in/out   2m calls + adversarial separation
#
# Writes only logs/backbone_v1/.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
MCR=logs/backbone_v1/medcasereasoning
LOG=logs/backbone_v1/batch3
mkdir -p "$LOG"

# wait for batch 2 to clear the API
while pgrep -f run_backbone_batch2.sh >/dev/null; do sleep 30; done
echo "=== [$(date +%H:%M:%S)] batch2 clear, starting batch3 ==="

step () {
  local name="$1"; shift
  echo "=== [$(date +%H:%M:%S)] $name ==="
  $R "$@" >"$LOG/$name.log" 2>&1
  echo "    exit=$?"
}

# --- E12: the ladder, all paired on v0_s4b_k5's S1-S3 ---
step e12f_m4  --dataset diagnosisarena --arm e12_joint_m4_k5 --select f --s4-facts 4 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 12 --score
step e12e_m4  --dataset diagnosisarena --arm e12_sep_m4_k5 --select e --s4-facts 4 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 12 --score
step e12e_m8  --dataset diagnosisarena --arm e12_sep_m8_k5 --select e --s4-facts 8 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score

# --- E13: breadth (E7 k=3) + best selection, the full lightweight system ---
step e13_da   --dataset diagnosisarena --arm e13_k3comp_sep_m8_k5 --select e --s4-facts 8 \
    --max-k 5 --reuse-from "$DA/e7_k3_comp_k5" --workers 10 --score

# --- MCR slice 1: same two mechanisms ---
step e12e_mcr --dataset medcasereasoning --arm e12_sep_m8_k5 --select e --s4-facts 8 \
    --max-k 5 --reuse-from "$MCR/v0_s4b_k5" --workers 10 --score
step e13_mcr  --dataset medcasereasoning --arm e13_k3comp_sep_m8_k5 --select e --s4-facts 8 \
    --max-k 5 --reuse-from "$MCR/e7_k3_comp_k5" --workers 10 --score

echo "=== [$(date +%H:%M:%S)] BATCH3 DONE ==="
