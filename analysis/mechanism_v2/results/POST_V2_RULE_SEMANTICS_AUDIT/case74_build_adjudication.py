#!/usr/bin/env python3
"""Materialize single-reviewer, purposive source-to-execution adjudications.
Labels are manually authored below, not inferred from relation keywords or gold rank.
This script writes only the JSON/CSV ledger. The reviewed narrative is maintained
separately in case74_audit.md and is never generated or overwritten here.
"""
import csv,json,pathlib,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[4]; OUT=pathlib.Path(__file__).resolve().parent
L=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'; KEY='MCR_v1_seq100/74'
def c(f):return next(x for x in json.loads((L/f).read_text()) if x['case_key']==KEY)
OLD='trial_extraction_x2_v2idxclean_groups.json';NEW='trial_extraction_x2_v2idxclean_groups_free.json'
ES={f:c(f) for f in [OLD,NEW]};R=c('trial_retrieval_x2_v2idx.json');PS={p['gid']:p for b in R['retrieved'].values() for p in b['passages']}
T=json.loads((OUT/'case74_pipeline_trace.json').read_text()); TS={r['input_file']:r for r in T}
rows=[]
def add(id,kind,refs,gids,verdict,correct,mechanism,harm,epistemic='source-and-code-direct'):
    assertions=[]; trace=[]
    for f,ixs in refs:
        for ix in ixs:
            a=ES[f]['assertions'][ix]
            assertions.append({'file':str((L/f).relative_to(ROOT)),'array_path':f"case_key={KEY}/assertions/{ix}",'index_zero_based':ix,'assertion':a})
            for label,items in TS[f]['bound'].items():
                for x in items:
                    if x.get('_audit_raw_index')==ix:
                        trace.append({'file':f,'candidate':label,'raw_index':ix,'post_gate_relation':x['relation'],'post_gate_polarity':x['polarity'],'post_gate_predicate':x['predicate'],'gate':x.get('_gate'),'join':x.get('_join'),'finding':x.get('_finding'),'support':x.get('_support'),'post_gate_group':x.get('criterion_group')})
    src=[]
    for gid in gids:
        p=PS[gid];src.append({'retrieval_file':'RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retrieval_x2_v2idx.json','gid':gid,'window_gids':p.get('window_gids'),'doc_key':p['doc_key'],'title':p['title'],'section_path':p.get('section_path'),'sha256_text':hashlib.sha256(p['text'].encode()).hexdigest()})
    rows.append({'id':id,'case_key':KEY,'unit':kind,'adjudicator':'single AI reviewer performing source-close-reading; not a human clinical consensus','selection':'purposive mechanism sample; no prevalence estimate','verdict':verdict,'correct_interpretation':correct,'error_mechanism':mechanism,'downstream_harm':harm,'evidence_status':epistemic,'source_locators':src,'raw_assertions':assertions,'postprocessing_execution_trace':trace})
