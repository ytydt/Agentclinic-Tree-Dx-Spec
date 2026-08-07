#!/usr/bin/env bash
# B11a DiagnosisGPT-6B small-scale smoke on 3 GPUs; report wall / per-case latency.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

LIMIT="${LIMIT:-3}"
WORKERS="${WORKERS:-3}"
GPU_IDS="${GPU_IDS:-0,1,2}"
MAPPER_MODE="${MAPPER_MODE:-deterministic_gold_blind}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_b11a_smoke}"
B11A_MODEL="${B11A_MODEL:-$ROOT/baselines/chain_of_diagnosis/models/DiagnosisGPT-6B}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/b11a_smoke_${STAMP}.log}"

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
export RUNS_ROOT
export OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
export TREE_DX_EMBED_DEVICE=cpu
# Parent shells may export invalid max_split_size_mb:4; GPU workers need it unset.
unset PYTORCH_CUDA_ALLOC_CONF || true

{
  echo "=== B11a smoke ==="
  echo "limit=$LIMIT workers=$WORKERS gpus=$GPU_IDS model=$B11A_MODEL"
  date -Is
  python - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "baselines/chain_of_diagnosis")
import adapter
print("ready=", adapter.is_ready())
print("model=", adapter.DEFAULT_MODEL_DIR)
PY

  /usr/bin/time -f "ELAPSED_SEC=%e" python scripts/paper/run_baseline.py \
    --arms B11a-official-diagnosisgpt \
    --limit "$LIMIT" \
    --workers "$WORKERS" \
    --executor process \
    --start-method spawn \
    --gpu-ids "$GPU_IDS" \
    --b11a-model-dir "$B11A_MODEL" \
    --runs-root "$RUNS_ROOT" \
    --score \
    --mapper-mode "$MAPPER_MODE"

  python - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ.get("RUNS_ROOT", "runs/paper_v1/diagnosisarena_b11a_smoke"))
d = root / "B11a-official-diagnosisgpt" / "replicate_01"
man = json.loads((d / "manifest.json").read_text())
cost = json.loads((d / "cost.json").read_text())
preds = [json.loads(l) for l in (d / "predictions.jsonl").read_text().splitlines() if l.strip()]
print("=== timing ===")
print("wall_s", man.get("wall_s"))
print("mean_case_s", man.get("mean_case_latency_s"))
print("max_case_s", man.get("max_case_latency_s"))
print("min_case_s", man.get("min_case_latency_s"))
print("n_ok", man.get("n_ok"), "n_error", man.get("n_error"))
print("gpus", man.get("gpu_ids"), "pids", man.get("n_distinct_pids"))
print("=== predictions ===")
for p in preds:
    c = p.get("cost") or {}
    print(p["case_id"], p.get("top2_diagnoses"), f"latency_s={c.get('latency_s')}")
out = root / "smoke_timing.tsv"
out.write_text(
    "arm\tn\twall_s\tmean_case_s\tmax_case_s\tmin_case_s\tn_error\tgpus\n"
    f"B11a-official-diagnosisgpt\t{man.get('n_ok')}\t{man.get('wall_s')}\t"
    f"{man.get('mean_case_latency_s')}\t{man.get('max_case_latency_s')}\t"
    f"{man.get('min_case_latency_s')}\t{man.get('n_error')}\t"
    f"{','.join(map(str, man.get('gpu_ids') or []))}\n",
    encoding="utf-8",
)
print("wrote", out)
PY
  date -Is
} 2>&1 | tee -a "$LOG_FILE"
