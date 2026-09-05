"""Serialize close-reading adjudications; labels are manually assigned, not keyword rules."""
import json
from pathlib import Path
from collections import Counter

P = Path(__file__).resolve().parent
PACK = json.loads((P / 'output_pack_2.json').read_text())
DOCS = json.loads((P / 'sampled_doc_contexts.json').read_text())
DECISIONS = {}

def add(n, label, anchor, source, output, errors, rationale, *, cause='semantic', complexity=None, ambiguous=False, doc=False):
    DECISIONS[n] = dict(label=label, ancestor_anchor=anchor, source_semantics=source,
                        output_semantics=output, errors=errors.split('|') if errors else [],
                        rationale=rationale, cause=cause, complexity=complexity,
                        ambiguous_source=ambiguous, doc=doc)

add(1, 'faithful', 'MND requires an acquired decline in one or more cognitive domains',
    'MND requires acquired decline in at least one cognitive domain AND functional independence; vascular dementia is explicitly an MND etiology.',
    'An ALL group of acquired cognitive decline and functional independence decline, with obligatory modality, for vascular dementia.', '',
    'The two syndromic necessary components are recoverable together. This is a necessary MND substrate, not a sufficient vascular-etiology test. Do not penalize the group merely because its common effect is encoded through obligatory member modality rather than a separate group slot.', complexity='flat_group')
add(2, 'distorted', 'motor, reflex, and sensory changes confined to the territory of a single nerve',
    'Motor/reflex/sensory changes must have the stated nerve-territory distribution; alternatives of distribution separate mononeuropathy, multiplex and plexopathy.',
    'ANY motor, reflex or sensory change, without distribution, is the Mononeuropathy definition group.',
    'connective|scope_anatomic|group_membership_effect',
    'Raw indices 0–2 replace the linked pattern with unrelated ANY symptoms and erase the identity-defining nerve territory.', complexity='nested_group')
add(3, 'distorted', 'Stage IA: Low grade, <8 cm tumor size, no spread to regional lymph nodes, no distant metastasis',
    'The listed conjunction defines osteosarcoma Stage IA, within a stage-specific staging table.',
    'ANY low grade, small size or lack of spread is a generic Osteosarcoma definition feature.',
    'target_subtype|connective|group_membership_effect|scope_stage',
    'Stage IA is removed and its conjunction becomes alternatives; this is a traceable staging-to-disease distortion, not a fabricated finding.', complexity='flat_group')
add(4, 'distorted', 'Structural brain: posterior fossa anomalies: Danky-Walker complex, unilateral or bilateral cerebral dysplasia or hypoplasia',
    'A structural-brain major-criterion branch participates in definite PHACE: facial hemangioma >5 cm AND (one major OR two minor).',
    'An unlinked ANY list of posterior-fossa anomalies, Dandy-Walker complex, and cerebral dysplasia/hypoplasia, all mere typical PHACE features.',
    'nesting_branch|group_membership_effect|relation_strength',
    'The anatomical observations have an ancestor, but the major-criterion role and connection to the qualifying hemangioma/major-minor expression are absent. The Dandy/Danky spelling repair alone is not a hallucination.', cause='nested', complexity='nested_group')
add(5, 'distorted', "Only consider AChE inhibitors or memantine for people with vascular dementia if they have suspected comorbid Alzheimer's disease",
    'In vascular dementia, consider these drugs only if one of three suspected comorbid dementias is present.',
    'One of those comorbid dementias is REQUIRED FOR vascular dementia itself.',
    'non_diagnostic_task|relation_direction|target_effect',
    'Treatment eligibility has become disease necessity even though the drugs are absent from the output effect. All three findings are traceable; none is strictly source-free.', cause='required', complexity='scoped_rule')
add(6, 'distorted', "Typical skin lesions of mastocytosis associated with Darier's sign",
    'Skin criteria have major/minor roles; histology is lesional-skin mast proliferation, and the updated genetic criterion is an activating KIT mutation in lesional skin. The excerpt does not establish a complete combination threshold.',
    'ANY of five partly duplicate generic findings, including generic KIT mutation and generic typical skin lesions.',
    'predicate_identity|scope_tissue|group_membership_effect|cardinality_distinctness',
    'Darier sign, activating/tissue constraints, and distinct criterion identity are lost. Histologic proliferation and increased mast counts are duplicates; KIT mutation and activating KIT mutation overlap. No unsupported full source threshold is invented by the auditor.', complexity='flat_group', ambiguous=True)
add(7, 'distorted', 'Children who meet one out of four of these criteria have a 3% incidence',
    'The four thresholded Kocher findings produce count-dependent septic-hip incidence: 1/4→3%, 2/4→40%, 3/4→93%, 4/4→99%, in children.',
    'ANY of four typical septic-arthritis features; the count-to-risk program and pediatric hip scope are gone.',
    'score_semantics|cardinality_domain|group_membership_effect|scope_population|scope_anatomic',
    'The four leaves are correctly identified, including numeric thresholds. They are not a faithful extraction of the joint count-to-probability rule.', cause='score', complexity='score')
add(8, 'distorted', 'no documented history of ST segment elevation MI',
    'Negative exclusion-history conditions in a truncated LBBB-associated cardiomyopathy criteria list; absence of competing cause permits that etiologic diagnosis.',
    'ALL of negated MI and negated other causes EXCLUDES generic Cardiomyopathy.',
    'relation_direction|literal_polarity|target_subtype|group_membership_effect',
    'Even without recovering the complete subtype definition, excludes combined with negated necessary absences reverses their effect. The second available same-document window confirms an etiologic no-other-cause requirement. No source-free claim is alleged.', cause='negative', complexity='flat_group', ambiguous=True, doc=True)
add(9, 'distorted', 'There has never been a manic episode or a hypomanic episode',
    'The persistent-depressive-disorder criterion requires no lifetime manic/hypomanic episode and no cyclothymia.',
    'An ALL group says negated manic/hypomanic/cyclothymic conditions EXCLUDE Major depressive disorder.',
    'target_entity|relation_direction|literal_polarity|scope_time|group_membership_effect',
    'The surrounding note explicitly identifies persistent depressive disorder; the first D-line mentioning major depression is not the current criterion subject. The negative-literal exclusion flips a necessary absence.', cause='negative', complexity='flat_group')
add(10, 'distorted', 'In some cases with cervical epidural abscesses, stiff neck, fever, and deltoid-biceps weakness',
    'Some cervical epidural abscess cases have this level-specific neurological presentation.',
    'Generic Epidural abscess has an ANY group of stiff neck, fever and deltoid-biceps weakness.',
    'scope_anatomic|scope_population|relation_strength',
    'A limited cervical presentation is promoted to a typical generic definition; the clinically identifying cervical distribution and some-cases qualification disappear. The ordinary list need not be rigidly AND.', complexity='association_set')
