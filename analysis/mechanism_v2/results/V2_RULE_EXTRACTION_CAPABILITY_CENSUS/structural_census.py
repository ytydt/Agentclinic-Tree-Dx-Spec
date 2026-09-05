#!/usr/bin/env python3
"""Raw-cache census. Structural flags are NOT semantic error or hallucination rates."""
import hashlib,json
from collections import Counter,defaultdict
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
PREV=OUT.parent/'POST_V2_RULE_SEMANTICS_AUDIT'
CACHE=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_extraction_cache'
RELATIONS=set('feature_of required_for sufficient_for pathognomonic_for excludes argues_against distinguishes_from variant_of synonym_of caused_by treated_by'.split())
CONTEXTS=set('definition criteria differential histopathology imaging epidemiology treatment prognosis table_row other'.split())
def clean(x):
 return None if isinstance(x,str) and x.strip().lower() in ('','null','none','n/a') else x
def main():
 jobs=[json.loads(x) for x in (PREV/'extraction_job_manifest.jsonl').read_text().splitlines()]
 result={};records=[]
 for arm in ('old_old','free_old','old_v2','free_v2'):
  cids=sorted({j['cache_id'] for j in jobs if j['arm']==arm});counts=Counter();rels=Counter();sizes=Counter()
  for cid in cids:
   obj=json.loads((CACHE/f'{cid}.json').read_text());arr=(obj.get('assertions') or []) if isinstance(obj,dict) else []
   groups=defaultdict(list);counts['jobs']+=1;counts['raw_rows']+=len(arr)
   if not arr:counts['empty_jobs']+=1
   for idx,a in enumerate(arr):
    if not isinstance(a,dict) or not a.get('subject') or not a.get('predicate'):
     counts['invalid_rows']+=1
     badcg=a.get('criterion_group') if isinstance(a,dict) else None
     badgid=clean(badcg.get('group_id')) if isinstance(badcg,dict) else None
     if badgid is not None:
      groups[str(badgid)].append((idx,a));counts['invalid_group_member_rows']+=1
     continue
    counts['valid_rows']+=1;rels[str(a.get('relation'))]+=1
    if a.get('relation') not in RELATIONS:counts['rows_invalid_relation_enum']+=1
    if a.get('context_type') not in CONTEXTS:counts['rows_invalid_context_enum']+=1
    if a.get('polarity') not in ('asserted','negated'):counts['rows_invalid_polarity_enum']+=1
    if a.get('modality') not in ('obligatory','typical','frequent','occasional','rare'):counts['rows_invalid_modality_enum']+=1
    cg=a.get('criterion_group') or {};gid=clean(cg.get('group_id')) if isinstance(cg,dict) else None
    if gid is None:counts['atomic_units']+=1
    else:groups[str(gid)].append((idx,a))
   for gid,rows in groups.items():
    counts['group_units']+=1;counts['group_member_rows']+=len(rows);counts['group_valid_member_rows']+=sum(bool(a.get('subject') and a.get('predicate')) for _,a in rows);sizes[str(len(rows))]+=1
    fields={f:sorted({str(clean(a.get(f))) for _,a in rows}) for f in ('subject','relation','polarity','context_type')}
    fields['logic']=sorted({str(clean(a['criterion_group'].get('logic'))) for _,a in rows})
    fields['n']=sorted({str(clean(a['criterion_group'].get('n'))) for _,a in rows})
    flags=[]
    if any(not a.get('subject') or not a.get('predicate') for _,a in rows):flags.append('has_invalid_member')
    for f in ('subject','relation','logic','n'):
     if len(fields[f])>1:flags.append('mixed_'+f)
    if len(rows)==1:flags.append('singleton')
    if 'negated' in fields['polarity']:flags.append('has_negative_literal')
    if any(isinstance(a.get('threshold'),dict) and any(clean(v) is not None for v in a['threshold'].values()) for _,a in rows):flags.append('has_threshold')
    if any(clean(a['criterion_group'].get('logic')) not in ('all','any','at_least_n') for _,a in rows):flags.append('invalid_or_missing_logic')
    ns=[a['criterion_group'].get('n') for _,a in rows if a['criterion_group'].get('logic')=='at_least_n']
    if ns and any(not isinstance(n,int) or isinstance(n,bool) or n<1 or n>len(rows) for n in ns):flags.append('n_outside_emitted_member_count')
    for flag in flags:counts[flag]+=1
    records.append({'arm':arm,'cache_id':cid,'group_id':gid,'raw_indices':[i for i,_ in rows],'members':len(rows),'fields':fields,'flags':flags})
  result[arm]={'counts':dict(counts),'relations':dict(rels),'group_size_distribution':dict(sizes)}
 (OUT/'raw_group_census.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (OUT/'raw_group_ledger.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
 print(json.dumps({k:v['counts'] for k,v in result.items()},indent=2))
if __name__=='__main__':main()
