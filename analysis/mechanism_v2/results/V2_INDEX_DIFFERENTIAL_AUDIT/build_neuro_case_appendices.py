#!/usr/bin/env python3
"""Deterministic matrices, paired accounting and validation of manual probes."""
import json,gzip,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
ARMS=['old_old','free_old','old_v2','free_v2'];cases={'522':'DA_d2_heldout200b/522','773':'DA_d2_heldout200b/773','74':'MCR_v1_seq100/74'}
R=json.loads((P/'interventions_neuro_cardio.json').read_text());J=json.loads((P/'judgments_neuro_cardio.json').read_text())
base={}
for k,key in cases.items():
 for arm in ARMS:base[k,arm]=json.load(gzip.open(P/'replay_outputs'/f"{key.replace('/','__')}__{arm}.json.gz",'rt'))
for r in R:
 k=r['case_key'].split('/')[-1];r['summary']['n_raw']=len(base[k,r['arm']]['stages']['raw'])+len(r['intervention'].get('append_raw',[]))-len(set(r['intervention'].get('delete_raw_ids',[])))
(P/'interventions_neuro_cardio.json').write_text(json.dumps(R,ensure_ascii=False,indent=2))
codes={
'B12_test_menu':['TASK_PROMOTION','POPULATION_SCOPE_LOSS','TEST_RESULT_CONFUSION'],
'B12_measurement_not_deficiency':['NUMERIC_TRUTH_LOSS','PREDICATE_ARGUMENT_CONFUSION','REPEATED_FACT_VOTES'],
'mesenteric_site_assignment':['CANDIDATE_SITE_LOSS','FACT_IDENTITY_ERROR','RELATION_DUPLICATION'],
'echolalia_is_not_echopraxia':['FACT_IDENTITY_ERROR','DISTINCT_CRITERIA_DOUBLECOUNT'],
'catatonia_unentailed_imaging_and_loss':['TEST_RESULT_CONFUSION','LEXICAL_FALSE_JOIN','DISEASE_IDENTITY_ERROR'],
'catatonia_group_vote_suspension':['GROUP_LOCAL_ID_COLLISION','GLOBAL_LEAF_DEDUP','SENSITIVITY_NOT_FULL_CLINICAL_REPAIR'],
'CTEPH_nonidentical_subject_assignment_upper_bound':['SENSITIVITY_MIXED_VALID_PARENT_AND_INVALID_SPECIFIC'],
'CTEPH_type_result_scope_errors':['MEASUREMENT_TYPE_ERROR','NUMERIC_TRUTH_LOSS','TEST_RESULT_CONFUSION'],
'PFO_family_role_patient_swap':['PERSON_ROLE_SCOPE_LOSS','TEST_INDICATION_PROMOTION'],
'PFO_wrong_test_exclusion':['TASK_PROMOTION','RELATION_DIRECTION_ERROR','POPULATION_SCOPE_LOSS','FACT_IDENTITY_ERROR'],
'PFO_size_and_test_votes':['MEASUREMENT_ENTITY_ERROR','TEST_TREATMENT_CONFUSION','DIRECTION_SCOPE_LOSS'],
'Eisenmenger_wrong_direction_and_pressure':['DIRECTION_SCOPE_LOSS','CAUSAL_HISTORY_LOSS','MEASUREMENT_ENTITY_ERROR'],
'LQTS_unentailed_QT_positive_votes':['NUMERIC_TRUTH_LOSS','TEST_RESULT_CONFUSION','TEMPORAL_SCOPE_LOSS','REPEATED_FACT_VOTES'],
'CPVT_inexact_positive_fact_joins':['FACT_IDENTITY_ERROR','TREATMENT_OUTCOME_CONFUSION','PARENT_SCOPE_TRANSFER'],
'seizure_wrong_entity_and_modality_joins':['FACT_IDENTITY_ERROR','SPECIES_SCOPE_LOSS','RELATION_DIRECTION_ERROR'],
'CTEPH_exact_IPAH_subject_suspension':['SPECIFIC_DISEASE_IDENTITY_ERROR'],
'IPAH_exact_identity_restore':['SPECIFIC_DISEASE_IDENTITY_ERROR'],
'DLB_exact_identity_restore':['SPECIFIC_DISEASE_IDENTITY_ERROR']}
for j in J['judgments']:j['error_codes']=codes[j['family']]
J['limits']='Purposive, AI-reviewed mechanism witnesses. Family counts are not prevalence; whole nonidentical-subject suspension includes legitimate inherited parent evidence and is an upper-bound sensitivity probe.'
(P/'judgments_neuro_cardio.json').write_text(json.dumps(J,ensure_ascii=False,indent=2))
def c(p,label):return next(r for r in p['result']['ranking'] if r['label']==label)
def direct(k,arm,fams):
 return sum(j.get('baseline_direct_delta',0) for j in J['judgments'] if j['case_key']==cases[k] and j['arm']==arm and j['family'] in fams)
