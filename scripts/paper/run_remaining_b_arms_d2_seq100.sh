#!/usr/bin/env bash
# Remaining non-ablation B-arms for DiagnosisArena d2_seq100_v1.
#
# Runnable now (same backbone; B03/B07 use shared KB):
#   B00-direct-cot, B03-flat-beam, B07-meddxagent-complete,
#   B12-sc-cot-5, B13-self-refine-1
#
# Gated (not run on DiagnosisArena):
#   B08 DeepRare, B09 phenotype tools → RareBench/RareArena
#   B10 mixed-vendor MAC → multi-vendor backends (use B06 for single-vendor)
# Ablations skipped: B14, A01, A13
#
# Flow: live smoke (limit=2) → if OK, full 100 with --resume.
#
# Usage:
#   bash scripts/paper/run_remaining_b_arms_d2_seq100.sh
#   SMOKE_ONLY=1 bash scripts/paper/run_remaining_b_arms_d2_seq100.sh
#   SKIP_SMOKE=1 bash scripts/paper/run_remaining_b_arms_d2_seq100.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi

PURE_ARMS="${PURE_ARMS:-B00-direct-cot,B12-sc-cot-5,B13-self-refine-1}"
RAG_ARMS="${RAG_ARMS:-B03-flat-beam,B07-meddxagent-complete}"
WORKERS="${WORKERS:-20}"
SMOKE_LIMIT="${SMOKE_LIMIT:-2}"
SMOKE_WORKERS="${SMOKE_WORKERS:-2}"
MAPPER_MODE="${MAPPER_MODE:-typed_llm_disagreement_rag}"
SMOKE_MAPPER="${SMOKE_MAPPER:-deterministic_gold_blind}"
MODEL="${MODEL:-meta-llama/llama-3.3-70b-instruct}"
RUNS_ROOT="${RUNS_ROOT:-$ROOT/runs/paper_v1/diagnosisarena_remaining_v1}"
SUBSET_DIR="${SUBSET_DIR:-$ROOT/data/benchmarks/diagnosisarena/subsets/d2_seq100_v1}"
REPLICATE="${REPLICATE:-1}"
EXECUTOR="${EXECUTOR:-process}"
START_METHOD="${START_METHOD:-spawn}"
OMP_THREADS="${OMP_THREADS:-2}"
CONDA_ENV="${CONDA_ENV:-gnn-llm}"
SMOKE_ONLY="${SMOKE_ONLY:-0}"
SKIP_SMOKE="${SKIP_SMOKE:-0}"
RESUME="${RESUME:-1}"
LOG_DIR="${LOG_DIR:-$RUNS_ROOT/logs}"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_FILE:-$LOG_DIR/remaining_b_arms_${STAMP}.log}"

mkdir -p "$RUNS_ROOT" "$LOG_DIR"

if [[ -f "$(conda info --base)/etc/profile.d/conda.sh" ]]; then
  set +u
  # shellcheck source=/dev/null
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV"
  set -u
fi

export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
export RUNS_ROOT REPLICATE PURE_ARMS RAG_ARMS SMOKE_LIMIT
export OMP_NUM_THREADS="$OMP_THREADS" MKL_NUM_THREADS="$OMP_THREADS"
export OPENBLAS_NUM_THREADS="$OMP_THREADS" NUMEXPR_NUM_THREADS="$OMP_THREADS"
export VECLIB_MAXIMUM_THREADS="$OMP_THREADS" TREE_DX_EMBED_DEVICE=cpu

RESUME_FLAG=()
if [[ "$RESUME" == "1" ]]; then
  RESUME_FLAG=(--resume)
fi

echo "[$(date +%F\ %T)] remaining B-arms pure=$PURE_ARMS rag=$RAG_ARMS"
echo "[$(date +%F\ %T)] runs_root=$RUNS_ROOT log=$LOG_FILE"
echo "[gate] B08/B09/B10 skipped on DiagnosisArena (RareBench / multi-vendor)"

