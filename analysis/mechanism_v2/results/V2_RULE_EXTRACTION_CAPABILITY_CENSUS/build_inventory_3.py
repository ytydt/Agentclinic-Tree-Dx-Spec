"""Source-only human-style inventory transcription; no extraction outputs are read."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
sources = json.loads((BASE / 'source_only_pack_3.json').read_text())
inventory = []

def begin(n, note):
    source = sources[n - 1]
    item = dict(sample_id=source['sample_id'], window_id=source['window_id'],
                reviewer='source_inventory_3_AI_source_blinded', reading_note=note,
                non_target_source=[], rules=[])
    inventory.append(item)
    return item

def non(item, anchor, kind, reason):
    item['non_target_source'].append(dict(anchor=anchor, kind=kind, reason=reason))

def rule(item, anchor, target, kind, semantics, logic, scope='', status='adjudicable',
         flat='exact', complexity='atomic', notes=''):
    item['rules'].append(dict(
        rule_id=f"{item['sample_id']}-R{len(item['rules'])+1:02d}",
        source_anchor=anchor, target=target, rule_kind=kind,
        source_semantics=semantics, logical_form=logic, scope=scope,
        source_status=status, flat_schema=flat, complexity=complexity, notes=notes))

x = begin(1, 'Read all three recommendations. The compression-neuropathy conjunction is a management eligibility condition, not a definition or an exclusion rule. The FND sentence supplies a weak descriptive association despite appearing in advice.')
rule(x, 'their limb or facial weakness might fluctuate and evolve over time and might increase during times of stress',
     'Functional neurological disorder', 'descriptive_features',
     'In adults with limb or facial weakness already ascribed to FND, weakness may fluctuate/evolve and may increase during stress. Neither stress nor fluctuation is necessary or sufficient for FND.',
     'FND_related_weakness IN adults -> MAY(fluctuate, evolve_over_time, increase_during_stress)',
     'Adults; weakness already attributed to FND; modal might', complexity='association_set')
non(x, 'For adults with clear features of compression neuropathy', 'management_eligibility',
    'Compression neuropathy AND no radiculopathy selects splint/review management, not a rule excluding compression neuropathy when radiculopathy is present.')
non(x, 'review the symptoms after 6', 'followup', 'Six weeks and non-improvement determine referral; they are not diagnostic thresholds.')
non(x, 'avoid any activity that might lead to further pressure', 'prevention', 'Advice about further compression, without a result-to-diagnosis claim.')

x = begin(2, 'Read full neuroimaging/EEG window. Separate ordering from the stated interpretive role and explicit prohibition of exclusion. No particular EEG pattern is supplied.')
rule(x, 'to support diagnosis and provide information about seizure type or epilepsy syndrome',
     'Epilepsy / epileptic seizure', 'conditional_test_support',
     'When history and examination suggest an epileptic seizure and epilepsy is suspected, routine awake EEG can provide supportive diagnostic and classification information; the source does not specify an EEG result or declare EEG sufficient.',
     'IF(history_and_exam_suggest_seizure AND epilepsy_suspected) THEN MAY_USE(routine_awake_EEG, supportive_information)',
     'Routine awake EEG in suspected epilepsy; no result threshold supplied', flat='lossy', complexity='scoped_rule',
     notes='This is an interpretive capability claim embedded in a workup instruction, not a positive-EEG criterion.')
rule(x, 'Do not use EEG to exclude a diagnosis of epilepsy.',
     'Epilepsy', 'test_nonexclusion',
     'EEG must not be used to exclude epilepsy; no EEG finding, including an unremarkable result inferred as the common relevant case, is licensed here as a standalone exclusion.',
     'NOT_VALID(EEG_result -> exclude(epilepsy))',
     'Diagnostic exclusion; source does not prescribe a particular EEG finding', flat='lossy',
     notes='Do not rewrite as epilepsy excludes EEG or abnormal EEG excludes epilepsy.')
non(x, 'Offer brain neuroimaging tests if an underlying structural cause is suspected', 'workup', 'Suspicion triggers imaging; no imaging result-to-diagnosis rule is given.')

x = begin(3, 'Read the abscess-management paragraphs and complete bacteremia material. Risk/organism-site associations are weak diagnostic context. Treatment and downstream complications without differential interpretation are retained as non-target provenance.')
rule(x, 'Bacteremia is the presence of bacteria in the bloodstream.', 'Bacteremia', 'definition',
     'Bacteremia denotes bacteria present in bloodstream, without adding symptoms or requiring sepsis.',
     'bacteremia := bacteria_present_in_bloodstream')
rule(x, 'It can occur spontaneously, during', 'Bacteremia', 'etiologic_risk_associations',
     'Bacteremia can be spontaneous or associated with tissue infections, indwelling GU/IV catheters, and dental/GI/GU/wound-care/other procedures. These are possible contexts, not necessary conditions.',
     'MAY_CONTEXT(bacteremia; spontaneous, tissue_infection, GU_or_IV_catheter, dental_or_GI_or_GU_or_wound_or_other_procedure)',
     'Possible contexts; list open-ended', complexity='association_set')
rule(x, 'Transient bacteremia is', 'Transient bacteremia', 'descriptive_features',
     'Transient bacteremia is often asymptomatic but can cause fever. Fever is optional and absence of symptoms does not exclude it.',
     'transient_bacteremia -> OFTEN(asymptomatic) AND MAY(fever)',
     'Transient bacteremia', complexity='association_set')
rule(x, 'Development of other symptoms usually suggests', 'Sepsis / septic shock', 'support',
     'In the bacteremia discussion, symptoms beyond the asymptomatic/fever picture usually suggest more serious infection, of which sepsis and septic shock are examples. The extra symptoms are not specified.',
     'bacteremia_context AND additional_symptoms -> SUPPORTS(serious_infection; examples=sepsis,septic_shock)',
     'Symptoms unspecified; examples not an exhaustive or sufficient diagnostic list', flat='lossy', complexity='scoped_rule')
rule(x, 'Gram-negative bacteremia secondary to infection usually originates', 'Gram-negative bacteremia', 'conditional_source_distribution',
     'When gram-negative bacteremia is secondary to infection, its usual origins are GU/GI infection or skin infection in patients with decubitus ulcers.',
     'infectious_gram_negative_bacteremia -> USUAL_SOURCE(GU OR GI OR (skin AND decubitus_ulcers))',
     'Conditional on infection-related bacteremia; decubitus-ulcer qualifier belongs to skin branch', flat='lossy', complexity='nested_group')
rule(x, 'Chronically ill and immunocompromised patients have an increased risk of', 'Gram-negative bacteremia', 'risk_association',
     'Chronic illness and immunocompromise identify patients with increased gram-negative bacteremia risk; the wording does not establish that both must coexist.',
     'chronic_illness OR immunocompromise -> increased_risk(gram_negative_bacteremia)',
     'Risk rather than sufficient diagnosis', complexity='association_set',
     notes='English list of patient categories, not obligatory clinical AND.')
rule(x, 'They may also develop bacteremia with gram-positive cocci, anaerobes, and', 'Bacteremia with gram-positive cocci/anaerobes; fungemia', 'possible_pathogens',
     'The same chronically ill/immunocompromised patients may have bloodstream infection with gram-positive cocci, anaerobes or fungi; fungi are included by the source in this sentence without correcting its terminology.',
     'chronic_illness OR immunocompromise -> MAY_BLOODSTREAM_PATHOGEN(gram_positive_cocci, anaerobes, fungi)',
     'Preserve source terminology; non-exclusive possibilities', complexity='association_set')
rule(x, 'Staphylococcal bacteremia is common among injection drug users and patients with IV catheters.',
     'Staphylococcal bacteremia', 'risk_association',
     'Staphylococcal bacteremia is common among injection drug users and among patients with IV catheters; neither exposure is required.',
     'injection_drug_use OR IV_catheter -> ASSOCIATED_WITH(staphylococcal_bacteremia)',
     'Population association', complexity='association_set')
rule(x, 'bacteremia may develop in patients with infections of the abdomen and the pelvis,', 'Bacteroides bacteremia', 'risk_association',
     'Bacteroides bacteremia may arise with abdominal/pelvic infection, particularly female genital-tract infection. This is an optional source association.',
     'abdomen_or_pelvic_infection -> MAY(Bacteroides_bacteremia); emphasis=female_genital_tract',
     'Bacteroides heading spans a blank line', complexity='association_set')
rule(x, 'If an infection in the abdomen causes bacteremia, the organism is', 'Gram-negative bacillary bacteremia', 'conditional_pathogen_support',
     'Given that an abdominal infection has caused bacteremia, the organism is most likely a gram-negative bacillus. Abdominal infection alone is not sufficient to diagnose bacteremia.',
     'bacteremia AND caused_by(abdominal_infection) -> MOST_LIKELY_PATHOGEN(gram_negative_bacillus)',
     'Requires bacteremia and causal source, not mere abdominal symptoms', flat='lossy', complexity='scoped_rule')
rule(x, 'If an infection above the diaphragm causes bacteremia, the', 'Gram-positive bacteremia', 'conditional_pathogen_support',
     'Given bacteremia caused by infection above the diaphragm, gram-positive organisms are most likely.',
     'bacteremia AND caused_by(infection_above_diaphragm) -> MOST_LIKELY_PATHOGEN(gram_positive)',
     'Conditional source localization', flat='lossy', complexity='scoped_rule')
rule(x, 'abscess formation is especially common with staphylococcal bacteremia.', 'Staphylococcal bacteremia', 'descriptive_complication_pattern',
     'Multiple abscess formation is especially common with staphylococcal bacteremia, a pathogen-specific pattern, not a sufficient diagnostic criterion.',
     'staphylococcal_bacteremia -> ESPECIALLY_COMMON(multiple_abscesses)',
     'Association useful as differential context',
     notes='The full source phrase starts Multiple across a paragraph break.')
rule(x, 'most commonly with enterococcal, streptococcal, or staphylococcal bacteremia and less commonly',
     'Infective endocarditis', 'conditional_pathogen_risk',
     'Bacteremia may cause endocarditis, most commonly enterococcal/streptococcal/staphylococcal and less commonly gram-negative bacteremia or fungemia; this comparative association is not an exclusion.',
     'MAY(endocarditis | bloodstream_infection); higher_association(enterococcal,streptococcal,staphylococcal) vs lower_association(gram_negative,fungal)',
     'Relative pathogen association without numerical likelihoods', flat='lossy', complexity='association_set')
rule(x, 'Patients with structural heart disease', 'Infective endocarditis', 'risk_association',
     'Structural heart disease, prosthetic valves, or other intravascular prostheses predispose to endocarditis. Staphylococcal endocarditis is particularly associated with injection drug use and may involve the tricuspid valve.',
     'RISK_CONTEXT(endocarditis; structural_heart_disease,prosthetic_valve,other_intravascular_prosthesis); staphylococcal_endocarditis -> PARTICULAR_CONTEXT(injection_drug_use) AND MAY(tricuspid_involvement)',
     'General predisposition plus pathogen-specific optional pattern', flat='lossy', complexity='association_set',
     notes='Kept as one contiguous endocarditis risk/feature set; no sufficient condition.')
non(x, 'Superficial abscesses may resolve with heat and oral antibiotics.', 'treatment', 'Abscess drainage/antibiotic recommendations, including deep abscess OR cellulitis antibiotic eligibility, are not diagnostic rules.')
non(x, 'Spontaneous rupture and drainage may occur', 'natural_history', 'Abscess resolution, sinuses, loculation and calcification are natural-history descriptions without a diagnostic target inference here.')
non(x, 'Transient or sustained bacteremia can cause metastatic infection', 'complications', 'Generic metastatic/systemic consequences are not converted into sufficient evidence for bacteremia.')

x = begin(4, 'Read full author-response extract, retaining its genre as reviewer response rather than guideline. Definition, age association and test limitations are target claims; none is a threshold criterion.')
rule(x, 'Dementia is a heterogeneous neurocognitive disorder that compromises the activities of daily living', 'Dementia', 'definition',
     'Dementia is described as a heterogeneous neurocognitive disorder compromising daily living. This brief definition does not supply a complete diagnostic standard.',
     'dementia -> neurocognitive_disorder AND compromises(activities_of_daily_living)',
     'Definition in article author response; not a full operational criterion', complexity='association_set')
rule(x, 'with a higher prevalence with advancing age', 'Dementia', 'age_association',
     'Dementia prevalence increases with age; no age cutoff or age-based exclusion is given.',
     'advancing_age -> higher_prevalence(dementia)', 'Population association only')
rule(x, 'the ceiling effect may limit their sensitivity to subtle impairment in highly educated individuals', 'Subtle cognitive impairment', 'conditional_test_limitation',
     'MMSE/MoCA ceiling effects may limit sensitivity to subtle impairment in highly educated people. A good score is not licensed as exclusion in that scope.',
     'high_education AND subtle_impairment -> MAY(reduced_sensitivity(MMSE_or_MoCA,ceiling_effect))',
     'MMSE/MoCA; highly educated; subtle impairment', flat='lossy', complexity='scoped_rule')
rule(x, 'performance measurement may misclassify cases as false-positive or false-negative absent collateral information', 'Cognitive impairment / dementia screening', 'conditional_test_limitation',
     'Without collateral information, objective performance testing can yield false positives and false negatives; the source does not define a specific score or guaranteed direction of error.',
     'absent(collateral_information) -> MAY(false_positive OR false_negative, performance_based_test)',
     'Performance-based assessment in dementia-screening discussion', flat='lossy', complexity='scoped_rule')
non(x, 'The global prevalence of dementia has been estimated to be around 7%', 'population_burden', 'Global aggregate prevalence is not a patient-level diagnostic claim; its separate age gradient is inventoried.')
non(x, 'require more time and expertise to administer', 'administration', 'Comparative administration burden and screening motivation do not define diagnostic rules.')

x = begin(5, 'Read all CT and PET material. Modality sensitivity/resolution and biopsy guidance are not operational result rules. Separate early, late and complication imaging patterns, preserving temporal qualifiers and the tuberculosis-specific calcification inference.')
rule(x, 'The reduction in density of the intervertebral disc can be visualized in very early stages', 'Infectious spondylodiscitis', 'early_imaging_features',
     'In very early infection, CT can show reduced intervertebral-disc density and thinning of paravertebral fat; these are possible findings, not requirements.',
     'early(infectious_spondylodiscitis) -> MAY_CT(reduced_disc_density,thinned_paravertebral_fat)',
     'CT; very early stage', complexity='association_set')
rule(x, 'Bone destruction and sequestra formation can be seen in later stages.', 'Infectious spondylodiscitis', 'late_imaging_features',
     'Later stages may show bone destruction and sequestra; absence in early disease cannot exclude infection.',
     'late(infectious_spondylodiscitis) -> MAY_CT(bone_destruction,sequestra)',
     'CT; later stage', complexity='association_set')
rule(x, 'the extension of the inflammation can be seen clearly, along with potential abscesses and epidural phlegmons', 'Infectious spondylodiscitis', 'imaging_extent_features',
     'CT may delineate inflammatory extension, abscesses and epidural phlegmons, with possible spinal-cord compression. These are optional extent/complication features.',
     'infectious_spondylodiscitis -> MAY_CT(inflammation_extension,abscess,epidural_phlegmon); MAY_CAUSE(epidural_process,cord_compression)',
     'Optional complications; not necessary disease features', flat='lossy', complexity='association_set')
rule(x, 'the latter points towards tuberculous spondylodiscitis', 'Tuberculous spondylodiscitis', 'support',
     'Calcifications (the latter of sequestra and subsequent calcifications) point toward tuberculous spondylodiscitis, without standalone certainty.',
     'calcifications_in_spondylodiscitis_context -> SUPPORTS(tuberculous_spondylodiscitis)',
     'Resolve latter to calcifications, not sequestra or CT modality', complexity='scoped_rule')
non(x, 'CT has a far higher sensitivity', 'modality_comparison', 'Sensitivity/earlier visibility comparisons lack a patient-level result criterion.')
non(x, 'CTs are also useful for guided biopsies', 'workup', 'Biopsy guidance and cause determination are procedures, not rule conditions.')
non(x, 'PET imaging is inherently of higher resolution', 'modality_comparison', 'PET resolution and uptake differentiation have no supplied uptake threshold or interpretable result rule.')

x = begin(6, 'Read complete histopathology extract including incidental nerve-sheath/vascular targets. The low-grade characterization is retained as written, not silently corrected from outside knowledge. Marker lists are associations/panels, never an invented all-positive requirement.')
rule(x, 'Myxofibrosarcoma encompasses a spectrum of malignant fibroblastic tumors', 'Myxofibrosarcoma', 'histologic_definition_features',
     'The source describes malignant fibroblastic tumors with myxoid stroma, variable pleomorphism and curvilinear vasculature, then describes low-grade nature, fibrous/myxoid regions, whorling, low cellularity and bland fibroblasts. These descriptive features are not declared a sufficient panel.',
     'DESCRIBED_FEATURE_SET(myxofibrosarcoma; malignant_fibroblastic,myxoid_stroma,variable_pleomorphism,curvilinear_vessels,low_grade,fibrous_and_myxoid,whorled,low_cellularity,bland_fibroblasts)',
     'Preserve source low-grade wording without external clinical endorsement', complexity='association_set')
rule(x, 'histopathology is insufficient to distinguish fibrosarcomas from other spindle-cell sarcomas', 'Fibrosarcoma versus other spindle-cell sarcomas', 'test_insufficiency',
     'Histopathology alone is insufficient for this distinction; appropriate IHC markers can assist, without a named sufficient IHC panel.',
     'NOT_SUFFICIENT(histopathology_alone, distinguish(fibrosarcoma,other_spindle_sarcoma)); MAY_ASSIST(appropriate_IHC)',
     'Differential discrimination', flat='lossy', complexity='scoped_rule')
rule(x, 'Vimentin is a marker indicative of a mesenchymal cell origin', 'Mesenchymal cell origin', 'marker_support',
     'Vimentin positivity indicates mesenchymal origin and is not specific for fibrosarcoma.',
     'vimentin_positive -> SUPPORTS(mesenchymal_origin)', 'Cell-origin category')
rule(x, 'is often the only positively stained marker in the diagnosis of fibrosarcomas', 'Fibrosarcoma', 'marker_pattern',
     'Vimentin is often the only positive stain in fibrosarcoma, rather than always positive/always uniquely positive.',
     'fibrosarcoma -> OFTEN(only_positive_stain=vimentin)', 'Frequency qualifier often', flat='lossy', complexity='scoped_rule')
rule(x, 'alpha-smooth muscle actin, muscle-specific actin, and desmin', 'Myofibroblastic differentiation', 'marker_associations',
     'Alpha-SMA, muscle-specific actin and desmin are common myogenic markers often representing myofibroblastic differentiation; source does not require all three.',
     'MARKER_ASSOCIATION(myofibroblastic_differentiation; alpha_SMA,muscle_specific_actin,desmin)',
     'Often; no panel positivity cardinality specified', complexity='association_set')
rule(x, 'a positive S-100 protein marker would indicate a nerve sheath tumor', 'Nerve sheath tumor', 'marker_support',
     'A positive S-100 marker indicates the nerve-sheath alternative in this differential; the prose does not establish a universally sufficient standalone diagnosis.',
     'S100_positive -> SUPPORTS(nerve_sheath_tumor)', 'Fibrosarcoma differential context')
rule(x, 'CD31, CD34, and Factor VIII non-von Willebrand factor would suggest a vascular tumor', 'Vascular tumor', 'marker_panel_support',
     'The named vascular markers suggest vascular tumor; no all/any positivity operator is specified for the panel.',
     'POSITIVE_MARKER_PANEL_UNSPECIFIED(CD31,CD34,Factor_VIII_non_vWF) -> SUPPORTS(vascular_tumor)',
     'Retain source factor-VIII wording; panel connective not operationally specified', flat='ambiguous', complexity='association_set')
rule(x, 'rather than a true fibrosarcoma', 'Fibrosarcoma', 'relative_counterevidence',
     'Vascular-marker evidence favors a vascular tumor over true fibrosarcoma. Relative differential preference is not a universal hard exclusion.',
     'vascular_marker_evidence -> RELATIVE_AGAINST(fibrosarcoma)',
     'Same panel as preceding rule; independent opposing target/effect', flat='ambiguous', complexity='association_set')
non(x, 'monitoring treatment efficacy and tumor recurrence', 'monitoring', 'Marker monitoring is not initial diagnostic evidence.')

x = begin(7, 'Read all cells of the five-column classification table. This is a causal/category taxonomy, not criteria that diagnose PH from a listed comorbidity. Five category-level definition rules preserve ancestry and causal qualifiers; one extra vasoreactivity subdivision is not turned into IPAH proof.')
rule(x, 'conditions characterized by high pulmonary pressures', 'Pulmonary hypertension', 'definition',
     'PH is characterized by high pulmonary pressures; the extract gives no numeric measurement cutoff.',
     'pulmonary_hypertension -> high_pulmonary_pressure', 'No hemodynamic numeric threshold supplied')
rule(x, 'Group 1: Pulmonary Arterial Hypertension (PAH)', 'Group 1 pulmonary arterial hypertension', 'etiologic_subtype_taxonomy',
     'PAH category includes idiopathic, heritable, drug/toxin-induced, associated disease forms (CTD/HIV/portal hypertension/CHD/schistosomiasis), venous/capillary-involvement forms (PVOD/PCH), and persistent PH of the newborn. A listed condition alone is not sufficient for PAH.',
     'SUBTYPES(PAH; idiopathic,heritable,drug_or_toxin_induced,associated_with(CTD|HIV|portal_hypertension|CHD|schistosomiasis),venous_or_capillary_involvement(PVOD|PCH),persistent_PH_newborn)',
     'Classification within already established pulmonary-hypertension context; no comorbidity=>PAH implication', flat='exact', complexity='nested_group',
     notes='Non-operational taxonomy counted as category definition; variant_of edges can preserve taxonomic ancestry without requiring a Boolean criterion group. Separate sensitivity analysis may exclude taxonomy rules.')
rule(x, '1.1.1 Non-responders to vasoreactivity testing 1.1.2 Acute responders to vasoreactivity testing', 'Idiopathic PAH response subtypes', 'subtype_definition',
     'The IPAH entry has vasoreactivity nonresponder and acute-responder subtypes. Neither response pattern establishes IPAH by itself.',
     'IPAH AND vasoreactivity_nonresponse -> subtype(nonresponder); IPAH AND acute_vasoreactivity_response -> subtype(acute_responder)',
     'Conditional on IPAH; response thresholds absent', flat='lossy', complexity='scoped_rule')
rule(x, 'Group 2: Pulmonary Hypertension due to left heart disease (PH-LHD)', 'Group 2 PH due to left heart disease', 'causal_subtype_definition',
     'This group is PH caused by left-heart disease: heart failure with preserved/reduced EF, valvular disease, or congenital/acquired cardiovascular conditions leading to postcapillary PH. The causal link and PH must be retained.',
     'group2_PH := PH AND due_to(left_heart_disease[HF(preserved_EF|reduced_EF)|valvular|congenital_or_acquired_cardiovascular_causing_postcapillary_PH])',
     'Classification; causal attribution required; alternatives not a necessary all-items panel', flat='lossy', complexity='nested_group')
rule(x, 'Group 3:Pulmonary Hypertension due to Lung Diseases, Hypoxia, or Both', 'Group 3 PH due to lung disease/hypoxia', 'causal_subtype_definition',
     'Group 3 is PH due to lung disease, hypoxia, or both, with obstructive/restrictive/mixed lung disease, hypoventilation, hypoxia without lung disease, and developmental lung disorder subtypes.',
     'group3_PH := PH AND due_to(lung_disease OR hypoxia OR both); lung_disease_subtypes=[obstructive,restrictive,mixed,developmental]; other_subtypes=[hypoventilation,hypoxia_without_lung_disease]',
     'Causal classification, not lung-disease/hypoxia presence as sufficient PH criterion', flat='lossy', complexity='nested_group')
rule(x, 'Group 4:Pulmonary Hypertension Due to Pulmonary Artery Obstructions', 'Group 4 PH due to pulmonary artery obstruction', 'causal_subtype_definition',
     'Group 4 is PH due to pulmonary artery obstruction, including chronic thromboembolic PH and other obstructions; obstruction without PH is not enough.',
     'group4_PH := PH AND due_to(pulmonary_artery_obstruction[CTEPH|other])',
     'Causal classification', flat='lossy', complexity='scoped_rule')
rule(x, 'Group 5:Pulmonary Hypertension with Unclear or Multifactorial Mechanisms', 'Group 5 PH with unclear/multifactorial mechanisms', 'etiologic_subtype_taxonomy',
     'Group 5 PH has unclear or multifactorial mechanisms associated with hematological/systemic/metabolic disorders, chronic renal failure with or without dialysis, pulmonary tumor thrombotic microangiopathy, or fibrosing mediastinitis. Any one listed disease does not establish PH.',
     'group5_PH := PH AND mechanism(unclear OR multifactorial); ASSOCIATED_SUBTYPES(hematologic,systemic,metabolic,chronic_renal_failure(with|without_dialysis),tumor_thrombotic_microangiopathy,fibrosing_mediastinitis)',
     'Classification in established PH; association strength not supplied', flat='lossy', complexity='nested_group')
non(x, 'The World Health Organization classifies pulmonary hypertension into 5 clinical groups', 'classification_metadata', 'The number of taxonomy groups is not a patient criterion cardinality.')

x = begin(8, 'Read all AFX material and incidental comparator diagnoses. Separate optional morphology/staining patterns from diagnosis of exclusion. Preserve exploratory nature of the Ras observation, nonspecific positive stains, sparse S100 and cytokeratin-loss exception.')
rule(x, 'atypical fibroxanthoma predilection for sun-exposed areas of the body', 'Atypical fibroxanthoma', 'site_risk_association',
     'AFX favors sun-exposed sites and is associated with xeroderma pigmentosum and Li-Fraumeni syndrome; these are not necessary conditions.',
     'AFX -> PREDILECTION(sun_exposed_site); ASSOCIATED_WITH(AFX,XP,Li_Fraumeni)',
     'Rare genetic correlations; weak etiologic/clinical context', complexity='association_set')
rule(x, 'mutations of H-Ras and K-Ras genes were present in malignant fibrous histiocytoma', 'Malignant fibrous histiocytoma', 'research_molecular_features',
     'One study found H-Ras/K-Ras mutations in MFH; this is a study-specific positive pattern, not a universally required panel.',
     'IN_ONE_STUDY(MFH -> observed(H_Ras_mutations,K_Ras_mutations))',
     'Single-study finding; mutation co-occurrence per individual unspecified', complexity='association_set')
rule(x, 'but not in atypical fibroxanthoma lesions', 'Atypical fibroxanthoma', 'research_negative_molecular_features',
     'The same study did not find those H-Ras/K-Ras mutations in AFX; source says this may assist future diagnosis, not that a positive Ras mutation categorically excludes AFX.',
     'IN_ONE_STUDY(AFX -> not_observed(H_Ras_mutations,K_Ras_mutations))',
     'Exploratory study-specific absence, not universal hard exclusion', complexity='association_set')
rule(x, 'Hematoxylin and eosin stains of atypical fibroxanthoma lesions show a dermally-based tumor', 'Atypical fibroxanthoma', 'histologic_features',
     'AFX has a dermal pleomorphic/spindled tumor with atypical mitoses; may occasionally extend into subcutis; giant cells/solar elastosis are often seen, and peripheral mixed inflammation may occur.',
     'FEATURE_SET(AFX; dermal_based,pleomorphism,atypical_mitoses,spindled); OCCASIONAL(subcutis_extension); OFTEN(giant_cells,solar_elastosis); MAY(peripheral_mixed_infiltrate)',
     'Different frequency modifiers must remain attached to features', complexity='association_set')
rule(x, 'spindle cell squamous cell carcinoma variants (on the differential diagnosis) connect with the epidermis and show signs of keratinization', 'Spindle cell squamous cell carcinoma', 'histologic_features',
     'Spindle SCC variants connect with epidermis and exhibit keratinization, as comparative histologic features versus dermal AFX; no sufficient panel is declared.',
     'spindle_SCC -> FEATURE_SET(epidermal_connection,keratinization)',
     'Comparative histology', complexity='association_set')
rule(x, 'it is considered a diagnosis of exclusion histologically', 'Atypical fibroxanthoma', 'exclusion_based_diagnostic_process',
     'AFX is histologically a diagnosis of exclusion because positive stains are nonspecific. IHC is required to exclude competing neoplasms including spindloid SCC, melanoma and undifferentiated pleomorphic sarcoma; the named list is illustrative, not a complete sufficient negative panel.',
     'histologic_AFX_diagnosis REQUIRES exclusion_of(competing_neoplasms,using_IHC); competing_neoplasms INCLUDE SCC,melanoma,UPS; NOT_SUFFICIENT(excluding_only_named_examples)',
     'Open-ended differential domain; group-level necessity pertains to adequate exclusion, not any single negative stain', flat='impossible', complexity='nested_group')
rule(x, 'non-specific stains, including a cluster of differentiation 10 (CD10), p53, S100A6, vimentin, and procollagen-1', 'Atypical fibroxanthoma', 'nonspecific_marker_features',
     'AFX may stain positively for the named nonspecific stains; the list cannot independently confirm AFX or require every marker.',
     'NONSPECIFIC_POSITIVE_STAIN_ASSOCIATIONS(AFX; CD10,p53,S100A6,vimentin,procollagen1)',
     'Nonspecificity explicit; source list not a cardinality criterion', complexity='association_set')
rule(x, 'atypical fibroxanthoma stains negative for HMB-45, p40', 'Atypical fibroxanthoma', 'negative_marker_features',
     'AFX stains negative for HMB45, p40, desmin, pan-cytokeratin and CD31, with sparse rather than categorically absent S100 staining; this pattern may help differentiate from melanoma.',
     'NEGATIVE_STAIN_FEATURES(AFX; HMB45,p40,desmin,pan_cytokeratin,CD31); SPARSE_STAIN(S100); MAY_ASSIST_DIFFERENTIATION(AFX,melanoma)',
     'Sparse S100 must not become S100-negative; no standalone sufficient stain panel', complexity='association_set')
rule(x, 'p40 (often positive in squamous cell carcinoma)', 'Squamous cell carcinoma', 'marker_feature',
     'p40 is often positive in SCC; it is not always positive or a necessary SCC marker.',
     'SCC -> OFTEN(p40_positive)', 'Incidental comparator target')
rule(x, 'poorly differentiated sarcomatoid carcinomas may lose cytokeratin expression', 'Poorly differentiated sarcomatoid carcinoma', 'marker_exception',
     'Poorly differentiated sarcomatoid carcinoma may lose cytokeratin expression; a negative cytokeratin stain cannot be converted into guaranteed carcinoma exclusion.',
     'poorly_differentiated_sarcomatoid_carcinoma -> MAY(cytokeratin_expression_loss)',
     'Subtype-specific exception', complexity='scoped_rule')
rule(x, 'pigmented atypical fibroxanthoma due to hemosiderin deposit and not actual melanin pigment', 'Pigmented atypical fibroxanthoma', 'causal_feature_definition',
     'Pigmentation in the named AFX variant is due to hemosiderin rather than actual melanin; pigment identity and causal binding are part of the distinction.',
     'pigmented_AFX -> pigmentation_due_to(hemosiderin) AND NOT(pigmentation_due_to(actual_melanin))',
     'AFX variant; causally bound pigment exclusion, not blanket absence of any melanin in specimen', flat='lossy', complexity='scoped_rule')
non(x, 'The pathophysiology of atypical fibroxanthomas is poorly characterized.', 'mechanism', 'Mechanistic uncertainty and UV-repair/p53 causal explanations are not independent diagnostic criteria beyond explicitly recorded observed features.')
non(x, 'UV-induced pyrimidine dimers in atypical fibroxanthoma lesions and mutations in the tumor suppressor gene p53', 'mechanistic_cell_observation', 'UV dimers and p53 mutations appear only as support for the UV pathogenesis explanation here. Unlike the following explicitly diagnostic Ras comparison, this sentence does not supply a diagnostic phenotype/interpretation.')
non(x, 'various cytokeratin stains should be used', 'workup', 'The recommendation to use multiple stains is management of a test limitation, not a threshold rule.')
non(x, 'granular cell atypical fibroxanthoma, sclerotic atypical fibroxanthoma', 'taxonomic_names_only', 'Remaining variant names provide no defining observations or diagnostic effects; not one rule per name.')

x = begin(9, 'Read all three management/outcomes paragraphs. Disease-on-biopsy antecedents presuppose a biopsy interpretation; they do not state novel histologic criteria. No operational disease rule is present.')
non(x, 'an accurate history and physical should be reported to the pathologist', 'workup_communication', 'History/staining recommendations do not give diagnostic findings.')
non(x, 'Should a cutaneous vascular malignancy such as angiosarcoma be seen on biopsy', 'treatment_referral', 'A diagnosis already seen on biopsy triggers oncology referral; not a new rule that any biopsy diagnoses angiosarcoma.')
non(x, 'Should a Kaposi sarcoma be seen on biopsy', 'treatment_branch', 'HIV status chooses care/referral and HAART, not whether the biopsy diagnosis exists.')
non(x, 'If Kaposi sarcoma is seen in the mucosal lining of the mouth', 'workup_branch', 'Oral KS warrants GI investigation; it does not imply gastrointestinal lesions are already present.')
non(x, 'The outcomes of cutaneous vascular malignancies of the head and neck depend', 'prognosis', 'Metastasis/outcomes and team-care recommendations are non-target.')

x = begin(10, 'Read all three disease paragraphs. One weak phenotype set per independent disease; shape alternatives and optional sites are not AND or all-required groups.')
rule(x, 'Mucosal melanomas are macular or nodular lesions with pigmented brown-to-black coloration.', 'Oral mucosal melanoma', 'descriptive_features',
     'Mucosal melanomas can be macular or nodular, brown-to-black pigmented, and most oral tumors measure 2–6 cm. The usual size range is not an exclusion boundary.',
     'oral_mucosal_melanoma -> FEATURE_SET(macular_OR_nodular,brown_to_black_pigment); MOST(size_cm IN [2,6])',
     'Size claim limited to oral cavity; most rather than all', complexity='association_set')
rule(x, 'Kaposi sarcoma presents with focal or widespread violaceous-brown patches, papules, plaques, or exophytic nodules.', 'Kaposi sarcoma', 'descriptive_features',
     'KS has focal or widespread violaceous-brown patches/papules/plaques/exophytic nodules and can affect mucosa, skin, nodes or viscera; alternatives are not a required joint panel.',
     'KS -> FEATURE_ALTERNATIVES(distribution=focal|widespread,morphology=patch|papule|plaque|exophytic_nodule,color=violaceous_brown); MAY_SITE(mucosa,skin,node,viscera)',
     'Possible morphology/sites', complexity='association_set')
rule(x, 'NHL often presents as a painless, submucosal mass', 'Non-Hodgkin lymphoma of the palate', 'descriptive_features',
     'Palatal NHL often presents as painless submucosal mass at the hard/soft palate junction, without ulceration and with cervical nodes. The whole pattern is typical rather than mandatory/sufficient.',
     'palatal_NHL -> OFTEN_PATTERN(painless,submucosal_mass,hard_soft_palate_junction,no_ulceration,cervical_lymphadenopathy)',
     'Palatal presentation; often', complexity='association_set')

x = begin(11, 'Read complete endothelin pathophysiology extract. Count the explicit female-predominance association; exclude molecule-to-disease mechanisms and differential drug response as non-diagnostic.')
rule(x, 'pulmonary artery hypertension (PAH) is a predominantly female disease', 'Pulmonary arterial hypertension', 'population_association',
     'PAH predominates among females; male sex does not exclude it.',
     'PAH -> MORE_PREVALENT_IN(females)', 'Population tendency; no age/sex threshold')
non(x, 'established associations with endothelin as a part of their pathophysiology', 'mechanism', 'Listing PH, HF, post-menopausal hypertension, preeclampsia, ovarian cancer and kidney disease as endothelin-mediated does not establish a diagnostic endothelin measurement rule.')
non(x, 'increasing the vascular tone and promoting vascular remodeling', 'mechanism', 'ET-1 tone/remodeling causal mechanism without diagnostic test interpretation.')
non(x, 'better response in women compared to that of men', 'treatment_response', 'Sex-specific drug efficacy does not make response a sufficient/necessary diagnosis.')

x = begin(12, 'Read complete corneal-pump/FED pathophysiology window. Generic physiology/causal theories and the enzyme observation used only to support mitochondrial mechanism are non-target. No diagnostic phenotype/test interpretation is supplied, so this is a retained zero-rule window.')
non(x, 'Endothelial cells in FED exhibit decreased cytochrome oxidase activity, particularly in areas of corneal edema.', 'mechanistic_cell_observation', 'This cellular finding is used solely to support a mitochondrial ATP mechanism, without a diagnostic phenotype, specificity claim or diagnostic assay interpretation.')
non(x, 'Corneal transparency depends on maintaining stromal hydration below 3.5 mg of water per mg of dry tissue.', 'physiology', 'The hydration limit concerns corneal transparency, not a 3.5 threshold defining FED.')
non(x, 'When endothelial function is compromised', 'generic_mechanism', 'Generic pump failure causing edema/hazy vision is not stated to distinguish FED from other causes.')
non(x, 'several proposed mechanisms, including channelopathies, oxidative stress, apoptosis, and epithelial-mesenchymal transition', 'mechanism', 'Proposed pathways/genetic pump dysfunction and downstream ATP explanations are not independent diagnostic rules.')

x = begin(13, 'Read entire overlapping textbook window. Duplicate text is counted once. Keep conditional site/age/subtype priors; historical subtype proportions are a single descriptive distribution. The final GIST sentence is truncated before making a determinate claim.')
rule(x, 'Sarcomas are a heterogeneous group of neoplasms that arise predominantly from cells of the embryonic mesoderm.', 'Sarcoma', 'definition_origin',
     'Sarcomas are heterogeneous neoplasms predominantly arising from embryonic mesoderm-derived cells; predominantly must not become universally necessary.',
     'sarcoma -> neoplasm AND PREDOMINANT_ORIGIN(embryonic_mesoderm)', 'Predominantly, not all', complexity='association_set')
rule(x, 'Ewing’s sarcoma/peripheral primitive neuroectodermal tumor, which can occur either in the bone or in the soft tissues.', 'Ewing sarcoma / peripheral primitive neuroectodermal tumor', 'site_features',
     'This entity can occur in bone or soft tissue; neither site alone is required.',
     'Ewing_peripheral_PNET -> MAY_SITE(bone OR soft_tissue)', 'Anatomic alternatives', complexity='association_set')
rule(x, 'Most primary soft tissue sarco-mas originate in an extremity (50–60%)', 'Primary soft tissue sarcoma', 'site_distribution',
     'Primary STS usually arises in extremity (50–60%); other reported common sites are trunk (19%), retroperitoneum (15%), and head/neck (9%). These are descriptive site frequencies, not thresholds applied to an individual.',
     'SITE_DISTRIBUTION(primary_STS; extremity=50_to_60_percent,trunk=19_percent,retroperitoneum=15_percent,head_neck=9_percent)',
     'Primary soft tissue sarcoma; retain approximate source frequencies without requiring their sum to equal 100', flat='lossy', complexity='association_set')
rule(x, 'Historically, the most common subtypes in adults (excluding Kaposi’s sarcoma)', 'Adult soft tissue sarcoma subtype distribution', 'historical_subtype_distribution',
     'Historical adult STS subtype frequencies, excluding KS, are MFH 28%, liposarcoma 15%, leiomyosarcoma 12%, synovial sarcoma 10%, and malignant peripheral nerve sheath tumor 6%. This is one scoped distribution, not sufficient age-to-subtype diagnosis.',
     'HISTORICAL_DISTRIBUTION(subtype | adult_STS AND not_KS; MFH=.28,liposarcoma=.15,leiomyosarcoma=.12,synovial_sarcoma=.10,MPNST=.06)',
     'Historical adults; excludes KS; repeated overlap counted once', flat='lossy', complexity='association_set',
     notes='Joint distribution unit; classify as nonrigid descriptive information rather than five rigid rules.')
rule(x, 'Today, malignant fibrous histiocytoma is classified as either', 'Historical malignant fibrous histiocytoma label', 'classification_redefinition',
     'The historical MFH label is reclassified, using differentiation/genetics, into leiomyosarcoma, pleomorphic undifferentiated sarcoma, myxofibrosarcoma or dedifferentiated liposarcoma. This does not make these four entities synonymous or interchangeable.',
     'RECLASSIFY(historical_MFH,one_of(leiomyosarcoma,pleomorphic_undifferentiated_sarcoma,myxofibrosarcoma,dedifferentiated_liposarcoma),by=cell_differentiation_and_genetics)',
     'Historical classification mapping; actual subtype-selection predicates absent', flat='impossible', complexity='scoped_rule')
rule(x, 'Embryonal/alveolar rhabdomyosarcomas are the most common soft tissue sarcomas of childhood', 'Embryonal/alveolar rhabdomyosarcoma', 'age_association',
     'Embryonal/alveolar RMS are the most common childhood soft tissue sarcomas; this does not exclude adults or make childhood sufficient.',
     'childhood_STS -> MOST_COMMON_SUBTYPES(embryonal_RMS,alveolar_RMS)',
     'Conditional on childhood soft tissue sarcoma', complexity='association_set')
rule(x, 'pleomorphic rhabdomyosar-coma occurs predominantly in adults', 'Pleomorphic rhabdomyosarcoma', 'age_association',
     'Pleomorphic RMS occurs predominantly in adults and should not be conflated with pediatric RMS biology based on the shared name.',
     'pleomorphic_RMS -> PREDOMINANT_AGE(adult); not_equivalent_biology(pediatric_RMS)',
     'Predominantly, not exclusive adult age', complexity='association_set')
non(x, 'other types of sarcoma include bone sarcomas', 'taxonomic_names_only', 'Bone subtype names supply no specific distinguishing diagnostic criteria; Ewing site statement is separately counted.')
non(x, 'The anatomic site of a primary sarcoma influ-ences treatment and outcome.', 'treatment_prognosis', 'Multimodality treatment, recurrence/survival and fatal metastatic outcomes are not diagnosis conditions.')
non(x, 'approximately 11,280 new cases of soft tissue sarcoma were diagnosed', 'population_burden', 'Absolute incidence, mortality and calendar trends lack patient-level diagnostic scope.')
non(x, 'gastrointestinal stromal tumors (GISTs) likely account', 'truncated_nonclaim', 'The window ends before saying what GISTs account for; do not invent a source rule.')

x = begin(14, 'Read entire fragment. Opening differentiator is source-truncated and stays ambiguous. Do not turn the severe-pain symptom list into necessary all-of epidural-abscess criteria; retain the endocarditis counterexample and source/etiology patterns.')
rule(x, 'bodies is one of the features that differentiates infectious from neoplastic diseases of the spine.',
     'Infectious versus neoplastic spinal disease', 'truncated_differential',
     'A missing feature involving bodies differentiates infectious from neoplastic disease, but the affected structure/action and diagnostic direction are absent from this window.',
     'UNKNOWN_FEATURE(...bodies) -> differentiates(infectious_spinal,neoplastic_spinal)',
     'Sentence begins mid-clause; source window insufficient', status='ambiguous_source', flat='ambiguous',
     notes='Do not supply spared/preserved/destroyed vertebral bodies from outside knowledge.')
rule(x, 'A paravertebral mass is often found, indicating an abscess', 'Paravertebral abscess', 'support',
     'In the spinal-infection discussion, a paravertebral mass often indicates abscess; it is not asserted universally sufficient.',
     'spinal_infection_context AND paravertebral_mass -> SUPPORTS(abscess)',
     'Context inherited from local spinal-infection discussion', complexity='scoped_rule')
rule(x, 'particularly in the case of tuberculosis, drain spontaneously at sites quite remote from the vertebral column',
     'Spinal/paravertebral tuberculosis-associated abscess', 'descriptive_feature',
     'The abscess may spontaneously drain remotely from the spine, particularly with tuberculosis; remote drainage is optional.',
     'spinal_abscess -> MAY(remote_spontaneous_drainage); particularly_associated(TB)',
     'Abscess referent; optional pattern', complexity='scoped_rule')
rule(x, 'subacute bacterial endocarditis who complained of severe midline thoracic and lumbar back pain but had no evident infection of the spine',
     'Subacute bacterial endocarditis', 'observed_symptom_counterexample',
     'Patients with subacute bacterial endocarditis have been observed with severe midline thoracolumbar pain despite no evident spinal infection. Severe back pain does not imply spinal infection in every case.',
     'OBSERVED(SBE AND severe_midline_thoracolumbar_pain AND no_evident_spinal_infection)',
     'Authors case observations; not a universal SBE phenotype', complexity='association_set')
rule(x, 'Tuberculous spinal infection and the resultant kyphotic deformity (Pott disease)',
     'Pott disease', 'causal_composite_definition',
     'The passage names tuberculous spinal infection and its resultant kyphotic deformity as Pott disease. Preserve tuberculosis, spinal site and causal deformity relationship, without replacing it by any kyphosis.',
     'TEXTUAL_DEFINITION(Pott_disease; tuberculous_spinal_infection AND resultant(kyphotic_deformity))',
     'Definition as worded in this source; not an externally completed operational criterion', flat='lossy', complexity='scoped_rule')
rule(x, 'Most often this is caused by staphylococcal infection', 'Spinal epidural abscess', 'etiologic_association',
     'Spinal epidural abscess is most often staphylococcal, but other/unknown sources are possible.',
     'spinal_epidural_abscess -> MOST_OFTEN_PATHOGEN(staphylococcus)',
     'This refers to preceding spinal epidural abscess; no exclusivity')
rule(x, 'Another important avenue of infection is the intravenous self-administration of drugs and use of contaminated needles.',
     'Spinal epidural abscess', 'risk_source_associations',
     'Source contexts include a septic focus or osteomyelitic lesion, injection drug use/contaminated needles, and rarely lumbar puncture, epidural injection or laminectomy; in some cases no source is ascertainable.',
     'POSSIBLE_SOURCES(spinal_epidural_abscess; septic_focus,osteomyelitis,injection_drugs_or_contaminated_needles,RARE(lumbar_puncture,epidural_injection,laminectomy),unknown)',
     'Unknown source permitted; cannot require procedure or skin focus', complexity='association_set')
rule(x, 'The main symptoms are low-grade fever, leukocytosis, and persistent and severe localized pain',
     'Spinal epidural abscess', 'descriptive_features',
     'Main features are low-grade fever, leukocytosis and persistent severe localized pain worsened by percussion/pressure over vertebral spines; radicular radiation may additionally occur. They form a descriptive set, not a necessary or sufficient all-of criterion.',
     'FEATURE_SET(spinal_epidural_abscess; low_grade_fever,leukocytosis,persistent_severe_local_pain[worse_with_percussion_or_pressure]); MAY(radicular_radiation)',
     'Pain modifiers belong to pain; optional radiation', complexity='association_set')
non(x, 'usually necessitates urgent surgical treatment', 'treatment_prognosis', 'Urgent treatment and paraplegia/death consequences do not define the diagnostic condition.')
non(x, 'These symptoms mandate immediate investigation by MRI', 'workup', 'Symptoms trigger investigation; they are not sufficient confirmation.')

x = begin(15, 'Read donor/recipient screening extract including repeated overlap. Count explicit transmission/exposure information as weak disease-specific etiologic context; ordering screens and unspecified serology reliability remain non-target. The initial list is already truncated.')
rule(x, 'Creutzfeldt-Jakob disease has been transmitted through corneal transplants.', 'Creutzfeldt-Jakob disease', 'transmission_exposure_association',
     'Corneal transplantation is a documented CJD transmission route; this does not establish CJD in a transplant recipient. Transfused-blood transmission of ordinary CJD is stated to be unknown.',
     'DOCUMENTED_ROUTE(CJD,corneal_transplant); UNKNOWN_ROUTE(CJD,transfused_blood)',
     'Ordinary CJD; repeated source sentence counted once', flat='lossy', complexity='association_set')
rule(x, 'Variant Creutzfeldt-Jakob disease can be transmitted with transfused non-leukodepleted blood', 'Variant Creutzfeldt-Jakob disease', 'transmission_exposure_association',
     'vCJD can be transmitted by non-leukodepleted transfused blood; the risk to transplant recipients is described as theoretical, not a proven organ-transplant route.',
     'POSSIBLE_ROUTE(vCJD,transfused_non_leukodepleted_blood); THEORETICAL_RISK(vCJD,transplant_recipient)',
     'Variant CJD; preserve blood-product qualifier and theoretical transplant scope', flat='lossy', complexity='association_set')
non(x, 'herpes-virus (KSHV); acute infection with hepatitis A virus;', 'truncated_screening_list', 'Opening donor-screening list lacks its governing clause; no result-to-diagnosis rule.')
non(x, 'Donors should be screened, when relevant', 'workup', 'Named viruses/parasites, chest radiograph review and TB tests are recommendations to investigate, without supplied result criteria.')
non(x, 'An investigation of the donor’s dietary habits', 'workup', 'Diet/occupation/travel history triggers additional testing but no named exposure-to-pathogen diagnostic rule is supplied.')
non(x, 'serologic testing of the recipient may prove less reliable than usual', 'unspecified_test_caveat', 'Immune dysfunction affects unspecified serology reliability. No explicitly named disease target, direction, assay or exclusion rule is given.')

x = begin(16, 'Read full flattened WikEM navigation/list window. Do not reconstruct unobserved indentation from medical knowledge. Pure headings, condition names and aliases are navigation, not diagnostic criteria. Two potentially diagnostic relationships are retained as source-ambiguous rather than forced into targets.')
rule(x, "Vincent's angina - tonsillitis and pharyngitis", "Vincent's angina", 'ambiguous_gloss',
     'A dash gloss connects Vincent angina with tonsillitis and pharyngitis, but the list does not explain whether this is a definition, presentation or linked category; it cannot safely be made a sufficient conjunction.',
     'GLOSS_RELATION_UNSPECIFIED(Vincent_angina; tonsillitis,pharyngitis)',
     'Flattened navigation list without diagnostic prose', status='ambiguous_source', flat='ambiguous', complexity='association_set')
rule(x, 'Gingival hyperplasia\n Phenytoin\n Cyclosporine\n Nifedipine , Amlodipine\n Leukemia', 'Gingival hyperplasia / listed drugs / leukemia', 'ambiguous_list_hierarchy',
     'The listed drugs and leukemia follow gingival hyperplasia, but flattening removes whether they are child causes/associations or sibling navigation entries. No causal/diagnostic direction can be safely fixed from this window.',
     'UNRESOLVED_HIERARCHY(gingival_hyperplasia; phenytoin,cyclosporine,nifedipine,amlodipine,leukemia)',
     'Indentation/parenthood absent; no external medical reconstruction', status='ambiguous_source', flat='ambiguous', complexity='nested_group')
non(x, 'Odontogenic Infections', 'navigation_taxonomy', 'Infection and trauma lists name entities and synonyms without patient findings or diagnostic effect. Pulpitis (dental caries) is not silently accepted as a medically exact synonym.')
non(x, 'Maxillofacial Trauma', 'navigation_taxonomy', 'Anatomic headings and related trauma links do not diagnose any listed lesion.')

assert len(inventory) == 16
for item, source in zip(inventory, sources):
    assert item['sample_id'] == source['sample_id']
    for r in item['rules']:
        assert r['source_anchor'] in source['text'], (r['rule_id'], r['source_anchor'])
    for row in item['non_target_source']:
        assert row['anchor'] in source['text'], (item['sample_id'], row['anchor'])
(BASE / 'source_inventory_3.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({x['sample_id']: len(x['rules']) for x in inventory}, indent=2))
print('total_rules', sum(len(x['rules']) for x in inventory))
print('ambiguous', sum(r['source_status']=='ambiguous_source' for x in inventory for r in x['rules']))