add(11, 'faithful', 'The identifiable leading causes of delirium broadly include, but are not limited to:',
    'The fourteen listed categories are non-exhaustive alternative causes of delirium.',
    'ANY of the fourteen source categories may cause delirium; all relations are caused_by/typical.', '',
    'The cause relation and alternatives are coherently recoverable. This is a soft non-exhaustive etiologic association set, not a requirement that every cause occur.', complexity='association_set')
add(12, 'distorted', 'Epsilon wave (reproducible low-amplitude signals between end of QRS complex to onset of the T wave) in the right precordial leads',
    'A right-precordial epsilon wave, defined morphologically, is a minor depolarization criterion within the ARVC criteria scheme.',
    'A singleton ANY criteria group contains only generic epsilon wave as a typical feature.',
    'scope_anatomic|group_membership_effect|relation_strength',
    'Raw index 6 drops the right-precordial location and minor-criterion role; a mere wave-name match cannot certify the group criterion.', complexity='scoped_rule')
add(13, 'distorted', 'Timing of listing:',
    'The first listing block gives lung-transplant timing indications; a later separate PAH block begins after the pulmonary vascular disease heading.',
    'All eight indications from the preceding block are typical PAH diagnostic criteria under ANY.',
    'non_diagnostic_task|target_entity|scope_time|group_membership_effect',
    'The header boundary is crossed backwards and transplant listing criteria become disease evidence. Six-month change windows are also absent in FVC/DLCO predicates.', cause='boundary', complexity='scoped_rule')
add(14, 'distorted', 'Differential diagnoses of PAVSD include the following:',
    'Eight alternative diagnoses may resemble pulmonary atresia with VSD.',
    'An ANY group gives each alternative diagnosis itself as a finding that distinguishes PAVSD from that same diagnosis.',
    'predicate_identity|relation_direction|group_membership_effect',
    'A list of competitors supplies no distinguishing observation. Turning competitor labels into discriminating evidence is not faithful differential extraction.', cause='differential', complexity='association_set')
add(15, 'faithful', 'scaly, erythematous macules, papules, plaques, or cutaneous horns',
    'Actinic keratosis can have alternative scaly/erythematous macular, papular, plaque or horn appearances.',
    'An ANY group of scaly macules, erythematous papules, plaques and cutaneous horns as typical features.', '',
    'This preserves a non-obligatory morphology association set. The selective adjective attachment does not introduce a conflicting finding, and the group makes no sufficient/necessary diagnostic claim.', complexity='association_set')
add(16, 'faithful', 'Later, a fourth sign, fusiform swelling of the digit, was also added to become the 4 cardinal signs.',
    'The named four Kanavel signs are flexor-sheath tenderness, a flexed digit, painful passive extension and fusiform swelling; detection of the full pattern is sensitive.',
    'One ALL group contains exactly those four signs, each feature_of with typical modality.', '',
    'The complete named pattern is preserved and no member says required_for/obligatory. Treating failure of one sign as a disease veto would be an executor error. The malformed sensitivity range in source is not repaired or imputed here.', complexity='flat_group')
add(17, 'distorted', 'Musculoskeletal System',
    'A body-system heading organizes weakness, myalgia, cramps and rhabdomyolysis in a truncated toxic-exposure presentation list; no disease named Musculoskeletal disorder is stated.',
    'Musculoskeletal disorder is created as the disease with an ANY criteria group of those four findings.',
    'target_entity|group_membership_effect|provenance_subject',
    'The heading is converted to a disease. The symptoms have clear source ancestors, so this is target distortion despite the source disease remaining underdetermined.', cause='boundary', complexity='association_set', ambiguous=True)
add(18, 'distorted', 'ITP is typically an acquired disease and is not likely to have a familial pattern',
    'Familial inheritance and failure to respond to IVIG/steroids favor BSS over typical acquired ITP.',
    'Negated familial pattern EXCLUDES ITP; negated treatment response is attached to ITP as a distinguishing finding against BSS, in one ANY mixed-relation group.',
    'relation_direction|relation_strength|literal_polarity|target_entity|group_membership_effect',
    'Absence of familial pattern is made an exclusion despite supporting ordinary ITP. The next BSS-favoring bullet is bound to ITP. Unlikely is also strengthened to excludes.', cause='negative', complexity='flat_group')
add(19, 'distorted', 'Surgical removal may be considered in any of the below-mentioned cases:',
    'Brain-stem cavernoma removal may be considered for alternative accessibility/progressive hemorrhage/compression situations.',
    'ANY of four findings is REQUIRED FOR Brain stem cavernoma, although context_type is treatment.',
    'target_effect|non_diagnostic_task|relation_direction|relation_strength|predicate_identity',
    'The operation is lost as the consequent, and may-consider indications are changed to disease necessity. Recurrent hemorrhage also loses its progressive-deficit condition.', cause='required', complexity='scoped_rule')
add(20, 'distorted', 'The four cardinal features are',
    'The payload preserves only one visible tetralogy feature from an incomplete four-feature list, then separately describes their embryological cause.',
    'An ALL group has two obligatory members: overriding aorta and the causal infundibular displacement; their relations differ.',
    'group_membership_effect|cardinality_domain|relation_direction|non_diagnostic_task',
    'A missing source list is not faithfully completed by appending its explanatory mechanism as a second criterion. Missing source leaves and raw false regrouping are distinct damage steps.', cause='boundary', complexity='flat_group', ambiguous=True)
add(21, 'distorted', 'Exclusion of hypertensive, valvular and ischemic heart diseases',
    'Alcoholic cardiomyopathy requires the dilated/low-EF structural pattern and exclusion of alternative hypertensive, valvular and ischemic etiologies.',
    'One ALL group mixes three positive features with three negated EXCLUDES members.',
    'relation_direction|literal_polarity|group_membership_effect',
    'The absence of an alternative etiology should satisfy a necessary negative clause, not exclude the target. Correct echocardiographic thresholds do not repair the joint mixed-effect rule.', cause='negative', complexity='flat_group')
add(22, 'distorted', 'motor, reflex, and sensory changes confined to the territory of a single nerve',
    'The combined neurological changes identify mononeuropathy only with confinement to a single nerve; other territories define other patterns.',
    'ALL motor, reflex and sensory changes, with no nerve territory, define Mononeuropathy.',
    'scope_anatomic|predicate_identity|group_membership_effect',
    'Unlike O2-002 this copy selects ALL, but it still erases the joint anatomical condition that differentiates neuropathy patterns.', complexity='nested_group')
add(23, 'distorted', 'The disturbance is not better explained by a persistent schizoaffective disorder',
    'Persistent depressive disorder is not better explained by one of the listed psychotic disorders.',
    'Negated presence of each competing disorder EXCLUDES Major depressive disorder in one ALL group.',
    'target_entity|relation_direction|literal_polarity|negation_scope|group_membership_effect',
    'The target is switched; not-better-explained-by is flattened to absence of a diagnosis; and a negative exclusion literal reverses the criterion direction.', cause='negative', complexity='flat_group')
