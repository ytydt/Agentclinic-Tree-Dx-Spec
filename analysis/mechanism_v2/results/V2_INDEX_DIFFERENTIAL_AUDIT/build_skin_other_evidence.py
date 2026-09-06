#!/usr/bin/env python3
"""Serialize explicitly selected, manually reviewed source-to-score cases.
Selections locate known events; the human-style semantic judgments below are
AI review, not automatic clinical labels or a probability sample.
"""
import gzip,hashlib,json
from pathlib import Path
import replay_audit as ra
OUT=Path(__file__).resolve().parent
SPECS={
'119':[
 ('119-confirmation','cornoid lamella', ['strength_overstatement','exception_disconnected'], 'Source supports porokeratosis morphology but explicitly limits historical pathognomonic status; general disease evidence does not identify EPPP.'),
 ('119-IgA','granular deposits of IgA',['target_parent_collapse','predicate_identity','false_confirmation'],'IgA deposits in papillary dermis are not the decreased epidermal granular layer in this patient.'),
 ('119-sideeffects',['skin irritation','skin atrophy'],['treatment_effect_to_disease_feature','site_state_loss'],'Topical treatment adverse effects are not current porokeratosis diagnostic manifestations; facial asymptomatic papules do not establish these effects.'),
 ('119-malignancy',['malignant degeneration','basal cell carcinoma transformation'],['causal_direction','predicate_identity'],'Risk of malignant progression is not a cause of porokeratosis; basal-cell carcinoma transformation is not vacuolar basal-cell degeneration.'),
 ('119-growth','expansion of abnormal epidermal keratinocytes',['predicate_state_opposition'],'Expansion of abnormal keratinocytes is not epidermal atrophy.'),
 ],
'56':[
 ('56-IHC',['positive staining for desmin','positive staining for h-caldesmon','positive staining for myocardin','positive staining for p16'],['marker_identity','scope_loss','evidence_multiplication'],'Different stains are not evidence of one another: these source-listed markers were joined to unconnected vimentin positivity.'),
 ('56-exact-subject',None,['first_match_parent_capture','candidate_starvation'],'Every selected raw row explicitly names the existing complete candidate, but earlier Carcinoma captures it before exact matching.'),
 ('56-L4',None,['differential_list_to_discriminator','focus_subject','cross_organ_scope','predicate_identity','comparator_parent_broadcast'],'These source propositions do not establish an observed discriminator against the full SCC candidate. They are bare differential names or unavailable markers from different sites/entities.'),
 ],
'91':[
 ('91-PECAM-alias','PECAM-1 expression',['missed_marker_synonym_join'],'PECAM-1 is CD31. This is source-backed Kaposi sarcoma knowledge successfully extracted but unjoined to patient CD31; it is not an Angiosarcoma rule or proof of complete disease-source coverage.'),
 ('91-visceral','gastrointestinal hemorrhage',['population_scope','subject_identity','anatomic_identity'],'Infantile visceral hemangioma complication is bound to cavernous angioma and intracerebral bleeding.'),
 ('91-age','resolution before age 4',['population_scope','temporal_argument','numeric_failure_positive'],'Age of infantile lesion involution is not current age 36; false/irrelevant threshold still gets positive soft evidence.'),
 ('91-THS',None,['focus_subject','group_omission','group_partial_credit','anatomic_scope'],'A Tolosa-Hunt diagnostic set is reassigned to Cavernous angioma; only nonspecific headache supplies partial all-group credit.'),
 ('91-surgical',None,['workflow_to_diagnosis','scope_qualifier_loss','group_partial_credit'],'Surgical indications in diagnosed cavernoma are converted to diagnostic features/requirements; brain-stem/location and symptom-severity scopes disappear.'),
 ('91-molecular',None,['procedure_to_necessity','predicate_identity','absence_scope','gate_reentry'],'A recommended SFT workup becomes mandatory all; molecular testing joins normal neurologic testing and vetoes the competing HPC label.'),
 ],
'179':[
 ('179-proxy',['decreased or absence of platelet granules','abnormalities of platelet components','mean platelet volume (MPV)','immature platelet fraction (IPF)'],['subject_identity','predicate_measurement_identity','numeric_unit','source_to_proxy_drift'],'GPS/IPD morphology, volume, and fraction are not platelet count. These distinct assertions provide all positive soft score for the thrombocytopenia proxy.'),
 ('179-high','platelet counts >450,000/L',['opposite_disease_subject','source_unit_corruption','numeric_unknown_positive'],'Source is thrombocytosis with corrupted micro-unit; becomes positive Immune thrombocytopenia evidence without validated numeric satisfaction.'),
 ('179-nonimmune','dose-dependent suppression of platelet production',['immune_nonimmune_identity','drug_scope','mechanism_to_observation'],'Drug-induced NONimmune mechanism is given to immune thrombocytopenia and a count is treated as observation of its mechanism.'),
 ('179-L4',None,['restored_list_to_discriminator','comparator_subject_confusion','population_scope','candidate_broadcast'],'Restored differential lists from gids652720/372441 generate invalid L4 penalties against PAVSD/TOF-PA from bare disease names.'),
 ('179-heart',['increased pulmonary blood flow','pulmonary arterial hypertension','pulmonary plethora','increased pulmonary vascular markings','Atrial septal defect','ventricular dysfunction'],['atrial_ventricular_identity','anatomic_physiologic_opposition','condition_component_binding'],'ASD/increased pulmonary-flow and ventricular dysfunction predicates do not establish pulmonary atresia or a ventricular septal defect.'),
 ]}

