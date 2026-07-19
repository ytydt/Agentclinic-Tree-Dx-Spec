#!/bin/bash
set -euo pipefail
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
# Wait for generation PID if present
while pgrep -f 'eval_l2_a_variant_v2_generation.py generate' >/dev/null; do sleep 30; done
# Wait for control eval
while pgrep -f 'eval_l2_a_variant_v2_legacy.py' >/dev/null; do sleep 30; done
# Evaluate remaining arms that need A20 trees
python3 -u scripts/eval_l2_a_variant_v2_legacy.py \
  --generation-dir logs/l2_a_variant_matrix_v2/generation \
  --output-dir logs/l2_a_variant_legacy_ab_v2 \
  --replicates 3 --workers 3 --backend llm --resume \
  --arms "A18-parent-safe,A19-budget-safe,A20-generation-v2,A21-generation-v2+F4,A22-adaptive-local-rescue" \
  > logs/l2_a_variant_legacy_ab_v2/eval_remaining.log 2>&1
python3 scripts/analyze_l2_a_variant_v2.py \
  --records logs/l2_a_variant_legacy_ab_v2/evaluation/records.json \
  --output-dir logs/l2_a_variant_legacy_ab_v2/evaluation \
  >> logs/l2_a_variant_legacy_ab_v2/eval_remaining.log 2>&1
