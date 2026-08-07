#!/usr/bin/env bash
set -euo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
export TREE_DX_USE_PROXY=1
export TREE_DX_EMBED_DEVICE=cpu
export TREE_DX_DIRECT_POST_OUTPUT_CAP=8192
rm -f logs/diagnosisarena_d2_m01_v1/c2_ab21_v1/annotate/stage_manifest.json
rm -f logs/diagnosisarena_d2_m01_v1/c2_ab22_v1/annotate/stage_manifest.json
: > logs/c2_ablation_workspace_v1/da_suite.log
nohup /home/wanghongyi/.conda/envs/gnn-llm/bin/python3 -u scripts/paper/run_c2_da_selector_suite.py \
  --arms ab21,ab22 --workers 12 \
  >> logs/c2_ablation_workspace_v1/da_suite.log 2>&1 &
echo $! | tee logs/c2_ablation_workspace_v1/da_suite.pid
