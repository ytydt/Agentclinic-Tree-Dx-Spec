#!/usr/bin/env bash
# Full d2_seq100_v1 run for *corrected* baselines (non-placeholder implementations).
#
# Fresh runs_root by default (do NOT resume old alias/placeholder predictions):
#   runs/paper_v1/diagnosisarena_fixed_v1
#
# Arms:
#   Pure multi-step (thread pool): B04 Dual-Inf, B05 MDAgents, B06 MAC
#   Shared-KB RAG (process pool):  B02 flat retrieve-rerank, B15 MedPrompt-style,
#                                  B16 MedRAG-elicited
#
# Env overrides:
#   PURE_ARMS RAG_ARMS WORKERS MAPPER_MODE MODEL RUNS_ROOT SUBSET_DIR REPLICATE
#   EXECUTOR START_METHOD OMP_THREADS CONDA_ENV SKIP_PURE SKIP_RAG RESUME
#
# Usage:
#   bash scripts/paper/run_fixed_baselines_d2_seq100.sh
#   WORKERS=10 bash scripts/paper/run_fixed_baselines_d2_seq100.sh
#   SKIP_PURE=1 bash scripts/paper/run_fixed_baselines_d2_seq100.sh   # RAG only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

PURE_ARMS="${PURE_ARMS:-B04-dual-inf,B05-mdagents,B06-mac-single-vendor}"
RAG_ARMS="${RAG_ARMS:-B02-flat-matched-rerank,B15-medprompt-style,B16-medrag-kg}"
WORKERS="${WORKERS:-20}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_fixed_v1}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
REPLICATE="${REPLICATE:-1}"
EXECUTOR="${EXECUTOR:-process}"
START_METHOD="${START_METHOD:-spawn}"
OMP_THREADS="${OMP_THREADS:-2}"
RAG_INDEX="${RAG_INDEX:-$ROOT/data/corpus/rag_index}"
CPG_INDEX="${CPG_INDEX:-$ROOT/data/corpus/cpg_index}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
SKIP_PURE="${SKIP_PURE:-0}"
SKIP_RAG="${SKIP_RAG:-0}"
RESUME="${RESUME:-1}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/fixed_baselines_d2_seq100_${STAMP}.log}"

mkdir -p "$RUNS_ROOT" "$LOG_DIR"

