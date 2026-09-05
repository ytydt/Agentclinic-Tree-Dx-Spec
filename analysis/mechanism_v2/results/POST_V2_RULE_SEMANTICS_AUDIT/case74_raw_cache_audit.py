#!/usr/bin/env python3
"""Reconnect the 8 decisive model caches to source payload and normalized rows."""
import collections,copy,hashlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[4];OUT=pathlib.Path(__file__).parent;L=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
sys.path.insert(0,str(ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'))
import run_trial_extraction as ex
KEY='MCR_v1_seq100/74';MODEL='meta-llama/llama-3.3-70b-instruct'
def case(fn):return next(x for x in json.loads((L/fn).read_text()) if x['case_key']==KEY)
r=case('trial_retrieval_x2_v2idx.json');records=[]
for label,b in r['retrieved'].items():
 if label.lower()!='catecholaminergic polymorphic ventricular tachycardia':continue
 for p in b['passages']:
  if p['gid'] not in [74601,74602]:continue
  payload={'focus_disease':label,'source':p['source'],'document_title':p['title'],'section_path':p['section_path'],'context_hint':ex.context_hint(p['source'],p['section_path'],p['title']),'passage':p['text'][:6000]}
  for kind in ['guideline_groups','guideline_groups_free']:
   k=ex.cache_key(kind,payload,MODEL);cache=L/'trial_extraction_cache'/f'{k}.json';d=json.loads(cache.read_text());suffix='_free' if kind.endswith('_free') else ''
   fn=f'trial_extraction_x2_v2idxclean_groups{suffix}.json';aout=case(fn)['assertions'];rows=[]
   for i,a in enumerate(d.get('assertions',[])):
    z=copy.deepcopy(a);stats=collections.Counter();ex.normalise_group(z,stats)
    match=[j for j,b in enumerate(aout) if b.get('_focus')==label and {x:v for x,v in b.items() if not x.startswith('_')}==z]
    rows.append({'cache_assertion_index':i,'raw_response_assertion':a,'normalized_assertion':z,'normalization_changes':{x:{'raw':a.get(x),'normalized':z.get(x)} for x in set(a)|set(z) if a.get(x)!=z.get(x)},'normalization_counters':dict(stats),'extraction_output_indices':match})
   records.append({'gid':p['gid'],'focus':label,'cache_kind':kind,'model_key':MODEL,'cache_file':str(cache.relative_to(ROOT)),'cache_sha256':hashlib.sha256(cache.read_bytes()).hexdigest(),'payload':payload,'output_file':fn,'rows':rows})
(OUT/'case74_raw_cache_audit.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
print('records',len(records),'rows',sum(len(x['rows']) for x in records),'linked_rows',sum(bool(y['extraction_output_indices']) for x in records for y in x['rows']))
