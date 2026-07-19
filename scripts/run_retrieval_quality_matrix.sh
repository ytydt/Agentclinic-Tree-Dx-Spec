#!/usr/bin/env bash
# §25.2(#2)/(#3) controlled-variable MATRIX, layered on top of the
# already-confirmed (#1) retrieval-priority fix (kept ON in EVERY arm — we do
# NOT re-enumerate #1, per the design decision that #1 is necessarily correct).
#
#   factor G = match-guards        (#2): off | on (--match-guards)
#   factor C = confidence-cascade  (#3): off | on (--confidence-cascade)
#
# All arms share the §24.1 best base (--fix-a2 --fix-b) AND #1 (--retrieval-priority),
# branch-knowledge OFF (isolate retrieval-quality factors). The (G=off,C=off) cell
# == rp_on_bk_off, ALREADY collected by run_retrieval_x_branch_matrix.sh — so we
# only collect the 3 NEW cells:
#   rq_mg     = base #1 +#2            (--match-guards)
#   rq_cc     = base #1     +#3        (--confidence-cascade)
#   rq_mg_cc  = base #1 +#2 +#3        (--match-guards --confidence-cascade)
#
# §26.6 harness change: NO rigid per-repeat (9-question) timeout. Instead each
# case runs concurrently (workers=9 → all 9 start at once) under a PER-CASE wall
# cap (--case-timeout = 2× observed max single-case dt ≈ 2×12820 = 25640s). The
# repeat is naturally bounded by the slowest case. OpenRouter tolerates ~40
# concurrent calls in this network, so MAX_PARALLEL=4 repeats (4×9=36 calls) is
# safe and saturates throughput.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)
MAX_PARALLEL=4     # repeats in flight (4×9=36 ≤ ~40 OpenRouter ceiling)
BASE="--fix-a2 --fix-b --retrieval-priority"

# ── 1. WAIT for the in-flight R=on matrix to finish ───────────────────────────
echo "[$(date +%H:%M:%S)] waiting for R=on matrix ('MATRIX (R=on arms) DONE')…"
for _ in $(seq 1 1440); do          # up to ~12h (1440 × 30s)
  if grep -q "MATRIX (R=on arms) DONE" logs/run_matrix_driver.out 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] R=on matrix finished — proceeding to retrieval-quality matrix."
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
    sleep 2
    if [ "${#batch[@]}" -ge "$MAX_PARALLEL" ]; then
      wait "${batch[@]}"
      batch=()
    fi
  done
  [ "${#batch[@]}" -gt 0 ] && wait "${batch[@]}"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} DONE ====="
}

run_arm rq_mg    "$BASE --match-guards"
run_arm rq_cc    "$BASE --confidence-cascade"
run_arm rq_mg_cc "$BASE --match-guards --confidence-cascade"
echo "[$(date +%H:%M:%S)] ===== RETRIEVAL-QUALITY MATRIX (#2/#3 on #1) DONE ====="