if [[ -f "$(conda info --base)/etc/profile.d/conda.sh" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  set -u
fi

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
export RUNS_ROOT REPLICATE PURE_ARMS RAG_ARMS
export OMP_NUM_THREADS="$OMP_THREADS"
export MKL_NUM_THREADS="$OMP_THREADS"
export OPENBLAS_NUM_THREADS="$OMP_THREADS"
export NUMEXPR_NUM_THREADS="$OMP_THREADS"
export VECLIB_MAXIMUM_THREADS="$OMP_THREADS"
export TREE_DX_EMBED_DEVICE=cpu

RESUME_FLAG=()
if [[ "$RESUME" == "1" ]]; then
  RESUME_FLAG=(--resume)
fi

echo "[$(date +%F\ %T)] start fixed baselines workers=$WORKERS mapper=$MAPPER_MODE"
echo "[$(date +%F\ %T)] pure=$PURE_ARMS"
echo "[$(date +%F\ %T)] rag=$RAG_ARMS"
echo "[$(date +%F\ %T)] runs_root=$RUNS_ROOT subset=$SUBSET_DIR resume=$RESUME"
echo "[$(date +%F\ %T)] log=$LOG_FILE"

_inventory() {
  local label="$1"
  local arms_csv="$2"
  python - <<PY
import os
from pathlib import Path
runs = Path(os.environ["RUNS_ROOT"])
arms = [a.strip() for a in """$arms_csv""".split(",") if a.strip()]
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
print("=== $label inventory ===")
for arm in arms:
    pred = runs / arm / rep / "predictions.jsonl"
    n = 0
    if pred.is_file():
        n = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip())
    print(f"{arm}\tpredictions={n}\tremaining≈{max(0, 100 - n)}")
PY
}

_summary() {
  python - <<'PY'
import json
import os
from pathlib import Path

runs = Path(os.environ["RUNS_ROOT"])
arms = []
for key in ("PURE_ARMS", "RAG_ARMS"):
    arms.extend(a.strip() for a in os.environ.get(key, "").split(",") if a.strip())
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
out = runs / "summary_at1_at2_mrr.tsv"
lines = [
    "arm\tn\tn_pred\tn_error\toption_top1\toption_top2\tmrr2\t"
    "mapper_mode\texecutor\tn_distinct_pids\tmethod"
]
print("arm\tn\topt@1\topt@2\tmrr2\tn_pred\tn_error\tmethod")
for arm in arms:
    d = runs / arm / rep
    pred = d / "predictions.jsonl"
    n_pred = 0
    if pred.is_file():
        n_pred = sum(
            1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    man = {}
    mp = d / "manifest.json"
    if mp.is_file():
        man = json.loads(mp.read_text(encoding="utf-8"))
    summary = {}
    rp = d / "mapper" / "records.json"
    if rp.is_file():
        doc = json.loads(rp.read_text(encoding="utf-8"))
        summary = doc.get("summary") or {}
    method = ""
    tp = d / "trace.jsonl"
    if tp.is_file():
        for line in tp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                method = str((json.loads(line).get("trace") or {}).get("method") or "")
                break
    lines.append(
        f"{arm}\t{summary.get('n')}\t{n_pred}\t{man.get('n_error')}\t"
        f"{summary.get('option_top1')}\t{summary.get('option_top2')}\t"
        f"{summary.get('mrr2')}\t{summary.get('mapper_mode')}\t"
        f"{man.get('executor')}\t{man.get('n_distinct_pids')}\t{method}"
    )
    print(
        f"{arm}\t{summary.get('n')}\t{summary.get('option_top1')}\t"
        f"{summary.get('option_top2')}\t{summary.get('mrr2')}\t"
        f"{n_pred}\t{man.get('n_error')}\t{method}"
    )
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {out}")
PY
}

{
  echo "=== env ==="
  echo "PURE_ARMS=$PURE_ARMS"
  echo "RAG_ARMS=$RAG_ARMS"
  echo "WORKERS=$WORKERS"
  echo "MAPPER_MODE=$MAPPER_MODE"
  echo "MODEL=$MODEL"
  echo "RUNS_ROOT=$RUNS_ROOT"
  echo "SUBSET_DIR=$SUBSET_DIR"
  echo "REPLICATE=$REPLICATE"
  echo "RESUME=$RESUME"
  echo "SKIP_PURE=$SKIP_PURE SKIP_RAG=$SKIP_RAG"
  echo

  if [[ "$SKIP_PURE" != "1" ]]; then
    _inventory pure_before "$PURE_ARMS"
    echo "=== pure multi-step (thread pool) ==="
    python scripts/paper/run_baseline.py \
      --arms "$PURE_ARMS" \
      --subset-dir "$SUBSET_DIR" \
      --runs-root "$RUNS_ROOT" \
      --replicate "$REPLICATE" \
      --model "$MODEL" \
      --workers "$WORKERS" \
      --executor thread \
      "${RESUME_FLAG[@]}" \
      --score \
      --mapper-mode "$MAPPER_MODE"
  else
    echo "[skip] pure arms"
  fi

  if [[ "$SKIP_RAG" != "1" ]]; then
    _inventory rag_before "$RAG_ARMS"
    echo "=== shared-KB RAG corrected (process pool) ==="
    python scripts/paper/run_baseline.py \
      --arms "$RAG_ARMS" \
      --subset-dir "$SUBSET_DIR" \
      --runs-root "$RUNS_ROOT" \
      --replicate "$REPLICATE" \
      --model "$MODEL" \
      --workers "$WORKERS" \
      --executor "$EXECUTOR" \
      --start-method "$START_METHOD" \
      --omp-threads "$OMP_THREADS" \
      --rag-index "$RAG_INDEX" \
      --cpg-index "$CPG_INDEX" \
      "${RESUME_FLAG[@]}" \
      --score \
      --mapper-mode "$MAPPER_MODE"
  else
    echo "[skip] rag arms"
  fi

  echo
  echo "=== @1/@2/MRR summary ==="
  _summary

  echo "[$(date +%F\ %T)] DONE"
} 2>&1 | tee -a "$LOG_FILE"
