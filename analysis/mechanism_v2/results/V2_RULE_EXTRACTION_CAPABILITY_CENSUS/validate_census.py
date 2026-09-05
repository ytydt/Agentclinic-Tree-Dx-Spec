#!/usr/bin/env python3
"""Check audit linkage, denominators, immutable source snapshots and review coverage."""
import hashlib,json,re
from collections import Counter
from pathlib import Path

P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 checks=[]
 def check(name,ok,detail=None):
  checks.append({'check':name,'passed':bool(ok),**({'detail':detail} if detail is not None else {})})
  if not ok:raise AssertionError(name+': '+str(detail))
 sm=read('source_sample_manifest.json');om=read('output_sample_manifest.json');summary=read('sampling_summary.json');freeze=read('inventory_freeze_manifest.json')
 check('protocol_unchanged',sha(P/'PROTOCOL.md')==summary['protocol_sha256'])
 check('source64_unique',len(sm)==len({x['window_id'] for x in sm})==64)
 check('output180_unique',len(om)==len({x['unit_id'] for x in om})==180)
 check('stratified_output60_120',Counter(x['stratum'] for x in om)=={'grouped':60,'atomic':120})
 source_rules={};initial_matches={};source_byid={};reveal={}
 for i in range(1,5):
  check('freeze_pack_'+str(i),sha(P/f'source_inventory_{i}.json')==sha(P/f'source_inventory_{i}.frozen.json')==freeze[str(i)]['sha256'])
  inv=read(f'source_inventory_{i}.frozen.json');ss={w['sample_id']:w for w in read(f'source_only_pack_{i}.json')};source_byid.update(ss)
  rv={w['sample_id']:w for w in read(f'source_reveal_pack_{i}.json')};reveal.update(rv)
  check('pack16_'+str(i),len(inv)==len(ss)==16)
  for w in inv:
   for r in w['rules']:
    check('anchor_'+r['rule_id'],r['source_anchor'] in ss[w['sample_id']]['text'])
    check('unique_'+r['rule_id'],r['rule_id'] not in source_rules)
    source_rules[r['rule_id']]={**r,'sample_id':w['sample_id']}
  mm=read(f'source_matches_{i}.json')
  check('complete_match_pack_'+str(i),{m['rule_id'] for m in mm}=={r['rule_id'] for w in inv for r in w['rules']})
  for m in mm:
   initial_matches[m['rule_id']]=m
   for arm in ['old','new']:
    arr=rv[m['sample_id']]['outputs'][arm]['output'].get('assertions') or []
    check('indices_'+m['rule_id']+'_'+arm,all(isinstance(j,int) and 0<=j<len(arr) for j in m[arm]['raw_indices']))
    if m[arm]['label']=='omitted':check('omitted_no_descendant_'+m['rule_id']+'_'+arm,not m[arm]['raw_indices'])
    if source_rules[m['rule_id']]['source_status']=='ambiguous_source':check('ambiguity_preserved_'+m['rule_id']+'_'+arm,m[arm]['label']=='ambiguous_source')
 check('source_rule286_272_14',len(source_rules)==286 and Counter(r['source_status'] for r in source_rules.values())=={'adjudicable':272,'ambiguous_source':14})
 for i in [1,2]:
  pack={u['unit_id']:u for u in read(f'output_pack_{i}.json')};rr=read(f'output_adjudication_{i}.json')
  check('output_pack_complete_'+str(i),len(rr)==90 and {r['unit_id'] for r in rr}==set(pack))
  for r in rr:
   anchor=r.get('ancestor_anchor')
   if r['label'] in ['faithful','distorted','out_of_scope_traceable']:check('has_ancestor_'+r['sample_id'],bool(anchor))
   # Nonverbatim quote is legal as an audit finding, so do not force model quote matching.
 check('sampling_rerun_unchanged',read('sampling_regeneration_check.json')['all_unchanged'])
 metrics=read('census_metrics.json');final_s=read('source_rule_results.json');final_o=read('output_unit_results.json')
 check('final_sizes',len(final_s)==572 and len(final_o)==180)
 for arm in ['old','new']:
  check('source_denominator_'+arm,metrics['source'][arm]['adjudicable']['n']==272)
  check('source_rates_sum_'+arm,abs(sum(metrics['source'][arm]['adjudicable']['weighted_rates'].values())-1)<1e-12)
 for st in ['atomic','grouped','all']:check('output_rates_sum_'+st,abs(sum(metrics['output'][st]['weighted_rates'].values())-1)<1e-12)
 check('zero_hallucination_not_zero_bound',metrics['output']['zero_fabrication_bound']['observed_count']==0 and metrics['output']['zero_fabrication_bound']['weighted_upper95']>0)
 selected=set(read('review_selection.json')['output']);cross=[r for i in [1,2] for r in read(f'cross_review_output_{i}.json')];crossids={r['sample_id'] for r in cross}
 check('fixed_output_review_coverage',selected<=crossids)
 initialfaithful={r['sample_id'] for i in [1,2] for r in read(f'output_adjudication_{i}.json') if r['label']=='faithful' and next(x for x in om if x['unit_id']==r['unit_id'])['stratum']=='grouped'}
 check('initial_faithful_groups_reviewed',initialfaithful<=crossids)
 check('reviewed32_output_units',len(crossids)==32)
 rootreview=read('root_source_review.json');check('fixed8_source_review70rules',len(rootreview['windows'])==8 and len(rootreview['rules'])==70)
 for f in ['REPORT.md','ERROR_TAXONOMY_AND_CAUSAL_MAP.md','GROUP_SEMANTIC_CASEBOOK.md']:
  missing=[]
  for target in re.findall(r'\]\(([^)]+)\)',(P/f).read_text()):
   if not target.startswith(('http:','https:','#','sandbox:')) and not (P/target.split('#')[0]).exists():missing.append(target)
  check('links_'+f,not missing,missing)
 files=[f for f in P.rglob('*') if f.is_file() and '__pycache__' not in f.parts]
 suspicious=[]
 for f in files:
  b=f.read_bytes()
  if re.search(rb'(?:sk-or-v1-[a-zA-Z0-9]{40,}|ghp_[a-zA-Z0-9]{30,})',b):suspicious.append(f.name)
 check('no_credentials',not suspicious,{'files_flagged':len(suspicious)})
 check('no_new_lfs_objects',not any(f.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1') for f in files))
 check('files_below_github100MB',all(f.stat().st_size<100_000_000 for f in files))
 (P/'validation.json').write_text(json.dumps({'all_passed':True,'checks':checks,'n_checks':len(checks)},ensure_ascii=False,indent=2)+'\n')
 (P/'artifact_manifest.json').write_text(json.dumps({str(f.relative_to(P)):{'bytes':f.stat().st_size,'sha256':sha(f)} for f in sorted(files) if f.name not in ('validation.json','artifact_manifest.json')},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'all_passed':True,'n_checks':len(checks),'artifact_files':len(files)},indent=2))
if __name__=='__main__':main()
