#!/usr/bin/env bash
# Backbone batch 5: is the evidence machine an irreducible compute-scaling
# regime, or was the single-winner contract simply too lossy?
#
#   e18e_m16 - same sparse single-winner contract, 32 calls (pure dose-response;
#              m=4 -> 0.45, m=8 -> 0.48 option@1, 0-call baseline 0.50)
#   e18g_m12 - ranked top-3 contract with rank credits (1.0/0.5/0.25), 12 calls
#              (3x the information per call at a third of the budget)
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
LOG=logs/backbone_v1/batch5
mkdir -p "$LOG"

while pgrep -f run_backbone_batch4.sh >/dev/null; do sleep 30; done
echo "=== [$(date +%H:%M:%S)] batch4 clear, starting batch5 ==="

step () {
  local name="$1"; shift
  echo "=== [$(date +%H:%M:%S)] $name ==="
  $R "$@" >"$LOG/$name.log" 2>&1
  echo "    exit=$?"
}

step e18g_m12 --dataset diagnosisarena --arm e18_ranked_m12_k5 --select g --s4-facts 12 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score
step e18e_m16 --dataset diagnosisarena --arm e18_sep_m16_k5 --select e --s4-facts 16 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 8 --score
step e18g_wide --dataset diagnosisarena --arm e18_k3comp_ranked_m12_k5 --select g \
    --s4-facts 12 --max-k 5 --reuse-from "$DA/e7_k3_comp_k5" --workers 10 --score

echo "=== [$(date +%H:%M:%S)] BATCH5 DONE ==="
