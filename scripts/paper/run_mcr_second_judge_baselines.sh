#!/usr/bin/env bash
# T1-11 extension: re-score the MCR reasoning-recall endpoint with the second
# judge for the full model and every baseline arm. Writes to a distinct
# --out-name so the primary pass is untouched.
#
# Failed judge calls now raise instead of being cached as a zero-coverage
# verdict, so a case that fails simply goes unscored; each arm is retried until
# all 100 cases are scored or a pass makes no progress.
set -uo pipefail

ROOT=/data2/wanghongyi/Agentclinic-Tree-Dx-Spec
RUNS=$ROOT/runs/paper_v1/medcasereasoning_mcr_val_seq100_v1
APHHM_RUN=$ROOT/logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1
PARQUET=$ROOT/data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet
JUDGE=deepseek/deepseek-v4-flash
WORKERS=${WORKERS:-50}
MAX_PASSES=${MAX_PASSES:-4}

ARMS=${ARMS:-"APHHM B00-direct-cot B01-cot-rag B02-flat-matched-rerank B03-flat-beam \
B04-dual-inf B05-mdagents B06-mac-single-vendor B07-meddxagent-complete \
B11b-cod-prompt-shared-kb B12-sc-cot-5 B13-self-refine-1 B15-medprompt-style \
B16-medrag-kg B17-imedrag"}

export PYTHONPATH=$ROOT/src:$ROOT/scripts:$ROOT/scripts/paper
export TREE_DX_USE_PROXY=1
export TREE_DX_EMBED_DEVICE=cpu

cd "$ROOT"
i=0
total=$(echo "$ARMS" | wc -w)
for arm in $ARMS; do
  i=$((i + 1))
  if [ "$arm" = "APHHM" ]; then
    run_dir=$APHHM_RUN
    out_name=official_eval_llm_compat_rr_dsv4f
    src_args="--ddx-source compat"
  else
    run_dir=$RUNS/$arm/replicate_01
    out_name=official_eval_llm_rr_dsv4f
    src_args="--projection-subdir eval_projection"
  fi
  scores=$run_dir/annotate/$out_name/case_scores

  for pass in $(seq 1 "$MAX_PASSES"); do
    before=$(ls "$scores" 2>/dev/null | wc -l)
    if [ "$before" -ge 100 ]; then
      echo "=== [$i/$total] $arm complete ($before)  $(date '+%H:%M:%S')"
      break
    fi
    echo "=== [$i/$total] $arm pass $pass (have $before)  $(date '+%H:%M:%S')"
    # shellcheck disable=SC2086
    python3 -u scripts/paper/run_ox_mcr_official_eval.py \
      --dataset medcasereasoning \
      --run-dir "$run_dir" \
      --subset-parquet "$PARQUET" \
      --judge llm \
      --workers "$WORKERS" \
      $src_args \
      --out-name "$out_name" \
      --judge-model "$JUDGE" \
      --resume-scores \
      >"/tmp/secondjudge_${arm}_p${pass}.log" 2>&1
    after=$(ls "$scores" 2>/dev/null | wc -l)
    echo "--- $arm pass $pass: $before -> $after  $(date '+%H:%M:%S')"
    if [ "$after" -le "$before" ]; then
      echo "--- $arm no progress, stopping retries"
      break
    fi
  done
done
echo "=== ALL DONE $(date '+%H:%M:%S') ==="
