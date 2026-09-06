#!/usr/bin/env python3
"""Manually specified source-grounded probes for cases119/56/91/179.
These probes block invalid joins, not valid source propositions. Non-additive.
"""
import copy,gzip,json
from pathlib import Path
import replay_audit as ra
OUT=Path(__file__).resolve().parent

def summarize(p):
 r=p['result'];return {'case_key':r['case_key'],'arm':p['arm'],'intervention':p['intervention'],'top1':r['top1'],'gold_proxy_rank':r['gold_rank'],'ranking':[{'rank':i+1,**{k:v.get(k) for k in ['label','score','n_assertions','n_joined','confirmed','eliminated']}}for i,v in enumerate(r['ranking'])],'applied_interventions':p['applied_interventions']}

def main():
 packs=[]
 for arm in range(4):
  c='DA_d2_seq100/119'; ext=next(e for e in ra.load(ra.ARMS[arm][1]) if e['case_key']==c)
  cor=[{'raw_id':i,'changes':{'relation':'feature_of'}} for i,a in enumerate(ext['assertions']) if 'porokeratos' in a['subject'].lower() and a['predicate']=='cornoid lamella' and a['relation']=='pathognomonic_for']
  iga=[1071,993,1166,1096][arm]
  blocks=[{'candidate':'Dermatitis','raw_ids':[iga]}]
  soft=[i for i,a in enumerate(ext['assertions']) if a['subject'].lower()=='porokeratosis' and a['predicate'] in ['basal cell carcinoma transformation','skin irritation','skin atrophy','malignant degeneration','expansion of abnormal epidermal keratinocytes']]
  probes=[('119_block_false_IgA',{'block_joins':blocks}),('119_downgrade_overstrong_cornoid',{'patch_raw':cor}),('119_joint_confirm_repair',{'patch_raw':cor,'block_joins':blocks}),('119_block_target_false_soft',{'block_joins':[{'candidate':'Porokeratosis','raw_ids':soft}]}),('119_joint_confirm_and_soft',{'patch_raw':cor,'block_joins':blocks+[{'candidate':'Porokeratosis','raw_ids':soft}]})]
  for name,iv in probes:
   x=ra.run(c,arm,iv,detailed=False);x['probe_name']=name;packs.append(x);print(arm,name,x['result']['top1'],x['result']['gold_rank'],flush=True)
  c='MCR_v2_seq100/179'; counts=[[2341,2343,2346,2347],[2316,2317],[2760,2762,2765,2766],[2678,2679]][arm]; high=[1728,1741,2060,2015][arm]
  for n in range(1,len(counts)+1):
   name=f'179_proxy_wrong_platelet_cumulative_{n}';iv={'block_joins':[{'candidate':'Thrombocytopenia','raw_ids':counts[:n]}]};x=ra.run(c,arm,iv,detailed=False);x['probe_name']=name;packs.append(x);print(arm,name,x['result']['gold_rank'],flush=True)
  iv={'block_joins':[{'candidate':'Thrombocytopenia','raw_ids':counts},{'candidate':'Immune thrombocytopenia','raw_ids':[high]}]};x=ra.run(c,arm,iv,detailed=False);x['probe_name']='179_proxy_plus_ITP_high_count';packs.append(x)
  c='MCR_v1_seq100/91';ext=next(e for e in ra.load(ra.ARMS[arm][1]) if e['case_key']==c)
  wrong=[i for i,a in enumerate(ext['assertions']) if a['predicate'] in ['gastrointestinal hemorrhage','resolution before age 4']]
  for name,ids in [('91_block_wrong_organ_and_age',wrong)]:
   x=ra.run(c,arm,{'block_joins':[{'candidate':'Cavernous Angioma','raw_ids':ids}]},detailed=False);x['probe_name']=name;packs.append(x);print(arm,name,x['result']['top1'],x['result']['gold_rank'],flush=True)
  (OUT/'skin_other_probe_results.json').write_text(json.dumps([{'probe_name':x['probe_name'],**summarize(x)}for x in packs],ensure_ascii=False,indent=2))
  with gzip.open(OUT/'skin_other_probe_full.json.gz','wt')as f:json.dump(packs,f,ensure_ascii=False)
if __name__=='__main__':main()
