#!/usr/bin/env bash
# Backbone batch 4:
#   E16 - drop S4 entirely and take S3's own ranking (S3 first item is +7pp over
#         S2 first, while S4-b gives it back; test whether the cheapest system is
#         the one with no final selection call at all).
#   E14 - fact neutrality: run the sequential evidence update on key_facts (the
#         faithful, un-prioritised list, analogue of AB02's static_evidence_items)
#         instead of salient_findings, which are pre-filtered by the same prior.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
R="python3 scripts/paper/run_backbone_v1.py"
DA=logs/backbone_v1/diagnosisarena
LOG=logs/backbone_v1/batch4
mkdir -p "$LOG"

while pgrep -f run_backbone_batch3.sh >/dev/null; do sleep 30; done
echo "=== [$(date +%H:%M:%S)] batch3 clear, starting batch4 ==="

step () {
  local name="$1"; shift
  echo "=== [$(date +%H:%M:%S)] $name ==="
  $R "$@" >"$LOG/$name.log" 2>&1
  echo "    exit=$?"
}

# E16: no S4 at all (0 marginal generation calls; scoring only)
step e16_k3_nos4 --dataset diagnosisarena --arm e16_k3comp_nos4_k5 --select a --max-k 5 \
    --reuse-from "$DA/e7_k3_comp_k5" --workers 25 --score
step e16_k2_nos4 --dataset diagnosisarena --arm e16_k2comp_nos4_k5 --select a --max-k 5 \
    --reuse-from "$DA/e7_k2_comp_k5" --workers 25 --score

# E14: neutral fact source for the sequential update
step e14_keyfacts --dataset diagnosisarena --arm e14_sep_m8_keyfacts_k5 --select e \
    --s4-facts 8 --s4-fact-source key --max-k 5 \
    --reuse-from "$DA/e7_k3_comp_k5" --workers 10 --score

echo "=== [$(date +%H:%M:%S)] BATCH4 DONE ==="
