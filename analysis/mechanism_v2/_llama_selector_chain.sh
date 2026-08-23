#!/usr/bin/env bash
set -u
PY=/home/wanghongyi/.conda/envs/gnn-llm/bin/python
OUT=/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/analysis/mechanism_v2/results/SLOT_YIELD_BREAKTHROUGH_LLAMA_SELECTOR
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
MODEL=meta-llama/llama-3.3-70b-instruct

if [ -n "${WAIT_PID:-}" ]; then
  echo "[llama] waiting for pid ${WAIT_PID}"
  while kill -0 "${WAIT_PID}" 2>/dev/null; do sleep 20; done
  echo "[llama] pid ${WAIT_PID} finished"
fi

for arm in A0_control A1_views A2_views_typed A3_full B1_corelift; do
  echo "[llama] ${arm} at $(date -Is)"
  ${PY} analysis/mechanism_v2/corelift_experiment.py \
    --out "${OUT}" \
    --selector-model "${MODEL}" \
    --arm "${arm}" --workers 24 \
    --call-timeout 300 --max-retries 4
  echo "[llama] ${arm} first-pass exit=$? at $(date -Is)"
  ${PY} analysis/mechanism_v2/corelift_experiment.py \
    --out "${OUT}" \
    --selector-model "${MODEL}" \
    --arm "${arm}" --workers 16 --retry-failures \
    --call-timeout 420 --max-retries 5
  echo "[llama] ${arm} retry exit=$? at $(date -Is)"
done

${PY} analysis/mechanism_v2/corelift_experiment.py \
  --out "${OUT}" --selector-model "${MODEL}" --finalize
echo "[llama] finalized at $(date -Is)"