add(24, 'distorted', 'T4a: Tumor invades skin, mandible, ear canal, and/or facial nerve',
    'For major salivary-gland carcinoma, T4a is invasion of any listed structure, with combinations permitted.',
    'ALL four invasions are obligatory features of generic Carcinoma.',
    'connective|target_subtype|scope_anatomic|scope_stage|relation_strength',
    'The source explicitly says and/or; all is incorrect. Both salivary-gland restriction and T4a are lost.', complexity='flat_group')
add(25, 'distorted', 'The surgical option should be considered if there is a poor response to nonsurgical treatments',
    'The carpal-tunnel surgery paragraph supplies poor response, thenar atrophy/weakness and denervation as considerations; brachial plexitis is discussed in the next paragraph.',
    'Brachial Plexitis has an ANY group of thenar atrophy, generic weakness and EMG denervation.',
    'target_entity|non_diagnostic_task|group_membership_effect|predicate_identity',
    'The model carries findings across the paragraph boundary to the preferred focus disease and strips surgery as their effect.', cause='boundary', complexity='scoped_rule')
add(26, 'distorted', 'at least three of the 12 diagnostic features listed in Criterion A',
    'The catatonia specifier requires at least 3 of a 12-feature domain, in a marked psychomotor disturbance and appropriate mental-disorder setting; only the last 4 list items are in this payload.',
    'At least 3 of the 4 visible symptoms define Catatonia; agitation loses not-influenced-by-external-stimuli.',
    'cardinality_domain|group_membership_effect|predicate_identity|scope_population',
    'The number 3 is copied faithfully but its domain becomes four instead of twelve. This is a denominator error, not a wrong integer. The incomplete payload should have been marked partial, not emitted as a complete executable group.', cause='boundary', complexity='flat_group', ambiguous=True)
add(27, 'distorted', 'For evaluation of acute thromboembolic disease: suspicion for DVT or PE',
    'Suspicion of DVT/PE or positive D-dimer can indicate ultrasound evaluation.',
    'Actual DVT, PE and positive D-dimer are typical features in an ANY Acute Thromboembolic Disease indication group.',
    'non_diagnostic_task|epistemic_status|target_effect|predicate_identity',
    'Suspicion is silently promoted to established disease and the indication for a test is lost; DVT/PE are also treated as symptoms.', cause='semantic', complexity='scoped_rule')
add(28, 'faithful', 'Minor criteria are growth (50–87%) and/or developmental delay (16–52%)',
    'Alagille syndrome has non-universal minor manifestations: growth/developmental delay, renal disease and exocrine pancreatic insufficiency. This excerpt states no diagnostic combination threshold for the minor set.',
    'An ANY group of those four typical feature associations, without a required_for or sufficient_for claim.', '',
    'The output is a coherent soft minor-feature association set. It does not encode the different frequencies or establish a complete Alagille diagnostic rule; that source-coverage issue must not turn a true output association into a false one.', complexity='association_set')
add(29, 'distorted', 'Persistent hemodynamic instability and an expanding or pulsatile hematoma are indications',
    'In the blunt-trauma decision context, persistent instability with an expanding/pulsatile hematoma indicates surgical management.',
    'ANY instability or expanding/pulsatile hematoma is REQUIRED FOR Traumatic Retroperitoneal Hematomas.',
    'non_diagnostic_task|target_effect|relation_direction|connective|scope_population',
    'The diagnosis is substituted for surgical management, and the source conjunction becomes ANY.', cause='required', complexity='scoped_rule')
add(30, 'out_of_scope_traceable', 'all 3 stages of single ventricle palliation should be offered',
    'Patients with Jacobsen syndrome and hypoplastic left heart syndrome should be offered the three named stages of single-ventricle palliation.',
    'The exact three operations are a common ALL treated_by group for that scoped patient category.', '',
    'This is a faithful treatment-set extraction, outside the diagnostic target. No operation is converted to diagnostic necessity.', complexity='flat_group')

add(31, 'distorted', 'Low voltage QRS in the limb leads (pericardial/pleural effusion, amyloidosis)',
    'A general right-ventricular-dysfunction table associates limb-lead low voltage with effusions/amyloidosis; ARVC is explicitly attached to the separate epsilon-wave cell.',
    'Low limb-lead QRS voltage is a typical Arrhythmogenic Right Ventricular Cardiomyopathy feature.',
    'target_entity|provenance_subject|table_cell_binding',
    'The output transfers an observation across table cells to the focus/nearby ARVC name. It is traceable to a real low-voltage cell, rather than strictly hallucinated.', cause='boundary')
add(32, 'distorted', 'Additional neurologic deficits include Argyll Robertson pupils, ocular palsies, diminished reflexes, vibratory and proprioceptive impairment, and Charcot joints.',
    'The Tabes Dorsalis subsection attributes Charcot joints to that neurosyphilis presentation.',
    'Charcot joints is a typical criteria feature of undifferentiated Neurosyphilis.',
    'target_subtype|scope_population',
    'The subgroup is explicitly recoverable from the same bullet. Upcasting a late specific tabetic feature to typical neurosyphilis loses the source population; no claim of a new symptom is needed.')
add(33, 'distorted', 'In pregnancy, these antibodies may cross the placenta and cause fetal thrombocytopenia',
    'Maternal ITP antibodies may cross the placenta and cause thrombocytopenia in a different person, the fetus.',
    'Fetal thrombocytopenia is a typical feature of Immune Thrombocytopenia with no maternal/fetal causal roles.',
    'scope_population|relation_direction|participant_binding',
    'A two-person causal complication is flattened to a same-subject feature. The maternal pregnancy and placental transmission constraints are clinically material.')
add(34, 'distorted', 'decreased seizure emergencies, medical complications, and days of hospitalization',
    'A study reports fewer seizure emergencies under coordinated multidisciplinary management of EPM2A patients, compared with NHLRC1 patients.',
    'Seizure emergencies are a typical feature of EPM2A mutations, with NHLRC1 as comparator.',
    'non_diagnostic_task|scope_intervention|relation_direction|numeric_comparison',
    'The treatment-associated decrease and study context are removed. A comparative outcome is changed to an intrinsic genotype feature.')
add(35, 'distorted', 'around 1% of all appendectomy specimens',
    'Approximately 1% of appendectomy specimens contain appendiceal neoplasms, with uncertainty about true incidence.',
    'Appendiceal neoplasms have incidence 1% with no denominator or approximate/unknown qualification.',
    'scope_denominator|numeric_comparator|non_diagnostic_task',
    'The number is copied, but surgical-specimen prevalence is not general disease incidence. The quote is a source ancestor, not a replacement for the missing rule denominator.')
