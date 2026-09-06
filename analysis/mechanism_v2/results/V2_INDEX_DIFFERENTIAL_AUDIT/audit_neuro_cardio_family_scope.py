#!/usr/bin/env python3
"""A final directly-read family-role witness in the PFO screening group."""
import json
import audit_neuro_cardio as m
m.RESULT=json.loads((m.OUT/'interventions_neuro_cardio.json').read_text())
prior=json.loads((m.OUT/'judgments_neuro_cardio.json').read_text());m.J=prior['judgments']
for a in range(4):
 p=m.pack('773',a);l='Patent Foramen Ovale'
 rows=[r for r in p['stages']['bound'][l] if r['predicate'].lower()=='family history of patent foramen ovale' and (r.get('_finding') or {}).get('label')=='patent foramen ovale width']
 role=m.family(p,'PFO_family_role_patient_swap',l,rows,'Family history motivating screening is not the patient own imaged PFO. It is the only satisfied member of this any-group and creates 2.627 points in all four baselines.')
 j=next(x for x in m.J if x['arm']==p['arm'] and x['case_key']==p['case_key'] and x['family']=='PFO_wrong_test_exclusion')
 j2=next(x for x in m.J if x['arm']==p['arm'] and x['case_key']==p['case_key'] and x['family']=='PFO_size_and_test_votes')
 m.execute('773',a,'release_PFO_and_suspend_soft_errors_including_family_role',m.combine(role,{'block_joins':[j['selector']]},{'remove_contributions':[j2['selector']]}))
prior['judgments']=m.J
(m.OUT/'judgments_neuro_cardio.json').write_text(json.dumps(prior,ensure_ascii=False,indent=2))