_summary() {
  python - <<'PY'
import json, os
from pathlib import Path
runs = Path(os.environ["RUNS_ROOT"])
arms = []
for key in ("PURE_ARMS", "RAG_ARMS"):
    arms.extend(a.strip() for a in os.environ.get(key, "").split(",") if a.strip())
rep = f"replicate_{int(os.environ['REPLICATE']):02d}"
out = runs / "summary_at1_at2_mrr.tsv"
lines = ["arm\tn\tn_pred\tn_error\toption_top1\toption_top2\tmrr2\tmapper_mode\tmethod"]
print("arm\tn\topt@1\topt@2\tmrr2\tn_pred\tn_error\tmethod")
for arm in arms:
    d = runs / arm / rep
    pred = d / "predictions.jsonl"
    n_pred = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip()) if pred.is_file() else 0
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if (d / "manifest.json").is_file() else {}
    summary = {}
    rp = d / "mapper" / "records.json"
    if rp.is_file():
        summary = (json.loads(rp.read_text(encoding="utf-8")).get("summary") or {})
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
        f"{summary.get('mrr2')}\t{summary.get('mapper_mode')}\t{method}"
    )
    print(f"{arm}\t{summary.get('n')}\t{summary.get('option_top1')}\t{summary.get('option_top2')}\t{summary.get('mrr2')}\t{n_pred}\t{man.get('n_error')}\t{method}")
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"wrote {out}")
PY
}

{
  if [[ "$SKIP_SMOKE" != "1" ]]; then
    echo "=== SMOKE pure limit=$SMOKE_LIMIT ==="
    python scripts/paper/run_baseline.py \
      --arms "$PURE_ARMS" \
      --subset-dir "$SUBSET_DIR" \
      --runs-root "$RUNS_ROOT" \
      --replicate "$REPLICATE" \
      --limit "$SMOKE_LIMIT" \
      --model "$MODEL" \
      --workers "$SMOKE_WORKERS" \
      --executor thread \
      --score \
      --mapper-mode "$SMOKE_MAPPER"

    echo "=== SMOKE rag limit=$SMOKE_LIMIT ==="
    python scripts/paper/run_baseline.py \
      --arms "$RAG_ARMS" \
      --subset-dir "$SUBSET_DIR" \
      --runs-root "$RUNS_ROOT" \
      --replicate "$REPLICATE" \
      --limit "$SMOKE_LIMIT" \
      --model "$MODEL" \
      --workers "$SMOKE_WORKERS" \
      --executor process \
      --start-method "$START_METHOD" \
      --omp-threads "$OMP_THREADS" \
      --score \
      --mapper-mode "$SMOKE_MAPPER"

    python - <<'PY'
import json, os, sys
from pathlib import Path
runs = Path(os.environ["RUNS_ROOT"])
limit = int(os.environ["SMOKE_LIMIT"])
arms = [a.strip() for a in (os.environ["PURE_ARMS"] + "," + os.environ["RAG_ARMS"]).split(",") if a.strip()]
expected = {
    "B00-direct-cot": None,  # single-call; method may be absent
    "B03-flat-beam": "flat_beam",
    "B07-meddxagent-complete": "meddxagent_complete_profile",
    "B12-sc-cot-5": None,
    "B13-self-refine-1": None,
}
failed = []
print("arm\tn_pred\tn_error\tmethod\tok")
for arm in arms:
    d = runs / arm / "replicate_01"
    pred, man_p = d / "predictions.jsonl", d / "manifest.json"
    if not pred.is_file() or not man_p.is_file():
        print(f"{arm}\tMISSING"); failed.append(arm); continue
    n = sum(1 for line in pred.read_text(encoding="utf-8").splitlines() if line.strip())
    err = int(json.loads(man_p.read_text(encoding="utf-8")).get("n_error") or 0)
    method = None
    tp = d / "trace.jsonl"
    if tp.is_file():
        for line in tp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                method = (json.loads(line).get("trace") or {}).get("method")
                break
    exp = expected.get(arm)
    ok = n >= limit and err == 0 and (exp is None or method == exp)
    print(f"{arm}\t{n}\t{err}\t{method}\t{ok}")
    if not ok:
        failed.append(arm)
if failed:
    print(f"SMOKE FAILED: {failed}", file=sys.stderr)
    sys.exit(1)
print("SMOKE OK")
PY
  else
    echo "[skip] smoke"
  fi

  if [[ "$SMOKE_ONLY" == "1" ]]; then
    echo "[$(date +%F\ %T)] SMOKE_ONLY done"
    exit 0
  fi

  echo "=== FULL pure (resume remaining) ==="
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

  echo "=== FULL rag (resume remaining) ==="
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
    "${RESUME_FLAG[@]}" \
    --score \
    --mapper-mode "$MAPPER_MODE"

  echo "=== summary ==="
  _summary
  echo "[$(date +%F\ %T)] DONE"
} 2>&1 | tee -a "$LOG_FILE"
