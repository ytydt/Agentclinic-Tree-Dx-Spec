#!/usr/bin/env bash
# Evidence-form factor. Both arms use the axis-free evid contract at K=10, so the
# only change from NoAxis is what the selector reads:
#   CandEv   = C1+C3+C4+selector (4 calls); selector reads per-candidate spans
#              instead of ledger cells. Isolates the evidence form exactly.
#   Collapse = C1+C3+selector (3 calls); C4 dropped. Same budget as B07/Lite.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper
LOG=logs/backbone_v1
MASTER="$LOG/aphhm_c_candev_master.log"
: >"$MASTER"

run() {
  local ds="$1" arm="$2" mode="$3" logfile="$4"
  echo "### START $ds $arm mode=$mode $(date -Is)" | tee -a "$MASTER" >>"$logfile"
  if [[ "$ds" == medcasereasoning* ]]; then
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode "$mode" --concept-contract evid --axis-mode off \
      --unique-budget 10 --workers 32 --score --mcr-judge-workers 50 >>"$logfile" 2>&1
  else
    python3 -u scripts/paper/run_aphhm_c.py --dataset "$ds" --arm "$arm" \
      --mode "$mode" --concept-contract evid --axis-mode off \
      --unique-budget 10 --workers 32 --score >>"$logfile" 2>&1
  fi
  echo "### DONE $ds $arm exit=$? $(date -Is)" | tee -a "$MASTER" >>"$logfile"
}

for spec in "aphhm_c_candev_v1 c4_selector_candev" \
            "aphhm_c_collapse3_v1 c4_selector_candev_nomatrix"; do
  set -- $spec
  arm="$1"; mode="$2"
  run diagnosisarena         "$arm" "$mode" "$LOG/${arm}_da_seq100.log" &
  run diagnosisarena_heldout "$arm" "$mode" "$LOG/${arm}_da_heldout.log" &
  run medcasereasoning       "$arm" "$mode" "$LOG/${arm}_mcr_v1.log" &
  run medcasereasoning_v2    "$arm" "$mode" "$LOG/${arm}_mcr_v2.log" &
done
wait
echo APHHM_C_CANDEV_DONE | tee -a "$MASTER"
