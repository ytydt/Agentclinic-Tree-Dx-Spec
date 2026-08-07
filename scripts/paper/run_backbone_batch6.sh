#!/usr/bin/env bash
# Batch 6 (E19): does the sparse per-fact evidence machine only work on
# ATOMISED single-attribute facts? AB02 feeds it 17.55 typed atoms/case; the
# backbone was feeding it compound clinical sentences.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
LOG=logs/backbone_v1/batch6; mkdir -p "$LOG"
step () { local n="$1"; shift; echo "=== [$(date +%H:%M:%S)] $n ==="; $R "$@" >"$LOG/$n.log" 2>&1; echo "    exit=$?"; }

step e19_atom_g16 --dataset diagnosisarena --arm e19_atom_ranked_m16_k5 --select g \
    --s4-facts 16 --s4-fact-source atomised --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score
step e19_atom_e8  --dataset diagnosisarena --arm e19_atom_sep_m8_k5 --select e \
    --s4-facts 8 --s4-fact-source atomised --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score
step e19_atom_wide --dataset diagnosisarena --arm e19_k3comp_atom_ranked_m16_k5 --select g \
    --s4-facts 16 --s4-fact-source atomised --max-k 5 --reuse-from "$DA/e7_k3_comp_k5" --workers 10 --score
step e19_atom_mcr --dataset medcasereasoning --arm e19_atom_ranked_m16_k5 --select g \
    --s4-facts 16 --s4-fact-source atomised --max-k 5 \
    --reuse-from logs/backbone_v1/medcasereasoning/v0_s4b_k5 --workers 10 --score
echo "=== [$(date +%H:%M:%S)] BATCH6 DONE ==="
