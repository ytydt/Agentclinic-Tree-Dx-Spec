#!/usr/bin/env bash
# §26.5 (new-5) controlled-variable MATRIX — measures the objective effect of the
# detox / mandatory-kb-branches / phase-subaxis fixes.
#
# Empirical anchor (from the completed §25.4 #1 matrix, K=5, 45 scored each):
#   bk_off 33.3% | bk_on 42.2% | rp_on_bk_off 28.9% | rp_on_bk_on 22.2%
# → retrieval-priority (#1) HURTS (esp. -20pp with bk on); branch-knowledge HELPS
#   when rp is OFF. So the strongest base is bk_on (rp OFF), which is ALSO required
#   by mandatory/phase (they need --branch-knowledge). We therefore anchor the
#   §26.5 factors on bk_on (rp OFF):
#
#   factor D = lr-detox              (--lr-detox)              [independent]
#   factor M = mandatory-kb-branches (--mandatory-kb-branches) [needs bk]
#   factor P = phase-subaxis         (--phase-subaxis)         [needs bk]
#
# OFAT + full-stack (baseline bk_on already 5/5, NOT re-run here):
#   n5_detox  = bk_on +D
#   n5_mand   = bk_on +M
#   n5_phase  = bk_on +P
#   n5_full   = bk_on +D+M+P
# Plus a RESCUE diagnostic on the regressed arm (baseline = rp_on_bk_on, 5/5):
#   n5_rp_full = rp_on_bk_on + full §26.5 stack  (can §26.5 recover case 17/22?)
#
# Harness: §26.6 — workers=9 (all 9 cases concurrent), per-case cap 25640s
# (2× max single-case dt), NO rigid per-repeat limit, MAX_PARALLEL=4 (4×9=36).
# CHAINED: waits for the old-path fill ("OLD-PATH FILL DONE") so total endpoint
# concurrency stays ≤ ~40.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=9
TEMP=0
CASE_TIMEOUT=25640
MAX_PARALLEL=4

# ── wait for the old-path fill to finish ──────────────────────────────────────
echo "[$(date +%H:%M:%S)] waiting for old-path fill ('OLD-PATH FILL DONE')…"
for _ in $(seq 1 2880); do          # up to ~24h (2880 × 30s)
  if grep -q "OLD-PATH FILL DONE" logs/run_oldpath_fill_driver.out 2>/dev/null; then
    echo "[$(date +%H:%M:%S)] old-path fill finished — proceeding to §26.5 matrix."
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

BK="--fix-a2 --fix-b --branch-knowledge"
run_arm n5_detox  "$BK --lr-detox"
run_arm n5_mand   "$BK --mandatory-kb-branches"
run_arm n5_phase  "$BK --phase-subaxis"
run_arm n5_full   "$BK --lr-detox --mandatory-kb-branches --phase-subaxis"
run_arm n5_rp_full "--fix-a2 --fix-b --retrieval-priority --branch-knowledge --lr-detox --mandatory-kb-branches --phase-subaxis"
echo "[$(date +%H:%M:%S)] ===== §26.5 (n5) MATRIX DONE ====="
