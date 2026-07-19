#!/usr/bin/env bash
# §31.9 K=10 extension batch 2: +5 reps (rep 6–10) for three additional arms.
#   nc_nrq_cc      (confidence-cascade, NO retrieval-priority — nrq backbone)
#   nc_u29_mand    (mandatory-kb-branches on bk backbone)
#   nc_nrq_mg_cc   (match-guards + confidence-cascade, NO retrieval-priority)
# ALL --no-secondary-cache; nc_ tags only.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

export EXTRA_FLAGS="--no-secondary-cache"
export CPU_SLOTS="${CPU_SLOTS:-3}"
source scripts/run_lib.sh

A2B="--fix-a2 --fix-b"
BK="$A2B --branch-knowledge"

expand () {
  local base="$1" flags="$2"
  for k in $(seq 6 10); do echo "${base}_${k}|${flags}"; done
}

JOBS=()
while IFS= read -r j; do JOBS+=("$j"); done < <(
  expand nc_nrq_cc     "$A2B --confidence-cascade"
  expand nc_u29_mand  "$BK --mandatory-kb-branches"
  expand nc_nrq_mg_cc  "$A2B --match-guards --confidence-cascade"
)

echo "[$(date +%H:%M:%S)] ===== §31.9 K=10 extension batch2 (nrq cc/mg+cc): ${#JOBS[@]} reps ====="
run_reps "${JOBS[@]}"
echo "[$(date +%H:%M:%S)] ===== §31.9 K=10 extension batch2 COMPLETE ====="
