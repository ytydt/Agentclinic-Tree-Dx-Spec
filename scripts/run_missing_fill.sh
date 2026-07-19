#!/usr/bin/env bash
# §26.6 harness change: fill missing repeats with the new per-case discipline —
# NO rigid per-repeat (9-question) timeout. Each repeat runs all 9 cases
# concurrently (workers=9) under a PER-CASE wall cap (--case-timeout = 2× max
# observed single-case dt ≈ 25640s). OpenRouter tolerates ~40 concurrent calls,
# so MAX_PARALLEL=4 repeats (4×9=36) run together.
#
# Missing as of 16:xx:
#   rp_on_bk_off : reps 1,3,4,5  (only rep2 produced a JSON)
#   bk_on        : rep 3
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)
MAX_PARALLEL=4     # repeats in flight (4×9=36 ≤ ~40 OpenRouter ceiling)

# (tag, repeat, flags) triples — one line each.
JOBS=(
  "rp_on_bk_off 1 --fix-a2 --fix-b --retrieval-priority"
  "rp_on_bk_off 3 --fix-a2 --fix-b --retrieval-priority"
  "rp_on_bk_off 4 --fix-a2 --fix-b --retrieval-priority"
  "rp_on_bk_off 5 --fix-a2 --fix-b --retrieval-priority"
  "bk_on 3 --fix-a2 --fix-b --branch-knowledge"
)

batch=()
for job in "${JOBS[@]}"; do
  read -r tag k flags <<< "$job"
  echo "[$(date +%H:%M:%S)] launch ${tag}_${k} (workers=${WORKERS}, case_timeout ${CASE_TIMEOUT}s) flags='${flags}'"
  conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
      --temp "$TEMP" $flags \
      --tag "${tag}_${k}" > "logs/run_${tag}_${k}.out" 2>&1 &
  batch+=("$!")
  sleep 2
  if [ "${#batch[@]}" -ge "$MAX_PARALLEL" ]; then
    wait "${batch[@]}"; batch=()
  fi
done
[ "${#batch[@]}" -gt 0 ] && wait "${batch[@]}"
echo "[$(date +%H:%M:%S)] ===== missing-fill DONE ====="
