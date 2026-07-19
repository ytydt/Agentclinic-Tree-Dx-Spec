#!/usr/bin/env bash
# Run temperature=0 F30 full-horizon replicates for saturation profiling.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=src

LOG_DIR="$ROOT/logs/l1_bfs_adaptive_stop"
mkdir -p "$LOG_DIR"

run_one() {
  local tag="$1"
  echo "[$(date -Is)] starting $tag"
  python scripts/eval_l1_bfs_adaptive_stop.py \
    --profiles p5_headline \
    --max-micro-rounds 30 \
    --temperature 0 \
    --n-boot 5000 \
    --tag "$tag" \
    --call-timeout 240 \
    --resume \
    2>&1 | tee "$LOG_DIR/${tag}.run.log"
  echo "[$(date -Is)] finished $tag"
}

# r01 already exists as f30_saturation_t0_r1; launch r02..r09 for 9-run lane.
for idx in 02 03 04 05 06 07 08 09; do
  run_one "f30_saturation_t0_r${idx}"
done

echo "[$(date -Is)] all replicates complete"
