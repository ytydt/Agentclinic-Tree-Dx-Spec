#!/usr/bin/env python3
"""Check evidence links, interventions and the numerical claims in four reports.
Artifact consistency only; does not prove clinical labels or source semantics.
"""
import gzip,hashlib,json
from collections import Counter
from pathlib import Path
OUT=Path(__file__).resolve().parent
ARMS=['old_old','free_old','old_v2','free_v2']
CASES=['DA_d2_seq100/119','MCR_v1_seq100/56','MCR_v1_seq100/91','MCR_v2_seq100/179']
count=0

def check(v,msg):
 global count
 assert v,msg
 count+=1

def ranking(x,label):return next(v for v in x['result']['ranking']if v['label']==label)
def main():
 base={(ck,arm):json.load(gzip.open(OUT/'replay_outputs'/f'{ck.replace("/","__")}__{arm}.json.gz','rt'))for ck in CASES for arm in ARMS}
 allprobes=[]
 for stem in ['skin_other_probe','skin_other_additional_probe','skin_other_179_source_L4_probe']:
  full=json.load(gzip.open(OUT/(stem+'_full.json.gz'),'rt'));summ=json.loads((OUT/(stem+'_results.json')).read_text());check(len(full)==len(summ),'summary count')
  for x,s in zip(full,summ):
   check(x['probe_name']==s['probe_name'],'probe name');check(x['result']['top1']==s['top1'],'top1');check(x['result']['gold_rank']==s['gold_proxy_rank'],'proxy rank')
   for a in x['score_reconstruction']:check(a['pass']and a['reconstructed']==a['actual'],'score reconstruction')
   b=base[x['case_key'],x['arm']];n=len(b['stages']['raw']);raw=b['stages']['raw']
   for row in x['applied_interventions']:
    ids=row.get('raw_ids',[])
    if 'raw_id'in row:ids=[row['raw_id']]
    for i in ids:check(0<=i<n,'raw bounds')
    if row.get('action')=='force_candidate_binding':check(raw[row['raw_id']]['subject'].lower()==row['to'].lower(),'exact full subject only');check(row['from']=='Carcinoma','actual source binding')
   allprobes.append(x)
 by={(x['arm'],x['probe_name']):x for x in allprobes}
 for arm,rank1,rank2 in zip(ARMS,[3,3,5,5],[3,2,3,3]):
  check(ranking(by[arm,'56_force_explicit_full_subject_binding'],'Sarcomatoid squamous cell carcinoma')['_audit_rank']==rank1,'56 exact binding rank')
  check(ranking(by[arm,'56_binding_plus_wrong_L4_and_IHC'],'Sarcomatoid squamous cell carcinoma')['_audit_rank']==rank2,'56 joint rank')
  check(by[arm,'119_downgrade_overstrong_cornoid']['result']['top1']=='Dermatitis','119 false winner')
 check(by['old_old','119_joint_confirm_and_soft']['result']['gold_rank']==4,'119 old top3 loss')
 check(by['free_old','91_remove_molecular_testing_false_veto']['result']['gold_rank']==6,'91 zero-score shift')
 check(by['old_v2','179_block_restored_list_L4_652720_372441']['result']['gold_rank']==6,'179 joint source loss')
 for gid in [652720,372441]:check(by['old_v2',f'179_block_restored_list_L4_{gid}']['result']['gold_rank']==5,'179 single source not enough')
 ledger=json.loads((OUT/'judgments_skin_other.json').read_text());rows=0
 for case in ledger['cases']:
  for event in case['events']:
   b=base[case['case_key'],event['arm']]
   for row in event['rows']:
    i=row['raw_index'];check(row['raw_assertion']==b['stages']['raw'][i],'raw evidence identity');check(row['source']['input_sha256']==row['raw_assertion']['_audit_source']['passage_sha256'],'source window hash')
    for outcome in row['outcomes']:
     v=ranking(b,outcome['candidate']);check(v[outcome['stage']][outcome['item_index']]==outcome['payload'],'outcome index');check(i in outcome['payload']['_audit_raw_ids'],'outcome provenance')
    rows+=1
 result={'status':'pass','checks':count,'baseline_case_arms':len(base),'probes':len(allprobes),'source_event_arms':sum(len(c['events'])for c in ledger['cases']),'evidence_rows_including_companions':rows,'scope':'artifact consistency; not independent clinical verification','files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in OUT.glob('skin_other*')if p.is_file()}}
 (OUT/'skin_other_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items()if k!='files'}))
if __name__=='__main__':main()
