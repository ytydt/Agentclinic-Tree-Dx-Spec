#!/usr/bin/env python3
"""Materialize independently close-read annotations with reproducible row pointers.

Annotations are deliberately selected counterexamples, not random samples or
expert clinical adjudication. They compare the supplied passage to the supplied
extraction; no claim is made that the passage is a current clinical guideline.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LEDGER=ROOT/"RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
sys.path.insert(0,str(HERE.parent/"RAG_GUIDELINE_ORACLE_CEILING_LOCAL"))
from audit_criteria_fidelity import passages,stated_logic

SCREEN={
"599595":("diagnostic_or_specifier_criterion","Several Alzheimer/nCD criteria and an all-3 sublist; a single all label does not encode their scopes or relations."),
"338188":("trigger_not_a_diagnostic_combination","'All of these symptoms can start from age 40–90' describes age of onset, not a requirement that every listed symptom be present. The passage also discusses diagnostic criteria, but this regex trigger supplies no all-of rule."),
"628186":("trigger_not_a_diagnostic_combination","'2.5% to 5% of these cases' is prevalence; the digit 5 is not a k-of-n criterion."),
"889603":("trigger_not_a_diagnostic_combination","'may be present in any of ... five psychotic disorders' lists disorders associated with catatonia, not alternative sufficient diagnostic findings."),
"889480":("diagnostic_or_specifier_criterion","Good-prognosis specifier requires at least 2 features; the negative specifier must preserve the negated count. It is not the disease's base diagnostic rule."),
"854182":("diagnostic_or_specifier_criterion","DLB source describes a 2-of-3 criterion, with separate descriptive features and historical/newer-criteria commentary."),
"889487":("diagnostic_or_specifier_criterion","Schizophrenia criterion A has >=2 of 5 AND >=1 of the first 3 AND a time window; functioning is a separate necessary criterion."),
"889594":("diagnostic_or_specifier_criterion","Catatonia requires >=3 of 12 distinct qualified symptoms. Last four members are repeated in the source window."),
"892708":("trigger_not_a_diagnostic_combination","'criteria ... across all of these disorders' is metatext about DSM changes, not all member predicates required in a patient."),
"794222":("diagnostic_or_specifier_criterion","Mania includes >=3 symptoms plus duration/mood/impairment context; this window ends mid-list. Other disorders occur earlier in the window."),
"435686":("trigger_not_a_diagnostic_combination","'All of these conditions have the potential to progress to SCC' is a precursor-condition list, not a diagnostic conjunction."),
"42494":("clinical_action_or_suspicion_rule","Referral for spondyloarthritis assessment: persistent OR multiple sites OR an additional listed feature; action target is referral, not confirmed diagnosis."),
"666274":("graded_risk_score","Kocher count maps 1/2/3/4 findings to 3/40/93/99 percent in the supplied source; it is not one at-least-n hard criterion."),
"382014":("clinical_action_or_suspicion_rule","Consider abuse in EACH listed scenario means ANY scenario can trigger consideration. Proxy labels all, reversing the connective and ignoring 'consider'."),
"825864":("trigger_not_a_diagnostic_combination","'both because of these differences and because ...' coordinates reasons for a nomenclature choice, not patient findings."),
"522304":("trigger_not_a_diagnostic_combination","'management includes all ... specialists' is an interprofessional team instruction."),
"814521":("clinical_action_or_suspicion_rule","Two or more findings increase suspicion for epidural abscess; implication target is suspicion, not definitive diagnosis. Overlaps gid814520."),
"17576":("trigger_not_a_diagnostic_combination","'all of these ... scoring systems' evaluates diagnostic tools rather than conjoining their patient criteria."),
"851295":("trigger_not_a_diagnostic_combination","'All of these drugs ... penetrate the blood–brain barrier' is pharmacology."),
"212407":("trigger_not_a_diagnostic_combination","'calculate all of the above indicators' refers to a calculator, not patient diagnostic rules."),
"403899":("trigger_not_a_diagnostic_combination","Reference marker '[2] Of these forms' is mistaken for a count quantifier."),
"814520":("clinical_action_or_suspicion_rule","Same epidural-abscess >=2 suspicion sentence as gid814521; overlapping windows are not independent source rules."),
"856509":("trigger_not_a_diagnostic_combination","'In more chronic cases, all of these features are evident' is time-conditioned electrodiagnostic description, not explicit all-of diagnostic admission."),
"778204":("trigger_not_a_diagnostic_combination","'may or may not be accompanied by any ... symptoms' states optional findings; no member suffices for diagnosis."),
"27457":("clinical_action_or_suspicion_rule","Diverticulitis suspicion is abdominal pain WITH alternatives (some nested conjunctions); overlaps gid27456. Complicated-diverticulitis referral is a separate rule."),
"27456":("clinical_action_or_suspicion_rule","Same abdominal-pain AND alternatives suspicion rule as gid27457, not a flat any-of list."),
"692979":("trigger_not_a_diagnostic_combination","'All of these layers are divided' describes surgical access through tissue layers."),
"826232":("trigger_not_a_diagnostic_combination","'related both to ... factors of these species and ...' is an explanation of culture/virulence, not count logic."),
"541846":("diagnostic_or_specifier_criterion","Leiomyosarcoma >=2 of 3 histologic features, with numerical threshold and graded atypia. Source framing is tissue-specific."),
"657039":("trigger_not_a_diagnostic_combination","Citation '[5] About 60% of these tumors' is epidemiology, not k-of-n criteria."),
"652917":("diagnostic_or_specifier_criterion","Brugada algorithm diagnoses ventricular tachycardia when ANY one criterion holds. Vereckei aVR contains an ANY sublist. Regex all comes from unrelated 'both ... one of the above' span."),
"750684":("trigger_not_a_diagnostic_combination","'All of these etiologies can cause ... pressure' is a cause list, not a diagnostic conjunction."),
"609622":("trigger_not_a_diagnostic_combination","'All of the above differentials may be ruled out with biopsies' discusses a procedure and multiple diagnoses, not conjunction of patient features."),
"685016":("trigger_not_a_diagnostic_combination","'three-quarters of these ... moderate to severe infections' is epidemiologic proportion, not a patient criterion."),
"399793":("trigger_not_a_diagnostic_combination","'the two sides, one of the following defects may occur' is an anatomic defect list; two is not a threshold count. Overlaps gids399791/399792."),
"399791":("trigger_not_a_diagnostic_combination","Same anatomic defect list as gid399793; number two refers to heart sides."),
"869628":("trigger_not_a_diagnostic_combination","Figure/table marker '11.2 ... majority of these (90%)' is incorrectly captured as count 2."),
"444828":("trigger_not_a_diagnostic_combination","'all deliveries, with about 25% of these cases' is prevalence, incorrectly classified all."),
"444829":("trigger_not_a_diagnostic_combination","Same congenital-heart-disease prevalence statement as gid444828; not an independent all-of rule."),
"716474":("trigger_not_a_diagnostic_combination","'All three of these regions fuse at 16 to 19 years' is embryology/ossification, not diagnostic conjunction."),
"399792":("trigger_not_a_diagnostic_combination","Same heart-side/defect list as gids399791/399793, not a k-of-n criterion."),
}

# id, case suffix, focus, predicate, title substring, source gid or None,
# source contract, extraction error, counterexample, verdict
EXAMPLES=[
("E01",522,"Alzheimer's disease","absence of delirium","memantine","599595",
 "Cognitive deficits must not occur ONLY during delirium.",
 "Only-in-context negation is converted into absence of delirium.",
 "Persistent cognitive deficits also outside delirium plus a concurrent delirium episode satisfy the source clause but violate the extracted absence predicate.","semantic_error"),
("E02",522,"Alzheimer's disease","absence of other mental disorder","memantine","599595",
 "Another mental disorder must not BETTER EXPLAIN the cognitive deficits.",
 "Comparative explanatory exclusion becomes absence of any other mental disorder.",
 "A comorbid disorder that does not explain the cognitive deficits does not violate the source but violates the extracted absence predicate.","semantic_error"),
("E03",74,"Brugada syndrome","AV dissociation","Ventricular Tachycardias","652917",
 "Any single Brugada algorithm criterion suffices for the stated VT diagnostic algorithm.",
 "An eponymic diagnostic algorithm is assigned to Brugada syndrome; criterion members receive required_for.",
 "A case meeting this VT criterion without Brugada syndrome is supported for VT by the source but assigned evidence for the wrong disease by the extraction.","semantic_error"),
("E04",74,"Brugada syndrome","initial R-wave","Ventricular Tachycardias","652917",
 "The aVR branch explicitly says any one of the listed findings.",
 "Vereckei members are emitted as all with subject 'Vereckei Criteria', not the clinical target.",
 "Initial R wave present while the other aVR alternatives are absent satisfies the source branch and fails the extracted all group.","semantic_error"),
("E05",522,"Psychotic disorder","Delusions","Psichiatry_DSM-5","889487",
 "The F20.9 schizophrenia block is a new disease section after schizophreniform differential discussion.",
 "Its delusion criterion is attributed to Schizophreniform disorder.",
 "The disease identity is already wrong before patient matching or ranking.","semantic_error"),
("E06",522,"Psychotic disorder","Delusions","Psichiatry_DSM-5","889487",
 "Criterion A is count>=2 across 5, AND count>=1 across first 3, with a time requirement.",
 "One flat at_least_n=2 group cannot represent the overlapping mandatory subset and time quantification; no nested group relation exists in the schema.",
 "Catatonic behavior plus negative symptoms, without delusions/hallucinations/disorganized speech, reaches 2/5 but fails the source's mandatory subset.","representation_and_extraction_error"),
("E07",522,"Major depressive disorder with psychotic features","Agitation","Psichiatry_DSM-5","889594",
 "Count agitation only when not influenced by external stimuli.",
 "The group member predicate is unqualified Agitation; the qualifier survives only in the quote.",
 "Externally induced agitation must not count under the source criterion; a matcher using the predicate cannot enforce that exclusion.","semantic_loss_in_executable_fields"),
("E08",522,"Major depressive disorder with psychotic features","Mutism","Psichiatry_DSM-5","889594",
 "Mutism member excludes known aphasia.",
 "Predicate Mutism lacks the member-local aphasia exclusion; storing it in a quote does not encode a gate.",
 "Aphasic mutism should not be counted as this catatonia member even if mutism is present.","semantic_loss_in_executable_fields"),
("E09",49,"Diverticulitis","constant abdominal pain","ng147-1_3_1","27456",
 "Suspect diverticulitis when abdominal pain AND an alternative accompanying pattern hold; parts of the alternatives contain further and/or structure.",
 "Pain and accompanying features become members of the same flat any group.",
 "An isolated fever or rectal bleeding without the required pain does not satisfy the source decision rule but satisfies the flattened any expression.","semantic_error"),
("E10",522,"Dementia with Lewy Bodies","parkinsonian syndrome","Neurology_Adams","854182",
 "At least 2 of 3 members are required collectively, not every member separately.",
 "Every leaf is required_for while the group says at_least_n=2; modality is frequent. This mixes member-level necessity and group-level necessity.",
 "Fluctuations and hallucinations without parkinsonism satisfy 2/3; treating parkinsonism as individually necessary would exclude a source-consistent case.","unsafe_relation_scope_ambiguity"),
("E11",257,"Septic Arthritis","fever higher than 38.5 C","Septic arthritis following","666274",
 "The source gives a four-member score with a distinct risk at each count, not a single diagnostic threshold.",
 "An any feature group drops the count-to-risk mapping; the regex reference at_least_n is also not a faithful gold representation.",
 "One finding and four findings correspond to very different source risks; a single any value cannot distinguish them.","representation_loss_not_hard_rule_error"),
("E12",74,"Catecholaminergic Polymorphic Ventricular Tachycardia","early diagnosis","young athletes",None,
 "Failure to diagnose early is associated with poor prognosis.",
 "A prognosis statement becomes obligatory required_for early diagnosis of the disease itself.",
 "A late-diagnosed patient still has the disease; lateness affects prognosis, not membership in the diagnosis.","semantic_error"),
("E13",74,"Seizure disorder","coagulation studies","visual pathway",None,
 "Coagulation studies may be required BEFORE THROMBOLYTICS for ischemic stroke.",
 "A treatment-preparation requirement is recast as required_for ischemic stroke.",
 "Stroke exists without thrombolytic administration or completed coagulation studies; the source imposes no disease prerequisite.","semantic_error"),
("E14",74,"Seizure disorder","abnormal electroencephalography","visual pathway",None,
 "EEG may be necessary to evaluate possible seizure disorder.",
 "Possible need to perform a test becomes a necessary abnormal test result.",
 "Performing EEG and obtaining a normal result still fulfills a testing instruction; the extraction demands an abnormality the source never states.","semantic_error"),
("E15",74,"Long QT Syndrome","type I pattern","Cardiac pain",None,
 "The type I pattern is described as necessary for the diagnosis.",
 "The leaf relation is pathognomonic_for and obligatory, reversing a necessary condition into standalone sufficient evidence.",
 "A necessary finding without the remaining diagnosis conditions need not establish the disease; the extracted relation asserts that stronger direction.","semantic_error"),
("E16",74,"Brugada syndrome","Type 1 morphology","ST-segment elevation myocardial",None,
 "Type 1 is the only ECG abnormality that is POTENTIALLY diagnostic.",
 "Potential diagnostic significance is escalated to obligatory pathognomonic_for.",
 "The modal qualifier reserves cases where the ECG pattern is not by itself diagnostic; the extracted hard relation removes that reservation.","semantic_error"),
("E17",74,"Seizure disorder","normal EEG","ng217-1_2_5",None,
 "Do not use EEG to exclude epilepsy: prohibition on an inference.",
 "The schema emits excludes with negated polarity and predicate normal EEG, without a typed prohibition-of-inference representation.",
 "This clause must disable EEG-based exclusion, not become a patient predicate that triggers a disease exclusion under either polarity convention.","unsafe_meta_rule_encoding"),
("E18",74,"Arrhythmogenic Right Ventricular Cardiomyopathy","EMB","endomyocardial biopsy",None,
 "Consider endomyocardial biopsy in diagnostic uncertainty.",
 "Conditional optional investigation is extracted as required_for EMB.",
 "A case resolved without biopsy does not violate the source recommendation but violates an unconditional required-test interpretation.","semantic_error"),
("E19",74,"Arrhythmogenic Right Ventricular Cardiomyopathy","absence of hypertension","Artificial Intelligence in the Differential",None,
 "The source definition describes cardiomyopathy in the absence of listed explanatory diseases.",
 "Absence of hypertension is stored as an asserted excludes predicate, reversing the source's admission direction.",
 "Confirmed absence of hypertension is compatible with the source definition; exclusion triggered by that absence contradicts it.","semantic_error"),
]


def norm(t):return " ".join(str(t or "").split())


def main():
 ps=passages(("trial_retrieval_x2_v2idx.json",))
 criteria={g:p for g,p in ps.items() if stated_logic(norm(p["text"]))}
 assert set(criteria)==set(SCREEN),(set(criteria)-set(SCREEN),set(SCREEN)-set(criteria))
 screened=[]
 for g,p in criteria.items():
  typ,note=SCREEN[g]
  screened.append({"gid":g,"proxy_label":stated_logic(norm(p["text"])),"source":p["source"],
                   "title":p["title"],"screen_category":typ,"rationale":note})
 (HERE/"v2_criteria_manual_screen.json").write_text(json.dumps({
  "review_type":"Independent single-agent source close reading; not clinical expert double adjudication",
  "unit":"The regex-matched span in each selected passage, not all statements in that passage",
  "counts":dict(Counter(r["screen_category"] for r in screened)),"rows":screened},indent=2,ensure_ascii=False)+"\n")
 extfile="trial_extraction_x2_v2idxclean_groups_free.json"
 ex=json.loads((LEDGER/extfile).read_text())
 ledger=[]
 for eid, suffix,focus,pred,title,gid,contract,error,witness,verdict in EXAMPLES:
  en=next(e for e in ex if e["case_key"].endswith('/'+str(suffix)))
  selected=[(i,a) for i,a in enumerate(en["assertions"]) if
            a.get('_focus')==focus and a.get('predicate')==pred and title in a.get('_title','')]
  assert selected,(eid,focus,pred,title)
  pss=[]
  for pg,p in ps.items():
   if p['source']==selected[0][1].get('_source') and p['title']==selected[0][1].get('_title'):
    if any(norm(a.get('quote')) in norm(p['text']) for _,a in selected):pss.append(pg)
  if gid:assert gid in pss,(eid,gid,pss)
  ledger.append({"id":eid,"case_key":en['case_key'],"extraction_file":extfile,
   "assertion_indices_zero_based":[i for i,_ in selected],"assertions":[a for _,a in selected],
   "compatible_source_gids":pss,"deliberately_reviewed_gid":gid,
   "source_contract":contract,"error":error,"counterexample_witness":witness,"verdict":verdict,
   "provenance_limit":"Extraction rows omit task/gid identity; source candidates are matched by source, title and quote, not asserted as unique origin."})
 (HERE/"measurement_counterexamples.json").write_text(json.dumps({
  "sampling":"Deliberate counterexamples selected by direct source comparison; no prevalence estimate",
  "purpose":"Refute inference from group availability or high-weight-label yield to semantic correctness",
  "examples":ledger},indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"screen_counts":dict(Counter(r['screen_category'] for r in screened)),
                   "counterexamples":len(ledger)},indent=2))


if __name__=="__main__":main()
