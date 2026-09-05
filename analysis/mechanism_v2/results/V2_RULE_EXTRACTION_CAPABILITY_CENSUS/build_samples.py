#!/usr/bin/env python3
"""Freeze independent source-window and output-unit probability samples."""
import hashlib,json
from collections import Counter,defaultdict
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
LEDGER=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
PREV=OUT.parent/'POST_V2_RULE_SEMANTICS_AUDIT'
SEED='V2-SEMANTIC-CENSUS-20260905-v1'
ALLOC={'statpearls':24,'pmc_oa':12,'textbooks':12,'merck':6,'manifest_cpg':6,'wikem':4}
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
def write(n,d):
 (OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def main():
 jobs=[json.loads(x) for x in (PREV/'extraction_job_manifest.jsonl').read_text().splitlines()]
 jj={(j['arm'],j['case_key'],j['focus'],j['gid']):j for j in jobs}
 windows={};cachejobs={};docs=defaultdict(dict)
 for rec in json.loads((LEDGER/'trial_retrieval_x2_v2idx.json').read_text()):
  for focus,b in rec['retrieved'].items():
   for p in b['passages']:
    text=p['text'][:6000];h=sha(text);wid=p['source']+':'+h[:20]
    old=jj['old_v2',rec['case_key'],focus,p['gid']];new=jj['free_v2',rec['case_key'],focus,p['gid']]
    base={'window_id':wid,'source':p['source'],'doc_key':p.get('doc_key'),'title':p['title'],'section_path':p['section_path'],'gid':p['gid'],'window_gids':p.get('window_gids'),'text':text,'sha256':h}
    w=windows.setdefault(wid,{**base,'jobs':[]})
    job={'case_key':rec['case_key'],'focus':focus,'old_cache_id':old['cache_id'],'new_cache_id':new['cache_id'],'old_assertion_start':old['assertion_start'],'new_assertion_start':new['assertion_start']}
    w['jobs'].append(job);cachejobs[new['cache_id']]={**base,**job}
    docs[p.get('doc_key')][h]=base
 counts=Counter(w['source'] for w in windows.values());selected=[]
 for source,n in ALLOC.items():
  pool=sorted([w for w in windows.values() if w['source']==source],key=lambda w:sha(SEED+'|S|'+w['window_id']))
  for w in pool[:n]:
   w={**w,'population_windows':len(pool),'sample_windows':n,'inclusion_probability':n/len(pool),'weight':len(pool)/n}
   selected.append(w)
 # Balancing for reviewer workload happens after selection, independent of outputs.
 packs=[[] for _ in range(4)];loads=[0]*4
 for w in sorted(selected,key=lambda w:len(w['text']),reverse=True):
  candidates=[i for i in range(4) if len(packs[i])<16];i=min(candidates,key=lambda i:loads[i]);packs[i].append(w);loads[i]+=len(w['text'])
 sman=[]
 for i,pack in enumerate(packs,1):
  source_only=[];reveal=[]
  for wi,w in enumerate(sorted(pack,key=lambda w:w['window_id']),1):
   sid=f'S{i}-{wi:02d}';job=min(w['jobs'],key=lambda j:j['new_cache_id'])
   source_only.append({'sample_id':sid,**{k:v for k,v in w.items() if k not in ('jobs','weight','inclusion_probability','population_windows','sample_windows')}})
   outputs={}
   for arm in ('old','new'):
    cid=job[arm+'_cache_id'];outputs[arm]={'cache_id':cid,'output':json.loads((LEDGER/'trial_extraction_cache'/f'{cid}.json').read_text()),'global_assertion_start':job[arm+'_assertion_start']}
   reveal.append({'sample_id':sid,'window_id':w['window_id'],'case_key':job['case_key'],'focus':job['focus'],'outputs':outputs})
   sman.append({'sample_id':sid,'reviewer_pack':i,**{k:v for k,v in w.items() if k not in ('jobs','text')},'selected_job':job})
  write(f'source_only_pack_{i}.json',source_only);write(f'source_reveal_pack_{i}.json',reveal)
 # Build grouped units from raw job-local IDs, preserving malformed groups.
 units=[];raw_invalid=[]
 for cid,job in sorted(cachejobs.items()):
  raw=json.loads((LEDGER/'trial_extraction_cache'/f'{cid}.json').read_text());arr=raw.get('assertions') or [] if isinstance(raw,dict) else []
  grouped=defaultdict(list)
  for idx,a in enumerate(arr):
   invalid=not isinstance(a,dict) or not a.get('subject') or not a.get('predicate')
   if invalid:raw_invalid.append({'cache_id':cid,'raw_index':idx,'raw':a})
   cg=a.get('criterion_group') if isinstance(a,dict) else None;gid=cg.get('group_id') if isinstance(cg,dict) else None
   if isinstance(gid,str) and gid.strip().lower() in ('','null','none','n/a'):gid=None
   if gid is None:
    if invalid:continue
    units.append({'unit_id':cid+':a'+str(idx),'stratum':'atomic','cache_id':cid,'rows':[{'raw_index':idx,'assertion':a}],**job})
   else:grouped[str(gid)].append({'raw_index':idx,'assertion':a,**({'invalid_member':True} if invalid else {})})
  for gid,rows in grouped.items():units.append({'unit_id':cid+':g'+gid,'stratum':'grouped','cache_id':cid,'group_id':gid,'rows':rows,**job})
 ocount=Counter(x['stratum'] for x in units);sample=[]
 for st,n in [('grouped',60),('atomic',120)]:
  pool=sorted([u for u in units if u['stratum']==st],key=lambda u:sha(SEED+'|O|'+u['unit_id']))
  for u in pool[:n]:sample.append({**u,'population_units':len(pool),'sample_units':n,'weight':len(pool)/n,'inclusion_probability':n/len(pool)})
 opacks=[[],[]]
 for st in ('grouped','atomic'):
  selected_st=[u for u in sample if u['stratum']==st]
  for k,u in enumerate(selected_st):
   i=k%2;u={**u,'sample_id':f'O{i+1}-{len(opacks[i])+1:03d}'};opacks[i].append(u)
 for i,pack in enumerate(opacks,1):write(f'output_pack_{i}.json',pack)
 write('source_sample_manifest.json',sman)
 write('output_sample_manifest.json',[{k:v for k,v in u.items() if k not in ('rows','text')} for pack in opacks for u in pack])
 write('sampled_doc_contexts.json',{k:list(v.values()) for k,v in docs.items() if k in {u['doc_key'] for u in sample}})
 summary={'seed':SEED,'source_frame':dict(counts),'source_sample':ALLOC,'source_sample_n':len(sman),'source_pack_characters':loads,'unique_new_cache_jobs':len(cachejobs),'output_frame':dict(ocount),'output_sample':{'grouped':60,'atomic':120},'raw_invalid_rows':raw_invalid,'source_sample_doc_count':len({w['doc_key'] for w in selected}),'output_sample_doc_count':len({u['doc_key'] for u in sample}),'protocol_sha256':hashlib.sha256((OUT/'PROTOCOL.md').read_bytes()).hexdigest()}
 write('sampling_summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
