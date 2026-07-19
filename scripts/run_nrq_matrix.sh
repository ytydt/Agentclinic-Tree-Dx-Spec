#!/usr/bin/env bash
# §26.8 — #2/#3 retrieval-quality matrix WITHOUT #1 (no --retrieval-priority).
#
# Rationale: the original rq matrix (rq_mg/rq_cc/rq_mg_cc) was anchored on
# `--retrieval-priority` (#1), which the §26.7 #1 matrix proved HARMFUL
# (-4.4pp bk_off, -20pp bk_on). So #2/#3 marginal effects there are confounded.
# This matrix re-runs #2/#3 on the clean rp-OFF base, mirroring the original
# structure with #1 removed. Baseline cell (G=off,C=off) == `bk_off`
# (--fix-a2 --fix-b), ALREADY collected at K=5 (33.3%), so we only add 3 arms:
#   nrq_mg    = base +#2          (--match-guards)
#   nrq_cc    = base     +#3      (--confidence-cascade)
#   nrq_mg_cc = base +#2 +#3      (--match-guards --confidence-cascade)
# Comparing to the rp-ON rq matrix shows whether #2/#3 depend on #1.
#
# Harness: §26.6 — workers=9 (all 9 concurrent), per-case cap 25640s, no rigid
# per-repeat limit, MAX_PARALLEL=4. CHAINED after the §26.5 (n5) matrix so total
# endpoint concurrency stays ≤ ~40.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=9
TEMP=0
CASE_TIMEOUT=25640
MAX_PARALLEL=4

# ── wait for the §26.5 (n5) matrix to finish ─────────────────────────────────
echo "[$(date +%H:%M:%S)] waiting for n5 matrix ('§26.5 (n5) MATRIX DONE')…"
for _ in $(seq 1 5760); do          # up to ~48h (5760 × 30s)
  if grep -q "(n5) MATRIX DONE" logs/run_n5_matrix_driver.out 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] n5 matrix finished — proceeding to nrq matrix."
    break
  fi
  sleep 30
done

run_arm () {
  local name="$1"; shift
  local flags="$*"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} flags='${flags}' K=${K} workers=${WORKERS} case_timeout=${CASE_TIMEOUT}s ====="
  local batch=()
  for k in $(seq 1 $K); do
    conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
        --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
        --temp "$TEMP" $flags \
        --tag "${name}_${k}" > "logs/run_${name}_${k}.out" 2>&1 &
    batch+=("$!")
    sleep 3
    if [ "${#batch[@]}" -ge "$MAX_PARALLEL" ]; then
      wait "${batch[@]}"; batch=()
    fi
  done
  [ "${#batch[@]}" -gt 0 ] && wait "${batch[@]}"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} DONE ====="
}

BASE="--fix-a2 --fix-b"
run_arm nrq_mg    "$BASE --match-guards"
run_arm nrq_cc    "$BASE --confidence-cascade"
run_arm nrq_mg_cc "$BASE --match-guards --confidence-cascade"
echo "[$(date +%H:%M:%S)] ===== #2/#3 (no-#1) NRQ MATRIX DONE ====="
