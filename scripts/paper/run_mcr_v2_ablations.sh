#!/usr/bin/env bash
# MCR-primary ablations on mcr_val_seq100_v2 (NOT for paper).
# Reuses main-run middleware (pre_compat_joint for C1; VP freeze for C3).
# Workers default 25; set WORKERS=12 on process storm / rate limits.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="src:scripts:scripts/paper"
export TREE_DX_USE_PROXY=1
export TREE_DX_EMBED_DEVICE="${TREE_DX_EMBED_DEVICE:-cpu}"
export TREE_DX_DIRECT_POST_OUTPUT_CAP="${TREE_DX_DIRECT_POST_OUTPUT_CAP:-8192}"

WORKERS="${WORKERS:-25}"
SLICE="mcr_val_seq100_v2"
RUN_DIR="logs/medcasereasoning_${SLICE}/compat_synonym_v1"
SUBSET="data/benchmarks/medcasereasoning/subsets/${SLICE}"
OUT_ROOT="logs/medcasereasoning_${SLICE}"
RUNS="runs/paper_v1/medcasereasoning_${SLICE}"
mkdir -p "$RUNS" "$OUT_ROOT"
LOG="$RUNS/ablations_driver.log"

note() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

note "START mcr v2 ablations workers=$WORKERS"
cat > "$RUNS/README_NOT_FOR_PAPER.md" <<'EOF'
# mcr_val_seq100_v2 ablations — NOT FOR PAPER

Replication / expansion slice (second 100 MCR cases). Do not cite in `paper_aaai/` or `paper/*.tex` unless explicitly promoted.
EOF

# --- C1: decision-time arms on recovered pre_compat_joint ---
note "C1 precompat ablation (reuse annotate/pre_compat_joint)"
python3 -u scripts/paper/run_mcr_c1_precompat_ablation.py \
  --run-dir "$RUN_DIR" \
  --subset-parquet "$SUBSET/cases.parquet" \
  --live-calib \
  --workers "$WORKERS" \
  --out-json "$RUNS/ablations_c1_mcr_precompat_live_results.json" \
  2>&1 | tee -a "$RUNS/c1_precompat.log"
note "C1 done exit=${PIPESTATUS[0]}"

# --- C3: AB04/AB06 no-semantic-dedupe trees (reuse M00 VP freeze only) ---
note "C3 AB04/AB06 suite (shared no-dedupe trees → annotate/mapper/eval)"
python3 -u scripts/paper/run_c3_dedupe_site_suite.py \
  --m00 "$RUN_DIR" \
  --subset "$SUBSET" \
  --out-root "$OUT_ROOT" \
  --results-json "$RUNS/ablations_c3_mcr_raw.json" \
  --workers "$WORKERS" \
  --arms ab04,ab06 \
  2>&1 | tee -a "$RUNS/c3_site.log"
note "C3 done exit=${PIPESTATUS[0]}"

# --- Post: confirmatory rank metrics (any-hit@5 / open-MRR + site 2×2) ---
note "LLM rank metrics + AB10b/c permutation (Prompt7)"
python3 -u scripts/paper/run_mcr_llm_rank_metrics.py \
  --run-dir "$RUN_DIR" \
  --subset-parquet "$SUBSET/cases.parquet" \
  --workers "$WORKERS" \
  --out-json "$RUNS/ablations_c1_mcr_llm_rank_metrics.json" \
  --out-perm "$RUNS/ablations_c1_ab10b_llm_permutation.json" \
  2>&1 | tee -a "$RUNS/llm_rank_metrics.log" || note "llm_rank_metrics failed (non-fatal for driver)"

note "Block2 site 2×2 rank metrics"
python3 -u scripts/paper/run_block2_site_rank_metrics.py \
  --mcr-root "$OUT_ROOT" \
  --subset-parquet "$SUBSET/cases.parquet" \
  --workers "$WORKERS" \
  --out-json "$RUNS/ablations_block2_site_rank_metrics.json" \
  2>&1 | tee -a "$RUNS/block2_site_rank.log" || note "block2_site_rank failed (non-fatal for driver)"

note "ALL ABLATION DRIVER DONE"
