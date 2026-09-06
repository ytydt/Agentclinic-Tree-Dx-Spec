#!/usr/bin/env python3
"""Supplement explicit disease-identity probes; rerun audit_neuro_cardio.py first."""
import json,copy
import audit_neuro_cardio as m
m.RESULT=json.loads((m.OUT/'interventions_neuro_cardio.json').read_text())
prior=json.loads((m.OUT/'judgments_neuro_cardio.json').read_text());m.J=prior['judgments']
for a in range(4):
 p=m.pack('773',a);l='Chronic Thromboembolic Pulmonary Hypertension';il='Idiopathic Pulmonary Arterial Hypertension'
 rows=[r for r in p['stages']['bound'][l] if r['subject'].lower()=='idiopathic pulmonary arterial hypertension']
 sub=m.family(p,'CTEPH_exact_IPAH_subject_suspension',l,rows,'Explicit IPAH subject is not CTEPH. This targeted probe separates identity error from medically reasonable inherited PH evidence.')
 ids=[r['_audit_raw_index'] for r in p['stages']['raw'] if r['subject'].lower()=='idiopathic pulmonary arterial hypertension']
 force={'force_bindings':[{'raw_ids':ids,'target_candidate':il}]}
 m.J.append({'id':f"{p['case_key']}/{p['arm']}/IPAH_exact_identity_restore",'case_key':p['case_key'],'arm':p['arm'],'family':'IPAH_exact_identity_restore','reason':'Global exact subject identity before loose or containment binding. It does not adjudicate extraction correctness inside these rows.','operation':'force_bindings','selector':force['force_bindings'][0]})
 m.execute('773',a,'suspend_CTEPH_only_explicit_IPAH_rows',sub)
 m.execute('773',a,'restore_exact_IPAH_subject_identity',force)
 p2=m.pack('522',a);target='Dementia with Lewy bodies';names={'dementia with lewy bodies','lewy body dementia','lewy body dementia (lbd)'}
 ids=[r['_audit_raw_index'] for r in p2['stages']['raw'] if r['subject'].lower() in names]
 f={'force_bindings':[{'raw_ids':ids,'target_candidate':target}]}
 m.J.append({'id':f"{p2['case_key']}/{p2['arm']}/DLB_exact_identity_restore",'case_key':p2['case_key'],'arm':p2['arm'],'family':'DLB_exact_identity_restore','reason':'Reassign only explicit DLB/LBD names to the existing DLB concept; keep generic Dementia or vascular rules and do not synthesize the missing Catatonia-related-to-DLB diagnosis.','operation':'force_bindings','selector':f['force_bindings'][0]})
 m.execute('522',a,'restore_explicit_DLB_subject_identity',f)
# Replace two earlier restore probes with identical logic but complete transplanted provenance.
p=m.pack('773',3);old=m.pack('773',1);r=copy.deepcopy(old['stages']['raw'][1872]);restore={'append_raw':[{'assertion':r,'source_arm':'free_old','source_raw_id':1872}]}
sel=next(j['selector'] for j in m.J if j['case_key']==m.CASE['773'] and j['arm']=='free_v2' and j['family']=='CTEPH_type_result_scope_errors')
m.RESULT=[r for r in m.RESULT if not (r['case_key']==m.CASE['773'] and r['arm']=='free_v2' and r['name'] in ['restore_old_proven_wrong_brake','restore_wrong_brake_and_suspend_numeric_votes'])]
m.execute('773',3,'restore_old_proven_wrong_brake',restore)
m.execute('773',3,'restore_wrong_brake_and_suspend_numeric_votes',m.combine(restore,{'remove_contributions':[sel]}))
for j in m.J:
 if j.get('family')=='CTEPH_stolen_subject_rows':
  j['family']='CTEPH_nonidentical_subject_assignment_upper_bound'
  j['reason']='Mechanism-only upper-bound suspension: nonidentical rows include generic PH evidence that can legitimately be inherited, plus stronger identity errors (IPAH/other etiologies). This entire family is NOT a clinical error count or correct universal fix. See separate exact-IPAH identity probes.'
prior['judgments']=m.J
(m.OUT/'judgments_neuro_cardio.json').write_text(json.dumps(prior,ensure_ascii=False,indent=2))