add('C74-01','nested route',[ (OLD,list(range(857,862))), (NEW,list(range(848,853))) ],[74601], 'wrong_connective_and_global_necessity',
'Route 1 is normal structure AND normal ECG AND age<40 AND unexplained exercise/catecholamine-induced (bidirectional VT OR polymorphic PVCs), sufficient for this route. Its components are not individually necessary across all four diagnostic routes.',
'Both arms encode all five flattened members as ALL; OR rhythm alternatives become AND, while route-local conditions become global required_for/obligatory. Schema has no nested AST or route identifier.',
'Actual group gets +0.417 from the false structure→pulse match despite only 1/5 matched; no formal route completes. Potential: false exclusion when one rhythm alternative is absent although another valid route is satisfied.')
add('C74-02','atomic alternative route',[(OLD,[862]),(NEW,[853,1038])],[74601],'sufficient_to_necessary_reversal',
'Within this CPVT table, a pathogenic CPVT-related mutation is an alternative route sufficient for diagnosis, not a requirement for every CPVT diagnosis. “Pathogenic mutation” needs disease/gene scope rather than any pathogenic variant.',
'New prompt turns sufficient_for into required_for; gate demotes both old correct and new wrong relations to feature_of because the isolated quote omits “CPVT is diagnosed”.',
'Actual no genetic result is joined, so zero local diagnostic action. Potential: excluding mutation-negative CPVT or failing to confirm a valid genotype route. High-stakes yield increase is not a fidelity gain.')
add('C74-03','family scoped route',[(OLD,[863,864]),(NEW,[854,855,856])],[74601],'scope_deleted_and_or_changed',
'FamilyMemberOf(CPVT_index) AND normal_heart AND (exercise-induced PVCs OR bidirectional/polymorphic VT) provides route 3. Missing family membership is unknown, not false.',
'Old makes two rhythm members ALL and drops family and normal-heart conditions; new makes separate ungrouped global necessities.',
'No selected rhythm member actually joins in case74. Potential: generalizing family-screening criteria to unrelated patients, or excluding patients lacking each rhythm subtype.')
add('C74-04','age scoped route',[(OLD,[865]),(NEW,[857,1041])],[74601],'sufficiency_scope_collapse',
'Age>40 is one applicability condition within route 4, which also requires specified normal structure/coronary arteries/ECG and induced arrhythmia; age alone is never sufficient.',
'New extraction writes age>40 as sufficient_for (one obligatory, one typical), discarding the rest of the older-patient route. Old merely calls age an occasional feature, also not an executable route.',
'Currently age is absent from extracted findings and gate demotes the sufficiency, so no observed confirmation. Potential severe false positives after age backfill or reactivation of layer2.')
add('C74-05','scorecard applicability',[(OLD,list(range(825,845))),(NEW,list(range(818,836)))],[74602],'missing_score_program_and_gate',
'Preserve the scorecard as a named program with signed points and mandatory ≥1 exercise stress-test/ambulatory Holter finding. If no qualifying finding is available, output indeterminate/no score, not a low score.',
'Neither arm represents the applicability gate, point coefficients, ordered output bands, or no-score state. New prompt produces generic ANY groups spanning symptoms and exercise-test criteria.',
'Actual new symptom/test ANY group scores +0.490 from generic collapse, even without the prerequisite test. Both arms treat QTc row as independent positive evidence. This is not execution of the source scorecard.')
add('C74-06','negative score component',[(OLD,[836,1017]),(NEW,[831,1018])],[74602],'negative_weight_to_exclusion_and_polarity_instability',
'Within this scorecard, evidence of ischemic/structural disease contributes −2 points; it is not an unconditional standalone CPVT veto. The term requires affirmative structural/ischemic evidence, not pulse measurement.',
'Old two case-variant focuses produce excludes/negated versus excludes/asserted for the same table row. F7 demotes negated variant only; asserted survives. New retains excludes/asserted but adds “evidence of”, changing lexical match.',
'Actual old-v2 row1017 matches pulse by loose token overlap and kills CPVT. New wording does not join and remains latent. Full harm chain needs both relation corruption and unsound matching.')
add('C74-07','negative score component',[(OLD,[835]),(NEW,[830,1017])],[74602],'negative_weight_to_positive_feature_or_exclusion',
'Ambulatory ventricular ectopy burden >2% of total beats contributes −1 to this scorecard. Requires ambulatory measurement, ectopy identity, and denominator/burden; ventricular fibrillation alone does not establish it.',
'New two focus variants encode same source row as positive feature_of and asserted excludes. Engine ignores exclusion threshold and joins to ventricular fibrillation by loose lexical overlap.',
'Actual new-v2 simultaneously adds +1.354 via row830 and kills CPVT via row1017. This is contradictory evidence generated from one source, not genuine conflicting guidelines.')
add('C74-08','negative genetic score component',[(NEW,[829,1016])],[74602],'negative_score_to_hard_exclusion',
'A negative CPVT panel contributes −1; this table does not authorize negative genetics⇒not CPVT.',
'Points sign is recast as excludes/asserted, losing graded and multi-input program semantics.',
'No genetic finding in case74, so latent. A future measured negative result would cause an unwarranted hard veto.')
add('C74-09','negative age score component',[(OLD,[837]),(NEW,[832,1019])],[74602],'signed_points_and_age_scope_lost',
'Age≥50 at sentinel event contributes −1. Preserve event time; being older is not exclusion.',
'Old marks age as positive typical feature; new makes it excludes/asserted. Age>40 diagnosis elsewhere in same source remains valid under route4 conditions.',
'Age missing in current findings prevents activation. Restoring age without fixing semantics exposes new errors; age repair alone is not a safe extraction improvement.')
add('C74-10','piecewise score rows',[(OLD,[830,831,832]),(NEW,[823,824,825])],[74602],'weights_dropped_then_threshold_rows_deduplicated',
'QTc≤420 yields +0.5; 421<QTc<460 yields 0; QTc≥460 yields −0.5. Preserve disjoint branch conditions and coefficients. The source itself leaves a boundary issue near 420/421; do not silently invent an interval correction.',
'All three rows become identical predicate/relation/polarity despite different thresholds; engine dedupe key omits threshold, so six entries across focus aliases collapse to first QTc row. New ANY group becomes singleton and is discarded.',
'Actual first QTc row alone scores +2.215 old-v2 / +1.824 new-v2 instead of source +0.5, and bypasses scorecard test gate. Potential: other QTc values evaluated against wrong surviving branch.')
add('C74-11','variant score rows',[(NEW,[826,827,828])],[74602],'evidence_grade_and_zero_weight_lost',
'Pathogenic, likely pathogenic, and VUS are distinct laboratory classifications weighted 4,2,0 in this scorecard; VUS is not established causation.',
'All become caused_by/typical in ANY g3; zero coefficient and evidence uncertainty disappear.',
'Latent in case74 with no variant result. Potential VUS is treated as causal and given same group contribution as pathogenic variant.')
add('C74-12','score output bands',[(OLD,[841,842,843,844])],[74602],'program_output_reified_as_patient_feature',
'Probability bands are outputs of an applicable computed score; low/nondiagnostic or no-evidence states are not universal biological absence.',
'Old extracts CPVT score thresholds as generic feature_of; new arm omits these outputs entirely in the selected focus.',
'No score finding exists in case74, hence no join. Counts of extracted atoms cannot detect loss of the actual executable decision program.')
add('C74-13','ARVC nested criterion',[(OLD,[131,132,133]),(NEW,[145,146,147])],[472428],'and_or_nesting_lost',
'Group I major requires (regional akinesia OR dyskinesia OR bulging) AND (global RV dilation OR global RV systolic dysfunction), with modality/nomogram qualifiers. This major item is not the entire ARVC diagnosis.',
'Both arms encode regional akinesia, global dilation and systolic dysfunction as one ANY group and lose alternative regional members and measurement qualifiers.',
'Potential false major-criterion satisfaction from isolated dilation; current case does not establish these RV-specific criteria. No gold-rank effect is required for this clear source-fidelity failure.')
add('C74-14','ARVC higher-level prerequisite',[(OLD,list(range(131,143))),(NEW,list(range(145,154)))],[472428],'quantifier_domain_and_category_gate_missing',
'At least one structural/tissue criterion from categories I or II is required in addition to the broader diagnostic framework; count distinct criterion categories/rows, not generic finding matches.',
'Table is now retrieved intact, but no executable cross-category ≥1 gate is extracted. Major/minor level, puberty/RBBB guards, region and sample domains are flattened.',
'This directly localizes residual failure after v2 table restoration to extraction/schema. Merely increasing at_least_n counts elsewhere is not evidence that this criterion became usable.')
add('C74-15','management eligibility',[(OLD,[1636]),(NEW,[1592])],[373402],'treatment_eligibility_to_disease_criteria',
'The ≥15mm septal criterion belongs to selection of existing HCM patients for alcohol septal ablation; source scope is procedure eligibility, not a necessary diagnosis rule for all HCM.',
'Extracts as HCM feature_of, context criteria, ALL group; group_all_required promotes ALL to disease veto regardless of the procedure target.',
'Actual this assertion binds to generic Cardiomyopathy before HCM because first matching candidate wins. Its ALL/5 procedure group actually eliminates Cardiomyopathy for normal septal thickness in both v2 arms; HCM candidate remains empty.')
add('C74-16','LQTS probability output',[(OLD,[1821]),(NEW,[1793])],[678396],'low_probability_to_exclusion',
'Schwartz score≤1 is labelled low probability by the source, not a logical proof that LQTS is absent.',
'excludes/asserted/obligatory invents hard effect from probabilistic classification.',
'No computed score finding is supplied, so presently latent. Enabling score compilation without correcting output effect could introduce hard false negatives.')
add('C74-17','reference interval',[(OLD,[1737]),(NEW,[1694])],[678396,301941],'reference_range_to_universal_necessity_and_sex_loss',
'A male normal-QTc interval defines a reference range; it is not a universal LQTS necessity and it is not the female cutoff. Retrieved source explicitly says basal ECG can be normal in LQTS.',
'Raw excludes/negated is unjustified; G2_reference_range rewrites it to abnormal QTc required_for/asserted. Dedup combines male/female thresholds under same predicate and drops sex scope.',
'Actual LQTS gets threshold_violated hard veto using female patient QTc380 against male cutoff440; this can help CPVT rank while remaining an invalid universal exclusion claim.')
add('C74-18','source exception and clinical ceiling',[],[301941,74601,74602],'prior_manual_oracle_overclaim',
'The provided vignette supports CPVT as the benchmark best answer but does not report induced bidirectional/polymorphic VT, qualifying Holter testing or a pathogenic variant. Source scorecard should be indeterminate; normal single ECG does not establish universal exclusion of LQTS or intermittent Brugada.',
'Prior manual_flow interprets normal baseline QTc/no Brugada pattern as certain exclusion and noisy shop as fully observed adrenergic trigger. These are stronger claims than the supplied data/source licenses.',
'Prevents using “recover all manual exclusions” as extractor ground truth. Benchmark rank correctness, formal criteria completion and clinical rule-out are different endpoints.','source-close-reading, benchmark label preserved')
add('C74-19','temporal patient fact',[],[],'past_negative_flattens_current_event',
'No prior cardiac arrest is a historical negative; current VF arrest followed by defibrillation and ROSC is a separate event. Record subject/time and event relation explicitly.',
'Finding5 is cardiac arrest absent with timing null; present-current arrest is not extracted, while VF/ROSC are separate. Later feature matches read the past negative as disease counterevidence.',
'Actual CPVT contributions include sudden cardiac death→cardiac arrest absent (−0.4). “Sudden death” is itself not equivalent to survived arrest, so identity and time errors compound.','vignette-and-execution-direct')
add('C74-20','patient fact omissions',[],[],'age_and_trigger_missing',
'Retain age21, sex female, temporal noisy-shop event, and relation of collapse to event; stress inference should be marked inferred rather than fabricated as measured.',
'All four extraction arms share 34 findings lacking age/sex/trigger. Extractor called clean text; malformed source Options still affected retrieval TF-IDF case_terms.',
'Age-applicability criteria cannot join; sex-specific threshold selection cannot work; induced-arrhythmia event cannot be reconstructed from independent words.','vignette-and-code-direct')
add('C74-21','positive normality',[(NEW,[849])],[74601],'normality_encoded_as_polarity',
'Normal ECG is a positive proposition about ECG status, not absence of an ECG feature. Group satisfaction must evaluate typed state/threshold and source negation, not whether generic finding polarity==present.',
'Group engine treats normal/absent findings as violations and ignores member polarity/threshold. Current normal ECG fails to join, while structurally normal heart joins pulse.',
'Actual group gives partial credit for wrong member. Potential: a correct normal ECG finding would be interpreted as violation and, with F4b, trigger false veto.')
add('C74-22','source specificity binding',[],[438270],'generic_disease_to_specific_candidate',
'Polymorphic VT is not synonymous with CPVT; generic etiologies/treatment features in a polymorphic-VT paragraph must retain parent scope and not become CPVT-specific discriminators.',
'First-match subject containment binds generic polymorphic ventricular tachycardia to CPVT. Generic long-QT/sinus-pause/electrolyte alternatives are scored as CPVT group features.',
'Actual old-v2 group:any/5 awards +1.477 with sinus pauses→sinus rhythm and prolonged QT→measured QTc380. Correct top1 in old index was partly supported by analogous wrong joins.','source-and-execution-direct')
add('C74-23','measurement threshold matching',[],[370013],'failed_threshold_still_positive',
'Patient EF45–50 does not satisfy EF<35. A qualified proposition known false must not receive net positive match credit.',
'Layer3 computes positive feature match then only subtracts 0.5*w for a failed threshold; remaining positive delta is weighted as evidence.',
'Actual CPVT gets +0.167 old-v2 / +0.137 new-v2 for EF<35 against extracted EF47.5; source scope is also unrelated risk stratification.','execution-direct')
add('C74-24','causal/treatment event',[],[450507],'spontaneous_termination_to_treated_ROSC',
'ROSC after two defibrillations is not spontaneous termination of a ventricular arrhythmia. The intervention and temporal relation are essential.',
'Loose/embedding-style semantic agreement confuses outcomes while erasing intervention dependence; generic arrhythmia paragraph is attached to CPVT.',
'Actual +3.746 CPVT score in both v2 arms and old-old despite no evidence of spontaneous termination. Old correct gold ranking does not validate rule semantics.','source-and-execution-direct')
add('C74-25','candidate identity endpoint',[],[],'duplicate_empty_gold_masks_elimination_rank',
'Case variants of CPVT and LQTS are one concept each. All candidate names must resolve before binding/scoring; aggregate elimination and rank over concepts.',
'13 task rows include two CPVT strings; first matching row consumes every bound assertion, second remains empty and score0. gold_rank selects any gold-labelled row.',
'Actual v2 active CPVT rank10/13 and eliminated, while empty duplicate rank4 produces reported gold_rank4. The reported 4→2 ablation is not the active gold trajectory.','task-and-execution-direct')
add('C74-26','cross-source provenance',[],[74601,74602],'table_scope_mislabel_and_assertion_provenance_loss',
'Keep doc id, table id, passage/window id and offsets on every rule and use them in group identity. Raw BioC marks T002 and T003 as TABLE.',
'v2 retrieved CPVT tables still use section_path ending References; extraction persists title/section/focus but no gid, table id or offsets. Group key uses title,section,focus,gid-string and subject.',
'Prevents a verifier from establishing exact rule scope reliably; single passage g1 names may collide or fragment across aliases. Concrete CPVT QTc group is destroyed by dedupe even before this group identity issue.','raw-source-and-code-direct')
for row in rows:
    if row['id'] in ['C74-19','C74-20','C74-25']:
        row['task_file']='RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_tasks_11_all4.json'
    if row['id']=='C74-19':row['finding_indices']=[5,11,12,13]
    if row['id']=='C74-20':row['finding_indices']=list(range(34));row['retrieval_case_terms']=R['case_terms']