add(36, 'distorted', 'can also be an essential sign of sepsis',
    'Neonatal thrombocytopenia is shared by Jacobsen syndrome and sepsis/TORCH/NEC, motivating alternatives.',
    'Sepsis itself distinguishes Jacobsen syndrome from comparator Jacobsen syndrome.',
    'predicate_identity|relation_direction|comparator_identity',
    'The shared finding disappears, the alternative disease becomes a finding, and comparator equals subject. This cannot encode the supplied differential relation.', cause='differential')
add(37, 'faithful', 'a strong membranous pattern in PNET',
    'PNET shows strong membranous CD99 staining, contrasted with cytoplasmic staining in synovial sarcoma.',
    'Strong membranous CD99 staining is a typical Ewing/PNET feature.', '',
    'The target and discriminating staining localization are preserved. The output need not restate the comparator to remain a true target feature.')
add(38, 'distorted', 'Managing severe tricuspid regurgitation includes medical therapy',
    'The paragraph describes management conditional on TR severity.',
    'Severe tricuspid regurgitation is a typical course feature of Tricuspid Regurgitation.',
    'predicate_identity|non_diagnostic_task|target_subtype',
    'A treatment-population qualifier is reified as a tautological disease finding. The source discusses a severity stratum, not severity as a typical criterion.')
add(39, 'faithful', 'irregular, red, scaly papules or plaques',
    'Actinic keratosis may have an irregular red scaly papular/plaque morphology, commonly in sun-exposed regions.',
    'The same morphology is a typical feature of Actinic keratosis.', '',
    'This output is a valid morphology association. It does not assert that every lesion has the pattern or that the pattern alone confirms AK; missing parallel location information affects source coverage, not this true subclaim.')
add(40, 'distorted', 'if an emergency airway intervention is necessary',
    'Respiratory distress/toxicity can require airway intervention and urgent specialist notification in the retropharyngeal-abscess management setting.',
    'Abscess is necessarily treated by emergency airway intervention.',
    'scope_population|scope_condition|relation_strength|target_subtype',
    'An explicit if-needed intervention becomes necessary for generic Abscess. The source treatment is identifiable, so this is a distorted management rule.', cause='required')
add(41, 'faithful', 'PD is characterized by progressive primary motor disabilities',
    'Progressive primary motor disability characterizes Parkinson disease.',
    'Progressive primary motor disabilities is a typical PD feature.', '',
    'The descriptive disease claim is faithfully retained; the broad feature has low specificity but is not false.')
add(42, 'faithful', 'nail anomalies including longitudinal erythronychia',
    'Longitudinal erythronychia is a characteristic nail manifestation of Darier disease.',
    'Longitudinal erythronychia is a typical Darier disease feature.', '',
    'The named finding and target match the source. Calling the finding a symptom rather than a sign is a separate coarse typing issue, not reversal of the clinical association.')
add(43, 'faithful', 'and bacteremia.',
    'Bacteremia is explicitly in the list of spinal epidural abscess risk factors.',
    'Bacteremia is a risk factor for Spinal epidural abscess.', '',
    'The semantic risk relation is correct although risk factor for is outside the allowed relation enum and the quote is a non-verbatim sentence reconstruction. These contract defects are separately recorded and must not inflate semantic distortion.')
add(44, 'faithful', 'RV dilation',
    'ARVC has RV dilation, mainly RVOT; athlete heart also has dilation, mainly main RV body.',
    'RV dilation is a typical ARVC feature, with an extraneous athlete-heart comparator.', '',
    'The source does support the positive feature. The output does not say dilation alone distinguishes the diseases. Comparator placement and lack of RVOT specificity are separately visible limitations.')
add(45, 'distorted', 'The most common defects leading to Eisenmenger syndrome are ASD, VSD, and PDA defects.',
    'PDA is one of several congenital defects that can lead to PAH and then Eisenmenger physiology.',
    'PDA is a typical feature_of Eisenmenger Syndrome.',
    'relation_direction|scope_causal_condition',
    'An alternative causal substrate is changed to an intrinsic feature; the progression condition through PAH is absent. This promotes a component cause into diagnosis evidence without the source causal relation.')
add(46, 'faithful', 'Marked CD8+ epidermotropism',
    'CD8+ AECTCL histology includes marked CD8+ epidermotropism.',
    'CD8+ epidermotropism is a typical histopathologic feature of CD8+ AECTCL.', '',
    'A valid component of the pathology profile is retained; not extracting every co-stain in this atom does not make this positive association false.')
add(47, 'out_of_scope_traceable', 'Perirectal abscesses require surgical treatment with incision and drainage.',
    'Perirectal abscesses require surgical incision/drainage.',
    'Perirectal abscesses are obligatorily treated by surgery.', '',
    'A correct broad treatment relation is outside the diagnostic-rule target. Unlike the required_for errors, the effect remains treated_by.')
add(48, 'distorted', 'This sex difference is not observed in pediatric populations.',
    'Brugada is 8–10 times more common in males outside pediatric populations; the source explicitly excludes children from this sex difference.',
    'Brugada has 8–10-fold male predominance without the pediatric exception.',
    'scope_population|scope_exception',
    'The number and direction are correct, but an explicit population exception is dropped. This is a consequential scope error, not a fabricated epidemiologic statistic.')
add(49, 'faithful', 'Patients with actinic keratoses may present with skin lesions that are pruritic, painful',
    'AK lesions may be painful, itchy and trauma-sensitive.',
    'Painful skin lesions is a typical AK feature.', '',
    'A soft feature association is supported. Typical is read as the schema’s ordinary non-obligatory clinical-feature category, not an invented numerical prevalence.')
add(50, 'distorted', 'A sagittal computed tomography image (a) of the lumbosacral spine of a 70-year-old female patient with brucellar spondylitis.',
    'An illustrative brucellar-spondylitis case has mild T2 hyperintensity specifically in an intervertebral disc.',
    'Generic mild T2 hyperintense signal changes are a typical Brucellosis feature.',
    'scope_anatomic|scope_case_report|target_subtype|relation_strength',
    'A case-caption observation is generalized and the disc site is erased, leaving a nonspecific imaging phrase.', cause='boundary')
add(51, 'faithful', 'abdominal tenderness in the right iliac fossa',
    'The Mycobacterial tuberculosis subsection states possible right-iliac-fossa abdominal tenderness in intestinal involvement.',
    'Right-iliac-fossa abdominal tenderness is a typical Mycobacterial tuberculosis feature.', '',
    'The source names the same broad disease target and the output retains the discriminating location; it remains a non-obligatory association.')
add(52, 'distorted', 'cerebral vasculitis.',
    'Seizures are rare manifestations of cerebral vasculitis in the relevant neurological involvement setting.',
    'Seizures is a rare feature of generic Vasculitis.',
    'scope_anatomic|target_subtype',
    'Rare modality is preserved, but the cerebral involvement qualifier attached to the source causal statement is lost. This broadens the applicable disease population.')
