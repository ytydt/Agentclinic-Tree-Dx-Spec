#!/usr/bin/env bash
# CompactForest v1.1 pilot (MCR+DA) then optional 800 + v1 r2.
set -u
cd /data2/wanghongyi/Agentclinic-Tree-Dx-Spec
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
export TREE_DX_DIRECT_POST_OUTPUT_CAP=8192
export http_proxy="${http_proxy:-http://127.0.0.1:7890}"
export https_proxy="${https_proxy:-http://127.0.0.1:7890}"

LOG=logs/backbone_v1/r7_v11
mkdir -p "$LOG"
MASTER=$LOG/master.log
: >"$MASTER"

echo "### V11_PILOT START $(date -Is)" | tee -a "$MASTER"

# Pilot slices: MCR gap + DA regression
for ds in medcasereasoning medcasereasoning_v2 diagnosisarena; do
  (
    lf="$LOG/v11_${ds}.log"
    echo "### START v11 $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_compact_forest_v1.py \
      --dataset "$ds" --arm compact_forest_v11 --workers 24 --shortlist-k 8 \
      >>"$lf" 2>&1
    echo "### DONE v11 $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
  (
    lf="$LOG/v11facts_${ds}.log"
    echo "### START v11facts $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    python3 -u scripts/paper/run_compact_forest_v1.py \
      --dataset "$ds" --arm compact_forest_v11_facts --with-facts --workers 24 --shortlist-k 8 \
      >>"$lf" 2>&1
    echo "### DONE v11facts $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
  ) &
done
# optional: v1 r2 on DA seq100 for stability of 0.244 claim (partial)
(
  lf="$LOG/v1r2_diagnosisarena.log"
  echo "### START v1_r2 diagnosisarena $(date -Is)" | tee -a "$MASTER" >>"$lf"
  python3 -u scripts/paper/run_compact_forest_v1.py \
    --dataset diagnosisarena --arm compact_forest_v1_r2 --workers 24 \
    >>"$lf" 2>&1
  echo "### DONE v1_r2 diagnosisarena exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
) &

echo "### pilot launched $(date -Is)" | tee -a "$MASTER"
wait
echo "### pilot DONE $(date -Is)" | tee -a "$MASTER"

python3 analysis/backbone_v1/eval_arm_dirs_slice.py \
  --arms mosaic_forest_v1,compact_forest_v0,compact_forest_v1,compact_forest_v11,compact_forest_v11_facts,aphhm_c_collapse3c_v1,compact_forest_v1_r2 \
  --slices medcasereasoning,medcasereasoning_v2,diagnosisarena \
  | tee "$LOG/pilot_eval.json" | tee -a "$MASTER"

# Gate: pick best of v11 / v11_facts by mean of three pilot slices
python3 - <<'PY' | tee -a "$MASTER"
import json
from pathlib import Path
ev=json.load(open('logs/backbone_v1/r7_v11/pilot_eval.json'))
# eval_arm_dirs_slice prints one json for all arms pooled across slices — need per-slice.
# Recompute per slice.
import sys
sys.path.insert(0,'analysis/backbone_v1')
from r7_scale_summarize import load_champ, cluster_rel
import r5_lib as r5
gold=r5.load_gold()
arms=['compact_forest_v1','compact_forest_v11','compact_forest_v11_facts','mosaic_forest_v1','compact_forest_v0']
slices=['medcasereasoning','medcasereasoning_v2','diagnosisarena']
table={}
for arm in arms:
  table[arm]={}
  for log_ds in slices:
    dkey=next(dk for ld,dk,_ in r5.SLICES if ld==log_ds)
    sl=next(s for ld,_,s in r5.SLICES if ld==log_ds)
    n=chain=0
    for cid in [c for (dd,ss,c),_ in gold.items() if dd==dkey and ss==sl]:
      g=gold[(dkey,sl,cid)]; champ=load_champ(log_ds,arm,cid)
      if champ is None: continue
      n+=1
      if cluster_rel(champ,g)=='chain': chain+=1
    table[arm][log_ds]=round(chain/n,4) if n else None
    table[arm].setdefault('_n',{})[log_ds]=n
print(json.dumps(table,indent=2))
Path('logs/backbone_v1/r7_v11/pilot_by_slice.json').write_text(json.dumps(table,indent=2)+'\n')
# decide winner
def mean3(arm):
  vals=[table[arm][s] for s in slices if table[arm].get(s) is not None]
  return sum(vals)/len(vals) if vals else 0
base=mean3('compact_forest_v1')
cands=[('compact_forest_v11', mean3('compact_forest_v11'), False),
       ('compact_forest_v11_facts', mean3('compact_forest_v11_facts'), True)]
# prefer improvement on MCR without big DA drop
mcr_base=0.5*((table['compact_forest_v1']['medcasereasoning'] or 0)+(table['compact_forest_v1']['medcasereasoning_v2'] or 0))
da_base=table['compact_forest_v1']['diagnosisarena'] or 0
best=None
for name,mu,facts in cands:
  mcr=0.5*((table[name]['medcasereasoning'] or 0)+(table[name]['medcasereasoning_v2'] or 0))
  da=table[name]['diagnosisarena'] or 0
  ok = (mcr >= mcr_base - 0.01) and (da >= da_base - 0.03) and (mcr >= mcr_base + 0.01 or mu >= base + 0.01)
  print('candidate', name, 'mcr', mcr, 'da', da, 'mean', mu, 'gate', ok)
  if ok and (best is None or mcr > best[1]):
    best=(name, mcr, facts)
Path('logs/backbone_v1/r7_v11/gate.json').write_text(json.dumps({
  'base_mcr': mcr_base, 'base_da': da_base,
  'winner': best[0] if best else None,
  'with_facts': best[2] if best else None,
  'table': table,
}, indent=2)+'\n')
print('WINNER', best)
PY

WINNER=$(python3 -c "import json; print(json.load(open('logs/backbone_v1/r7_v11/gate.json')).get('winner') or '')")
FACTS=$(python3 -c "import json; print('1' if json.load(open('logs/backbone_v1/r7_v11/gate.json')).get('with_facts') else '0')")

if [[ -z "$WINNER" ]]; then
  echo "### GATE FAIL — no 800 scale; write null result $(date -Is)" | tee -a "$MASTER"
  echo PILOT_ONLY_DONE | tee -a "$MASTER"
  exit 0
fi

echo "### GATE PASS winner=$WINNER facts=$FACTS → 800 $(date -Is)" | tee -a "$MASTER"
DS800=(diagnosisarena diagnosisarena_heldout diagnosisarena_heldout200b medcasereasoning medcasereasoning_v2 medcasereasoning_200b)
EXTRA=()
[[ "$FACTS" == "1" ]] && EXTRA+=(--with-facts)

for ds in "${DS800[@]}"; do
  (
    lf="$LOG/scale_${ds}.log"
    echo "### START scale $ds $(date -Is)" | tee -a "$MASTER" >>"$lf"
    # skip if pilot already filled this arm on this ds
    n_pred=0; [[ -f "logs/backbone_v1/${ds}/${WINNER}/predictions.jsonl" ]] && n_pred=$(wc -l <"logs/backbone_v1/${ds}/${WINNER}/predictions.jsonl")
    n_cases=$(python3 - <<PY
from run_backbone_v1 import SUBSETS
import baseline_common as bc
ds="$ds"
subset=SUBSETS[ds]
name="medcasereasoning" if ds.startswith("medcasereasoning") else "diagnosisarena"
print(len(bc.load_runtime_cases(dataset=name, subset_dir=subset)))
PY
)
    if [[ "${n_pred:-0}" -ge "${n_cases:-0}" && "${n_cases:-0}" -gt 0 ]]; then
      echo "### SKIP scale $ds already $n_pred/$n_cases $(date -Is)" | tee -a "$MASTER" >>"$lf"
    else
      python3 -u scripts/paper/run_compact_forest_v1.py \
        --dataset "$ds" --arm "$WINNER" --workers 24 --shortlist-k 8 "${EXTRA[@]}" \
        >>"$lf" 2>&1
      echo "### DONE scale $ds exit=$? $(date -Is)" | tee -a "$MASTER" >>"$lf"
    fi
  ) &
done
wait
echo "### scale DONE $(date -Is)" | tee -a "$MASTER"

python3 - <<PY | tee "$LOG/summary800.json" | tee -a "$MASTER"
import json, sys
from pathlib import Path
sys.path.insert(0,'analysis/backbone_v1')
import r7_scale_summarize as s
winner=json.load(open('logs/backbone_v1/r7_v11/gate.json'))['winner']
s.EXTRA_ARMS.update({
  'v11': winner,
  'v1': 'compact_forest_v1',
  'v0': 'compact_forest_v0',
  'forest': 'mosaic_forest_v1',
  'collapse3c': 'aphhm_c_collapse3c_v1',
  'v1_r2': 'compact_forest_v1_r2',
})
keys=['v11','v1','v0','forest','collapse3c']
out={k:s.eval_arm(k) for k in keys}
# v1_r2 only DA — report separately if present
from r7_scale_summarize import load_champ, cluster_rel
import r5_lib as r5
gold=r5.load_gold()
n=chain=0
for cid in [c for (dd,ss,c),_ in gold.items() if dd=='da' and ss=='d2_seq100']:
  g=gold[('da','d2_seq100',cid)]; champ=load_champ('diagnosisarena','compact_forest_v1_r2',cid)
  if champ is None: continue
  n+=1
  if cluster_rel(champ,g)=='chain': chain+=1
out['v1_r2_seq100']={'n':n,'chain': round(chain/n,4) if n else None}
print(json.dumps(out, indent=2))
Path('analysis/backbone_v1/mosaic_eval/r7_scale/compact_v11_summary.json').write_text(json.dumps(out,indent=2)+'\n')
PY

echo "### V11_SCALE DONE $(date -Is)" | tee -a "$MASTER"
