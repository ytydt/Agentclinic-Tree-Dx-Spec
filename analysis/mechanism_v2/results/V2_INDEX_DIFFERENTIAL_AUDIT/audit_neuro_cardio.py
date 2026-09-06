#!/usr/bin/env python3
"""Execute the manually defined differential case probes for 522, 773 and 74.
Selections serialize exact historical row IDs; this is not an automatic semantic
classifier. Full source windows and baseline rows live in the replay/source ledgers.
"""
import gzip,json,copy,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT));import replay_audit as rp
CASE={'522':'DA_d2_heldout200b/522','773':'DA_d2_heldout200b/773','74':'MCR_v1_seq100/74'}
J=[];RESULT=[]
def pack(k,a): return json.load(gzip.open(rp.pack_path(CASE[k],a),'rt'))
def cand(p,l): return next(z for z in p['result']['ranking'] if z['label']==l)
def family(p,name,label,rows,reason,kind='block_joins'):
 ids=sorted({i for r in rows for i in rp.row_ids(r)})
 selector={'candidate':label,'raw_ids':ids}
 raw={a['_audit_raw_index']:a for a in p['stages']['raw']}
 J.append({'id':f"{p['case_key']}/{p['arm']}/{name}",'case_key':p['case_key'],'arm':p['arm'],'family':name,'reason':reason,'operation':kind,'selector':selector,'n_bound_rows':len(rows),'raw_evidence':[raw[i] for i in ids]})
 return {kind:[selector]} if ids else {}
def cf(p,name,label,cs,reason):
 ids=sorted({i for c in cs for i in c['_audit_raw_ids']});raw={a['_audit_raw_index']:a for a in p['stages']['raw']}
 J.append({'id':f"{p['case_key']}/{p['arm']}/{name}",'case_key':p['case_key'],'arm':p['arm'],'family':name,'reason':reason,'operation':'remove_contributions','selector':{'candidate':label,'raw_ids':ids},'baseline_direct_delta':sum(c['_audit_effective_score_delta'] for c in cs),'contribution_evidence':cs,'raw_evidence':[raw[i] for i in ids]})
 return {'remove_contributions':[{'candidate':label,'raw_ids':ids}]} if ids else {}
def combine(*args):
 d={}
 for arg in args:
  for k,v in arg.items():d.setdefault(k,[]).extend(v)
 return d
def execute(k,a,name,iv):
 r=rp.run(CASE[k],a,iv,detailed=False)
 RESULT.append({'case_key':CASE[k],'arm':rp.ARM_IDS[a],'name':name,'intervention':iv,'applied_interventions':r['applied_interventions'],'summary':rp.summary_row(r),'score_reconstruction':r['score_reconstruction']})
 RESULT[-1]['summary']['n_raw']=len(next(e for e in rp.load(rp.ARMS[a][1]) if e['case_key']==CASE[k])['assertions']) + len(iv.get('append_raw',[])) - len(set(iv.get('delete_raw_ids',[])))
 (OUT/'interventions_neuro_cardio.json').write_text(json.dumps(RESULT,ensure_ascii=False,indent=2))
 print(k,rp.ARM_IDS[a],name,'gold',r['result']['gold_rank'],'top',[(z['label'],z['score']) for z in r['result']['ranking'][:4]],flush=True)
