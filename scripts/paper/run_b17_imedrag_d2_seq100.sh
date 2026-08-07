#!/usr/bin/env bash
# i-MedRAG (B17) on d2_seq100_v1 — shared KB only.
#
# Flow: live smoke (limit=2) → full 100 with --resume.
#
# Usage:
#   bash scripts/paper/run_b17_imedrag_d2_seq100.sh
#   SMOKE_ONLY=1 bash scripts/paper/run_b17_imedrag_d2_seq100.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

ARMS="${ARMS:-B17-imedrag}"
WORKERS="${WORKERS:-10}"
SMOKE_LIMIT="${SMOKE_LIMIT:-2}"
SMOKE_WORKERS="${SMOKE_WORKERS:-2}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"
SMOKE_MAPPER="${SMOKE_MAPPER:-deterministic_gold_blind}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_imedrag_v1}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
REPLICATE="${REPLICATE:-1}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
SMOKE_ONLY="${SMOKE_ONLY:-0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
RESUME="${RESUME:-1}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/b17_imedrag_${STAMP}.log}"

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
export RUNS_ROOT REPLICATE ARMS SMOKE_LIMIT

RESUME_FLAG=()
if [[ "$RESUME" == "1" ]]; then
  RESUME_FLAG=(--resume)
fi

echo "[$(date +%F\ %T)] B17 i-MedRAG arms=$ARMS runs_root=$RUNS_ROOT"
echo "[$(date +%F\ %T)] log=$LOG_FILE"
echo "[kb] shared rag_index + cpg_index only (no MedRAG private corpora)"

{
  if [[ "$SKIP_SMOKE" != "1" ]]; then
    echo "=== SMOKE ==="
    python scripts/paper/run_baseline.py \
      --arms "$ARMS" \
      --subset-dir "$SUBSET_DIR" \
      --runs-root "$RUNS_ROOT" \
      --limit "$SMOKE_LIMIT" \
      --model "$MODEL" \
      --workers "$SMOKE_WORKERS" \
      --executor process \
      --start-method spawn \
      --omp-threads 2 \
      --score \
      --mapper-mode "$SMOKE_MAPPER"

    python - <<'PY'
import json, os, sys
from pathlib import Path
runs = Path(os.environ["RUNS_ROOT"])
limit = int(os.environ["SMOKE_LIMIT"])
arm = [a.strip() for a in os.environ["ARMS"].split(",") if a.strip()][0]
d = runs / arm / "replicate_01"
pred, man_p, tp = d / "predictions.jsonl", d / "manifest.json", d / "trace.jsonl"
assert pred.is_file() and man_p.is_file(), "missing smoke outputs"
n = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip())
err = int(json.loads(man_p.read_text(encoding="utf-8")).get("n_error") or 0)
method = (json.loads(tp.read_text(encoding="utf-8").splitlines()[0]).get("trace") or {}).get("method")
ok = n >= limit and err == 0 and method == "imedrag"
print(f"{arm}\tn={n}\terr={err}\tmethod={method}\tok={ok}")
if not ok:
    sys.exit(1)
print("SMOKE OK")
PY
  fi

  if [[ "$SMOKE_ONLY" == "1" ]]; then
    echo "[$(date +%F\ %T)] SMOKE_ONLY done"
    exit 0
  fi

  echo "=== FULL ==="
  python scripts/paper/run_baseline.py \
    --arms "$ARMS" \
    --subset-dir "$SUBSET_DIR" \
    --runs-root "$RUNS_ROOT" \
    --replicate "$REPLICATE" \
    --model "$MODEL" \
    --workers "$WORKERS" \
    --executor process \
    --start-method spawn \
    --omp-threads 2 \
    "${RESUME_FLAG[@]}" \
    --score \
    --mapper-mode "$MAPPER_MODE"

  python - <<'PY'
import json, os
from pathlib import Path
runs = Path(os.environ["RUNS_ROOT"])
arm = [a.strip() for a in os.environ["ARMS"].split(",") if a.strip()][0]
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
d = runs / arm / rep
summary = {}
rp = d / "mapper" / "records.json"
if rp.is_file():
    summary = (json.loads(rp.read_text(encoding="utf-8")).get("summary") or {})
out = runs / "summary_at1_at2_mrr.tsv"
line = (
    f"{arm}\t{summary.get('n')}\t{summary.get('option_top1')}\t"
    f"{summary.get('option_top2')}\t{summary.get('mrr2')}\n"
)
out.write_text("arm\tn\toption_top1\toption_top2\tmrr2\n" + line, encoding="utf-8")
print(line.strip())
print(f"wrote {out}")
PY
  echo "[$(date +%F\ %T)] DONE"
} 2>&1 | tee -a "$LOG_FILE"