add(53, 'distorted', 'The pupils may show a slow reaction to light',
    'Amyloid neuropathy with autonomic involvement may cause slow pupil light reaction.',
    'Slow light reaction is a typical feature of Mononeuritis Multiplex.',
    'target_entity|provenance_subject',
    'The source explicitly introduces autonomic amyloid neuropathy before this sentence. An earlier unusual mononeuritis mention is incorrectly retained as subject.', cause='boundary')
add(54, 'faithful', 'Other common findings include growth and developmental delays, skeletal abnormalities, immunodeficiencies',
    'Immunodeficiencies are among common Jacobsen syndrome findings.',
    'Immunodeficiencies is a typical Jacobsen syndrome feature.', '',
    'The target, finding and non-obligatory commonness association are directly supported.')
add(55, 'faithful', 'Hereditary, traumatic, malignant, inflammatory, vascular, and metabolic disorders can cause damage to these structures.',
    'Traumatic disorders can damage peripheral/cranial nerve structures and cause neuropathies.',
    'Neuropathies can be caused by traumatic disorders.', '',
    'The causal relation and target are preserved as a soft etiologic association.')
add(56, 'faithful', 'Physical examination may reveal a small fluctuant mass with erythema',
    'Erythema can accompany the perirectal abscess mass on examination.',
    'Erythema is a typical Perirectal abscesses feature.', '',
    'This is a true positive sign association. The atom does not claim erythema is sufficient or required.')
add(57, 'distorted', 'Inherited thrombocytopenias, often presenting in children, include:',
    'Inherited thrombocytopenias constitute an etiologic subclass, followed by examples and a childhood presentation tendency.',
    'Inherited thrombocytopenias is a typical feature_of generic Thrombocytopenia.',
    'relation_direction|predicate_identity|target_subtype',
    'The disease-class relationship has become a same-disease feature. No actual finding or correctly directed subclass relation survives.')
add(58, 'distorted', 'In cases where actinic keratosis fails to respond to aggressive treatment, further investigation is warranted.',
    'Nonresponse is a conditional trigger to investigate adherence, misdiagnosis or malignant transformation.',
    'Treatment failure is a typical feature of actinic keratosis.',
    'non_diagnostic_task|scope_condition|relation_strength|target_effect',
    'The workflow contingency and alternative explanations are removed, turning a reason to question the diagnosis into ordinary positive disease evidence.')
add(59, 'faithful', 'dreaming-related motor behaviors',
    'REM-atonia loss in RBD leads to dream-related motor behavior.',
    'Dreaming-related motor behaviors is a typical Rapid eye movement behavior disorder feature.', '',
    'The symptom-target association is preserved. The context_type pathophysiology value is outside the declared enum, a separate contract issue.')
add(60, 'distorted', 'pseudopockets resulting from altered tooth eruption, genetic causes, or medications',
    'Pseudopockets from eruption, genetic or drug-induced gingival overgrowth are discussed as gingivectomy indications.',
    'Pseudopockets is a typical feature of Gingival Squamous Cell Carcinoma.',
    'target_entity|non_diagnostic_task|provenance_subject',
    'No carcinoma is named in the payload. The preferred focus diagnosis absorbs a genuine benign periodontal indication; this is clear source-ancestor distortion.', cause='target')
add(61, 'distorted', 'the risk of infection was 65% higher in diabetic patients compared to non-diabetic patients',
    'Studies of trigger-finger/carpal-tunnel procedures report higher postoperative infection risk in diabetic versus nondiabetic patients.',
    'Diabetic Hand Infection has frequent infection risk as a diagnostic criteria feature.',
    'target_entity|non_diagnostic_task|scope_intervention|scope_denominator',
    'A perioperative comparative risk in patients with diabetes becomes a tautological diagnostic feature of an infection target not named in the input.', cause='target')
add(62, 'distorted', 'Eclampsia',
    'Eclampsia appears in the source’s differential/etiologic list for a seizure presentation; the flattened hierarchy is itself problematic.',
    'Eclampsia distinguishes Non-epileptic seizure from Seizure disorder.',
    'relation_direction|predicate_identity|comparator_identity|source_hierarchy',
    'The list gives no distinguishing clinical observation. The source hierarchy is preserved as an uncertainty rather than corrected from outside knowledge, but the invented discriminator is still a traceable output error.', cause='differential', ambiguous=True)
add(63, 'faithful', 'an extremely rare disease with nonspecific symptoms',
    'Primary pulmonary arterial sarcoma has nonspecific symptoms and may be difficult to distinguish from CTEPH.',
    'Nonspecific symptoms is a typical feature of primary pulmonary arterial sarcoma.', '',
    'Low informational value is not semantic falsity; this accurately retains the broad descriptive association.')
add(64, 'distorted', 'These pathological structures are bilateral, pale, and gray-white or yellowish lesions',
    'Choroidal tubercles on fundoscopy have this appearance; their ocular identity/location supplies the diagnostic referent.',
    'Unlocated bilateral pale gray-white/yellowish lesions are a typical miliary-TB sign.',
    'predicate_identity|scope_anatomic',
    'Removing choroidal/fundoscopic identity makes the finding match lesions in any organ. The adjectives are real source text, not an untraceable hallucination.')
add(65, 'distorted', 'Weighted percentage',
    'Epithelioid sarcoma comprises 28% of 570 selected hand soft-tissue sarcoma patients across the reviewed studies.',
    'Epithelioid Sarcoma has prevalence =28%, quoted to a non-verbatim ES 25% cell.',
    'scope_denominator|scope_population|provenance_quote|non_diagnostic_task',
    'The weighted 28% has a table ancestor; it is not invented. The clinical denominator is missing and the supporting quote points to a different number.', cause='boundary')
add(66, 'faithful', 'Progressive supranuclear palsy produces balance, movement, and gait problems',
    'Balance problems are a manifestation of progressive supranuclear palsy.',
    'Balance problems is a typical PSP feature.', '',
    'The independent feature is directly supported; omission of neighboring manifestations is source coverage, not distortion of this atom.')
add(67, 'distorted', 'many patients with deposit disease have been followed for years with a diagnosis of left ventricular hypertrophy (LVH) or hypertrophic cardiomyopathy',
    'Deposit diseases can mimic and be misdiagnosed as LVH/HCM for years.',
    'Having an LVH/HCM diagnosis distinguishes Deposit disease from HCM.',
    'relation_direction|predicate_identity|scope_time',
    'Diagnostic confusion is inverted into a discriminator favoring one side. The predecessor claim is clearly identifiable.', cause='differential')
add(68, 'distorted', 'the duration of treatment did not differ statistically significantly',
    'In the studied cellulitis anatomical subgroups, treatment duration had no statistically significant between-group difference.',
    'Duration of treatment is a typical Cellulitis diagnostic criteria feature.',
    'predicate_identity|numeric_comparison|non_diagnostic_task|scope_population',
    'A null comparative outcome is reduced to the name of a variable, eliminating the actual assertion and making it diagnostic evidence.')
