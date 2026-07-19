#!/usr/bin/env bash
# §30 NO-CACHE rematrix: re-run the recent matrices (#1 / n5 / rq / nrq / u29)
# with the tier-2 RAG-LR cache DISABLED (`--no-secondary-cache`), so every RAG
# LR is recomputed from raw data. This removes the confound of stale
# cross-generation cache entries (computed under older/buggy code) that bypass
# the fixed quantification path. Tags are prefixed `nc_` so this is an ADDITIONAL
# matrix that NEVER overwrites the original cached results.
#
# Uses the §30 hybrid scheduler (1 rep/GPU + CPU_SLOTS reps/CPU, per-case resume,
# single-process retry, CPU pin for repeat crashers).
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
# set scheduler knobs BEFORE sourcing run_lib.sh (it uses := defaults)
export EXTRA_FLAGS="--no-secondary-cache"
export CPU_SLOTS="${CPU_SLOTS:-3}"   # 3 GPU + 3 CPU = 6-way
source scripts/run_lib.sh

K="${K:-5}"

A2B="--fix-a2 --fix-b"
BK="$A2B --branch-knowledge"

expand () { local base="$1" flags="$2"; for k in $(seq 1 $K); do echo "nc_${base}_${k}|${flags}"; done; }

JOBS=()
while IFS= read -r j; do JOBS+=("$j"); done < <(
  # ── matrix #1 (bk × retrieval-priority) ──
  expand bk_off        "$A2B"
  expand bk_on         "$BK"
  expand rp_on_bk_off  "$A2B --retrieval-priority"
  expand rp_on_bk_on   "$BK --retrieval-priority"
  # ── rq (retrieval-quality #2/#3 stacked on #1) ──
  expand rq_mg         "$A2B --retrieval-priority --match-guards"
  expand rq_cc         "$A2B --retrieval-priority --confidence-cascade"
  expand rq_mg_cc      "$A2B --retrieval-priority --match-guards --confidence-cascade"
  # ── n5 (§26.5 anchored on bk_on) ──
  expand n5_detox      "$BK --lr-detox"
  expand n5_mand       "$BK --mandatory-kb-branches"
  expand n5_phase      "$BK --phase-subaxis"
  expand n5_full       "$BK --lr-detox --mandatory-kb-branches --phase-subaxis"
  expand n5_rp_full    "$BK --retrieval-priority --lr-detox --mandatory-kb-branches --phase-subaxis"
  # ── nrq (#2/#3 without #1) ──
  expand nrq_mg        "$A2B --match-guards"
  expand nrq_cc        "$A2B --confidence-cascade"
  expand nrq_mg_cc     "$A2B --match-guards --confidence-cascade"
  # ── u29 (§27.6 upstream fixes on bk backbone) ──
  expand u29_bk        "$BK"
  expand u29_mand      "$BK --mandatory-kb-branches"
  expand u29_clean     "$BK --lr-clean"
  expand u29_mand_clean "$BK --mandatory-kb-branches --lr-clean"
  expand u29_full      "$BK --mandatory-kb-branches --lr-clean --phase-subaxis"
)
echo "[$(date +%H:%M:%S)] ===== §30 NO-CACHE rematrix: ${#JOBS[@]} reps ====="
run_reps "${JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== §30 NO-CACHE rematrix COMPLETE ====="
