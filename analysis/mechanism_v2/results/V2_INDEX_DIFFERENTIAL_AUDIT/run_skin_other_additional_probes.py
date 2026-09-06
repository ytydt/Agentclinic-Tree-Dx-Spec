#!/usr/bin/env python3
"""Additional exact-row probes; clinical judgments are in case reports."""
import gzip,json
from pathlib import Path
import replay_audit as ra
from run_skin_other_probes import summarize
OUT=Path(__file__).resolve().parent

def main():
 packs=[]
 for arm,aid in enumerate(ra.ARM_IDS):
  c='MCR_v1_seq100/56'; x=json.load(gzip.open(ra.output_path(c,arm),'rt')) if hasattr(ra,'output_path') else json.load(gzip.open(OUT/'replay_outputs'/f'MCR_v1_seq100__56__{aid}.json.gz','rt'))
  raw=x['stages']['raw'];t='Sarcomatoid squamous cell carcinoma';target=next(v for v in x['result']['ranking']if v['label']==t)
  selections=[{'candidate':a['from'],'raw_ids':a['_audit_raw_ids']}for a in target.get('layer4_penalties',[])]
  probes=[]
  for n in range(1,len(selections)+1):probes.append((f'56_wrong_L4_cumulative_{n}',{'block_layer4':selections[:n]}))
  marker_ids=[i for i,a in enumerate(raw)if a['predicate'] in ['positive staining for desmin','positive staining for h-caldesmon','positive staining for myocardin','positive staining for p16']]
  blocks=[{'candidate':'Leiomyosarcoma','raw_ids':marker_ids}]
  probes.append(('56_block_four_wrong_IHC_markers',{'block_joins':blocks}))
  exact=[i for i,a in enumerate(raw)if a['subject'].lower()==t.lower()]
  force=[{'raw_ids':exact,'target_candidate':t}]
  probes.append(('56_force_explicit_full_subject_binding',{'force_bindings':force}))
  probes.append(('56_binding_plus_wrong_L4_and_IHC',{'force_bindings':force,'block_layer4':selections,'block_joins':blocks}))
  for name,iv in probes:
   q=ra.run(c,arm,iv,detailed=False);q['probe_name']=name;packs.append(q);tt=next(z for z in q['result']['ranking']if z['label']==t);print(aid,name,'fullrank',tt['_audit_rank'],'score',tt['score'],'n',tt['n_assertions'],'proxy',q['result']['gold_rank'],flush=True)
  c='MCR_v1_seq100/91'; ext=next(e for e in ra.load(ra.ARMS[arm][1])if e['case_key']==c)
  wrong=[i for i,a in enumerate(ext['assertions'])if a['predicate']in['gastrointestinal hemorrhage','resolution before age 4']]
  extra={0:[],1:[],2:list(range(64,67))+list(range(70,74)),3:list(range(82,85))+list(range(228,232))}[arm]
  iv={'block_joins':[{'candidate':'Cavernous Angioma','raw_ids':wrong+extra}]}
  q=ra.run(c,arm,iv,detailed=False);q['probe_name']='91_wrong_organ_age_and_misapplied_groups';packs.append(q)
  if arm==1:
   iv={'block_joins':[{'candidate':'Hemangiopericytoma','raw_ids':[2110,2454]}]};q=ra.run(c,arm,iv,detailed=False);q['probe_name']='91_remove_molecular_testing_false_veto';packs.append(q);print('91 restore competitor proxy',q['result']['gold_rank'],flush=True)
  (OUT/'skin_other_additional_probe_results.json').write_text(json.dumps([{'probe_name':q['probe_name'],**summarize(q)}for q in packs],ensure_ascii=False,indent=2))
  with gzip.open(OUT/'skin_other_additional_probe_full.json.gz','wt')as f:json.dump(packs,f,ensure_ascii=False)
if __name__=='__main__':main()
