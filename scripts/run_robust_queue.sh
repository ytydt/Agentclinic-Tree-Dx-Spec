#!/usr/bin/env bash
# Robust orchestrator (GPU-balanced + crash-retry, concurrency UNCHANGED).
# Replaces the crash-prone tail of the old queue. Idempotently fills ALL missing
# repeats across three phases — already-collected repeats are skipped:
#   1) OLD-PATH fill   (re-runs crashed rq_mg_4/5, rq_cc_4/5, rq_mg_cc_5, …)
#   2) §26.5 (n5) matrix
#   3) #2/#3 (no-#1) nrq matrix
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
source scripts/run_lib.sh

K=5
expand () {  # arm_base | flags   →  emits "arm_base_k|flags" for k in 1..K
  local base="$1"; local flags="$2"
  for k in $(seq 1 $K); do echo "${base}_${k}|${flags}"; done
}

# ── wait for the in-flight old-path fill to drain its last batch ──────────────
echo "[$(date +%H:%M:%S)] waiting for old-path fill ('OLD-PATH FILL DONE')…"
for _ in $(seq 1 2880); do
  grep -q "OLD-PATH FILL DONE" logs/run_oldpath_fill_driver.out 2>/dev/null && break
  sleep 30
done
echo "[$(date +%H:%M:%S)] old-path fill drained — starting robust fill."

# ── Phase 1: OLD-PATH (fills only the crashed/missing reps) ───────────────────
echo "[$(date +%H:%M:%S)] ===== PHASE 1: OLD-PATH fill ====="
OLD_JOBS=()
while IFS= read -r j; do OLD_JOBS+=("$j"); done < <(
  expand bk_off          "--fix-a2 --fix-b"
  expand bk_on           "--fix-a2 --fix-b --branch-knowledge"
  expand rp_on_bk_off    "--fix-a2 --fix-b --retrieval-priority"
  expand rp_on_bk_on     "--fix-a2 --fix-b --retrieval-priority --branch-knowledge"
  expand rq_mg           "--fix-a2 --fix-b --retrieval-priority --match-guards"
  expand rq_cc           "--fix-a2 --fix-b --retrieval-priority --confidence-cascade"
  expand rq_mg_cc        "--fix-a2 --fix-b --retrieval-priority --match-guards --confidence-cascade"
)
run_reps "${OLD_JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== PHASE 1 DONE ====="

# ── Phase 2: §26.5 (n5) matrix ────────────────────────────────────────────────
echo "[$(date +%H:%M:%S)] ===== PHASE 2: §26.5 (n5) matrix ====="
BK="--fix-a2 --fix-b --branch-knowledge"
N5_JOBS=()
while IFS= read -r j; do N5_JOBS+=("$j"); done < <(
  expand n5_detox   "$BK --lr-detox"
  expand n5_mand    "$BK --mandatory-kb-branches"
  expand n5_phase   "$BK --phase-subaxis"
  expand n5_full    "$BK --lr-detox --mandatory-kb-branches --phase-subaxis"
  expand n5_rp_full "--fix-a2 --fix-b --retrieval-priority --branch-knowledge --lr-detox --mandatory-kb-branches --phase-subaxis"
)
run_reps "${N5_JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== PHASE 2 (n5) DONE ====="

# ── Phase 3: #2/#3 without #1 (nrq) matrix ───────────────────────────────────
echo "[$(date +%H:%M:%S)] ===== PHASE 3: #2/#3 no-#1 (nrq) matrix ====="
NRQ_JOBS=()
while IFS= read -r j; do NRQ_JOBS+=("$j"); done < <(
  expand nrq_mg    "--fix-a2 --fix-b --match-guards"
  expand nrq_cc    "--fix-a2 --fix-b --confidence-cascade"
  expand nrq_mg_cc "--fix-a2 --fix-b --match-guards --confidence-cascade"
)
run_reps "${NRQ_JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== PHASE 3 (nrq) DONE — ALL MATRICES COMPLETE ====="
