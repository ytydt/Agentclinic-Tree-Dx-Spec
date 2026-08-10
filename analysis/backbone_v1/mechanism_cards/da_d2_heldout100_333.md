# DA / d2_heldout100 / case 333

- **gold**: Rhombencephalitis caused by Listeria monocytogenes
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=0 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A woman in her early 30s with a 10-year history of treatment with various medications (glatiramer acetate, interferon beta, fingolimod, natalizumab, and most recently dimethyl fumarate for 3 years). No history of severe lymphocytopenia. At last outpatient visit, she had impaired extraocular movement and mild sinking of the right leg. A few months later, she developed dizziness and nausea. Five days after receiving methylprednisolone treatment, she presented with moderate tetraparesis, headache, fever, and neck stiffness. Prior to neurological symptoms, her entire family had experienced fever, nausea, vomiting, and diarrhea, recovering within 3 days, while the patient continued to have mild gastrointestinal symptoms.

Neurologic examination revealed:- Positive Romberg test- Impaired extraocular movement- Mild sinking of right leg at position test- Moderate tetraparesis- Neck stiffness- Fever

- Laboratory tests:  * Initial white blood cell count: 4900/μL (lymphocyte count: 1240/μL)  * Later white blood cell count: 18,000/μL (lymphocyte count: 780/μL)  * Cerebrospinal fluid analysis: Clear fluid, normal glucose level, increased protein level, 108 cells/mL (95% neutrophils)  * Cerebro…

## Options
- A: Bacterial meningitis (likely Listeria monocytogenes)
- B: Brainstem encephalitis (possibly viral or autoimmune)
- C: Streptococcus pneumoniae meningoencephalitis
- D: Rhombencephalitis caused by Listeria monocytogenes **←gold**

## Backbone e7

- S2 n=51 gold_rank=None
  - clusters: gold=0 near=1 other=50
- S3 shortlist (5):
  - [near] Listeria Meningitis
  - [other] Cryptococcal Meningitis
  - [other] Tuberculous Meningitis
  - [other] Brainstem Encephalitis
  - [other] Bickerstaff Brainstem Encephalitis
    - why_kept(Listeria Meningitis): Positive cerebrospinal fluid culture and signs of meningeal irritation
    - why_kept(Cryptococcal Meningitis): Increased protein level in cerebrospinal fluid and impaired extraocular movement
    - why_kept(Tuberculous Meningitis): Subacute neurological deterioration and signs of meningeal irritation
    - why_kept(Brainstem Encephalitis): Hyperintense lesion in the brainstem and cerebellum on MRI
    - why_kept(Bickerstaff Brainstem Encephalitis): Impaired extraocular movement and mild sinking of the right leg
- S4 champion: **Bickerstaff Brainstem Encephalitis** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms, including impaired extraocular movement, mild sinking of the right leg, dizziness, nausea, and moderate tetraparesis, are consistent with brainstem involvement. The positive Romberg test and the presence of a hyperintense lesion in the brainstem and cerebellum on MRI also support this diagnosis. Additionally, the patient's symptoms and MRI findings are more consistent with an inflammatory or autoimmune process, such as Bickerstaff Brainstem Encephalitis, rather than an infectious process like meningitis.
- S4 rejected:
  - [near] Listeria Meningitis: The patient's cerebrospinal fluid culture was positive, but the presence of a hyperintense lesion in the brainstem and cerebellum on MRI and the patient's symptoms are not typical of Listeria Meningitis
  - [other] Cryptococcal Meningitis: The patient's symptoms and laboratory results, including the cerebrospinal fluid analysis, do not suggest a fungal infection like Cryptococcal Meningitis
  - [other] Tuberculous Meningitis: The patient's symptoms and laboratory results, including the cerebrospinal fluid analysis, do not suggest a chronic infection like Tuberculous Meningitis
  - [other] Brainstem Encephalitis: While the patient's symptoms are consistent with brainstem involvement, Bickerstaff Brainstem Encephalitis is a more specific diagnosis that is supported by the patient's symptoms and MRI findings

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Brain abscess', 'Progressive multifocal leukoencephalopathy']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Progressive multifocal leukoencephalopathy', 'Multiple sclerosis', 'Acute disseminated encephalomyelitis', 'Brainstem encephalitis', 'Cerebral abscess', 'Brain abscess', 'Progressive multifocal leukoencephalopathy', 'Cerebral abscess']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Progressive Multifocal Leukoencephalopathy (PML)', 'Brainstem Encephalitis']
- diagnose: ['Progressive Multifocal Leukoencephalopathy (PML)', 'Brainstem Encephalitis']
- queries: ['progressive multifocal leukoencephalopathy vs brainstem encephalitis', 'multiple sclerosis treatment complications', 'dimethyl fumarate side effects', 'cerebrospinal fluid analysis in central nervous system infections']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=16 final_n=0
- final: []
- tree gold_cluster_n=0 final gold=False