add(69, 'out_of_scope_traceable', 'The mortality associated with appendectomy is low',
    'Appendectomy has low mortality.',
    'Appendectomy mortality is low, encoded as threshold operator = and string value low.', '',
    'The qualitative outcome is faithfully retained outside the diagnostic domain. The nonnumeric threshold violates the type contract but does not introduce a false mortality number.')
add(70, 'out_of_scope_traceable', 'erythromycin, clindamycin, tetracycline, and cephalosporins',
    'E. rhusiopathiae remains susceptible to clindamycin among other antibiotics.',
    'E. rhusiopathiae infection is typically treated by clindamycin.', '',
    'This is a reasonable faithful susceptibility-to-treatment statement, outside diagnostic-rule scope. The shortened reconstructed quote is separately marked non-verbatim.')
add(71, 'distorted', 'Fifty percent of BCC lesions are found on the lower lid',
    'In the eyelid-malignancy document, lower-lid lesions account for 50% of periocular BCC; the local paragraph abbreviates this to BCC.',
    '50% of generic Basal Cell Carcinoma lesions are on the lower lid.',
    'scope_population|scope_anatomic|scope_denominator',
    'All seven available same-document windows were checked; the epidemiology window explicitly establishes eyelid malignancy. The local payload already loses that global scope, so this is partly inherited source-window ambiguity, not solely model failure.', cause='boundary', ambiguous=True, doc=True)
add(72, 'faithful', 'polycyclic aromatic hydrocarbons',
    'Polycyclic aromatic hydrocarbon exposure is included among lung-cancer causes in the NSCLC etiology paragraph.',
    'NSCLC is caused_by polycyclic aromatic hydrocarbons with typical, non-obligatory modality.', '',
    'The target and etiologic association are supported; the abbreviated quote fails verbatim form but has a clear full-input ancestor.')
add(73, 'distorted', 'may worsen cognition or mobility',
    'Certain off-label drugs lack benefit and may worsen mobility in delirium management.',
    'Delirium is negated-treated_by improved mobility.',
    'predicate_identity|relation_direction|literal_polarity|participant_binding|non_diagnostic_task',
    'An adverse outcome of medication is converted into a negative treatment relation whose object is a mobility outcome rather than a drug. The original adverse-effect text is traceable.')
add(74, 'faithful', 'Patients are at higher risks for paradoxical emboli',
    'Eisenmenger syndrome predisposes to paradoxical embolic complications.',
    'Paradoxical emboli is a typical Eisenmenger syndrome feature.', '',
    'Under the permitted broad feature_of relation, this correctly represents an associated complication. It does not state emboli are required or sufficient; absolute frequency is not inferred.')
add(75, 'faithful', 'Well-differentiated cells embedded in the osseous matrix and fibrous stroma',
    'The low-grade osteosarcoma subtype has well-differentiated cells in the described stroma.',
    'Well-differentiated cells is a typical Low-grade osteosarcoma histopathology feature.', '',
    'The subtype target and independent cellular feature are preserved, even though this atom does not reproduce the whole tissue architecture.')
add(76, 'distorted', 'In bacteremia, independent predictors of death include',
    'Chronic kidney disease predicts death among bacteremic patients in the Acinetobacter context.',
    'Kidney disease is a typical epidemiologic feature of generic bacteremia.',
    'non_diagnostic_task|target_effect|scope_population|predicate_identity',
    'A mortality predictor becomes diagnostic feature evidence; both chronicity and Acinetobacter setting are lost.')
add(77, 'faithful', 'PPT is most commonly a complication of sinusitis',
    'Sinusitis is the usual antecedent cause of Pott puffy tumor/syndrome.',
    'PPT is typically caused_by sinusitis.', '',
    'The causal antecedent and source modality are accurately preserved.')
add(78, 'distorted', 'These tests include ECG, pulmonary function test (PFT)',
    'Chest radiography is one of the tests used to exclude common heart/lung causes when investigating suspected pulmonary hypertension.',
    'Abnormal chest x-ray is a typical pulmonary-hypertension criteria feature.',
    'non_diagnostic_task|epistemic_status|predicate_identity|unsupported_result',
    'The procedure is mentioned, but no chest-film result is supplied. The added abnormal result is a recognizable test-order-to-result distortion, not a source-free hallucination.')
add(79, 'distorted', 'The third group is pulmonary hypertension due to pathology within or related to the lungs.',
    'Interstitial-lung-disease scarring is a causal substrate of Group 3 pulmonary hypertension.',
    'ILD-related inflammatory scarring is a typical feature of generic Pulmonary Hypertension.',
    'target_subtype|scope_population|relation_direction',
    'The explicitly cause-defined group and causal relation are erased, turning one etiologic alternative into general feature evidence.')
add(80, 'faithful', 'sensory changes over the dorsoradial hand',
    'Radial neuropathy can present with dorsoradial-hand sensory change.',
    'Dorsoradial-hand sensory changes is a typical Radial neuropathy feature.', '',
    'The relevant nerve distribution is preserved in the predicate; the atom is a true sign association.')
add(81, 'faithful', 'Catecholaminergic polymorphic ventricular tachycardia - May present with VT/VF',
    'CPVT may present with VT/VF, especially in the described emotional-stress context.',
    'VT/VF is a typical CPVT feature.', '',
    'The broad arrhythmic feature remains true and non-obligatory; missing trigger detail reduces specificity/source coverage. Invalid context_type diagnosis is separately recorded.')
add(82, 'faithful', 'Symptoms include cyanosis, clubbing of fingers and toenails, dyspnea, poor weight gain',
    'Cyanotic congenital cardiac lesions can cause poor weight gain.',
    'Poor weight gain is a typical Cyanotic heart disease feature.', '',
    'The parent category matches the source grouping and the symptom is an explicitly listed soft manifestation.')
add(83, 'faithful', 'Nail involvement is common, with subungual hyperkeratosis, splinter hemorrhages',
    'Splinter hemorrhages occur with nail involvement in PRP.',
    'Splinter hemorrhages is a typical PRP feature.', '',
    'The named nail finding has a clear disease association; no contradictory exclusivity or necessity is added.')
add(84, 'faithful', 'often develop as complications of cranial surgery or trauma',
    'Intracranial epidural abscesses can follow cranial surgery/trauma.',
    'Intracranial epidural abscesses are typically caused by trauma.', '',
    'The etiologic association and intracranial target are maintained as a non-obligatory cause; this is not a claim that trauma alone suffices.')
add(85, 'distorted', 'we classify it as small bowel and large bowel obstruction',
    'Small-bowel obstruction is a subtype of intestinal obstruction.',
    'Intestinal obstruction is variant_of small bowel obstruction.',
    'relation_direction|target_subtype',
    'With ordinary directed variant_of semantics, the subject and subtype are reversed. The prompt enumerates variant_of without defining its argument orientation, so prompt versus model cause is not isolated.')
