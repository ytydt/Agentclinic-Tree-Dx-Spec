#!/usr/bin/env python3
"""Artifact, matching, literal-source and denominator checks; not clinical tests."""
from pathlib import Path
import json,hashlib
from collections import Counter
O=Path(__file__).resolve().parent;R=O.parents[3];S=R/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
def main():
 checks=0
 def ck(v,msg):
  nonlocal checks
  assert v,msg
  checks+=1
 d=json.loads((O/'source_exposure_delta.json').read_text());rows=[json.loads(l) for l in (O/'source_exposure_ledger.jsonl').read_text().splitlines()];byid={r['exposure_id']:r for r in rows};text={}
 ck(len(rows)==7769,'7769 total exposures');ck(len(byid)==len(rows),'unique exposure identifiers')
 for idx in ['oldidx','v2idx']:
  p=S/f'trial_retrieval_x2_{idx}.json';ck(hashlib.sha256(p.read_bytes()).hexdigest()==d['input_sha256'][p.name],'input fingerprint')
  for c in json.loads(p.read_text()):
   for f,b in c['retrieved'].items():
    for rank,pas in enumerate(b['passages'],1):text[f'{idx}|{c["case_key"]}|{f}|{rank}']=pas['text'][:6000]
  rr=[r for r in rows if r['index']==idx];sm=d['indexes'][idx]
  ck(len(rr)==sm['exposures'],'exposure count');ck(sum(r['input_chars'] for r in rr)==sm['input_characters'],'character denominator')
  ck(dict(Counter(r['cross_index_category'] for r in rr))==sm['cross_index_categories'],'exclusive category counts')
 for r in rows:
  ck(hashlib.sha256(text[r['exposure_id']].encode()).hexdigest()==r['text_sha256'],'literal source hash')
  for oid in r['counterpart_refs']:
   other=byid[oid];ck(other['index']!=r['index'] and other['case_key']==r['case_key'],'counterpart index and case')
   if r['cross_index_category']=='identical_payload':
    ck(other['payload_sha256']==r['payload_sha256'],'exact payload link')
    for arm,a in r['arms'].items():
     peer=('free' if arm.startswith('free') else 'old')+('_v2' if other['index']=='v2idx' else '_old');b=other['arms'][peer]
     ck(a['cache_id']==b['cache_id'] and a['cache_sha256']==b['cache_sha256'],'identical file')
 x=json.loads((O/'source_text_examples.json').read_text());ck(len(x['cases'])==11,'all cases represented')
 for c in x['cases']:
  e=c['identical_payload_example'];ot=text[e['old']['exposure_id']];nt=text[e['v2']['exposure_id']]
  ck(ot==nt,'retained text');ck(e['shared_verbatim_paragraph'] in nt,'retained paragraph')
  e=c['changed_window_example'];ot=text[e['old']['exposure_id']];nt=text[e['v2']['exposure_id']]
  ck(e['shared_verbatim_paragraph'] in ot and e['shared_verbatim_paragraph'] in nt,'changed shared literal')
  for p in e['added_paragraphs']:ck(p in nt,'new paragraph in actual v2 input')
  for p in e['lost_paragraphs']:ck(p in ot,'lost paragraph in actual old input')
  for kind in ['new_title_family_example','lost_title_family_example']:
   e=c[kind]
   if e:
    r=e['exposure'];ck(e['paragraph'] in text[r['exposure_id']],'added/lost paragraph literal')
    absent=not any(e['paragraph'] in t for key,t in text.items() if byid[key]['case_key']==c['case_key'] and byid[key]['index']!=r['index'])
    ck(absent==e['paragraph_exactly_absent_all_other_index_case_windows'],'whole case other-index exact paragraph absence')
 for motif in json.loads((O/'source_manual_motifs.json').read_text())['cases']:
  for side in motif['sides'].values():
   row=side['exposure'];ck(side['actual_input_text']==text[row['exposure_id']],'manual motif actual source text')
   for arm,raw in side['raw_outputs'].items():
    ck(raw==json.loads((S/'trial_extraction_cache'/f'{row["arms"][arm]["cache_id"]}.json').read_text()),'manual motif raw cache equality')
 ck(d['embedding_dictionary_provenance']['exact_string_set_equal'],'legacy dictionary provenance equality')
 res={'passed':True,'checks':checks,'scope':'Artifact/link/hash/denominator/exact-paragraph checks, not clinical semantic accuracy or rank-causality tests.'}
 (O/'retrieval_delta_validation.json').write_text(json.dumps(res,indent=2)+'\n');print(json.dumps(res))
if __name__=='__main__':main()
