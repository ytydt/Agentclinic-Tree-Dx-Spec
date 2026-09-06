#!/usr/bin/env python3
"""Later adaptive close-reading probe; no claim that it was prespecified."""
import json,gzip
from pathlib import Path
import replay_audit as api
from run_infect_neuro_probes import summary
p=Path(__file__).resolve().parent;d=json.loads((p/'judgments_infect_neuro.json').read_text());sources=json.loads((p/'infect_neuro_source_evidence.json').read_text())
for arm,raw_id,name,cand in [(0,2181,'inert_wrong_claimant','Appendiceal abscess'),(2,651,'restored_list_extra_histology_vote','Appendiceal stump appendicitis')]:
 r=next(r for r in d['cases'] if r['case']=='49' and r['arm']==arm);key=r['case_key'];b=json.loads(gzip.decompress(api.pack_path(key,arm).read_bytes()));a=b['stages']['raw'][raw_id]
 r['probes']['block_joins__'+name]=summary(api.run(key,arm,{'block_joins':[{'candidate':cand,'raw_ids':[raw_id]}]},detailed=False))
 r[name]={'selection':'Adaptive manual source/trace investigation after main error-family probes; not preregistered','raw_assertion':a,'baseline_claimants':b['stages']['claimants'].get('neutrophils'),'has_direct_contribution':any(raw_id in c['_audit_raw_ids'] for h in b['result']['ranking'] for c in h['contributions'])}
 print(arm,name,r['probes']['block_joins__'+name]['ranking'][:4],flush=True)
 s=a['_audit_source'];ret=next(x for x in api.load('trial_retrieval_x2_oldidx.json' if arm<2 else 'trial_retrieval_x2_v2idx.json') if x['case_key']==key);q=next(q for bb in ret['retrieved'].values() for q in bb['passages'] if q['gid']==s['gid']);sources[f"{key}|{'old' if arm<2 else 'v2'}|{s['gid']}"]={'case_key':key,'index':'old' if arm<2 else 'v2','source':s,'passage':q,'actual_input_text':q['text'][:6000]}
(p/'judgments_infect_neuro.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));(p/'infect_neuro_source_evidence.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
