#!/usr/bin/env bash
# Wait for MCR v2 main-method pipeline, then run official Acc + RR eval.
# Does NOT touch paper sources. Safe to re-run (resume).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

RUN="logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1"
LOG="$RUN/../compat_synonym_v1_run.log"
PARQUET="data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/cases.parquet"
OUT_ACC="official_eval_llm_compat"
OUT_RR="official_eval_llm_compat_rr"

if [[ -f /home/wanghongyi/clashctl/clashon.sh ]]; then
  bash /home/wanghongyi/clashctl/clashon.sh >/dev/null 2>&1 || true
fi
set +u
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
set -u
export PYTHONPATH="${ROOT}/src:${ROOT}/scripts:${ROOT}/scripts/paper${PYTHONPATH:+:$PYTHONPATH}"
export TREE_DX_USE_PROXY=1 TREE_DX_EMBED_DEVICE=cpu

echo "[$(date +%F\ %T)] waiting for pipeline_summary.json under $RUN"
while true; do
  if [[ -f "$RUN/pipeline_summary.json" ]]; then
    code="$(python3 -c "import json; print(json.load(open('$RUN/pipeline_summary.json')).get('exit_code'))")"
    if [[ "$code" == "0" ]]; then
      echo "[$(date +%F\ %T)] pipeline OK"
      break
    fi
    echo "[$(date +%F\ %T)] pipeline exit_code=$code — abort"
    exit 1
  fi
  alive=0
  if pgrep -f 'run_diagnosisarena_pipeline_staged.py' >/dev/null 2>&1; then
    if pgrep -af 'run_diagnosisarena_pipeline_staged.py' 2>/dev/null | grep -q 'mcr_val_seq100_v2'; then
      alive=1
    fi
  fi
  if [[ "$alive" -eq 0 ]]; then
    echo "[$(date +%F\ %T)] pipeline process gone without summary" >&2
    tail -40 "$LOG" >&2 || true
    exit 1
  fi
  n=0
  if [[ -d "$RUN/annotate/case_results" ]]; then
    n="$(find "$RUN/annotate/case_results" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
  elif [[ -d "$RUN/frozen/shared_trees" ]]; then
    n="trees:$(find "$RUN/frozen/shared_trees" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
  fi
  echo "[$(date +%F\ %T)] waiting… progress=$n"
  sleep 120
done

echo "[$(date +%F\ %T)] Acc eval → $OUT_ACC"
python -u scripts/paper/run_ox_mcr_official_eval.py \
  --dataset medcasereasoning \
  --run-dir "$RUN" \
  --subset-parquet "$PARQUET" \
  --judge llm --ddx-k 5 --ddx-source compat --workers 50 \
  --build-projection --resume --skip-reasoning-recall \
  --out-name "$OUT_ACC"

echo "[$(date +%F\ %T)] RR eval → $OUT_RR"
python -u scripts/paper/run_ox_mcr_official_eval.py \
  --dataset medcasereasoning \
  --run-dir "$RUN" \
  --subset-parquet "$PARQUET" \
  --judge llm --ddx-k 5 --ddx-source compat --workers 50 \
  --resume --out-name "$OUT_RR"

echo "[$(date +%F\ %T)] done"
python3 - <<'PY'
import json
from pathlib import Path
acc = Path("logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1/annotate/official_eval_llm_compat/summary.json")
rr = Path("logs/medcasereasoning_mcr_val_seq100_v2/compat_synonym_v1/annotate/official_eval_llm_compat_rr/summary.json")
for p in (acc, rr):
    if p.is_file():
        d = json.loads(p.read_text())
        m = d.get("metrics") or {}
        print(p.parent.name, "Acc", m.get("diagnostic_accuracy_single_trajectory"),
              "RR", m.get("reasoning_recall_mean"), "n", m.get("n_cases"))
PY
