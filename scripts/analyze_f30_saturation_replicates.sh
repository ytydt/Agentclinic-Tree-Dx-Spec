#!/usr/bin/env bash
# Aggregate completed F30 saturation replicates (mirrors F8 9-run lane).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=src

RUN_DIRS=()
for idx in 1 02 03 04 05 06 07 08 09; do
  dir="$ROOT/logs/l1_bfs_adaptive_stop/f30_saturation_t0_r${idx}"
  if [[ ! -d "$dir/full_traces" ]]; then
    continue
  fi
  count="$(find "$dir/full_traces" -maxdepth 1 -name '*.json' | wc -l)"
  if [[ "$count" -eq 17 ]]; then
    RUN_DIRS+=("$dir")
  fi
done

if [[ "${#RUN_DIRS[@]}" -eq 0 ]]; then
  echo "no completed F30 replicate runs found" >&2
  exit 1
fi

out="$ROOT/logs/l1_bfs_adaptive_stop/f30_saturation_t0_replicate_verification_v1.json"
python scripts/analyze_l1_bfs_budget_saturation.py \
  "${RUN_DIRS[@]}" \
  --profile p5_headline \
  --n-boot 10000 \
  --output "$out"
echo "wrote $out (${#RUN_DIRS[@]} runs)"
