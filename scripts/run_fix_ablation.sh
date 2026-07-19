#!/usr/bin/env bash
# §22 controlled-variable ablation for the corrected fixes (A′/B′).
# Single-factor design, K repeats/arm, temp=0, 9-case text subset.
# Runs arms SEQUENTIALLY (each arm = K concurrent repeats) to bound the
# remote endpoint concurrency (~K*workers simultaneous LLM calls).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=5
TEMP=0

run_arm () {
  local name="$1"; shift
  local flags="$*"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} flags='${flags}' K=${K} ====="
  local pids=()
  for k in $(seq 1 $K); do
    conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --temp "$TEMP" $flags \
      --tag "${name}_${k}" > "logs/run_${name}_${k}.out" 2>&1 &
    pids+=("$!")
    sleep 1
  done
  echo "[$(date +%H:%M:%S)] arm ${name} launched pids: ${pids[*]} — waiting…"
  wait "${pids[@]}"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} DONE ====="
}

run_arm base2 ""
run_arm a2    "--fix-a2"
run_arm b2    "--fix-b"
run_arm a2b2  "--fix-a2 --fix-b"
echo "[$(date +%H:%M:%S)] ALL ARMS DONE"
