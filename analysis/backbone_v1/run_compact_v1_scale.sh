#!/usr/bin/env bash
# CompactForest v1 800 + evidence-X3 A/B (reselect) + v0 X3 on forest pool.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
export TREE_DX_DIRECT_POST_OUTPUT_CAP=8192
export http_proxy="${http_proxy:-http://127.0.0.1:7890}"
export https_proxy="${https_proxy:-http://127.0.0.1:7890}"

LOG=logs/backbone_v1/r7_v1_scale
mkdir -p "$LOG"
MASTER=$LOG/master.log
: >"$MASTER"
DS800=(diagnosisarena diagnosisarena_heldout diagnosisarena_heldout200b medcasereasoning medcasereasoning_v2 medcasereasoning_200b)

echo "### V1_SCALE START $(date -Is)" | tee -a "$MASTER"

# Oracle X3 upper bound on seq100 (diagnostic)
echo "### START oracle_seq100 $(date -Is)" | tee -a "$MASTER"
python3 -u scripts/paper/reselect_compact_x3.py \
  --dataset diagnosisarena --from-arm compact_forest_v1 --arm compact_forest_v1_x3oracle \
  --x3-oracle-gold --workers 24 >>"$LOG/oracle_seq100.log" 2>&1
python3 analysis/backbone_v1/eval_arm_dirs_slice.py \
  --arms compact_forest_v1,compact_forest_v1_x3ev,compact_forest_v1_x3oracle,mosaic_forest_v1,aphhm_c_collapse3c_v1 \
  --slices diagnosisarena | tee "$LOG/seq100_oracle.json" | tee -a "$MASTER"
echo "### DONE oracle_seq100 $(date -Is)" | tee -a "$MASTER"

# Wave A: endogenous v1 on all slices in parallel
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/v1_${ds}.log"
    echo "### START v1 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    # skip if already complete
    n_pred=$(wc -l <"logs/backbone_v1/${ds}/compact_forest_v1/predictions.jsonl" 2>/dev/null || echo 0)
    n_cases=$(python3 - <<PY
from run_backbone_v1 import SUBSETS
import baseline_common as bc
ds="$ds"
subset=SUBSETS[ds]
name="medcasereasoning" if ds.startswith("medcasereasoning") else "diagnosisarena"
print(len(bc.load_runtime_cases(dataset=name, subset_dir=subset)))
PY
)
    if [[ "$n_pred" -ge "$n_cases" && "$n_cases" -gt 0 ]]; then
      echo "### SKIP v1 $ds already $n_pred/$n_cases $(date -Is)" | tee -a "$MASTER" >>"$lf"
    else
      python3 -u scripts/paper/run_compact_forest_v1.py \
        --dataset "$ds" --arm compact_forest_v1 --workers 24 >>"$lf" 2>&1
      echo "### DONE v1 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
    fi
  ) &
done
echo "### Wave A v1 launched $(date -Is)" | tee -a "$MASTER"
wait
echo "### Wave A v1 DONE $(date -Is)" | tee -a "$MASTER"

# Wave B: evidence-X3 reselect from v1 (1 call)
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/x3ev_${ds}.log"
    echo "### START x3ev $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/reselect_compact_x3.py \
      --dataset "$ds" --from-arm compact_forest_v1 --arm compact_forest_v1_x3ev \
      --x3-evidence --workers 24 >>"$lf" 2>&1
    echo "### DONE x3ev $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done
# Wave B parallel: v0 evidence-X3 on forest pool
for ds in "${DS800[@]}"; do
  (
    lf="$LOG/v0x3_${ds}.log"
    echo "### START v0x3 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_compact_forest_aphhm.py \
      --dataset "$ds" --arm compact_forest_v0_x3ev --x3-evidence --workers 24 >>"$lf" 2>&1
    echo "### DONE v0x3 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done
echo "### Wave B launched $(date -Is)" | tee -a "$MASTER"
wait
echo "### Wave B DONE $(date -Is)" | tee -a "$MASTER"

python3 - <<'PY' | tee "$LOG/summary.json" | tee -a "$MASTER"
import json, sys
from pathlib import Path
sys.path.insert(0, "analysis/backbone_v1")
import r7_scale_summarize as s
s.EXTRA_ARMS.update({
    "compact_forest_v1": "compact_forest_v1",
    "compact_forest_v1_x3ev": "compact_forest_v1_x3ev",
    "compact_forest_v0_x3ev": "compact_forest_v0_x3ev",
    "compact_forest": "compact_forest_v0",
    "forest": "mosaic_forest_v1",
    "collapse3c": "aphhm_c_collapse3c_v1",
})
keys = [
    "compact_forest_v1",
    "compact_forest_v1_x3ev",
    "compact_forest_v0_x3ev",
    "compact_forest",
    "forest",
    "collapse3c",
]
out = {k: s.eval_arm(k) for k in keys}
print(json.dumps(out, indent=2))
Path("analysis/backbone_v1/mosaic_eval/r7_scale/compact_v1_summary.json").write_text(
    json.dumps(out, indent=2) + "\n"
)
PY

echo "### V1_SCALE DONE $(date -Is)" | tee -a "$MASTER"
