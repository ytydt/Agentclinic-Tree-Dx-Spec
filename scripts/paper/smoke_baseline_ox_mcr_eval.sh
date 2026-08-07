#!/usr/bin/env bash
# Smoke: B00 on OX + MCR (limit=2), project, lexical official-style eval.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"

OX_RUNS="${ROOT}/runs/paper_v1/open_xddx_ox_mcr_smoke"
MCR_RUNS="${ROOT}/runs/paper_v1/medcasereasoning_ox_mcr_smoke"

echo "=== OX B00 limit=2 list_k=5 (dry-run) ==="
python3 scripts/paper/run_baseline.py \
  --dataset open_xddx \
  --list-k 5 \
  --arms B00-direct-cot \
  --limit 2 \
  --workers 1 \
  --dry-run \
  --runs-root "$OX_RUNS"

python3 scripts/paper/run_baseline_ox_mcr_eval.py \
  --dataset open_xddx \
  --pred-dir "$OX_RUNS/B00-direct-cot/replicate_01" \
  --list-k 5 \
  --judge lexical \
  --workers 1

echo "=== MCR B00 limit=2 (dry-run) ==="
python3 scripts/paper/run_baseline.py \
  --dataset medcasereasoning \
  --list-k 2 \
  --arms B00-direct-cot \
  --limit 2 \
  --workers 1 \
  --dry-run \
  --runs-root "$MCR_RUNS"

python3 scripts/paper/run_baseline_ox_mcr_eval.py \
  --dataset medcasereasoning \
  --pred-dir "$MCR_RUNS/B00-direct-cot/replicate_01" \
  --list-k 2 \
  --judge lexical \
  --workers 1 \
  --skip-reasoning-recall

echo "Smoke OK. LLM path (contract): conda activate gnn-llm && clashon && --judge llm --workers 50"
