#!/usr/bin/env python3
"""Restored differential lists: source-restricted L4 intervention, not global."""
import gzip,json
from pathlib import Path
import replay_audit as ra
from run_skin_other_probes import summarize
OUT=Path(__file__).resolve().parent
packs=[]
for arm in [2,3]:
 aid=ra.ARM_IDS[arm];ck='MCR_v2_seq100/179';p=json.load(gzip.open(OUT/'replay_outputs'/f'MCR_v2_seq100__179__{aid}.json.gz','rt'))
 for gids in [[652720],[372441],[652720,372441]]:
  sels=[]
  for candidate,rows in p['stages']['bound'].items():
   for a in rows:
    if a.get('_audit_source',{}).get('gid')in gids and a['relation']in['distinguishes_from','argues_against']:
     sels.append({'candidate':candidate,'raw_ids':a.get('_audit_support_raw_ids',[a['_audit_raw_index']])})
  iv={'block_layer4':sels};q=ra.run(ck,arm,iv,detailed=False);q['probe_name']='179_block_restored_list_L4_'+'_'.join(map(str,gids));packs.append(q);print(aid,gids,q['result']['gold_rank'],flush=True)
(OUT/'skin_other_179_source_L4_probe_results.json').write_text(json.dumps([{'probe_name':q['probe_name'],**summarize(q)}for q in packs],ensure_ascii=False,indent=2))
with gzip.open(OUT/'skin_other_179_source_L4_probe_full.json.gz','wt')as f:json.dump(packs,f,ensure_ascii=False)