meta={'case_key':KEY,'selection':'26 purposive adjudication units; each may span multiple raw rows; not a census/error rate','review_method':'Source text first, then required semantics, extracted rows, delivered F7/B1+S7 trace; single AI close-reading reviewer, no clinical co-review','source_tables_verified':'data/cpg/raw/pmc_oa/bioc-pmc10971616.json; TABLE ids jcm-13-01781-t002 (offset83028) and t003 (offset84000)','engine_trace_scope':'Default historical F7 evidence lookup to reproduce S35, no F7_EXTRA_RETRIEVAL override; see cohort agent for arm-matched F7. No new LLM calls.','indexing':'raw assertion indices are zero-based within the selected case, not list indices across cases','units':rows}
meta['counts']={'adjudication_units':len(rows),'distinct_extraction_records':len({(a['file'],a['index_zero_based']) for r in rows for a in r['raw_assertions']}),'row_references_including_reuse':sum(len(r['raw_assertions']) for r in rows),'unique_source_gids':len({s['gid'] for r in rows for s in r['source_locators']})}
meta['raw_model_response_verification']='case74_raw_cache_audit.json: 8 caches, 111 exact normalized-output links, zero field changes by normalise_group'
(OUT/'case74_manual_adjudication.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
with (OUT/'case74_manual_adjudication.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,lineterminator='\n',fieldnames=['id','unit','verdict','correct_interpretation','error_mechanism','downstream_harm','evidence_status','source_gids','assertion_refs']);w.writeheader()
    for r in rows:w.writerow({**{k:r[k] for k in w.fieldnames if k in r},'source_gids':';'.join(str(x['gid']) for x in r['source_locators']),'assertion_refs':';'.join(x['file'].split('/')[-1]+':'+str(x['index_zero_based']) for x in r['raw_assertions'])})
print('wrote',len(rows),'adjudication units')
