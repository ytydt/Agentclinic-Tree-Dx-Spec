#!/usr/bin/env bash
# Open-XDDx ox_seq100_v1: baseline inference + OX formal eval.
#
# Inference: open vignette → ordered Top-K (default list_k=5; fair vs tree ddx_k).
# Eval: run_baseline_ox_mcr_eval.py (lexical or llm).
#
# Env overrides:
#   ARMS_PURE ARMS_RAG WORKERS MODEL RUNS_ROOT SUBSET_DIR REPLICATE LIST_K
#   JUDGE EVAL_WORKERS RESUME SKIP_INFER SKIP_EVAL SKIP_RAG SKIP_PURE
#
# Usage:
#   bash scripts/paper/run_baselines_ox_seq100.sh
#   JUDGE=llm EVAL_WORKERS=50 bash scripts/paper/run_baselines_ox_seq100.sh
#   SKIP_INFER=1 JUDGE=llm bash scripts/paper/run_baselines_ox_seq100.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

# Same non-gated main-table arms as MCR / DA transfer.
ARMS_PURE="${ARMS_PURE:-B00-direct-cot,B04-dual-inf,B05-mdagents,B06-mac-single-vendor,B12-sc-cot-5,B13-self-refine-1}"
ARMS_RAG="${ARMS_RAG:-B01-cot-rag,B02-flat-matched-rerank,B03-flat-beam,B07-meddxagent-complete,B11b-cod-prompt-shared-kb,B15-medprompt-style,B16-medrag-kg,B17-imedrag}"
WORKERS="${WORKERS:-20}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/open_xddx_ox_seq100_v1}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/open_xddx/subsets/ox_seq100_v1}"
PARQUET="${PARQUET:-$SUBSET_DIR/cases.parquet}"
REPLICATE="${REPLICATE:-1}"
LIST_K="${LIST_K:-5}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
RESUME="${RESUME:-1}"
SKIP_INFER="${SKIP_INFER:-0}"
SKIP_EVAL="${SKIP_EVAL:-0}"
SKIP_PURE="${SKIP_PURE:-0}"
SKIP_RAG="${SKIP_RAG:-0}"
JUDGE="${JUDGE:-lexical}"
EVAL_WORKERS="${EVAL_WORKERS:-0}"
OMP_THREADS="${OMP_THREADS:-2}"
RAG_INDEX="${RAG_INDEX:-$ROOT/data/corpus/rag_index}"
CPG_INDEX="${CPG_INDEX:-$ROOT/data/corpus/cpg_index}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/ox_baselines_${STAMP}.log}"

mkdir -p "$RUNS_ROOT" "$LOG_DIR"

if [[ -f "$(conda info --base)/etc/profile.d/conda.sh" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  set -u
fi

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
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

EVAL_W_FLAG=()
if [[ "$EVAL_WORKERS" != "0" ]]; then
  EVAL_W_FLAG=(--workers "$EVAL_WORKERS")
fi

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[$(date +%F\ %T)] OX baselines start"
echo "  runs_root=$RUNS_ROOT"
echo "  subset=$SUBSET_DIR list_k=$LIST_K"
echo "  pure=$ARMS_PURE"
echo "  rag=$ARMS_RAG"
echo "  judge=$JUDGE workers_infer=$WORKERS"
echo "  log=$LOG_FILE"

run_infer() {
  local arms="$1"
  local executor="$2"
  [[ -z "$arms" ]] && return 0
  python3 scripts/paper/run_baseline.py \
    --dataset open_xddx \
    --subset-dir "$SUBSET_DIR" \
    --runs-root "$RUNS_ROOT" \
    --arms "$arms" \
    --list-k "$LIST_K" \
    --replicate "$REPLICATE" \
    --model "$MODEL" \
    --workers "$WORKERS" \
    --executor "$executor" \
    --rag-index "$RAG_INDEX" \
    --cpg-index "$CPG_INDEX" \
    "${RESUME_FLAG[@]}"
}

if [[ "$SKIP_INFER" != "1" ]]; then
  if [[ "$SKIP_PURE" != "1" ]]; then
    echo "[$(date +%F\ %T)] === pure arms (thread) ==="
    run_infer "$ARMS_PURE" thread
  fi
  if [[ "$SKIP_RAG" != "1" ]]; then
    echo "[$(date +%F\ %T)] === RAG arms (process) ==="
    run_infer "$ARMS_RAG" process
  fi
else
  echo "[$(date +%F\ %T)] SKIP_INFER=1"
fi

if [[ "$SKIP_EVAL" != "1" ]]; then
  echo "[$(date +%F\ %T)] === formal eval judge=$JUDGE ==="
  ALL_ARMS="${ARMS_PURE},${ARMS_RAG}"
  IFS=',' read -r -a ARM_ARR <<< "$ALL_ARMS"
  for arm in "${ARM_ARR[@]}"; do
    arm="$(echo "$arm" | xargs)"
    [[ -z "$arm" ]] && continue
    pred="$RUNS_ROOT/$arm/replicate_$(printf '%02d' "$REPLICATE")"
    if [[ ! -f "$pred/predictions.jsonl" ]]; then
      echo "[warn] skip eval missing predictions: $pred"
      continue
    fi
    n="$(wc -l < "$pred/predictions.jsonl" | tr -d ' ')"
    echo "[$(date +%F\ %T)] eval $arm n_pred=$n"
    python3 scripts/paper/run_baseline_ox_mcr_eval.py \
      --dataset open_xddx \
      --pred-dir "$pred" \
      --subset-parquet "$PARQUET" \
      --list-k "$LIST_K" \
      --judge "$JUDGE" \
      --resume-projection \
      --resume-scores \
      "${EVAL_W_FLAG[@]}"
  done
else
  echo "[$(date +%F\ %T)] SKIP_EVAL=1"
fi

echo "[$(date +%F\ %T)] OX baselines done → $RUNS_ROOT"
