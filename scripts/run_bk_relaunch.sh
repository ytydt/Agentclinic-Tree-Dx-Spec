#!/usr/bin/env bash
# §23.14 branch-knowledge ablation — RELAUNCH of the arms not completed in the
# first run (bk_off_1 hung on case_18 → its whole arm's wait blocked bk_on).
#
# §26.6 harness change: the single non-terminating case is now contained by a
# PER-CASE wall cap (--case-timeout) INSIDE the eval (it records status=TIMEOUT
# and hard-exits), so there is NO rigid per-repeat (9-question) timeout. Each
# repeat runs all 9 cases concurrently (workers=9). OpenRouter tolerates ~40
# concurrent calls here.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
WORKERS=9          # all 9 cases concurrent within a repeat
TEMP=0
CASE_TIMEOUT=25640 # per-case wall cap (2× max observed single-case dt)

run_repeat () {
  local name="$1"; shift
  local flags="$*"
  echo "[$(date +%H:%M:%S)] launch ${name} flags='${flags}' (case_timeout ${CASE_TIMEOUT}s)"
  conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --case-timeout "$CASE_TIMEOUT" \
      --temp "$TEMP" $flags \
      --tag "${name}" > "logs/run_${name}.out" 2>&1 &
}

# Arm bk_off: only repeat 1 is missing (2-5 completed in the first run).
echo "[$(date +%H:%M:%S)] ===== ARM bk_off (relaunch repeat 1 only) ====="
run_repeat bk_off_1 "--fix-a2 --fix-b"
wait
echo "[$(date +%H:%M:%S)] ===== bk_off_1 done ====="

# Arm bk_on: full K=5 (never ran in the first attempt).
echo "[$(date +%H:%M:%S)] ===== ARM bk_on (full K=5) ====="
pids=()
for k in 1 2 3 4 5; do
  run_repeat "bk_on_${k}" "--fix-a2 --fix-b --branch-knowledge"
  pids+=("$!")
  sleep 1
done
echo "[$(date +%H:%M:%S)] bk_on launched pids: ${pids[*]} — waiting…"
wait "${pids[@]}"
echo "[$(date +%H:%M:%S)] ===== ALL RELAUNCH ARMS DONE ====="
