#!/usr/bin/env bash
# §17.3 put conversion on a line that falls ~4.6pp per extra candidate, and §16.5
# ruled out fixing it with deterministic post-processing, which leaves the
# decision structure itself as the only untried lever. This arm splits the
# tournament into two calls: one round nominates a finalist per stance, a second
# round does nothing but adjudicate those finalists against the vignette.
#
# Pre-registered acceptance: on the same ~9-wide pool, conv must beat the fitted
# line by at least 0.10 more than the single-call tournament does, i.e.
#   DA  conv >= 0.477  (line 0.314 at width 9.04, current residual +0.065)
#   MCR conv >= 0.566  (line 0.424 at width 8.75, current residual +0.042)
# Anything less means the single-call version was not losing the final for want
# of attention, and the line is the paradigm's ceiling.
#
# Budget: C1 + 3 stances + nomination + final = 6 calls, 7 with the gap lane.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
ARM="${ARM:-aphhm_c_msplit_v1}"
LIMIT="${LIMIT:-0}"
MASTER="$LOG/${ARM}_master.log"
: >"$MASTER"

run() {
  local ds="$1" logfile="$2"
  echo "### START $ds $ARM $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  local extra=()
  [[ "$LIMIT" != "0" ]] && extra+=(--limit "$LIMIT")
  [[ "$ds" == medcasereasoning* ]] && extra+=(--mcr-judge-workers 50)
  python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$ARM" \
    --mode multistance_split --stances commit,coverage,mechanism --axis-mode off \
    --unique-budget 10 --workers 32 --score "${extra[@]}" >>"$logfile" 2>&1
  echo "### DONE $ds $ARM exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

run diagnosisarena         "$LOG/${ARM}_da_seq100.log" &
run medcasereasoning       "$LOG/${ARM}_mcr_v1.log" &
if [[ "$LIMIT" == "0" ]]; then
  run diagnosisarena_heldout "$LOG/${ARM}_da_heldout.log" &
  run medcasereasoning_v2    "$LOG/${ARM}_mcr_v2.log" &
fi
wait
echo APHHM_C_MSPLIT_DONE | tee -a "$MASTER"
