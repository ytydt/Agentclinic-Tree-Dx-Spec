#!/usr/bin/env python3
"""Source provenance and conservative exposure-bridge sensitivity for four cases."""
import gzip,json
from pathlib import Path
import replay_audit as api
from run_infect_neuro_probes import summary
OUT=Path(__file__).resolve().parent
p=OUT/'judgments_infect_neuro.json';d=json.loads(p.read_text())
# All selected output rows are linked to the full actual source window.
passages={}
for r in d['cases']:
 ret=next(x for x in api.load('trial_retrieval_x2_oldidx.json' if r['arm']<2 else 'trial_retrieval_x2_v2idx.json') if x['case_key']==r['case_key'])
 for a in r['selected_raw_assertions']:
  s=a['_audit_source'];key=f"{r['case_key']}|{'old' if r['arm']<2 else 'v2'}|{s['gid']}"
  if key in passages:continue
  q=next(q for b in ret['retrieved'].values() for q in b['passages'] if q['gid']==s['gid'])
  passages[key]={'case_key':r['case_key'],'index':'old' if r['arm']<2 else 'v2','source':s,'passage':q,'actual_input_text':q['text'][:6000]}
 r['source_lookup']='infect_neuro_source_evidence.json keyed case|index|gid; full source read required; predicates merely locate judgments.'
 if r['case']=='326':
  core=[x['selector'] for x in r['selected_rows'] if x['family'].startswith('T_') and x['family']!='T_exposure_route_mismatch']
  dd=[x['selector'] for x in r['selected_rows'] if x['family'].startswith('D_')]
  r['exposure_route_caveat']='Strict literal exposure-route mismatch is definite, but animal-product exposure may retain a bounded coarse diagnostic association; core sensitivity preserves every milk/animal bridge. Do not infer that all broad animal-exposure evidence should be removed.'
  for mode in ['remove_contributions','block_joins']:
   for name,ss in [('target_core_preserve_exposure',core),('joint_core_preserve_exposure',core+dd)]:
    r['probes'][mode+'__'+name]=summary(api.run(r['case_key'],r['arm'],{mode:ss},detailed=False))
 if r['case'] in ['257','326'] and r['arm']>=2:
  pack=json.loads(gzip.decompress(api.pack_path(r['case_key'],r['arm']).read_bytes()))
  candidate='Cellulitis' if r['case']=='257' else 'Discitis'
  ids=sorted({i for h in pack['result']['ranking'] if h['label']==candidate for e in h['eliminated'] for i in e['_audit_raw_ids']})
  r['false_competitor_veto_raw_ids']=ids
  r['probes']['delete_raw__false_competitor_veto']=summary(api.run(r['case_key'],r['arm'],{'delete_raw_ids':ids},detailed=False))
 (OUT/'judgments_infect_neuro.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
 print(r['case'],r['arm'],{k:v['gold_rank'] for k,v in r['probes'].items() if 'core' in k or 'veto' in k},flush=True)
(OUT/'infect_neuro_source_evidence.json').write_text(json.dumps(passages,ensure_ascii=False,indent=2))
print('sources',len(passages))
