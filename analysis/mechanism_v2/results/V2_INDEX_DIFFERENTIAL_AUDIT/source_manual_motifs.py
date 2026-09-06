#!/usr/bin/env python3
"""Four manually selected source-window counterparts with actual raw outputs."""
import json
from pathlib import Path
O=Path(__file__).resolve().parent;R=O.parents[3];S=R/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
SELECT=[
 ('catatonia_complete_domain','DA_d2_heldout200b/522','Catatonia',480632,'Catatonia',496392,'v2 retains the lead-in and supplies all 12 criterion members, while replacing the old neighboring Walter classification. Cardinality-domain completeness is a real source delta.'),
 ('ph_workup_scope_and_focus','DA_d2_heldout200b/773','Pulmonary Hypertension',628614,'Tricuspid Regurgitation',661576,'The same workup paragraph remains in v2 but only in a different focus exposure; four RV assessment parameters are appended. This is not loss of the paragraph from the case corpus.'),
 ('appendicitis_list_restoration','MCR_v1_seq100/49','Appendicitis',732645,'Appendicitis',778204,'The actual v2 window contains the old paragraphs plus ten symptom/sign list members; the source describes general appendicitis rather than a stump-specific criterion.'),
 ('cpvt_score_serialization','MCR_v1_seq100/74','Catecholaminergic Polymorphic Ventricular Tachycardia',74469,'Catecholaminergic Polymorphic Ventricular Tachycardia',74602,'The scoring table was already present as a flattened tab row in oldidx; v2 reconstructs row boundaries. Do not treat all scored observations as new clinical content.')]
def main():
 rows=[json.loads(l) for l in (O/'source_exposure_ledger.jsonl').read_text().splitlines()];text={}
 for idx in ['oldidx','v2idx']:
  for c in json.loads((S/f'trial_retrieval_x2_{idx}.json').read_text()):
   for f,b in c['retrieved'].items():
    for p in b['passages']:text[(idx,c['case_key'],f,p['gid'])]=p['text'][:6000]
 cases=[]
 for name,case,of,og,nf,ng,note in SELECT:
  sides={}
  for idx,f,g in [('oldidx',of,og),('v2idx',nf,ng)]:
   row=next(r for r in rows if (r['index'],r['case_key'],r['focus'],r['gid'])==(idx,case,f,g));raw={}
   for arm,j in row['arms'].items():raw[arm]=json.loads((S/'trial_extraction_cache'/f'{j["cache_id"]}.json').read_text())
   sides[idx]={'exposure':row,'actual_input_text':text[(idx,case,f,g)],'raw_outputs':raw}
  cases.append({'motif':name,'case_key':case,'manual_source_interpretation':note,'sides':sides})
 (O/'source_manual_motifs.json').write_text(json.dumps({'scope':'Manually selected source delta/provenance witnesses, not an independent semantic accuracy sample or patient intervention.','cases':cases},ensure_ascii=False,indent=2)+'\n')
 print('wrote four source motifs')
if __name__=='__main__':main()
