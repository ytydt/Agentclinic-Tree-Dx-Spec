#!/usr/bin/env bash
# Collapse3c converts well (conv|both 0.65 on MCR) but recalls badly: pool recall
# 0.385/0.390 against the original APHHM's 0.555/0.530. Offline union measurements
# showed the ceiling is set by stance diversity, not by budget: our four arms all
# condition on the same C1 ledger and pool to 0.530/0.445, while three genuinely
# different stances reach 0.590/0.495 at ~10 candidates versus APHHM's ~31 nodes.
# This arm buys that diversity with one generation call per stance (commit /
# coverage / mechanism) and protects conversion by deciding as a tournament:
# one finalist per stance first, then a final between finalists, so no single
# comparison is wider than the ~5 where our selector performed best.
# Budget: C1 + 3 stances + selector = 5 calls, 6 when the gap lane fires.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_multistance_master.log"
: >"$MASTER"

LIMIT="${LIMIT:-0}"
ARM="${ARM:-aphhm_c_multistance_v1}"

run() {
  local ds="$1" arm="$2" logfile="$3"
  echo "### START $ds $arm $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$LIMIT" != "0" ]] && extra+=(--limit "$LIMIT")
  if [[ "$ds" == medcasereasoning* ]]; then
    extra+=(--mcr-judge-workers 50)
  fi
  python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
    --mode multistance --stances commit,coverage,mechanism --axis-mode off \
    --unique-budget 10 --workers 32 --score "${extra[@]}" >>"$logfile" 2>&1
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena   "$ARM" "$LOG/${ARM}_da_seq100.log" &
run medcasereasoning "$ARM" "$LOG/${ARM}_mcr_v1.log" &
if [[ "$LIMIT" == "0" ]]; then
  run diagnosisarena_heldout "$ARM" "$LOG/${ARM}_da_heldout.log" &
  run medcasereasoning_v2    "$ARM" "$LOG/${ARM}_mcr_v2.log" &
fi
wait
echo APHHM_C_MULTISTANCE_DONE | tee -a "$MASTER"
