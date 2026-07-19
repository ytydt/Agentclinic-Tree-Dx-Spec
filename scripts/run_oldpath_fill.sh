#!/usr/bin/env bash
# §26.6 OLD-PATH backfill: re-run every previously-failed/missing repeat of the
# baseline (pre-§26.5) controlled-variable arms, using the NEW per-case-timeout
# harness — NO rigid per-repeat (9-question) limit, all 9 cases concurrent,
# per-case wall cap = 2× max observed single-case dt (25640s). This completes
# the comparison table so the §26.5 fixes can later be measured against a full
# baseline. NONE of these arms enable §26.5 flags (--lr-detox /
# --mandatory-kb-branches / --phase-subaxis) — they are the OLD path.
#
# Already-complete arms (5/5, NOT re-run): bk_off.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)
MAX_PARALLEL=4     # repeats in flight (4×9=36 ≤ ~40 OpenRouter ceiling)

# (tag, repeat, flags) — only the MISSING repeats of each old-path arm.
JOBS=(
  "bk_on 3 --fix-a2 --fix-b --branch-knowledge"
  "rp_on_bk_off 5 --fix-a2 --fix-b --retrieval-priority"
  "rp_on_bk_on 2 --fix-a2 --fix-b --retrieval-priority --branch-knowledge"
  "rq_mg 2 --fix-a2 --fix-b --retrieval-priority --match-guards"
  "rq_mg 4 --fix-a2 --fix-b --retrieval-priority --match-guards"
  "rq_mg 5 --fix-a2 --fix-b --retrieval-priority --match-guards"
  "rq_cc 1 --fix-a2 --fix-b --retrieval-priority --confidence-cascade"
  "rq_cc 2 --fix-a2 --fix-b --retrieval-priority --confidence-cascade"
  "rq_cc 4 --fix-a2 --fix-b --retrieval-priority --confidence-cascade"
  "rq_cc 5 --fix-a2 --fix-b --retrieval-priority --confidence-cascade"
  "rq_mg_cc 1 --fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
  "rq_mg_cc 2 --fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
  "rq_mg_cc 3 --fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
  "rq_mg_cc 4 --fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
  "rq_mg_cc 5 --fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
)

echo "[$(date +%H:%M:%S)] ===== OLD-PATH FILL: ${#JOBS[@]} repeats, workers=${WORKERS}, case_timeout=${CASE_TIMEOUT}s, max_parallel=${MAX_PARALLEL} ====="
batch=()
for job in "${JOBS[@]}"; do
  read -r tag k flags <<< "$job"
  echo "[$(date +%H:%M:%S)] launch ${tag}_${k} flags='${flags}'"
  conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
      --temp "$TEMP" $flags \
      --tag "${tag}_${k}" > "logs/run_${tag}_${k}.out" 2>&1 &
  batch+=("$!")
  sleep 3
  if [ "${#batch[@]}" -ge "$MAX_PARALLEL" ]; then
    wait "${batch[@]}"; batch=()
  fi
done
[ "${#batch[@]}" -gt 0 ] && wait "${batch[@]}"
echo "[$(date +%H:%M:%S)] ===== OLD-PATH FILL DONE ====="
