#!/usr/bin/env bash
# APHHM equal-input rerun: DA then MCR, options stripped from the vignette.
set -uo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1/aphhm_clean; mkdir -p "$LOG"
for DS in da mcr; do
  echo "=== [$(date +%H:%M:%S)] APHHM clean $DS start ==="
  python3 -u scripts/paper/run_aphhm_clean_input.py --dataset "$DS" --workers 12 \
    > "$LOG/$DS.log" 2>&1
  echo "    [$(date +%H:%M:%S)] $DS exit=$?"
done
echo "=== [$(date +%H:%M:%S)] APHHM CLEAN CHAIN DONE ==="
