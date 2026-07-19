#!/usr/bin/env bash
# §25.2(#1) × §23.14 controlled-variable MATRIX (2×2 over two factors):
#   factor R = retrieval-priority (HPO-exact ≥ fuzzy)   : off | on (--retrieval-priority)
#   factor B = branch-knowledge   (KB-anchored branches) : off | on (--branch-knowledge)
#
# All arms share the §24.1 best base (--fix-a2 --fix-b). The two R=off arms are
# ALREADY collected (rp_off_bk_off == bk_off n=5; rp_off_bk_on == bk_on n=5 after
# the fill run). This script CHAINS off the fill run and then collects the two
# NEW R=on arms to complete the matrix:
#   rp_on_bk_off  = --fix-a2 --fix-b --retrieval-priority
#   rp_on_bk_on   = --fix-a2 --fix-b --retrieval-priority --branch-knowledge
#
# §26.6 harness change: NO rigid per-repeat (9-question) timeout. Each case runs
# concurrently (workers=9) under a PER-CASE wall cap (--case-timeout = 2× max
# observed single-case dt ≈ 25640s); the repeat is bounded by the slowest case.
# OpenRouter tolerates ~40 concurrent calls here, so MAX_PARALLEL=4 (4×9=36) is
# safe — the earlier "throttle" diagnosis (workers=3) was over-conservative.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)
MAX_PARALLEL=4     # repeats in flight (4×9=36 ≤ ~40 OpenRouter ceiling)

# ── 1. WAIT for the in-flight bk_on fill run to finish ────────────────────────
echo "[$(date +%H:%M:%S)] waiting for bk_on fill (run_bk_on_fill_driver.out: 'fill DONE')…"
for _ in $(seq 1 720); do          # up to ~6h (720 × 30s)
  if grep -q "fill DONE" logs/run_bk_on_fill_driver.out 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] fill run finished — proceeding to matrix."
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
    # Barrier: once MAX_PARALLEL repeats are in flight, wait for the whole batch
    # before launching more (simple, correct bound on endpoint load).
    if [ "${#batch[@]}" -ge "$MAX_PARALLEL" ]; then
      wait "${batch[@]}"
      batch=()
    fi
  done
  [ "${#batch[@]}" -gt 0 ] && wait "${batch[@]}"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} DONE ====="
}

run_arm rp_on_bk_off "--fix-a2 --fix-b --retrieval-priority"
run_arm rp_on_bk_on  "--fix-a2 --fix-b --retrieval-priority --branch-knowledge"
echo "[$(date +%H:%M:%S)] ===== MATRIX (R=on arms) DONE ====="
