#!/usr/bin/env python3
"""Freeze source-linked human-style close reading; no model/API calls.
Indices refer to normalized extraction arrays, zero-based. Judgments were made
by direct comparison of full source windows, not by a lexical error classifier.
"""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent;SRC=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
NEW='trial_extraction_x2_v2idxclean_groups_free.json';OLD='trial_extraction_x2_v2idxclean_groups.json'
EXT={fn:{e['case_key'].split('/')[-1]:e for e in json.loads((SRC/fn).read_text())} for fn in [NEW,OLD]}
RET={e['case_key'].split('/')[-1]:e for e in json.loads((SRC/'trial_retrieval_x2_v2idx.json').read_text())}
JOBS=[json.loads(l) for l in (OUT/'extraction_job_manifest.jsonl').read_text().splitlines()]
rows=[]
def add(id,case,indices,gids,error,expected,observed,fn=NEW):
 e=EXT[fn][case];selected=[]
 for i in indices:
  a=e['assertions'][i];jobs=[j for j in JOBS if j['arm']==('free_v2' if fn==NEW else 'old_v2') and j['case_key']==e['case_key'] and j['assertion_start']<=i<j['assertion_stop_exclusive']]
  selected.append({'assertion_index':i,'assertion':a,'exact_extraction_jobs':jobs})
 passages=[]
 for focus,b in RET[case]['retrieved'].items():
  for p in b['passages']:
   if p['gid'] in gids and not any(x['gid']==p['gid'] for x in passages):passages.append({**p,'focus_for_first_occurrence':focus,'text_sha256':hashlib.sha256(p['text'].encode()).hexdigest()})
 assert len(passages)==len(gids),(id,gids,[p['gid'] for p in passages])
 rows.append({'audit_id':id,'case_key':e['case_key'],'extraction_file':fn,'extraction_sha256':hashlib.sha256((SRC/fn).read_bytes()).hexdigest(),
   'selection':'purposive failure-mode audit; not an error prevalence estimate','judgment_method':'assistant direct close reading of full served source windows; not an independent licensed-clinician panel',
   'assertions':selected,'source_passages':passages,'error_categories':error,'source_faithful_interpretation':expected,'observed_or_unmeasured_effect':observed})
add('C773_testing_not_indicated_is_not_disease_exclusion','773',[1336,1337,1338,1374,1451],[710361,710362,710363],
 ['action_vs_disease_scope','context_population_loss','negation_scope','unsafe_finding_join'],
 'The source recommends against PFO testing for divers who have ONLY minor decompression sickness symptoms. It does not state that joint pain/swelling excludes anatomical PFO. The antecedent is diver AND minor-only decompression sickness; the consequent is no indication for a test, not absence of disease. No diagnostic exclusion may be compiled from these sentences.',
 'Stored new-prompt/v2 replay records Patent Foramen Ovale eliminated through joint pain joined to post-activity chest pain. This demonstrates multiple errors in series: unsupported diagnostic effect and invalid body-site equivalence. The full IPAH+PFO gold is not itself a candidate; this is elimination of a gold component. Removing this one rule has not here been credited with recovering top1.')
add('C773_workup_goal_reversed_into_exclusion','773',[1733,1734],[652189],
 ['workup_vs_result','subject_role_reversal','wrong_candidate_binding'],
 'A V/Q scan is a procedure used to investigate/rule out pulmonary thromboembolism during PAH workup; performing such a workup or having pulmonary hypertension is not evidence that thromboembolism is absent. Likewise, a recommendation to exclude alternative causes of PH is not the rule PH => NOT left-heart-disease PH.',
 'Stored old-prompt/v2 reports a gold-label proxy excluded by pulmonary hypertension. Exact rank/trace provenance must be read alongside the replay; this source is an invalid high-stakes premise regardless of whether the parent/alias binder sends it to the IPAH candidate.',fn=OLD)
add('C522_count_scope_from_12_members_to_3_categories','522',[648,649,650],[889590,889591],
 ['quantifier_domain_substitution','cross_sentence_scope','alternatives_promoted_to_count'],
 'Three-or-more applies to the specified 12 psychomotor diagnostic features. The next sentence describes broad possible manifestations using MAY INVOLVE decreased motor activity, decreased engagement, OR excessive/peculiar motor activity. These broad categories do not become an at-least-3 diagnostic rule. A valid representation retains the named 12-member domain and separately represents optional broad categories.',
 'The normalized new/v2 extraction assigns all three broad categories at_least_n=3. They are not the specified twelve members. Downstream full gold rank is unavailable because the task accepts Catatonia/Dementia rather than the composite etiology. This item establishes extraction error without claiming an isolated rank effect.')