def fmt(z):return f"{z['_audit_rank']} / {z['score']:.3f}"+(' / E' if z['eliminated'] else '')
selections={
'522':['baseline','suspend_B12_menu_only','suspend_B12_value_votes','suspend_mesenteric_assignment','release_wrong_cognitive_veto','suspend_catatonia_group_vote','release_veto_and_suspend_group_vote','suspend_selected_positive_errors_both_sides','restore_explicit_DLB_subject_identity'],
'773':['baseline','suspend_CTEPH_numeric_and_test_votes','release_CTEPH_old_wrong_brake','release_brake_and_suspend_numeric_votes','release_PFO_wrong_veto','release_PFO_and_suspend_PFO_soft_errors','release_PFO_and_suspend_soft_errors_including_family_role','suspend_Eisenmenger_wrong_joins','restore_exact_IPAH_subject_identity','restore_old_proven_wrong_brake','restore_wrong_brake_and_suspend_numeric_votes'],
'74':['baseline','release_CPVT_wrong_veto','release_CPVT_and_suspend_its_bad_joins','release_both_QT_and_CPVT_vetoes_probe','release_both_vetoes_and_suspend_QT_scores','release_both_and_suspend_both_soft_error_families']}
account={'522':[('Catatonia',['catatonia_group_vote_suspension','catatonia_unentailed_imaging_and_loss']),('Vitamin B12 deficiency',['B12_test_menu'])], '773':[('Chronic Thromboembolic Pulmonary Hypertension',['CTEPH_type_result_scope_errors'])], '74':[('Long QT Syndrome',['LQTS_unentailed_QT_positive_votes'])]}
for k,key in cases.items():
 s=['\n\n<!-- GENERATED NEURO APPENDICES -->','## 完整四臂候选表','数格为“名次 / 软分 / E=已淘汰”。软分不等于最终排序；排除优先于软分。', '| 候选 | 旧提示/旧索引 | 新提示/旧索引 | 旧提示/v2 | 新提示/v2 |','|---|---:|---:|---:|---:|']
 for label in [z['label'] for z in base[k,'old_old']['task']['candidates']]:s.append('| '+label+' | '+' | '.join(fmt(c(base[k,a],label)) for a in ARMS)+' |')
 s+=['','## 分值差量与未裁决残余','下表是冻结基线上的账面分解，不是可相加的临床因果效应。选定家族仍有范围内的多个原子；其余合法变化、其他未裁决错误、去重/分组和claimant权重相互作用全部留在残余中。舍入误差可达0.001分。','| 对比 | 候选 | 总软分Δ | 已选直接贡献Δ | 残余Δ |','|---|---|---:|---:|---:|']
 for oa,na in [('old_old','old_v2'),('free_old','free_v2')]:
  for label,fams in account[k]:
   total=c(base[k,na],label)['score']-c(base[k,oa],label)['score'];dd=direct(k,na,fams)-direct(k,oa,fams)
   s.append(f'| {oa}→{na} | {label} | {total:+.3f} | {dd:+.3f} | {total-dd:+.3f} |')
 s+=['','已选家族：'+ '; '.join(f'{l}: `{", ".join(f)}`' for l,f in account[k])+'.','', '## 已执行的局部干预','下列仅展示旧0与新free-v2的重点切面；四臂全部运行及原始行号见 `../interventions_neuro_cardio.json`。`restore_old_proven_wrong_brake`故意恢复已证错误，只用于机制验证。`suspend_*`关闭证据或连接，并不自动补充遗漏的正确来源程序。','| 臂 | 干预 | 历史代理rank | top1 | 第一/第二名分数 |','|---|---|---:|---|---|']
 for r in R:
  if r['case_key']!=key or r['arm'] not in ['old_old','free_v2'] or r['name'] not in selections[k]:continue
  z=r['summary'];rr=z['ranking'];s.append(f"| {r['arm']} | `{r['name']}` | {z['gold_rank']} | {z['top1']} | {rr[0]['score']:.3f} / {rr[1]['score']:.3f} |")
 s+=['','完整重算命令：先运行 `python analysis/mechanism_v2/results/V2_INDEX_DIFFERENTIAL_AUDIT/audit_neuro_cardio.py`，再运行同目录 `audit_neuro_cardio_identity.py`、`audit_neuro_cardio_family_scope.py` 与 `build_neuro_case_appendices.py`。未调用新的LLM，未改生产代码。']
 f=P/'cases'/f'case_{k}.md';txt=f.read_text().split('<!-- GENERATED NEURO APPENDICES -->')[0].rstrip();f.write_text(txt+'\n'+'\n'.join(s)+'\n')
checks=[]
for r in R:
 k=r['case_key'].split('/')[-1];p=base[k,r['arm']];n=len(p['stages']['raw']);valid=set(range(n+len(r['intervention'].get('append_raw',[]))))
 allids=[]
 for key,vs in r['intervention'].items():
  if key=='delete_raw_ids':allids+=vs
  elif key not in ['append_raw','patch_raw']:
   for v in vs:allids+=v.get('raw_ids',[])
 checks.append({'case_key':r['case_key'],'arm':r['arm'],'name':r['name'],'all_raw_indices_valid':set(allids)<=valid,'all_scores_reconstructed':all(z['pass'] for z in r['score_reconstruction'])})
assert all(c['all_raw_indices_valid'] and c['all_scores_reconstructed'] for c in checks)
(P/'neuro_case_validation.json').write_text(json.dumps({'n_probes':len(R),'n_judgment_families':len(J['judgments']),'scope':'Provenance-index and score-reconstruction consistency, not independent clinical validation.','checks':checks},ensure_ascii=False,indent=2))
print('validated',len(R),'probes;',len(J['judgments']),'judgment families')
