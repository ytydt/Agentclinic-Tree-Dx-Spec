#!/usr/bin/env bash
# §29 upstream-fix matrix. Backbone = bk_on (the §28 strongest baseline:
# --branch-knowledge, retrieval-priority #1 OFF because it is harmful).
#
# Bugfixes ② (_LR_RE regex + float guard) and ④ (mandatory entity-set dedup) are
# ALWAYS-ON in code, so every arm here already carries them. The flag-gated
# upstream fixes under test are:
#   --lr-clean             ① purified secondary cache (strip ungrounded heuristic
#                            LR → context-only; stricter than --lr-detox)
#   --mandatory-kb-branches  mand — promoted to its §29 role: VARIANCE REDUCTION
#                            (guarantee the gold entity always has a home branch)
#   --phase-subaxis        ③ ADDITIVE blast-crisis sub-branch (keeps broad parent)
#
# Reliability: run_lib.sh now does SINGLE-PROCESS retry + CPU fallback (§29), so
# a persistently GPU-crashing repeat completes on CPU instead of being lost.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
source scripts/run_lib.sh

K=5
BK="--fix-a2 --fix-b --branch-knowledge"
expand () {
  local base="$1"; local flags="$2"
  for k in $(seq 1 $K); do echo "${base}_${k}|${flags}"; done
}

echo "[$(date +%H:%M:%S)] ===== §29 upstream-fix matrix (backbone=bk_on) ====="
JOBS=()
while IFS= read -r j; do JOBS+=("$j"); done < <(
  expand u29_bk         "$BK"
  expand u29_mand       "$BK --mandatory-kb-branches"
  expand u29_clean      "$BK --lr-clean"
  expand u29_mand_clean "$BK --mandatory-kb-branches --lr-clean"
  expand u29_full       "$BK --mandatory-kb-branches --lr-clean --phase-subaxis"
)
run_reps "${JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== §29 MATRIX COMPLETE ====="
