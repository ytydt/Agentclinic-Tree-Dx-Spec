#!/usr/bin/env bash
# Batch 7 (E20): dense ordinal effect labels + the §13 discrimination gate,
# i.e. AB02's ACTUAL update rule (updater.ordinal_update), rather than the
# sparse single-winner contract I reconstructed from l1_evidence_bfs.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
LOG=logs/backbone_v1/batch7; mkdir -p "$LOG"
step () { local n="$1"; shift; echo "=== [$(date +%H:%M:%S)] $n ==="; $R "$@" >"$LOG/$n.log" 2>&1; echo "    exit=$?"; }

step e20_ord_m10  --dataset diagnosisarena --arm e20_ordinal_m10_k5 --select h --s4-facts 10 \
    --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score
step e20_ord_atom --dataset diagnosisarena --arm e20_ordinal_atom_m16_k5 --select h --s4-facts 16 \
    --s4-fact-source atomised --max-k 5 --reuse-from "$DA/v0_s4b_k5" --workers 10 --score
step e20_ord_wide --dataset diagnosisarena --arm e20_k3comp_ordinal_m10_k5 --select h --s4-facts 10 \
    --max-k 5 --reuse-from "$DA/e7_k3_comp_k5" --workers 10 --score
step e20_ord_mcr  --dataset medcasereasoning --arm e20_ordinal_m10_k5 --select h --s4-facts 10 \
    --max-k 5 --reuse-from logs/backbone_v1/medcasereasoning/v0_s4b_k5 --workers 10 --score
echo "=== [$(date +%H:%M:%S)] BATCH7 DONE ==="
