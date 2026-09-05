#!/usr/bin/env python3
"""Recompute dual-denominator estimates from frozen judgments; no auto-semantic labeling."""
import hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np

OUT=Path(__file__).resolve().parent
S_LABELS=['faithful','distorted','omitted','ambiguous_source']
O_LABELS=['faithful','distorted','out_of_scope_traceable','untraceable_fabrication','unresolved_provenance']
def read(n):return json.loads((OUT/n).read_text())
def write(n,d):(OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def wilson(k,n,z=1.959963984540054):
 p=k/n;den=1+z*z/n;c=(p+z*z/(2*n))/den;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [max(0,c-h),min(1,c+h)]
def tally(rows,labels):
 c=Counter(r['label'] for r in rows);w=defaultdict(float)
 for r in rows:w[r['label']]+=r['weight']
 total=sum(w.values());return {'n':len(rows),'counts':{k:c[k] for k in labels},'weighted_totals':{k:w[k] for k in labels},'weighted_rates':{k:w[k]/total if total else None for k in labels}}
def bootstrap(sman,window_counts,labels,denlabels,B=10000):
 rng=np.random.default_rng(20260905);by=defaultdict(list)
 for s in sman:by[s['source']].append(s)
 values=[]
 for _ in range(B):
  num=np.zeros(len(labels));den=0.
  for source,ss in by.items():
   n=len(ss);N=ss[0]['population_windows'];f=n/N
   # Rao-Wu rescaled stratified cluster bootstrap: n-1 resamples, with FPC.
   m=rng.multinomial(n-1,np.full(n,1/n));mult=1-math.sqrt(1-f)+math.sqrt(1-f)*n/(n-1)*m
   for s,b in zip(ss,mult):
    cc=window_counts[s['sample_id']];w=s['weight']*b
    num+=np.array([cc.get(k,0) for k in labels])*w;den+=sum(cc.get(k,0) for k in denlabels)*w
  values.append(num/den if den else np.full(len(labels),np.nan))
 a=np.array(values);return {k:[float(x) for x in np.nanpercentile(a[:,i],[2.5,97.5])] for i,k in enumerate(labels)},a
def main():
 freeze=read('inventory_freeze_manifest.json');sman=read('source_sample_manifest.json');sm={x['sample_id']:x for x in sman}
 source=[];windows=[];matches={}
 for i in range(1,5):
  file=OUT/f'source_inventory_{i}.frozen.json';assert hashlib.sha256(file.read_bytes()).hexdigest()==freeze[str(i)]['sha256']
  inv=json.loads(file.read_text());windows+=inv
  mm=read(f'source_matches_{i}.json');assert len(mm)==sum(len(w['rules']) for w in inv)
  for m in mm:assert m['rule_id'] not in matches;matches[m['rule_id']]=m
  for w in inv:
   for r in w['rules']:source.append({**r,'sample_id':w['sample_id'],'source':sm[w['sample_id']]['source'],'weight':sm[w['sample_id']]['weight']})
 assert len(matches)==len(source)
 s_over=read('source_review_overrides.json') if (OUT/'source_review_overrides.json').exists() else []
 for rv in s_over:matches[rv['rule_id']][rv['arm']].update(rv['replacement'])
 results={'source':{},'output':{},'notes':{'estimand':'Rules in actually delivered v2 windows, one canonical existing focus per window; not all guideline corpus or all LLMs.','interval':'Source: 10,000 Rao-Wu stratified window-cluster rescaled bootstrap replicates with FPC; output: stratified Wilson intervals, no clinical adjudication uncertainty included.','source_rule_count':len(source),'source_window_count':len(windows),'zero_rule_windows':[w['sample_id'] for w in windows if not w['rules']]}}
 paired={};flat=[]
 for arm in ['old','new']:
  rows=[];wc={w['sample_id']:Counter() for w in windows}
  for r in source:
   m=matches[r['rule_id']][arm];assert m['label'] in S_LABELS
   if r['source_status']=='ambiguous_source':assert m['label']=='ambiguous_source'
   row={**r,**m,'arm':arm};rows.append(row);wc[r['sample_id']][m['label']]+=1
   flat.append(row)
  adjud=[r for r in rows if r['label']!='ambiguous_source'];summary=tally(rows,S_LABELS);summary['adjudicable']=tally(adjud,S_LABELS[:3])
  ci,arr=bootstrap(sman,wc,S_LABELS[:3],S_LABELS[:3]);summary['adjudicable']['cluster_bootstrap_ci95']=ci;paired[arm]=arr
  summary['by_source']={st:tally([r for r in rows if r['source']==st],S_LABELS) for st in sorted({r['source'] for r in rows})}
  summary['by_complexity']={st:tally([r for r in rows if r['complexity']==st and r['label']!='ambiguous_source'],S_LABELS[:3]) for st in sorted({r['complexity'] for r in rows})}
  summary['by_flat_schema']={st:tally([r for r in rows if r['flat_schema']==st and r['label']!='ambiguous_source'],S_LABELS[:3]) for st in sorted({r['flat_schema'] for r in rows})}
  results['source'][arm]=summary
 delta=paired['new']-paired['old'];results['source']['paired_delta_ci95']={k:[float(x) for x in np.nanpercentile(delta[:,i],[2.5,97.5])] for i,k in enumerate(S_LABELS[:3])}
 trans=Counter();wt=defaultdict(float)
 for r in source:
  m=matches[r['rule_id']];k=m['old']['label']+' -> '+m['new']['label'];trans[k]+=1;wt[k]+=r['weight']
 results['source']['paired_transition_counts']=dict(trans);results['source']['paired_transition_weighted_totals']=dict(wt)
 oman=read('output_sample_manifest.json');om={x['unit_id']:x for x in oman};outputs=[]
 for i in [1,2]:outputs+=read(f'output_adjudication_{i}.json')
 assert len(outputs)==len(om)==180 and len({r['unit_id'] for r in outputs})==180
 o_over=read('output_review_overrides.json') if (OUT/'output_review_overrides.json').exists() else []
 oo={r['unit_id']:r for r in outputs}
 for rv in o_over:oo[rv['unit_id']].update(rv['replacement'])
 outputs=[{**r,'weight':om[r['unit_id']]['weight'],'stratum':om[r['unit_id']]['stratum']} for r in outputs]
 for r in outputs:assert r['label'] in O_LABELS
 results['output']['all']=tally(outputs,O_LABELS);bounds={k:np.zeros(2) for k in O_LABELS};totalpop=sum({s:next(r['population_units'] for r in oman if r['stratum']==s) for s in ['atomic','grouped']}.values())
 for st in ['atomic','grouped']:
  rr=[r for r in outputs if r['stratum']==st];ss=tally(rr,O_LABELS);ss['wilson_ci95']={k:wilson(ss['counts'][k],len(rr)) for k in O_LABELS};results['output'][st]=ss
  N=next(r['population_units'] for r in oman if r['stratum']==st)
  for k in O_LABELS:bounds[k]+=np.array(wilson(ss['counts'][k],len(rr),2.241402727604947))*N/totalpop
 results['output']['all']['bonferroni_wilson_ci95_approx']={k:v.tolist() for k,v in bounds.items()}
 results['output']['all']['warning']='Approximate 97.5% stratum Wilson bounds aggregated with population weights via Bonferroni; not a guaranteed exact-coverage interval, and no adjudication uncertainty included.'
 if all(r['label']!='untraceable_fabrication' for r in outputs):
  zbound=0.;strat={}
  for st in ['atomic','grouped']:
   n=sum(r['stratum']==st for r in outputs);N=next(r['population_units'] for r in oman if r['stratum']==st)
   upper=1-0.0125**(1/n);strat[st]=upper;zbound+=upper*N/totalpop
  results['output']['zero_fabrication_bound']={'method':'Two-sided97.5% Clopper-Pearson binomial stratum upper endpoints, combined with Bonferroni and population weights; ignores finite-population correction conservatively and assumes fixed accurate audit labels.','stratum_upper':strat,'weighted_upper95':zbound,'observed_count':0}
 for side,rows in [('source_new',[r for r in flat if r['arm']=='new']),('output',outputs)]:
  err=Counter();causes=Counter();first=Counter();schema=Counter()
  for r in rows:
   for e in set(r.get('errors') or []):err[e]+=1
   for e in {x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,sort_keys=True) for x in (r.get('schema_errors') or [])}:schema[e]+=1
   for c in r.get('causes') or []:causes[c['cause']+'|'+str(c.get('evidence_level'))]+=1
   first[str(r.get('first_damage'))]+=1
  results[side+'_error_codes']={'multi_label_counts':dict(err),'schema_counts':dict(schema),'cause_codes':dict(causes),'first_damage':dict(first)}
 write('census_metrics.json',results);write('source_rule_results.json',flat);write('output_unit_results.json',outputs)
 print(json.dumps({'source':{a:results['source'][a]['adjudicable'] for a in ['old','new']},'output':{a:results['output'][a] for a in ['atomic','grouped','all']}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
