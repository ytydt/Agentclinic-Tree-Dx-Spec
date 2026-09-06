#!/usr/bin/env python3
"""Verbatim paragraph evidence for exposure deltas; descriptive, not clinical scoring."""
import json,re,difflib,hashlib
from pathlib import Path
from collections import defaultdict
O=Path(__file__).resolve().parent;R=O.parents[3];S=R/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
def paragraphs(t):return [x.strip() for x in t.splitlines() if x.strip()]
def jac(a,b):
 a=set(re.findall(r'\w+',a.lower()));b=set(re.findall(r'\w+',b.lower()));return len(a&b)/len(a|b) if a|b else 0

def main():
 rows=[json.loads(l) for l in (O/'source_exposure_ledger.jsonl').read_text().splitlines()];byid={r['exposure_id']:r for r in rows}
 text={}
 for idx in ['oldidx','v2idx']:
  for c in json.loads((S/f'trial_retrieval_x2_{idx}.json').read_text()):
   for f,b in c['retrieved'].items():
    for rank,p in enumerate(b['passages'],1):text[f'{idx}|{c["case_key"]}|{f}|{rank}']=p['text'][:6000]
 tasks=json.loads((S/'trial_tasks_11_all4.json').read_text());cases=[]
 def pack(r):return {k:r[k] for k in ['exposure_id','index','case_key','focus','gid','doc_key','title','source','text_sha256','cross_index_category','arms']}
 for task in tasks:
  ck=task['case_key'];gold=set(task['gold_labels_in_set']); rr=[r for r in rows if r['case_key']==ck];new=[r for r in rr if r['index']=='v2idx'];old=[r for r in rr if r['index']=='oldidx']
  def preference(r):return (r['focus'] in gold, any(x in r['title'].lower() for x in ['evaluation','diagnos','criteria','histopath']),-len(text[r['exposure_id']]))
  same=sorted([r for r in new if r['cross_index_category']=='identical_payload'],key=preference,reverse=True)[0]
  sameold=byid[same['counterpart_refs'][0]]
  sameentry={'old':pack(sameold),'v2':pack(same),'shared_verbatim_paragraph':paragraphs(text[same['exposure_id']])[0],'matching_evidence':'Entire delivered source+text+focus+title+section+hint payload is identical; same cache ID within each prompt.'}
  changed=[]
  for n in new:
   if n['cross_index_category']!='same_title_family_and_focus_changed_window':continue
   for oid in n['counterpart_refs']:
    o=byid[oid];op=paragraphs(text[oid]);np=paragraphs(text[n['exposure_id']]);shared=[x for x in np if x in op];add=[x for x in np if x not in op];drop=[x for x in op if x not in np]
    if not shared or not add:continue
    similarity=jac(text[oid],text[n['exposure_id']])
    score=(n['focus'] in gold, similarity>=.35, min(len(add),20),similarity)
    changed.append((score,n,o,shared,add,drop))
  chosen=max(changed,key=lambda x:x[0]) if changed else None
  ce=None
  if chosen:
   _,n,o,shared,add,drop=chosen
   ce={'old':pack(o),'v2':pack(n),'word_set_jaccard':jac(text[o['exposure_id']],text[n['exposure_id']]),'shared_verbatim_paragraph':shared[0],'added_paragraphs':add,'lost_paragraphs':drop,'old_input_chars':len(text[o['exposure_id']]),'v2_input_chars':len(text[n['exposure_id']]),'matching_evidence':'Same source/title family/focus plus literal shared paragraph; source continuity is corroborated, but this is not proof of unambiguous canonical document identity.'}
  nd=sorted([r for r in new if r['cross_index_category']=='no_same_case_document_or_title_family'],key=preference,reverse=True)
  od=sorted([r for r in old if r['cross_index_category']=='no_same_case_document_or_title_family'],key=preference,reverse=True)
  def one(r,opposite):
   pars=paragraphs(text[r['exposure_id']]);othertexts=[text[x['exposure_id']] for x in opposite]
   novel=[p for p in pars if not any(p in t for t in othertexts)]
   pool=novel or pars
   p=max(pool,key=lambda x:(len(x)>=80, sum(k in x.lower() for k in ['diagnos','differential','symptom','patient','disease','abscess','carcinoma','thrombocyt','nerve']),min(len(x),1000)))
   return {'exposure':pack(r),'paragraph':p,'paragraph_exactly_absent_all_other_index_case_windows':not any(p in t for t in othertexts),'matching_evidence':'No same source/title family in the other-index case exposure. Absence here does not mean absence from the whole source corpus.'}
  cases.append({'case_key':ck,'gold':task['gold'],'legacy_proxy_labels':task['gold_labels_in_set'],'identical_payload_example':sameentry,'changed_window_example':ce,'new_title_family_example':one(nd[0],old) if nd else None,'lost_title_family_example':one(od[0],new) if od else None})
 out={'method':'Deterministic illustrative selection, not a probability sample or clinical adequacy rating. Exact paragraphs checked against actual <=6000-char input. Changed-window example favors legacy proxy focus and expanded list; added/lost paragraphs are exact-string deltas, so rephrasing/sentence-boundary changes can appear as both.','cases':cases}
 (O/'source_text_examples.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 for c in cases:
  x=c['changed_window_example'];print('\n',c['case_key']);print('CHANGE',x['old']['focus'],x['old']['gid'],x['v2']['gid'],x['old']['title'],x['old_input_chars'],x['v2_input_chars']) if x else print('NOCHANGE')
  if x:print('ADD',str(x['added_paragraphs'])[:1800]);print('DROP',str(x['lost_paragraphs'])[:500])
  for k in ['new_title_family_example','lost_title_family_example']:
   y=c[k];print(k,y['exposure']['focus'],y['exposure']['gid'],y['exposure']['title'],y['paragraph'][:250]) if y else print(k,None)
if __name__=='__main__':main()
