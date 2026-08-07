#!/usr/bin/env bash
# Resume B11a DiagnosisGPT-6B on d2_seq100_v1 (skip smoke cases), run remaining
# with workers=3 (one process per GPU), then report Mapper option @1/@2/MRR@2.
#
# Usage:
#   bash scripts/paper/run_b11a_d2_seq100.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

ARMS="${ARMS:-B11a-official-diagnosisgpt}"
WORKERS="${WORKERS:-3}"
GPU_IDS="${GPU_IDS:-0,1,2}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_b11a_smoke}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
B11A_MODEL="${B11A_MODEL:-$ROOT/baselines/chain_of_diagnosis/models/DiagnosisGPT-6B}"
REPLICATE="${REPLICATE:-1}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/b11a_d2_seq100_${STAMP}.log}"

mkdir -p "$RUNS_ROOT" "$LOG_DIR"

if [[ -f "$(conda info --base)/etc/profile.d/conda.sh" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  set -u
fi

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
export B11A_MODEL_DIR="$B11A_MODEL"
export RUNS_ROOT ARMS REPLICATE
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export TREE_DX_EMBED_DEVICE=cpu
unset PYTORCH_CUDA_ALLOC_CONF || true

echo "[$(date +%F\ %T)] start arms=$ARMS workers=$WORKERS gpus=$GPU_IDS mapper=$MAPPER_MODE"
echo "[$(date +%F\ %T)] runs_root=$RUNS_ROOT model=$B11A_MODEL"
echo "[$(date +%F\ %T)] log=$LOG_FILE"

{
  echo "=== env ==="
  echo "ARMS=$ARMS"
  echo "WORKERS=$WORKERS"
  echo "GPU_IDS=$GPU_IDS"
  echo "MAPPER_MODE=$MAPPER_MODE"
  echo "RUNS_ROOT=$RUNS_ROOT"
  echo "B11A_MODEL=$B11A_MODEL"
  echo "REPLICATE=$REPLICATE"
  echo

  python - <<'PY'
import os
from pathlib import Path
import sys
sys.path.insert(0, "baselines/chain_of_diagnosis")
import adapter

runs = Path(os.environ["RUNS_ROOT"])
arms = [a.strip() for a in os.environ["ARMS"].split(",") if a.strip()]
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
print("ready=", adapter.is_ready(), "model=", adapter.DEFAULT_MODEL_DIR)
print("=== resume inventory (before) ===")
for arm in arms:
    pred = runs / arm / rep / "predictions.jsonl"
    n = 0
    if pred.is_file():
        n = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip())
    print(f"{arm}\tpredictions={n}\tremaining≈{max(0, 100 - n)}")
PY

  python scripts/paper/run_baseline.py \
    --arms "$ARMS" \
    --subset-dir "$SUBSET_DIR" \
    --runs-root "$RUNS_ROOT" \
    --replicate "$REPLICATE" \
    --workers "$WORKERS" \
    --executor process \
    --start-method spawn \
    --gpu-ids "$GPU_IDS" \
    --b11a-model-dir "$B11A_MODEL" \
    --omp-threads 2 \
    --resume \
    --score \
    --mapper-mode "$MAPPER_MODE"

  echo
  echo "=== @1/@2/MRR summary ==="
  python - <<'PY'
import json
import os
from pathlib import Path

runs = Path(os.environ["RUNS_ROOT"])
arms = [a.strip() for a in os.environ["ARMS"].split(",") if a.strip()]
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
out = runs / "summary_at1_at2_mrr.tsv"
lines = [
    "arm\tn\tn_pred\tn_error\toption_top1\toption_top2\tmrr2\t"
    "mapper_mode\twall_s\tmean_case_s\tgpus"
]
print("arm\tn\topt@1\topt@2\tmrr2\tn_pred\tn_error\twall_s\tmean_case_s")
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
    gpus = man.get("gpu_ids") or []
    gpu_s = ",".join(str(x) for x in gpus) if isinstance(gpus, list) else str(gpus)
    lines.append(
        f"{arm}\t{summary.get('n')}\t{n_pred}\t{man.get('n_error')}\t"
        f"{summary.get('option_top1')}\t{summary.get('option_top2')}\t"
        f"{summary.get('mrr2')}\t{summary.get('mapper_mode')}\t"
        f"{man.get('wall_s')}\t{man.get('mean_case_latency_s')}\t{gpu_s}"
    )
    print(
        f"{arm}\t{summary.get('n')}\t{summary.get('option_top1')}\t"
        f"{summary.get('option_top2')}\t{summary.get('mrr2')}\t"
        f"{n_pred}\t{man.get('n_error')}\t{man.get('wall_s')}\t"
        f"{man.get('mean_case_latency_s')}"
    )
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {out}")
PY

  echo "[$(date +%F\ %T)] DONE"
} 2>&1 | tee -a "$LOG_FILE"
