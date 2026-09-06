#!/usr/bin/env python3
"""Artifact validation only; does not substitute for clinical adjudication."""
import json
from pathlib import Path
p=Path(__file__).resolve().parent;d=json.loads((p/'judgments_infect_neuro.json').read_text());s=json.loads((p/'infect_neuro_source_evidence.json').read_text());checks=[]
assert len(d['cases'])==16
for r in d['cases']:
 assert r['baseline']['score_reconstruction_all_pass'];assert all(q['score_reconstruction_all_pass'] for q in r['probes'].values())
 raw={a['_audit_raw_index']:a for a in r['selected_raw_assertions']}
 for v in r['selected_rows']:
  ids=v['selector']['raw_ids'];assert set(ids)<=raw.keys();assert v['contribution']['_audit_representative_raw_id'] in ids
  for i in ids:
   a=raw[i];src=a['_audit_source'];key=f"{r['case_key']}|{'old' if r['arm']<2 else 'v2'}|{src['gid']}";assert key in s
  assert v['contribution']['_audit_stage']=='atomic_score'
  checks.append({'case':r['case'],'arm':r['arm'],'family':v['family'],'representative':v['contribution']['_audit_representative_raw_id'],'support_ids_verified':True})
 text=(p/'cases'/f"case_{r['case']}.md").read_text();assert '待补' not in text
 if r['case']=='49':
  assert len([x for x in r['selected_rows'] if x['family'].startswith('T')])==[6,6,7,6][r['arm']]
  assert r['probes']['block_joins__target_errors']['gold_rank']==[5,4,4,4][r['arm']]
 if r['case']=='326':assert r['probes']['block_joins__target_core_preserve_exposure']['gold_rank']==3
out={'scope':'Artifact/linkage checks, not external clinical validation','n_case_arms':len(d['cases']),'n_probes':sum(len(r['probes']) for r in d['cases']),'n_selected_contributions':len(checks),'n_source_windows':len(s),'score_reconstructions':'all pass','checks':checks}
(p/'infect_neuro_validation.json').write_text(json.dumps(out,indent=2));print({k:v for k,v in out.items() if k!='checks'})
