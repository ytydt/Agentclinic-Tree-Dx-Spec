#!/usr/bin/env python3
"""Source-read, manually delimited error-family probes for 257/326/475/49.
Predicate selectors are frozen audit judgments, not automatic clinical labels.
All raw row indices are merged-case indices; numeric-only and join interventions
remain separate, and all deduplicated support IDs are retained.
"""
import gzip,json,time
from pathlib import Path
import replay_audit as api
OUT=Path(__file__).resolve().parent
CASES={'257':'MCR_seq200b/257','326':'MCR_seq200b/326','475':'MCR_seq200b/475','49':'MCR_v1_seq100/49'}
TARGET={'257':'Abscess','326':'Brucellosis','475':'Neuralgic Amyotrophy','49':'Appendiceal stump appendicitis'}

def family(case,label,c):
 p=c['predicate'].lower();f=c.get('finding','').lower()
 if c.get('_audit_stage')!='atomic_score':return None
 if case=='257':
  if label=='Diabetic Hand Infection' and 'hba1c' in p:return 'D_postoperative_risk_to_current_diagnosis'
  if label=='Septic Arthritis' and ('synovial' in p and 'wbc' in p):return 'D_specimen_mismatch'
  if label=='Septic Arthritis' and ('age younger than 30' in p or 'hip' in p or 'acj' in p):return 'D_population_anatomic_scope'
  if label=='Infectious Tenosynovitis' and ('painful passive extension' in p or 'inability to touch the palm' in p or 'thenar eminence' in p or 'hand sonography' in p):return 'D_anatomy_action_join'
  if label=='Cellulitis' and p in ['age','age of patients','age under 18']:return 'D_research_population_to_feature'
 elif case=='326':
  if label=='Brucellosis':
   if c.get('_audit_relation')=='synonym_of' and 'fever' in p:return 'T_synonym_to_patient_symptom'
   if p=='reactive bone sclerosis' and 'protein' in f:return 'T_imaging_to_lab'
   if 'cerebrospinal fluid culture' in p and 'blood' in f:return 'T_specimen_mismatch'
   if ('abdominal pain' in p or 'scrotal pain' in p) and f=='back pain':return 'T_anatomic_mismatch'
   if 'unpasteurized milk' in p and 'sheep stomach' in f:return 'T_exposure_route_mismatch'
   if 'positive brucella serology' in p and 'tuberculosis' in f:return 'H_pathogen_test_mismatch'
  if label=="Pott's disease" and ('absence of polymorphic neutrophil infiltrates' in p or 'high protein concentration' in p or 'cell count in synovial fluid' in p or 'forehead' in p or 'subperiosteal abscess' in p or 'granulomatous' in p):return 'D_specimen_identity_anatomic_mismatch'
  if label=='Epidural abscess' and (p=='epidural tumor' or p=='elevated white blood cell count'):return 'D_wrong_lesion_or_numeric_state'
 elif case=='475':
  if label=='Neuralgic Amyotrophy':
   if p=='posterior interosseous nerve involvement':return 'T_nerve_identity_mismatch'
   if p=='muscle oedema':return 'T_mri_result_to_emg_change'
   if p in ['mri','imaging','mri sensitivity'] or (p=='sensory loss of the shoulder and upper extremity' and 'mri' in f):return 'H_test_method_to_negative_result'
  if label=='Anterior Interosseous Nerve Syndrome' and (p in ['subtle weakness in the apb','thenar atrophy',"ability to make 'ok' sign"]):return 'D_carpal_scope_and_ability_polarity'
 elif case=='49':
  if label=='Appendiceal stump appendicitis' and ('neutrophil' in p and ('infiltrat' in p or 'mucosa' in p or 'intraluminal' in p)):return 'T_blood_neutrophils_to_histology'
  if label=='Cecal diverticulitis' and p in ['computed tomography findings','contrast ct scan','ultrasound scan','full blood count','c-reactive protein test','ct scan of the abdomen and pelvis','abdominal ultrasound','computed tomography (ct) scan','ct scan','ct imaging','mri','ultrasound','ct imaging of the abdomen','ct scan of abdomen']:return 'D_diagnostic_action_to_disease_evidence'
  if label in ['Neutropenic colitis','Typhlitis'] and (p in ['bloody diarrhea','chronic diarrhea','watery diarrhea','rebound tenderness','ct scans','ct scan','neutrophil count']):return 'D_qualifier_test_numeric_scope'
 return None

def summary(d):
 r=d['result'];return {'gold_rank':r['gold_rank'],'top1':r['top1'],'ranking':[{'label':c['label'],'rank':i+1,'score':c['score'],'eliminated':c['eliminated']} for i,c in enumerate(r['ranking'])],'applied_interventions':d['applied_interventions'],'score_reconstruction_all_pass':all(x['pass'] for x in d['score_reconstruction'])}

def main():
 result={'method':'Manual source-grounded families; baseline plus numeric-only removal and join blocking. Effects are conditional, not additive population effects. No patient facts or source statements inserted.','cases':[]}
 for case,key in CASES.items():
  for arm in range(4):
   path=api.pack_path(key,arm)
   d=json.loads(gzip.decompress(path.read_bytes())) if path.exists() else api.run(key,arm)
   sels={'T':[],'D':[],'H':[]};selected=[]
   for cand in d['result']['ranking']:
    for c in cand['contributions']:
     fam=family(case,cand['label'],c)
     if not fam:continue
     sel={'candidate':cand['label'],'raw_ids':c['_audit_raw_ids'],'finding':c.get('finding')}
     sels[fam[0]].append(sel);selected.append({'family':fam,'candidate':cand['label'],'contribution':c,'selector':sel})
   row={'case':case,'case_key':key,'arm':arm,'target_label':TARGET[case],'selected_rows':selected,'baseline':summary(d),'probes':{}}
   # Freeze explicit IDs and complete source context from actual packets.
   raw={a['_audit_raw_index']:a for a in d['stages']['raw']}
   ids=sorted({i for s in selected for i in s['selector']['raw_ids']})
   row['selected_raw_assertions']=[raw[i] for i in ids]
   for mode in ['remove_contributions','block_joins']:
    for name,ss in [('target_errors',sels['T']),('distractor_errors',sels['D']),('joint_errors',sels['T']+sels['D']),('target_harm_errors',sels['H'])]:
     if not ss:continue
     probe=api.run(key,arm,{mode:ss},detailed=False)
     row['probes'][mode+'__'+name]=summary(probe)
   result['cases'].append(row)
   (OUT/'judgments_infect_neuro.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
   print(case,arm,'base',row['baseline']['gold_rank'],'selected',len(selected),{k:v['gold_rank'] for k,v in row['probes'].items()},flush=True)
 if not result['cases']:raise RuntimeError('no cases')
 print('completed',len(result['cases']),flush=True)
if __name__=='__main__':main()
