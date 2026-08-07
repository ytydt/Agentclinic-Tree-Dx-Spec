#!/usr/bin/env bash
# B02 compute-matched on OX and/or MCR (structural_proxy_v1).
#
# Env:
#   DATASETS   comma list: open_xddx,medcasereasoning (default both)
#   WORKERS    inference process workers (default 50)
#   EVAL_WORKERS  LLM judge workers (default 50)
#   JUDGE      llm|lexical (default llm)
#   RESUME LIMIT SKIP_INFER SKIP_EVAL
#
# Usage:
#   WORKERS=50 bash scripts/paper/run_b02_compute_matched_ox_mcr.sh
#   DATASETS=open_xddx WORKERS=50 bash scripts/paper/run_b02_compute_matched_ox_mcr.sh
set -eo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
set -u

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh || true
fi

DATASETS="${DATASETS:-open_xddx,medcasereasoning}"
WORKERS="${WORKERS:-50}"
EVAL_WORKERS="${EVAL_WORKERS:-50}"
JUDGE="${JUDGE:-llm}"
RESUME="${RESUME:-1}"
LIMIT="${LIMIT:-0}"
SKIP_INFER="${SKIP_INFER:-0}"
SKIP_EVAL="${SKIP_EVAL:-0}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"

run_one() {
  local dataset="$1"
  local schedule subset runs_root list_k parquet
  case "$dataset" in
    open_xddx|ox)
      dataset=open_xddx
      schedule="$ROOT/configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl"
      subset="$ROOT/data/benchmarks/open_xddx/subsets/ox_seq100_v1"
      runs_root="$ROOT/runs/paper_v1/open_xddx_b02_compute_matched_v1"
      list_k=5
      parquet="$subset/cases.parquet"
      ;;
    medcasereasoning|mcr)
      dataset=medcasereasoning
      schedule="$ROOT/configs/paper_experiments/paper_v1_budget_schedule_medcasereasoning.jsonl"
      subset="$ROOT/data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1"
      runs_root="$ROOT/runs/paper_v1/medcasereasoning_b02_compute_matched_v1"
      list_k=2
      parquet="$subset/cases.parquet"
      ;;
    *)
      echo "unknown dataset: $dataset" >&2
      return 1
      ;;
  esac

  mkdir -p "$runs_root/logs" "$(dirname "$schedule")"
  local log="$runs_root/logs/b02_matched_$(date +%Y%m%d_%H%M%S).log"
  local pred_dir="$runs_root/B02-flat-compute-matched/replicate_01"

  echo "======== DATASET=$dataset WORKERS=$WORKERS list_k=$list_k ========" | tee -a "$log"

  echo "[1/4] build budget schedule → $schedule" | tee -a "$log"
  python3 scripts/paper/build_budget_schedule.py \
    --dataset "$dataset" \
    --out "$schedule" | tee -a "$log"

  if [[ "$SKIP_INFER" != "1" ]]; then
    echo "[2/4] infer B02-flat-compute-matched" | tee -a "$log"
    EXTRA=(--list-k "$list_k")
    if [[ "$RESUME" == "1" ]]; then EXTRA+=(--resume); fi
    if [[ "$LIMIT" != "0" ]]; then EXTRA+=(--limit "$LIMIT"); fi
    python3 scripts/paper/run_baseline.py \
      --arms B02-flat-compute-matched \
      --dataset "$dataset" \
      --subset-dir "$subset" \
      --runs-root "$runs_root" \
      --budget-mode matched \
      --budget-schedule "$schedule" \
      --model "$MODEL" \
      --workers "$WORKERS" \
      --executor process \
      "${EXTRA[@]}" | tee -a "$log"
  else
    echo "[2/4] skip infer" | tee -a "$log"
  fi

  if [[ "$SKIP_EVAL" != "1" ]]; then
    echo "[3/4] formal eval judge=$JUDGE workers=$EVAL_WORKERS" | tee -a "$log"
    python3 scripts/paper/run_baseline_ox_mcr_eval.py \
      --dataset "$dataset" \
      --pred-dir "$pred_dir" \
      --subset-parquet "$parquet" \
      --judge "$JUDGE" \
      --list-k "$list_k" \
      --workers "$EVAL_WORKERS" | tee -a "$log"
  else
    echo "[3/4] skip eval" | tee -a "$log"
  fi

  echo "[4/4] audit budget match" | tee -a "$log"
  python3 scripts/paper/audit_b02_budget_match.py \
    --pred-dir "$pred_dir" \
    --schedule "$schedule" \
    --out "$runs_root/b02_compute_matched_budget_audit.md" | tee -a "$log"

  echo "DONE → $runs_root" | tee -a "$log"
}

IFS=',' read -r -a DS_ARR <<< "$DATASETS"
for ds in "${DS_ARR[@]}"; do
  ds="$(echo "$ds" | xargs)"
  [[ -z "$ds" ]] && continue
  run_one "$ds"
done

echo "ALL DONE datasets=$DATASETS"
