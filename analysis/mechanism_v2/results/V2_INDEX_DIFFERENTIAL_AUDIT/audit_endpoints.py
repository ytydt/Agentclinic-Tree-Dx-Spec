#!/usr/bin/env python3
"""Recompute frozen label-scope and paired rank accounting, without clinical relabeling."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PREV = OUT.parent / 'POST_V2_RULE_SEMANTICS_AUDIT'
ARMS = ['old_old','new_old','old_v2','new_v2']
# Direct label-scope adjudications. An empty list records absent complete labels;
# aliases that conflate parent/child or benign/malignant entities are not trusted.
COMPLETE = {
 '522': [], '773': [], '119': [], '257': [],
 '326': ['Brucellosis'],
 '475': ['Neuralgic Amyotrophy', 'Neuralgic amyotrophy'],
 '49': ['Appendiceal stump appendicitis'],
 '56': ['Sarcomatoid squamous cell carcinoma'],
 '74': ['Catecholaminergic Polymorphic Ventricular Tachycardia',
        'Catecholaminergic polymorphic ventricular tachycardia'],
 '91': [], '179': [],
}
NOTES = {
 '522':'Component Catatonia, parent Dementia; missing causal composite with DLB.',
 '773':'IPAH/PFO components and PAH parent; missing the IPAH with PFO composite.',
 '119':'Porokeratosis parent; missing eruptive pruritic papular subtype.',
 '257':'Abscess parent; missing collar-button configuration and site.',
 '326':'Exact disease label.',
 '475':'Neuralgic amyotrophy is the recorded disease synonym; case-only duplicates.',
 '49':'Complete stump appendicitis candidate plus an improperly accepted generic parent.',
 '56':'Generic Carcinoma accepted while explicit sarcomatoid SCC is excluded from legacy gold set. Other sarcomatoid labels need a contextual judgment and are not promoted here.',
 '74':'Complete concept but first-match binding creates an empty case-only duplicate.',
 '91':'Hemangioma is an unsafe benign/malignant alias conflation, not the gold Angiosarcoma.',
 '179':'Thrombocytopenia manifestation omits hypoxia causation.',
}

def main():
 tasks=json.loads((ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_tasks_11_all4.json').read_text())
 traces={arm:json.loads((PREV/f'cohort_trace_{i}_default_stale.json').read_text()) for i,arm in enumerate(ARMS)}
 byarm={a:{r['case_key'].split('/')[-1]:r for r in rs} for a,rs in traces.items()}
 cases=[]
 for t in tasks:
  case=t['case_key'].split('/')[-1]
  row={'case_key':t['case_key'],'gold':t['gold'],'legacy_labels':t['gold_labels_in_set'],
       'explicit_complete_labels':COMPLETE[case], 'scope_judgment':NOTES[case], 'arms':{}}
  for arm in ARMS:
   r=byarm[arm][case]
   complete=[{'rank':i+1,**{k:v[k] for k in ('label','score','n_assertions','n_joined','eliminated','confirmed')}}
             for i,v in enumerate(r['ranking']) if v['label'] in COMPLETE[case]]
   active=[v for v in complete if v['n_assertions']>0]
   labelrank=min([v['rank'] for v in complete],default=None)
   activerank=min([v['rank'] for v in active],default=None)
   joinedrank=min([v['rank'] for v in complete if v['n_joined']>0],default=None)
   row['arms'][arm]={'legacy_rank':r['gold_rank'],'legacy_top1':r['top1'],
       'legacy_rank_label':r['ranking'][r['gold_rank']-1]['label'],
       'complete_label_rank':labelrank,'complete_bound_assertion_rank':activerank,'complete_joined_assertion_rank':joinedrank,
       'complete_candidates':complete}
  cases.append(row)
 pairs=[]
 for before,after in [('old_old','old_v2'),('new_old','new_v2'),('old_old','new_v2')]:
  changes=[]
  for c in cases:
   b=c['arms'][before]['legacy_rank']; a=c['arms'][after]['legacy_rank']
   changes.append({'case_key':c['case_key'],'before_rank':b,'after_rank':a,
        'delta_reciprocal_rank':1/a-1/b,'contribution_to_mean_delta':(1/a-1/b)/len(cases),
        'before_top3':b<=3,'after_top3':a<=3})
  pairs.append({'before':before,'after':after,'delta_mrr':sum(x['contribution_to_mean_delta'] for x in changes),'cases':changes})
 metrics=[]
 for arm in ARMS:
  vals=[c['arms'][arm] for c in cases]
  metrics.append({'arm':arm,'legacy_top1':sum(v['legacy_rank']==1 for v in vals),
      'legacy_top3':sum(v['legacy_rank']<=3 for v in vals),'legacy_mrr':sum(1/v['legacy_rank'] for v in vals)/len(vals),
      'explicit_complete_label_available_cases':sum(bool(c['explicit_complete_labels']) for c in cases),
      'complete_label_top1':sum(v['complete_label_rank']==1 for v in vals),
      'complete_label_top3':sum(v['complete_label_rank'] is not None and v['complete_label_rank']<=3 for v in vals),
      'complete_label_mrr_missing_zero':sum(1/v['complete_label_rank'] if v['complete_label_rank'] else 0 for v in vals)/len(vals),
      'complete_bound_assertion_top3':sum(v['complete_bound_assertion_rank'] is not None and v['complete_bound_assertion_rank']<=3 for v in vals)})
 result={'scope':'Frozen emitted candidate-label scope audit, not clinical diagnostic adjudication or corrected clinical accuracy. No post-hoc alias promotion. Candidate absence is separate from rank failure.',
         'cases':cases,'metrics':metrics,'paired_arithmetic':pairs,
         'old_index_top3_cases':[c['case_key'] for c in cases if c['arms']['old_old']['legacy_rank']<=3]}
 (OUT/'endpoint_and_rank_accounting.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'metrics':metrics,'paired_delta_mrr':[(p['before'],p['after'],p['delta_mrr']) for p in pairs]},ensure_ascii=False))

if __name__=='__main__': main()
