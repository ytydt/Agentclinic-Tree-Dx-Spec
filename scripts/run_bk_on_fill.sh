#!/usr/bin/env bash
# §26.6 harness change: fill the 3 bk_on repeats (2,3,4) with the new per-case
# discipline — NO rigid per-repeat (9-question) timeout. Each repeat runs all 9
# cases concurrently (workers=9) under a PER-CASE wall cap (--case-timeout = 2×
# max observed single-case dt ≈ 25640s). 3 repeats × 9 = 27 concurrent calls,
# within OpenRouter's ~40 ceiling. accuracy is latency-independent (temp=0).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)

pids=()
for k in 2 3 4; do
  echo "[$(date +%H:%M:%S)] launch bk_on_${k} (workers=${WORKERS}, case_timeout ${CASE_TIMEOUT}s)"
  conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
      --temp "$TEMP" \
      --fix-a2 --fix-b --branch-knowledge \
      --tag "bk_on_${k}" > "logs/run_bk_on_${k}.out" 2>&1 &
  pids+=("$!")
  sleep 2
done
echo "[$(date +%H:%M:%S)] launched pids: ${pids[*]} — waiting…"
wait "${pids[@]}"
echo "[$(date +%H:%M:%S)] ===== bk_on fill DONE ====="