def main():
 result={'method':'AI direct source review; mechanism-enriched selection, not a frequency estimate. Events include faithful companion rows; codes characterize event-level failures, not every row as an error.','indexing':'zero-based original merged case extraction rows; source gid is within the named index','cases':[]}
 for short, specs in SPECS.items():
  ck=next(t['case_key']for t in ra.load('trial_tasks_11_all4.json')if t['case_key'].endswith('/'+short))
  task=next(t for t in ra.load('trial_tasks_11_all4.json')if t['case_key']==ck)
  obj={'case_key':ck,'gold':task['gold'],'legacy_proxy':task['gold_labels_in_set'],'events':[]}
  for arm,aid in enumerate(ra.ARM_IDS):
   pack=json.load(gzip.open(OUT/'replay_outputs'/f'{ck.replace("/","__")}__{aid}.json.gz','rt'))
   raw=pack['stages']['raw'];post={a['_audit_raw_index']:a for a in pack['stages']['post_gate']}
   ret=next(e for e in ra.load(ra.ARMS[arm][2])if e['case_key']==ck)
   passages={q['gid']:q for b in ret['retrieved'].values()for q in b['passages']}
   for event,preds,codes,judgment in specs:
    if event=='56-exact-subject':ids=[i for i,a in enumerate(raw)if a['subject'].lower()=='sarcomatoid squamous cell carcinoma']
    elif event=='179-L4':ids=sorted({i for v in pack['result']['ranking'] for p in v.get('layer4_penalties',[]) if p.get('_audit_source',{}).get('gid') in [652720,372441] for i in p['_audit_raw_ids']})
    elif event=='56-L4':ids=sorted({i for p in next(v for v in pack['result']['ranking']if v['label']=='Sarcomatoid squamous cell carcinoma').get('layer4_penalties',[])for i in p['_audit_raw_ids']})
    elif event=='91-THS':ids=list(range(228,232))if arm==3 else []
    elif event=='91-surgical':ids=({2:list(range(64,67))+list(range(70,74)),3:list(range(82,85))}).get(arm,[])
    elif event=='91-molecular':ids=list(range(2106,2111))+list(range(2450,2455))if arm==1 else []
    else:
     preds=[preds]if isinstance(preds,str)else preds
     ids=[i for i,a in enumerate(raw)if a['predicate']in preds]
     if short=='119' and event!='119-IgA':ids=[i for i in ids if 'porokeratos' in raw[i]['subject'].lower()]
    if not ids:continue
    entries=[]
    for i in ids:
     a=raw[i];meta=a.get('_audit_source',{});p=passages.get(meta.get('gid'));text=p['text'][:6000]if p else ''
     q=a.get('quote','');pos=text.lower().find(q.lower())if q else -1
     snippet=text[max(0,pos-300):min(len(text),pos+len(q)+500)]if pos>=0 else text[:1200]
     bindings=[{'candidate':label,'assertion':b}for label,items in pack['stages']['bound'].items()for b in items if i in b.get('_audit_support_raw_ids',[b['_audit_raw_index']])]
     outcomes=[]
     for v in pack['result']['ranking']:
      for stage in ['contributions','confirmed','eliminated','layer4_penalties']:
       for k,c in enumerate(v.get(stage,[])):
        if i in c.get('_audit_raw_ids',[]):outcomes.append({'candidate':v['label'],'stage':stage,'item_index':k,'payload':c})
     entries.append({'raw_index':i,'raw_assertion':a,'post_gate':post.get(i),'source':{'gid':meta.get('gid'),'title':p.get('title')if p else None,'doc_key':p.get('doc_key')if p else None,'input_sha256':hashlib.sha256(text.encode()).hexdigest(),'quote_exact_in_input':pos>=0,'excerpt':snippet},'bound':bindings,'outcomes':outcomes})
    obj['events'].append({'event_id':event,'arm':aid,'error_codes':codes,'manual_judgment':judgment,'rows':entries})
  result['cases'].append(obj)
 (OUT/'judgments_skin_other.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('cases',len(result['cases']),'event_arm_records',sum(len(c['events'])for c in result['cases']),'row_evidence',sum(len(e['rows'])for c in result['cases']for e in c['events']))
if __name__=='__main__':main()
