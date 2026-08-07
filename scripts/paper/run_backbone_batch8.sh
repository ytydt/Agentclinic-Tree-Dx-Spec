#!/usr/bin/env bash
# Batch 8: equal-input control. Replay the MCQ-option leak that M00/AB02 receive
# (env.get_case_summary() = vignette + Question + Options, gold always option A
# on MCR) into the backbone, and measure the full-system impact.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
LOG=logs/backbone_v1/batch8; mkdir -p "$LOG"
step () { local n="$1"; shift; echo "=== [$(date +%H:%M:%S)] $n ==="; $R "$@" >"$LOG/$n.log" 2>&1; echo "    exit=$?"; }

step leak_mcr_k1 --dataset medcasereasoning --arm leak_v0_s4b_k5 --select b --max-k 5 \
    --context-source pipeline_summary --workers 25 --score
step leak_mcr_k3 --dataset medcasereasoning --arm leak_e7_k3_comp_k5 --select b --max-k 5 \
    --s2-k 3 --s2-mode complement --context-source pipeline_summary --workers 25 --score
step leak_da_k1  --dataset diagnosisarena --arm leak_v0_s4b_k5 --select b --max-k 5 \
    --context-source pipeline_summary --workers 25 --score
step leak_da_k3  --dataset diagnosisarena --arm leak_e7_k3_comp_k5 --select b --max-k 5 \
    --s2-k 3 --s2-mode complement --context-source pipeline_summary --workers 25 --score
echo "=== [$(date +%H:%M:%S)] BATCH8 DONE ==="