add('C522_other_disorder_prognostic_group_transplanted','522',[692,693],[889480],
 ['wrong_disease_scope','specifier_vs_diagnosis','cross_section_contamination'],
 'The two-feature rule is for the WITH GOOD PROGNOSTIC FEATURES specifier of schizophreniform disorder. The nearby WITH CATATONIA instruction is an additional, separate specifier. The source does not license Catatonia => count>=2 of these prognostic features. Subject and output type must remain schizophreniform-good-prognosis, not Catatonia.',
 'Extraction subjects are Catatonia with at_least_n=2. The stored bookkeeping reuses g1 within the same book/focus, which also risks collision with the distinct Catatonia criterion groups. Rank effect is unmeasured, and wrong subject is already established before execution.')
add('C522_imaging_menu_becomes_sufficiency_group','522',list(range(2134,2146)),[11807],
 ['procedure_vs_positive_result','indication_vs_confirmation','enumeration_not_diagnostic_disjunction'],
 'The ACR source enumerates initial imaging procedures for suspected DLB. It gives no disease-specific positive test result or statement that any listed procedure alone establishes DLB. Retain as a procedure menu with its clinical indication, not a sufficient_for ANY diagnosis group.',
 'Twelve procedure names become sufficient_for/typical with group any. This is a semantic error even if F7 subsequently demotes a subset: counts of high-weight relations cannot be counted as extraction improvement. A pure procedure-name match to patient MRI/CT cannot confirm DLB.')
add('C257_cardinal_signs_not_all_required','257',list(range(1177,1181))+[1328,1340],[413915,413927],
 ['descriptive_conjunction_vs_necessity','exception_scope_not_executable','same_source_logical_conflict'],
 'Four Kanavel signs form a clinical sign set, not four universally necessary conditions. The served evaluation paragraph explicitly states PFT should not be excluded when tendon-sheath tenderness is lacking, and reports only about half of patients display all four. The rule must preserve this exception and must not use ANY absent member to veto PFT. Missing vignette mention is separately UNKNOWN.',
 'New/v2 contains feature_of/typical all groups and a separate required_for/negated row for all-four. F4b converts all to required; its evaluator does not incorporate the separate negated necessity exception. This is a real unsafe compilation route, but no gold-component hard exclusion from a group was recorded for this case in the frozen summary.')
add('C475_direct_trauma_exclusion_wrong_polarity','475',[22,23],[468793,468794],
 ['negated_excludes_inversion','loss_of_shared_definition'],
 'Within this source definition, a TRUE AIN syndrome requires a spontaneous presentation with appropriate weakness; directly traumatic AIN injury is explicitly outside that definition. Thus positive direct-trauma evidence excludes the narrowly defined syndrome: D => NOT trauma, equivalently trauma => NOT D. The extracted excludes must be asserted about positive trauma, not a negated exclusion.',
 'The normalized row is excludes/negated/obligatory, so the layer-1 asserted-only exclusion path ignores it. The current vignette does not establish direct trauma; therefore this is a latent missed exclusion, not a demonstrated cause of the wrong top1 in case475.')
add('C475_carpal_lesion_context_as_AIN_syndrome','475',[53],[707478],
 ['wrong_subject_from_focus','anatomic_scope_loss','test_result_polarity'],
 'The source describes the AIN being spared in a distal/carpal median nerve injury, because the AIN branches in the forearm. It is not a statement that true AIN syndrome has no motor deficit. The local nerve mention is an anatomical comparator; it must not inherit the query focus as the diagnosed disease.',
 'The normalized assertion declares Anterior Interosseous Nerve Syndrome excludes/negated thumb flexion strength, quoting No deficit should be expected in the AIN. This combines a wrong target with an impoverished predicate. It cannot support a clinical veto; an isolated ranking effect was not run.')
(OUT/'cohort_manual_ledger.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
print('wrote',len(rows),'manual incidents')