def main():
 for a in range(4):
  p=pack('522',a);label='Catatonia';b=p['stages']['bound'];c=cand(p,label)
  menu=cf(p,'B12_test_menu','Vitamin B12 deficiency',[c for c in cand(p,'Vitamin B12 deficiency')['contributions'] if c['predicate'].lower() in ['total b12','active b12','plasma homocysteine']], 'NICE test-selection recommendations (including pregnancy/nitrous-oxide scopes) are not positive diagnostic laboratory results.')
  b12=cf(p,'B12_measurement_not_deficiency','Vitamin B12 deficiency',[c for c in cand(p,'Vitamin B12 deficiency')['contributions'] if c.get('finding')=='B12' and c['_audit_effective_score_delta']>0], 'The observed B12=1154.67 pmol/L does not entail low/borderline B12, deficient intake/absorption, or treatment response; numeric-only suspension retains all other evidence and vetoes.')
  mes=family(p,'mesenteric_site_assignment','Chronic ischemia',[r for r in b['Chronic ischemia'] if 'mesenteric' in r['subject'].lower()], 'Mesenteric disease-specific risk/features are assigned to the unqualified candidate originally generated for brain MRI chronic ischemia; PAD also binds CAD. Suspend this candidate assignment, not the source rule.')
  echo=family(p,'echolalia_is_not_echopraxia',label,[r for r in b[label] if r['predicate'].lower()=='echolalia' and (r.get('_finding') or {}).get('label')=='echopraxia'], 'One observed motor imitation sign is reused as a distinct speech-imitation criterion, inflating cardinality.')
  badcat=cf(p,'catatonia_unentailed_imaging_and_loss',label,[z for z in c['contributions'] if z.get('finding') in ['MRI brain','weight loss'] or z['predicate']=='bipolar disorder'], 'MRI test presence is not brain metabolism/structural dysfunction; weight loss is not memory/communication loss; MDD history is not bipolar disorder.')
  group=cf(p,'catatonia_group_vote_suspension',label,[z for z in c['contributions'] if z['why'].startswith('group:') and 'Schizophrenia with prominent' in str(z.get('_audit_group_key'))], 'Mechanism-only ablation of the colliding local-g1 group vote. Does not assert the correct catatonia evidence should be zero.')
  elim=cand(p,'Chronic ischemic encephalopathy')['eliminated'];ids=sorted({i for e in elim for i in e['_audit_raw_ids']});release={'block_joins':[{'candidate':'Chronic ischemic encephalopathy','raw_ids':ids,'finding':'focal neurologic deficits'}]}
  execute('522',a,'baseline',{})
  execute('522',a,'suspend_B12_menu_only',menu)
  execute('522',a,'suspend_B12_value_votes',b12)
  execute('522',a,'suspend_mesenteric_assignment',mes)
  execute('522',a,'remove_catatonia_false_echo_join',echo)
  execute('522',a,'release_wrong_cognitive_veto',release)
  execute('522',a,'suspend_catatonia_group_vote',group)
  execute('522',a,'release_veto_and_suspend_group_vote',combine(release,group))
  execute('522',a,'suspend_selected_positive_errors_both_sides',combine(b12,mes,badcat,echo))
 for a in range(4):
  p=pack('773',a);b=p['stages']['bound'];cl='Chronic Thromboembolic Pulmonary Hypertension';pl='Patent Foramen Ovale';il='Idiopathic Pulmonary Arterial Hypertension';el='Eisenmenger Syndrome'
  misroute=family(p,'CTEPH_stolen_subject_rows',cl,[r for r in b[cl] if r['subject'].lower() not in ['cteph','chronic thromboembolic pulmonary hypertension']], 'Parent PH/PAH, idiopathic PAH, PVOD and other subjects do not identify thromboembolic etiology. Withhold these assignments while preserving native CTEPH rows; no fallback redistribution is performed.')
  badpred=['Right-to-left ventricle basal diameter area ratio','Tricuspid annular plane systolic excursion-systolic pulmonary artery pressure ratio','Pulmonary artery diameter','end-expiratory pulmonary artery wedge pressure','normal pulmonary capillary wedge pressure','oxygen saturation monitoring','chest imaging','abnormal chest x-ray','hypoxia','blood pressure monitoring']
  badnum=cf(p,'CTEPH_type_result_scope_errors',cl,[c for c in cand(p,cl)['contributions'] if c['predicate'] in badpred or 'mean pulmonary art' in c['predicate'].lower()], 'Diameter/ratio/wedge/mean pressure are not the observed systolic pressure; measurements or recommended tests are not positive diagnoses; chest imaging is not chest pain and hypoxia is not hemoptysis. Includes type-invalid comparisons even where PH clinically exists.')
  pf=family(p,'PFO_wrong_test_exclusion',pl,[r for r in b[pl] if r['relation']=='excludes' and r['predicate'].lower()=='joint pain'],'No indication to screen minor decompression illness is not exclusion of an imaged PFO; chest pain is not joint pain.')
  psoft=cf(p,'PFO_size_and_test_votes',pl,[c for c in cand(p,pl)['contributions'] if c.get('finding')=='right atrium size' or c['predicate'].lower() in ['left atrial pressure higher than right atrial pressure','foramen ovale closure']], 'Atrial size is not PFO size; normal LA>RA is not entailed by pure R-to-L shunt; closure recommendation is not a performed treatment or confirmation.')
  eis=family(p,'Eisenmenger_wrong_direction_and_pressure',el,[r for r in b[el] if r.get('_finding') and (('left-to-right' in r['predicate'].lower()) or ('exceeds systemic' in r['predicate'].lower()) or r['predicate'].lower() in ['left ventricular hypertrophy','left ventricle pressure similar to right ventricle pressure','right atrial pressures'])], 'Present pure right-to-left shunt does not establish antecedent large left-to-right shunt; PASP alone cannot satisfy pulmonary>systemic relation; RV size is not LV hypertrophy or ventricular pressure equality.')
  hardids=sorted({i for c in cand(p,cl)['eliminated'] for i in c['_audit_raw_ids']});release={'block_joins':[{'candidate':cl,'raw_ids':hardids}]}
  execute('773',a,'baseline',{})
  execute('773',a,'suspend_CTEPH_numeric_and_test_votes',badnum)
  execute('773',a,'suspend_CTEPH_wrong_subject_assignments',misroute)
  execute('773',a,'release_CTEPH_old_wrong_brake',release)
  execute('773',a,'release_brake_and_suspend_numeric_votes',combine(release,badnum))
  execute('773',a,'release_PFO_wrong_veto',pf)
  execute('773',a,'release_PFO_and_suspend_PFO_soft_errors',combine(pf,psoft))
  execute('773',a,'suspend_Eisenmenger_wrong_joins',eis)
  execute('773',a,'local_error_package',combine(misroute,pf,psoft,eis))
  if a==3:
   old=pack('773',1);o=old['stages']['raw'][1872];o=copy.deepcopy(o);restore={'append_raw':[{'assertion':o,'source_arm':'free_old','source_raw_id':1872}]}
   execute('773',a,'restore_old_proven_wrong_brake',restore)
   execute('773',a,'restore_wrong_brake_and_suspend_numeric_votes',combine(restore,badnum))
 for a in range(4):
  p=pack('74',a);b=p['stages']['bound'];cl='Catecholaminergic Polymorphic Ventricular Tachycardia';ll='Long QT Syndrome';sl='Seizure disorder'
  qt=cf(p,'LQTS_unentailed_QT_positive_votes',ll,[c for c in cand(p,ll)['contributions'] if c.get('finding')=='QTc interval' and c['_audit_effective_score_delta']>0], 'QTc 380 ms does not satisfy prolonged-QT thresholds. Presence of a measurement, normal reference interval, monitoring recommendation and recovery-phase response are different claims; numeric-only probe keeps the existing LQTS veto.')
  badcp=family(p,'CPVT_inexact_positive_fact_joins',cl,[r for r in b[cl] if r.get('_finding') and ((r['_finding']['label']=='pulse' and ('heart' in r['predicate'].lower())) or r['predicate'].lower() in ['spontaneous termination','sinus pauses','sinus bradycardia','loss of av synchrony'])], 'Pulse is not structural-heart assessment; defibrillation-mediated ROSC is not spontaneous arrhythmia termination; sinus rhythm is not pauses/bradycardia; loss of consciousness is not AV dyssynchrony.')
  badsz=family(p,'seizure_wrong_entity_and_modality_joins',sl,[r for r in b[sl] if r.get('_finding') and r['predicate'].lower() in ['premature birth','increased intracranial pressure','focal eeg patterns','structural abnormalities of the brain','stress on heart']], 'Premature complexes are not premature birth; arm BP is not ICP; Brugada pattern is not EEG; valve anatomy is not brain anatomy. Veterinary seizure discussion is also population-scoped.')
  cpids=sorted({i for c in cand(p,cl)['eliminated'] for i in c['_audit_raw_ids']});cq={'block_joins':[{'candidate':cl,'raw_ids':cpids}]}
  lqids=sorted({i for c in cand(p,ll)['eliminated'] for i in c['_audit_raw_ids']});lq={'block_joins':[{'candidate':ll,'raw_ids':lqids}]}
  execute('74',a,'baseline',{})
  execute('74',a,'suspend_LQTS_false_positive_QT_scores_only',qt)
  execute('74',a,'suspend_CPVT_inexact_positive_joins',badcp)
  execute('74',a,'suspend_seizure_wrong_joins',badsz)
  execute('74',a,'release_CPVT_wrong_veto',cq)
  execute('74',a,'release_CPVT_and_suspend_its_bad_joins',combine(cq,badcp))
  execute('74',a,'release_both_QT_and_CPVT_vetoes_probe',combine(cq,lq))
  execute('74',a,'release_both_vetoes_and_suspend_QT_scores',combine(cq,lq,qt))
  execute('74',a,'release_both_and_suspend_both_soft_error_families',combine(cq,lq,qt,badcp,badsz))
 (OUT/'judgments_neuro_cardio.json').write_text(json.dumps({'method':'AI auditor direct source and vignette reading; purposive mechanism interventions, no prevalence estimate','raw_indices':'zero-based merged-case original extraction, never cache-local','judgments':J},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
