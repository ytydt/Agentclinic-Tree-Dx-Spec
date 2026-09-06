#!/usr/bin/env python3
"""Frozen cross-index exposure/caching audit. No calls; no gid-based matching."""
from pathlib import Path
from collections import Counter,defaultdict
import hashlib,json,sys,re
OUT=Path(__file__).resolve().parent; ROOT=OUT.parents[3]
SRC=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'; PREV=OUT.parent/'POST_V2_RULE_SEMANTICS_AUDIT'
sys.path.insert(0,str(OUT.parent/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'))
import run_trial_extraction as ext
import run_mechanical_engine as eng
import build_join_embeddings as embbuilder
MODEL='meta-llama/llama-3.3-70b-instruct'
ARM={'oldidx':['old_old','free_old'],'v2idx':['old_v2','free_v2']}
def sha(x):return hashlib.sha256(x.encode() if isinstance(x,str) else x).hexdigest()
def dump(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def signature(x):return sha(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
def safe_doc(p):
 s=p.get('doc_key') or '';return s if s.partition('|')[2] else None
def family(p):return (p['source'],p['title'].split(' > ')[0].strip())
def main():
 prev=json.loads((PREV/'provenance_summary.json').read_text())
 jobs=[json.loads(l) for l in (PREV/'extraction_job_manifest.jsonl').read_text().splitlines()]
 jmaps=defaultdict(dict)
 for j in jobs:jmaps[j['arm']][(j['case_key'],j['focus'],j['gid'],j['passage_sha256'])]=j
 rows={}; payload_cache={}; normalized_cache={}; summaries={}; embeddings=set(eng._embeddings()['idx'])
 for idx in ARM:
  rr=[]; retrieval=json.loads((SRC/f'trial_retrieval_x2_{idx}.json').read_text())
  for case in retrieval:
   for focus,b in case['retrieved'].items():
    for rank,p in enumerate(b['passages'],1):
     text=p['text'][:6000]; payload={'focus_disease':focus,'source':p['source'],'document_title':p['title'],'section_path':p['section_path'],'context_hint':ext.context_hint(p['source'],p['section_path'],p['title']),'passage':text}
     r={'exposure_id':f'{idx}|{case["case_key"]}|{focus}|{rank}','index':idx,'case_key':case['case_key'],'focus':focus,'retrieval_rank':rank,'gid':p['gid'],'window_gids':p.get('window_gids'),'doc_key':p.get('doc_key'),'valid_doc_key':safe_doc(p),'source':p['source'],'title':p['title'],'section_path':p['section_path'],'title_family':list(family(p)),'text_sha256':sha(text),'payload_sha256':signature(payload),'input_chars':len(text),'source_window_chars':len(p['text']),'truncated':len(p['text'])>6000,'anchor':p.get('anchor'),'rrf':p.get('rrf'),'arms':{}}
     for arm,kind in zip(ARM[idx],['guideline_groups','guideline_groups_free']):
      ck=ext.cache_key(kind,payload,MODEL); cp=SRC/'trial_extraction_cache'/f'{ck}.json'
      if ck not in payload_cache:
       raw=json.loads(cp.read_text()) if cp.exists() else None
       aa=(raw.get('assertions') or []) if isinstance(raw,dict) else []
       payload_cache[ck]={'cache_id':ck,'exists':cp.exists(),'cache_sha256':sha(cp.read_bytes()) if cp.exists() else None,'raw_assertion_count':len(aa),'empty_object':raw=={},'empty_assertions':not aa,'valid_rows':sum(isinstance(a,dict) and bool(a.get('subject')) and bool(a.get('predicate')) for a in aa)}
      jr=jmaps[arm].get((case['case_key'],focus,p['gid'],sha(text)))
      assert jr and jr['cache_id']==ck and jr['raw_assertion_count']==payload_cache[ck]['raw_assertion_count']
      r['arms'][arm]={**payload_cache[ck],'assertion_start':jr['assertion_start'],'assertion_stop_exclusive':jr['assertion_stop_exclusive']}
     rr.append(r)
  rows[idx]=rr
  summaries[idx]={'exposures':len(rr),'unique_payloads':len({r['payload_sha256'] for r in rr}),'unique_source_text_windows':len({(r['source'],r['text_sha256']) for r in rr}),'unique_title_families':len({tuple(r['title_family']) for r in rr}),'valid_doc_key_exposures':sum(bool(r['valid_doc_key']) for r in rr),'by_source':dict(Counter(r['source'] for r in rr)),'input_characters':sum(r['input_chars'] for r in rr),'truncated_exposures':sum(r['truncated'] for r in rr)}
  for arm in ARM[idx]:
   assert len(rr)==prev['arms'][arm]['jobs']
   assert len({r['arms'][arm]['cache_id'] for r in rr})==prev['arms'][arm]['unique_cache_jobs']
   assert sum(r['arms'][arm]['valid_rows'] for r in rr)==prev['arms'][arm]['stored_rows']
 def category(r,other):
  case=[x for x in other if x['case_key']==r['case_key']]
  equalpayload=[x for x in case if x['payload_sha256']==r['payload_sha256']]
  equaltext=[x for x in case if x['source']==r['source'] and x['text_sha256']==r['text_sha256']]
  samefocus=[x for x in equaltext if x['focus']==r['focus']]
  fam=[x for x in case if x['title_family']==r['title_family']]
  samedoc=[x for x in case if r['valid_doc_key'] and x['valid_doc_key']==r['valid_doc_key'] and x['source']==r['source']]
  if equalpayload:return 'identical_payload',equalpayload
  if samefocus:return 'same_source_text_focus_metadata_changed',samefocus
  if equaltext:return 'same_source_text_other_focus_only',equaltext
  ff=[x for x in fam if x['focus']==r['focus']]
  if ff:return 'same_title_family_and_focus_changed_window',ff
  if fam:return 'same_title_family_other_focus_changed_window',fam
  if samedoc:return 'same_valid_doc_key_changed_title_or_window',samedoc
  return 'no_same_case_document_or_title_family',[]
 ledger=[]; percase=[]
 for idx,otheridx in [('oldidx','v2idx'),('v2idx','oldidx')]:
  for r in rows[idx]:
   cat,links=category(r,rows[otheridx]); r['cross_index_category']=cat
   r['counterpart_refs']=[x['exposure_id'] for x in links]
   ledger.append(r)
  summaries[idx]['cross_index_categories']=dict(Counter(r['cross_index_category'] for r in rows[idx]))
 allcases=sorted({r['case_key'] for r in ledger})
 for case in allcases:
  d={'case_key':case,'index':{}}
  for idx in ARM:
   rr=[r for r in rows[idx] if r['case_key']==case]
   d['index'][idx]={'exposures':len(rr),'unique_source_text_windows':len({(r['source'],r['text_sha256']) for r in rr}),'unique_payloads':len({r['payload_sha256'] for r in rr}),'unique_title_families':len({tuple(r['title_family']) for r in rr}),'cross_index_categories':dict(Counter(r['cross_index_category'] for r in rr)),'by_source':dict(Counter(r['source'] for r in rr)),'focus_passages':dict(Counter(r['focus'] for r in rr))}
  percase.append(d)
 paired={}
 for oldarm,newarm in [('old_old','old_v2'),('free_old','free_v2')]:
  oc={r['arms'][oldarm]['cache_id']:r['arms'][oldarm] for r in rows['oldidx']};nc={r['arms'][newarm]['cache_id']:r['arms'][newarm] for r in rows['v2idx']}
  shared=oc.keys()&nc.keys();oldonly=oc.keys()-nc.keys();newonly=nc.keys()-oc.keys()
  paired[oldarm+'__'+newarm]={'unique_old_jobs':len(oc),'unique_new_jobs':len(nc),'shared_identical_cache_jobs':len(shared),'shared_identical_output_files':sum(oc[k]['cache_sha256']==nc[k]['cache_sha256'] for k in shared),'old_only_jobs':len(oldonly),'new_only_jobs':len(newonly),'cache_missing_old':sum(not x['exists'] for x in oc.values()),'cache_missing_new':sum(not x['exists'] for x in nc.values()),'partitions':{}}
  for name,ids,which in [('shared',shared,oc),('old_only',oldonly,oc),('new_only',newonly,nc)]:paired[oldarm+'__'+newarm]['partitions'][name]={'jobs':len(ids),'raw_assertion_rows':sum(which[k]['raw_assertion_count'] for k in ids),'valid_assertion_rows':sum(which[k]['valid_rows'] for k in ids),'empty_jobs':sum(which[k]['empty_assertions'] for k in ids),'empty_object_jobs':sum(which[k]['empty_object'] for k in ids)}
 embed={}
 for idx in ARM:
  for arm in ARM[idx]:
   free=arm.startswith('free');fn=f'trial_extraction_x2_{idx}clean_groups'+('_free' if free else '')+'.json';data=json.loads((SRC/fn).read_text());ed={}
   for c in data:
    aa=c['assertions']; pp={a['predicate'].strip() for a in aa}
    er={'assertion_rows':len(aa),'predicate_rows_present':sum(a['predicate'].strip() in embeddings for a in aa),'unique_predicates':len(pp),'unique_predicates_present':len(pp&embeddings),'by_exposure_delta':{}}
    for cat in sorted({r['cross_index_category'] for r in rows[idx] if r['case_key']==c['case_key']}):
     selected=[r for r in rows[idx] if r['case_key']==c['case_key'] and r['cross_index_category']==cat]; ar=[a for r in selected for a in aa[r['arms'][arm]['assertion_start']:r['arms'][arm]['assertion_stop_exclusive']]]
     er['by_exposure_delta'][cat]={'rows':len(ar),'present':sum(a['predicate'].strip() in embeddings for a in ar)}
    ed[c['case_key']]=er
   aa=[a for c in data for a in c['assertions']];pp={a['predicate'].strip() for a in aa}
   embed[arm]={'per_case':ed,'overall':{'assertion_rows':len(aa),'predicate_rows_present':sum(a['predicate'].strip() in embeddings for a in aa),'unique_predicates':len(pp),'unique_predicates_present':len(pp&embeddings)}}
   oldmet=json.loads((PREV/'cohort_metrics.json').read_text())['arms'][['old_old','free_old','old_v2','free_v2'].index(arm)]
   assert embed[arm]['overall']['predicate_rows_present']==oldmet['embedding_coverage_assertion_predicates']['present']
   assert embed[arm]['overall']['unique_predicates_present']==oldmet['embedding_coverage_unique_predicates']['present']
 motif=[]
 for r in ledger:
  if any(k in r['focus'].lower() for k in ['catatonia','catecholaminergic','appendic','foramen','pulmonary arterial']):motif.append(r)
 collected_embeddings=set(embbuilder.collect())
 assert embeddings==collected_embeddings
 summary={'embedding_dictionary_provenance':{'actual_unique_strings':len(embeddings),'current_legacy_builder_collected_strings':len(collected_embeddings),'exact_string_set_equal':embeddings==collected_embeddings,'builder_input_files':embbuilder.ARMS,'new_x2_arms_in_builder':False},'scope':'All 11 frozen development cases, two index retrieval files and four extraction arms; gid is never an alignment key across indexes.','api_calls':0,'lfs_objects_downloaded':0,'matching':'Within-case hierarchical many-to-many exposure classification; title-family matches are proxies, not proof of document identity. Unique payload/cache comparison additionally pools all cases.','input_sha256':{f'trial_retrieval_x2_{i}.json':sha((SRC/f'trial_retrieval_x2_{i}.json').read_bytes()) for i in ARM},'indexes':summaries,'same_prompt_cross_index_cache_comparison':paired,'embedding_coverage':embed,'per_case':percase,'validation':{'all_exposure_and_unique_job_and_saved_row_counts_match_prior_provenance':True,'all_raw_cache_ids_counts_match_job_ledger':True,'embedding_counts_match_prior_cohort_metrics':True},'limits':['An identical cache is reused, not a new independent LLM draw. No same-payload extraction stochasticity can be estimated from it.','Cache identifiers omit prompt body, provider, parser version and time; arm kind is historical proxy rather than a complete immutable execution manifest.','Old statpearls document IDs are absent; exact source+text is strong window identity, while source+title-family changed-window links require manual confirmation.','Empty {} is retained and separated from assertions: []; missing cache is not inferred from either.','Embedding coverage is an availability mechanism; net ranking harm cannot be inferred without controlled replay.']}
 dump('source_exposure_delta.json',summary)
 (OUT/'source_exposure_ledger.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in ledger))
 (OUT/'source_motif_ledger.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in motif))
 print(json.dumps({'indexes':summaries,'paired':paired,'embedding':{k:v['overall'] for k,v in embed.items()}},indent=2))
if __name__=='__main__':main()
