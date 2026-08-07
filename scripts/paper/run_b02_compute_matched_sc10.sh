#!/usr/bin/env bash
# B02 compute-matched 10-SC across DA / OX / MCR (true call-scale match vs M00).
#
# Each SC sample runs a full matched B02 trajectory; aggregate with RRF.
# Mean llm_calls ≈ 10 × structural schedule (~90) ≈ main-method cache calls.
#
# Env:
#   DATASETS   diagnosisarena,open_xddx,medcasereasoning (default all)
#   WORKERS    default 50
#   EVAL_WORKERS default 50
#   SC_SAMPLES default 10
#   JUDGE RESUME LIMIT SKIP_INFER SKIP_EVAL
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

DATASETS="${DATASETS:-diagnosisarena,open_xddx,medcasereasoning}"
WORKERS="${WORKERS:-50}"
EVAL_WORKERS="${EVAL_WORKERS:-50}"
SC_SAMPLES="${SC_SAMPLES:-10}"
JUDGE="${JUDGE:-llm}"
RESUME="${RESUME:-1}"
LIMIT="${LIMIT:-0}"
SKIP_INFER="${SKIP_INFER:-0}"
SKIP_EVAL="${SKIP_EVAL:-0}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"

run_one() {
  local dataset="$1"
  local schedule subset runs_root list_k parquet seed_dir arm_dir ref_arm_dir
  arm_dir="B02-flat-compute-matched-sc10"
  case "$dataset" in
    diagnosisarena|da)
      dataset=diagnosisarena
      schedule="$ROOT/configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl"
      subset="$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1"
      runs_root="$ROOT/runs/paper_v1/diagnosisarena_b02_compute_matched_sc10_v1"
      seed_dir="$ROOT/runs/paper_v1/diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01"
      list_k=2
      parquet=""
      ;;
    open_xddx|ox)
      dataset=open_xddx
      schedule="$ROOT/configs/paper_experiments/paper_v1_budget_schedule_open_xddx.jsonl"
      subset="$ROOT/data/benchmarks/open_xddx/subsets/ox_seq100_v1"
      runs_root="$ROOT/runs/paper_v1/open_xddx_b02_compute_matched_sc10_v1"
      seed_dir="$ROOT/runs/paper_v1/open_xddx_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01"
      list_k=5
      parquet="$subset/cases.parquet"
      ;;
    medcasereasoning|mcr)
      dataset=medcasereasoning
      schedule="$ROOT/configs/paper_experiments/paper_v1_budget_schedule_medcasereasoning.jsonl"
      subset="$ROOT/data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1"
      runs_root="$ROOT/runs/paper_v1/medcasereasoning_b02_compute_matched_sc10_v1"
      seed_dir="$ROOT/runs/paper_v1/medcasereasoning_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01"
      list_k=2
      parquet="$subset/cases.parquet"
      ;;
    *)
      echo "unknown dataset: $dataset" >&2
      return 1
      ;;
  esac

  mkdir -p "$runs_root/logs"
  local log="$runs_root/logs/b02_sc10_$(date +%Y%m%d_%H%M%S).log"
  local pred_dir="$runs_root/$arm_dir/replicate_01"

  echo "======== DATASET=$dataset SC=$SC_SAMPLES WORKERS=$WORKERS ========" | tee -a "$log"

  echo "[1/5] ensure budget schedule" | tee -a "$log"
  python3 scripts/paper/build_budget_schedule.py \
    --dataset "$dataset" \
    --out "$schedule" | tee -a "$log"

    if [[ "$SKIP_INFER" != "1" ]]; then
    echo "[2/5] infer $arm_dir (seed sample0 from matched single-traj)" | tee -a "$log"
    EXTRA=(--list-k "$list_k" --sc-samples "$SC_SAMPLES")
    if [[ "$RESUME" == "1" ]]; then EXTRA+=(--resume); fi
    if [[ "$LIMIT" != "0" ]]; then EXTRA+=(--limit "$LIMIT"); fi
    if [[ -d "$seed_dir" ]]; then EXTRA+=(--sc-seed-pred-dir "$seed_dir"); fi
    python3 scripts/paper/run_baseline.py \
      --arms "$arm_dir" \
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
    echo "[2/5] skip infer" | tee -a "$log"
  fi

  if [[ "$SKIP_EVAL" != "1" ]]; then
    echo "[3/5] reuse eval for unchanged answers vs single-traj matched" | tee -a "$log"
    python3 scripts/paper/reuse_baseline_eval_if_unchanged.py \
      --new-pred-dir "$pred_dir" \
      --ref-pred-dir "$seed_dir" \
      --dataset "$dataset" \
      --out-manifest "$runs_root/eval_reuse_vs_matched.json" | tee -a "$log"

    if [[ "$dataset" != "diagnosisarena" ]]; then
      echo "[4/5] formal eval judge=$JUDGE (resume-scores skips unchanged)" | tee -a "$log"
      python3 scripts/paper/run_baseline_ox_mcr_eval.py \
        --dataset "$dataset" \
        --pred-dir "$pred_dir" \
        --subset-parquet "$parquet" \
        --judge "$JUDGE" \
        --list-k "$list_k" \
        --workers "$EVAL_WORKERS" \
        --resume-projection \
        --resume-scores | tee -a "$log"
    else
      echo "[4/5] DA Mapper score (mapper cache reused for unchanged top2)" | tee -a "$log"
      python3 scripts/paper/run_baseline.py \
        --arms "$arm_dir" \
        --dataset diagnosisarena \
        --subset-dir "$subset" \
        --runs-root "$runs_root" \
        --budget-mode matched \
        --budget-schedule "$schedule" \
        --workers 1 \
        --resume \
        --score \
        --mapper-mode "$MAPPER_MODE" \
        --limit 0 | tee -a "$log"
    fi
  else
    echo "[3/5][4/5] skip eval" | tee -a "$log"
  fi

  echo "[5/5] audit SC budget (targets are sc_samples × schedule)" | tee -a "$log"
  python3 scripts/paper/audit_b02_budget_match.py \
    --pred-dir "$pred_dir" \
    --schedule "$schedule" \
    --out "$runs_root/b02_sc10_budget_audit.md" | tee -a "$log" || true
  # Note: audit compares against schedule rows; SC stores 10× targets in cost.budget_target,
  # so stored mismatch is preferred by the auditor.

  echo "DONE → $runs_root" | tee -a "$log"
}

IFS=',' read -r -a DS_ARR <<< "$DATASETS"
for ds in "${DS_ARR[@]}"; do
  ds="$(echo "$ds" | xargs)"
  [[ -z "$ds" ]] && continue
  run_one "$ds"
done

echo "ALL DONE datasets=$DATASETS sc_samples=$SC_SAMPLES"
