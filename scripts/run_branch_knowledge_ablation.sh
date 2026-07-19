#!/usr/bin/env bash
# §23.14 controlled-variable ablation for KB-anchored branch generation (Mode A).
# Single factor: --branch-knowledge OFF (legacy pure-LLM path) vs ON
# (deterministic syndrome→axis L1 domain partition + entity down-push).
# K repeats/arm, temp=0, 9-case text subset. Arms run SEQUENTIALLY; each arm =
# K concurrent repeats (bounds the remote endpoint at ~K*WORKERS calls).
#
# The OFF arm reproduces the legacy BranchCreator payload byte-for-byte
# (_build_branch_candidates returns None), so any delta is attributable to the
# branch-knowledge factor alone. We pair it with --fix-a2 --fix-b (the best §24.1
# arm) to measure whether deterministic L1 anchoring REDUCES the §22.8 branch-set
# variance on top of the entity/anti-anchoring fixes.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true

CASES="1,9,13,14,17,18,22,23,24"
K=5
WORKERS=5
TEMP=0

run_arm () {
  local name="$1"; shift
  local flags="$*"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} flags='${flags}' K=${K} ====="
  local pids=()
  for k in $(seq 1 $K); do
    conda run -n gnn-llm python scripts/eval_pipeline_medbullets.py \
      --cases "$CASES" --workers "$WORKERS" --temp "$TEMP" $flags \
      --tag "${name}_${k}" > "logs/run_${name}_${k}.out" 2>&1 &
    pids+=("$!")
    sleep 1
  done
  echo "[$(date +%H:%M:%S)] arm ${name} launched pids: ${pids[*]} — waiting…"
  wait "${pids[@]}"
  echo "[$(date +%H:%M:%S)] ===== ARM ${name} DONE ====="
}

# Factor isolation against the strongest §24.1 baseline (a2b2):
run_arm bk_off "--fix-a2 --fix-b"
run_arm bk_on  "--fix-a2 --fix-b --branch-knowledge"
echo "[$(date +%H:%M:%S)] ALL ARMS DONE"