add(86, 'faithful', 'DAD-induced ventricular arrhythmias occur in catecholaminergic polymorphic VT',
    'CPVT includes DAD-induced ventricular arrhythmias in the explained ryanodine/catecholamine mechanism.',
    'DAD-induced ventricular arrhythmias is a typical CPVT feature.', '',
    'The output retains a diagnostic causal-mechanistic qualifier on the arrhythmia; it does not assert an unrelated cellular mechanism as an independent bedside test.')
add(87, 'distorted', 'without evidence of an associated clonal hematologic disorder',
    'Indolent SM requires SM criteria with no associated clonal hematologic disorder or mast-cell-related end-organ damage.',
    'Negated evidence of associated clonal hematologic disorder EXCLUDES Indolent SM.',
    'relation_direction|literal_polarity',
    'A necessary absence is rendered as a negative literal that excludes the diagnosis when satisfied. This error is already present in the single raw atom, independently of group execution.', cause='negative')
add(88, 'faithful', 'Variant Creutzfeldt-Jakob disease is related to the consumption of meat from cattle',
    'Variant CJD is transmitted in relation to consumption of meat from BSE-affected cattle.',
    'Variant CJD is caused_by eating meat from cattle with BSE.', '',
    'The source’s explanatory causal/epidemiologic relationship is faithfully normalized without dropping the affected-cattle condition.')
add(89, 'out_of_scope_traceable', 'desmosomal breakdown, causing the classic acantholytic process',
    'ATPase dysfunction in Darier disease causes desmosomal breakdown and then acantholysis.',
    'Desmosomal breakdown is a typical Darier disease histopathologic feature.', '',
    'This is a traceable pure pathophysiologic statement rather than a stated diagnostic observation or criterion. It has not been strengthened to necessity or confirmation.')
add(90, 'distorted', 'Differential diagnosis of tricuspid regurgitation include the following:',
    'Carcinoid tumor appears among TR differential considerations; the preceding treatment paragraph also mentions carcinoid-caused valve disease.',
    'Carcinoid tumor as a symptom distinguishes Tricuspid Regurgitation from comparator Tricuspid Regurgitation.',
    'predicate_identity|relation_direction|comparator_identity|participant_binding',
    'An alternative/etiologic disease label supplies no differentiating finding, and self-comparison is incoherent. The list remains an identifiable ancestor.', cause='differential')

RELATIONS = set('feature_of required_for sufficient_for pathognomonic_for excludes argues_against distinguishes_from variant_of synonym_of caused_by treated_by'.split())
MODALITIES = set('obligatory typical frequent occasional rare'.split())
KINDS = set('symptom sign lab imaging histopathology ecg hemodynamic exposure demographic course other'.split())
CONTEXTS = set('definition criteria differential histopathology imaging epidemiology treatment prognosis table_row other'.split())

def schema_errors(unit):
    """Formal contract checks only. These checks never choose semantic labels."""
    found = []
    for row in unit['rows']:
        a = row['assertion']
        i = row['raw_index']
        for key, enum in [('relation', RELATIONS), ('modality', MODALITIES), ('predicate_kind', KINDS), ('context_type', CONTEXTS)]:
            if a.get(key) not in enum:
                found.append({'raw_index': i, 'field': key, 'value': a.get(key), 'error': 'value_outside_prompt_enum'})
        t = a.get('threshold')
        if isinstance(t, dict):
            if t.get('operator') == 'null':
                found.append({'raw_index': i, 'field': 'threshold.operator', 'value': 'null', 'error': 'string_null_instead_of_json_null'})
            if t.get('value') is not None and not isinstance(t['value'], (int, float)):
                found.append({'raw_index': i, 'field': 'threshold.value', 'value': t['value'], 'error': 'nonnumeric_threshold_value'})
            if t.get('value') is not None and t.get('operator') is None:
                found.append({'raw_index': i, 'field': 'threshold.operator', 'value': None, 'error': 'numeric_value_without_operator'})
        if a.get('comparator') is not None and a.get('relation') not in {'distinguishes_from', 'argues_against'}:
            found.append({'raw_index': i, 'field': 'comparator', 'value': a['comparator'], 'error': 'comparator_not_allowed_for_relation'})
        if 'criterion_group' not in a:
            found.append({'raw_index': i, 'field': 'criterion_group', 'value': None, 'error': 'missing_requested_field'})
        if a.get('quote') and a['quote'] not in unit['text']:
            found.append({'raw_index': i, 'field': 'quote', 'value': a['quote'], 'error': 'quote_not_verbatim_in_payload'})
    return found

def causes(d, n):
    if d['label'] == 'faithful':
        return []
    if d['label'] == 'out_of_scope_traceable':
        return [{'cause': 'prompt_task_scope_mismatch', 'evidence_level': 'A',
                 'rationale': 'GUIDELINE_PROMPT asks for every assertion about a named disease and explicitly permits treated_by, treatment, prognosis and epidemiology. Emitting faithfully traceable non-diagnostic content is therefore permitted by this broad extraction contract; diagnostic utility is a different target.'}]
    c = d['cause']
    out = [{'cause': 'unisolated_prompt_or_model_semantic_error', 'evidence_level': 'C',
            'rationale': 'The supplied full passage and raw cached output establish the semantic discrepancy before normalization/binding. They do not isolate whether a revised prompt would prevent it or establish an intrinsic model capacity limit.'}]
    if c == 'required':
        out.append({'cause': 'model_violated_clear_instruction', 'evidence_level': 'B',
                    'rationale': 'The actual prompt reserves required_for for a feature necessary for the diagnosis. The raw output instead attaches a treatment/evaluation indication to the disease. This localizes a clear contract violation, without claiming a controlled estimate of prompt causality.'})
    if c == 'target':
        out.append({'cause': 'model_violated_clear_instruction', 'evidence_level': 'B',
                    'rationale': 'The prompt requires disease names as the passage calls them and permits other named diseases. The output binds the observed finding to a focus disease absent from this payload.'})
    if c == 'negative':
        out.append({'cause': 'prompt_underspecification', 'evidence_level': 'C',
                    'rationale': 'The prompt tells the model to negate absent findings but does not define how literal truth composes with excludes versus required_for, or provide a truth table for necessary absences. The negated+excludes error is present raw; this prompt mechanism is plausible, not experimentally isolated.'})
    if c == 'differential':
        out.append({'cause': 'prompt_underspecification', 'evidence_level': 'C',
                    'rationale': 'The prompt supplies distinguishes_from and a comparator slot but does not explicitly forbid converting a bare differential list into a discriminating finding. No actual discriminator is stated in the source ancestor.'})
    if c in {'nested', 'score'}:
        out.append({'cause': 'schema_unrepresentable', 'evidence_level': 'A',
                    'rationale': ('The flat group has one logic/count and cannot link this major/minor subgroup to facial hemangioma AND (major-count OR minor-count), with nested group effect.' if c == 'nested' else 'The flat all/any/at_least_n group has no count-to-probability/score map. The supplied four different Kocher count outcomes cannot be represented faithfully as this one ANY group.')})
    if c == 'boundary':
        out.append({'cause': 'source_structure_or_ambiguity', 'evidence_level': 'A' if n in {20,26,71} else 'C',
                    'rationale': ('The actual payload loses the source-list/domain/global scope required for a complete rule; this precedes extraction. The model additionally emits a completed or unscoped raw claim.' if n in {20,26,71} else 'The payload contains a truncated head, juxtaposed sections, table cells or a case caption. This layout is an observed possible contributor to wrong scope/subject; it is not a controlled causal effect.')})
    return out

