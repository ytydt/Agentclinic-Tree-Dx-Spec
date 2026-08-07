#!/usr/bin/env bash
# Build structural proxy budget schedule and rerun B02 compute-matched on DA d2_seq100.
set -eo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Avoid nounset breakage inside conda.sh (PS1 unbound in non-interactive).
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
set -u

# VPN optional but recommended for OpenRouter
if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh || true
fi

SCHEDULE="${SCHEDULE:-$ROOT/configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_b02_compute_matched_v1}"
SUBSET="${SUBSET:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
WORKERS="${WORKERS:-20}"
LIMIT="${LIMIT:-0}"
RESUME="${RESUME:-1}"
SCORE="${SCORE:-1}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"

mkdir -p "$(dirname "$SCHEDULE")" "$RUNS_ROOT/logs"
LOG="$RUNS_ROOT/logs/b02_matched_$(date +%Y%m%d_%H%M%S).log"

echo "[1/3] build budget schedule → $SCHEDULE" | tee -a "$LOG"
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/build_budget_schedule.py \
  --dataset diagnosisarena \
  --out "$SCHEDULE" | tee -a "$LOG"

echo "[2/3] run B02-flat-compute-matched" | tee -a "$LOG"
EXTRA=()
if [[ "$RESUME" == "1" ]]; then EXTRA+=(--resume); fi
if [[ "$SCORE" == "1" ]]; then EXTRA+=(--score --mapper-mode "$MAPPER_MODE"); fi
if [[ "$LIMIT" != "0" ]]; then EXTRA+=(--limit "$LIMIT"); fi

PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_baseline.py \
  --arms B02-flat-compute-matched \
  --dataset diagnosisarena \
  --subset-dir "$SUBSET" \
  --runs-root "$RUNS_ROOT" \
  --budget-mode matched \
  --budget-schedule "$SCHEDULE" \
  --workers "$WORKERS" \
  --executor process \
  "${EXTRA[@]}" | tee -a "$LOG"

echo "[3/3] audit budget match" | tee -a "$LOG"
PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/audit_b02_budget_match.py \
  --pred-dir "$RUNS_ROOT/B02-flat-compute-matched/replicate_01" \
  --schedule "$SCHEDULE" \
  --out "$RUNS_ROOT/b02_compute_matched_budget_audit.md" | tee -a "$LOG"

echo "DONE → $RUNS_ROOT" | tee -a "$LOG"
