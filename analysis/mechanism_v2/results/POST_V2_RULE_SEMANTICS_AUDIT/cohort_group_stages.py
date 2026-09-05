#!/usr/bin/env python3
"""Locate group losses in the actual four normalized x2 arms, without re-ranking."""
import json,copy
from collections import defaultdict,Counter
from pathlib import Path
from cohort_recompute import ROOT,OUT,SRC,eng,sw,gate,ARMS,passage_index

def gkey(a):
 cg=a.get('criterion_group') or {};gid=cg.get('group_id')
 if not gid or cg.get('logic') not in {'all','any','at_least_n'}:return None
 return (a.get('_title'),a.get('_section'),a.get('_focus'),str(gid),eng.norm(a['subject']))
def groups(items):
 d=defaultdict(list)
 for a in items:
  k=gkey(a)
  if k:d[k].append(a)
 return d

def main():
 tasks={t['case_key']:t for t in json.loads((SRC/'trial_tasks_11_all4.json').read_text())}
 jobs=[json.loads(l) for l in (OUT/'extraction_job_manifest.jsonl').read_text().splitlines()]
 out=[]
 for i,(name,fn,rfn) in enumerate(ARMS):
  ext=json.loads((SRC/fn).read_text());jarm=['old_old','free_old','old_v2','free_v2'][i];metrics=Counter();examples=[]
  sw.configure(sw.BASELINES['B1'],sw.stacks()['S7_+F7']);gate._PASSAGE_INDEX=passage_index(json.loads((SRC/rfn).read_text()))
  for e in ext:
   raw=copy.deepcopy(e['assertions']);ck=e['case_key'];jcase=[j for j in jobs if j['arm']==jarm and j['case_key']==ck]
   for aidx,a in enumerate(raw):a['_audit_index']=aidx
   for j in jcase:
    for a in raw[j['assertion_start']:j['assertion_stop_exclusive']]:a['_audit_cache']=j['cache_id'];a['_audit_gid']=j['gid']
   cooked=gate.gate_assertions([eng.clamp_relation(a) for a in raw],apply_nli=False)
   bound=defaultdict(list)
   for a in cooked:
    for c in tasks[ck]['candidates']:
     if any(eng.subject_match(a['subject'],n) for n in [c['label'],*c.get('aliases',[])]):bound[c['label']].append(a);break
   for label,aa in bound.items():
    before=groups(aa);seen={}
    for a in aa:
     k=(eng.norm(a.get('predicate')),a.get('relation'),a.get('polarity'))
     if k not in seen:seen[k]=a
     elif eng.MODALITY_W.get(a.get('modality'),eng.DEFAULT_W)>eng.MODALITY_W.get(seen[k].get('modality'),eng.DEFAULT_W):seen[k]['modality']=a.get('modality')
    after=groups(list(seen.values()))
    for k,v in before.items():
     if len(v)<2:continue
     metrics['bound_multimember_serialized_groups_before_dedup']+=1
     remain=after.get(k,[])
     if len(remain)<2:
      metrics['groups_destroyed_by_predicate_dedup']+=1
      if remain:metrics['groups_reduced_to_single_atom']+=1
     if len({m.get('_audit_cache') for m in v})>1:metrics['pre_dedup_groups_spanning_extraction_jobs']+=1
    for k,v in after.items():
     if len(v)<2:continue
     metrics['engine_groups_after_dedup']+=1
     caches={m.get('_audit_cache') for m in v};logic={m.get('criterion_group',{}).get('logic') for m in v};ns={m.get('criterion_group',{}).get('n') for m in v}
     if len(caches)>1:metrics['engine_groups_spanning_extraction_jobs']+=1
     if len(logic)>1:metrics['engine_groups_inconsistent_logic']+=1
     if len(ns)>1:metrics['engine_groups_inconsistent_n']+=1
     if any(m.get('polarity')=='negated' for m in v):metrics['engine_groups_with_negated_members']+=1
     if any((m.get('threshold') or {}).get('value') is not None for m in v):metrics['engine_groups_with_threshold_members']+=1
     joined=[]
     for a in v:
      best=None
      for f in e['findings']:
       for side in (f.get('canonical'),f.get('label')):
        mt=eng.predicate_match(a['predicate'],side or '')
        if mt:
         rank={'exact':0,'containment':1,'overlap':2,'marker':3,'loose':4,'embed':5}[mt]
         if best is None or rank<best[0]:best=(rank,f,mt)
         break
      if best and best[1]['polarity']=='present':joined.append(best[1]['label'])
     if len(joined)>len(set(joined)):metrics['engine_groups_counting_same_present_finding_more_than_once']+=1
     if len(logic)>1 or len(ns)>1 or len(joined)>len(set(joined)):
      if len(examples)<60:examples.append({'case_key':ck,'candidate':label,'group_key':k,'logics':list(logic),'ns':list(ns),'cache_ids':list(caches),'joined_present_findings':joined,
       'members':[{'i':m['_audit_index'],'predicate':m['predicate'],'relation':m['relation'],'polarity':m['polarity'],'criterion_group':m['criterion_group'],'cache_id':m.get('_audit_cache')} for m in v]})
  out.append({'arm':name,'gate_evidence':'actual_arm_window_truncated6000','metrics':dict(metrics),'examples':examples});print(name,dict(metrics),flush=True)
  (OUT/'cohort_group_stages.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
