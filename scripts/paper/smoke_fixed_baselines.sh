#!/usr/bin/env bash
# Live smoke for corrected (non-placeholder) DiagnosisArena baselines.
# Runs limit=2 on d2_seq100_v1 with real API + shared KB; exits non-zero on errors.
#
# Usage:
#   bash scripts/paper/smoke_fixed_baselines.sh
#   LIMIT=3 WORKERS=2 bash scripts/paper/smoke_fixed_baselines.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

LIMIT="${LIMIT:-2}"
WORKERS="${WORKERS:-2}"
MAPPER_MODE="${MAPPER_MODE:-deterministic_gold_blind}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_fixed_smoke}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
PURE_ARMS="${PURE_ARMS:-B04-dual-inf,B05-mdagents,B06-mac-single-vendor}"
RAG_ARMS="${RAG_ARMS:-B02-flat-matched-rerank,B15-medprompt-style,B16-medrag-kg}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/smoke_fixed_${STAMP}.log}"

mkdir -p "$RUNS_ROOT" "$LOG_DIR"

if [[ -f "$(conda info --base)/etc/profile.d/conda.sh" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  set -u
fi

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export NUMEXPR_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 TREE_DX_EMBED_DEVICE=cpu
export RUNS_ROOT LIMIT PURE_ARMS RAG_ARMS

echo "[$(date +%F\ %T)] smoke limit=$LIMIT workers=$WORKERS"
echo "[$(date +%F\ %T)] runs_root=$RUNS_ROOT log=$LOG_FILE"

{
  echo "=== pure multi-step: $PURE_ARMS ==="
  python scripts/paper/run_baseline.py \
    --arms "$PURE_ARMS" \
    --subset-dir "$SUBSET_DIR" \
    --runs-root "$RUNS_ROOT" \
    --limit "$LIMIT" \
    --model "$MODEL" \
    --workers "$WORKERS" \
    --score \
    --mapper-mode "$MAPPER_MODE"

  echo "=== rag corrected: $RAG_ARMS ==="
  python scripts/paper/run_baseline.py \
    --arms "$RAG_ARMS" \
    --subset-dir "$SUBSET_DIR" \
    --runs-root "$RUNS_ROOT" \
    --limit "$LIMIT" \
    --model "$MODEL" \
    --workers "$WORKERS" \
    --executor process \
    --start-method spawn \
    --omp-threads 2 \
    --score \
    --mapper-mode "$MAPPER_MODE"

  python - <<'PY'
import json
import os
import sys
from pathlib import Path

runs = Path(os.environ.get("RUNS_ROOT", "runs/paper_v1/diagnosisarena_fixed_smoke"))
limit = int(os.environ.get("LIMIT", "2"))
arms = (
    os.environ.get("PURE_ARMS", "").split(",")
    + os.environ.get("RAG_ARMS", "").split(",")
)
arms = [a.strip() for a in arms if a.strip()]
expected = {
    "B02-flat-matched-rerank": "flat_matched_rerank",
    "B04-dual-inf": "dual_inf",
    "B05-mdagents": "mdagents",
    "B06-mac-single-vendor": "mac_single_vendor",
    "B15-medprompt-style": "medprompt_shared_kb",
    "B16-medrag-kg": "medrag_elicited_shared_kb",
}
failed = []
print("arm\tn_pred\tn_error\tmethod\tok")
for arm in arms:
    d = runs / arm / "replicate_01"
    pred = d / "predictions.jsonl"
    man_p = d / "manifest.json"
    if not pred.is_file() or not man_p.is_file():
        failed.append(arm)
        print(f"{arm}\tMISSING")
        continue
    n = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip())
    man = json.loads(man_p.read_text(encoding="utf-8"))
    err = int(man.get("n_error") or 0)
    method = None
    for line in (d / "trace.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        method = (json.loads(line).get("trace") or {}).get("method")
        break
    ok = n >= limit and err == 0 and method == expected.get(arm, method)
    print(f"{arm}\t{n}\t{err}\t{method}\t{ok}")
    if not ok:
        failed.append(arm)
if failed:
    print(f"SMOKE FAILED: {failed}", file=sys.stderr)
    sys.exit(1)
print("SMOKE OK")
PY

  echo "[$(date +%F\ %T)] DONE"
} 2>&1 | tee -a "$LOG_FILE"