def main():
    assert set(DECISIONS) == set(range(1,91))
    result = []
    bad_anchors = []
    for n, unit in enumerate(PACK, 1):
        d = DECISIONS[n]
        context = DOCS[unit['doc_key']] if d['doc'] else []
        anchor_exists = d['ancestor_anchor'] in unit['text'] or any(d['ancestor_anchor'] in w['text'] for w in context)
        if not anchor_exists:
            bad_anchors.append((n, d['ancestor_anchor']))
        first = 'source_to_raw_extraction' if d['label'] == 'distorted' else 'none_semantic'
        if n in {20,26,71}:
            first = 'source_to_payload_scope_loss_then_raw_completion'
        rec = {
            'sample_id': unit['sample_id'], 'unit_id': unit['unit_id'],
            'label': d['label'], 'ancestor_anchor': d['ancestor_anchor'],
            'source_semantics': d['source_semantics'], 'output_semantics': d['output_semantics'],
            'errors': d['errors'], 'first_damage': first, 'causes': causes(d,n),
            'rationale': d['rationale'],
            'provenance_search': {
                'scope': 'full_actual_input_and_all_available_same_doc_windows' if d['doc'] else 'full_actual_input',
                'doc_windows_checked': len(context) if d['doc'] else 1,
                'available_doc_windows': len(DOCS[unit['doc_key']]),
                'checked_window_ids': [w['window_id'] for w in context] if d['doc'] else [unit['window_id']],
                'reason': ('All available same-document windows were read for the scope issue; no source-free claim is alleged.' if d['doc'] else 'A specific ancestor is identified in the complete actual input; broader search is unnecessary to distinguish traceable distortion from strict fabrication.'),
                'ancestor_exact_match_verified': anchor_exists,
            },
            'reviewer': 'output_adjudication_2_ai_close_reading',
            'raw_indices': [r['raw_index'] for r in unit['rows']],
            'complexity': d['complexity'] or 'atomic',
            'source_status': 'ambiguous_source' if d['ambiguous_source'] else 'adjudicable',
            'schema_errors': schema_errors(unit),
        }
        result.append(rec)
    if bad_anchors:
        raise ValueError(bad_anchors)
    (P / 'output_adjudication_2.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    counts = Counter(r['label'] for r in result)
    grouped = Counter(r['label'] for r in result[:30])
    atomic = Counter(r['label'] for r in result[30:])
    notes = f'''# Output pack 2: close-reading adjudication

Reviewer: output_adjudication_2 (AI). All 90 full input windows and all selected raw members were read; labels below were manually assigned before serialization. This is not clinician validation or an independently blinded second judgment.

## Counts (unweighted)

- All 90: {dict(counts)}
- Whole groups, 30: {dict(grouped)}
- Atoms, 60: {dict(atomic)}
- Units with any separately recorded formal schema/quote-contract issue: {sum(bool(r['schema_errors']) for r in result)}.

No strict untraceable fabrication was identified in this pack. Every selected output has an identifiable source ancestor, including test-order→invented abnormal result, wrong-target transfers, and treatment→diagnosis promotions. These are distortions under the frozen definition, not evidence that the model never hallucinates. No unresolved provenance remains. Ambiguous source scope is retained separately for O2-006/008/017/020/026/062/071; those distorted labels rely on additional identifiable errors rather than an invented source criterion.

## Adjudication boundaries requiring root review

- Faithful whole groups: O2-001, O2-011, O2-015, O2-016, O2-028. Their common relation/modality can represent a shallow necessary substrate or a soft association set. None is condemned just for lacking a standalone group-effect field. Kanavel ALL typical features (O2-016) preserves a named complete pattern; downstream interpretation as disease necessity would be an engine error.
- O2-004 is a major-criterion subgroup without its role or connection to the PHACE hemangioma + major/minor expression; O2-012 drops the right-precordial minor-criterion scope of epsilon wave. These are more stringent group judgments than merely checking that their leaf nouns occur.
- A true independent feature is not labelled distorted merely because other parallel features are absent. O2-039, 046, 049, 066, 075 and 081 are examples. Explicit conditional populations, different persons, source-defined subtypes and omitted anatomical referents remain material errors (O2-032/033/048/050/052/064).
- O2-043 preserves the correct bacteremia risk relation but uses an illegal relation enum; O2-059/081 preserve features but have invalid context_type; O2-069 faithfully says low postoperative mortality using an invalid numeric threshold. Semantic labels and formal contract defects are separated in schema_errors. Verbatim-quote failure also does not automatically mean semantic hallucination.
- O2-030/047/069/070 are faithful non-diagnostic treatment/outcome content. O2-089 is a pure disease-mechanism statement, preserved without becoming a diagnostic necessary/sufficient claim.
- O2-071 was checked against all seven available same-document windows: the source is specifically about eyelid lesions. The local payload already loses this global denominator, so the generic BCC rate partly inherits a source-window scope defect. O2-008 was checked against both available same-document windows; precise complete LBBB subtype criteria remain truncated, but the negative-literal exclusion reversal is directly visible.

## Attribution discipline

The historical full input and raw cache localize errors before normalization and binding. They do not distinguish prompt causality from latent model capacity by themselves. Prompt cause is therefore C unless a direct contract conflict is demonstrable. required_for on treatment criteria violates a clear diagnosis-only instruction. Unsupported disease targets violate the named-source-subject instruction. The schema's lack of recursive group references and a count-to-risk program directly limits PHACE and Kocher representations. Negative-literal/excludes composition and bare differential lists are underspecified in the actual prompt, but their independent causal effect needs controlled intervention.

No API calls, source inventory disclosure, Git changes outside these adjudication artifacts, or production changes were made by this reviewer. The serializer validates exact source anchors and the one-record-per-unit accounting; it does not produce semantic labels using keyword logic.
'''
    (P / 'output_adjudication_2_notes.md').write_text(notes)
    print(json.dumps({'n': len(result), 'counts': dict(counts), 'groups': dict(grouped), 'atoms': dict(atomic), 'schema_flag_units': sum(bool(r['schema_errors']) for r in result)}, indent=2))

if __name__ == '__main__':
    main()
