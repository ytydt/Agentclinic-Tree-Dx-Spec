# DA / d2_heldout200b / case 477

- **gold**: Multisystem Inflammatory Syndrome in Children (MIS-C) with COVID-19 associated acute ischemic stroke
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 9-year-old girl presented with:- High-grade fever for 14 days- Throbbing frontal headache- Vomiting - Progressive weakness on the right side of body for 5 daysPast medical history: No significant history mentionedCurrent status: SARS-CoV-2 RNA was detected on nasopharyngeal swab by RT-PCR on presentation

On admission:- Bilateral non-purulent conjunctivitis- Axillary temperature: 39.4°C- Blood oxygen saturation: 98%- Heart rate: 64 bpm- Tachypnoea- Blood pressure: 132/102 mm Hg- Glasgow Coma Score: 11 (E3, V2, M6)- Upper motor neuron type right-sided seventh cranial-nerve palsy- Complete hemiplegia- Brisk deep tendon reflexes- Extensor plantar response on the right- Normal pupils- No signs of meningeal irritation- Pediatric qSOFA score: 2/3

Laboratory Tests:- Haemoglobin: 11.3 g/dL- Platelets: 2.5 ×10³ cells/mm³- Leucocyte count: 6980 cells/mm³- Serum bilirubin (total): 0.52 mg/dL- Aspartate aminotransferase: 53.4 IU/L- Alanine aminotransferase: 126.1 IU/L- Triglycerides: 416.6 mg/dL- CRP: 64.9 mg/L- ESR: 50 mm/h- D-dimer: 3.57 μg/mL- Ferritin: 614.6 ng/LImaging Studies:1. Chest X-ray:   Title: Chest radiograph   Description: Bilateral ground-glass opacification and reticulonodu…

## Options
- A: COVID-19 associated multisystem inflammatory syndrome in children (MIS-C) with neurological involvement
- B: Kawasaki disease
- C: Multisystem Inflammatory Syndrome in Children (MIS-C) with COVID-19 associated acute ischemic stroke **←gold**
- D: COVID-19–associated cerebral vasculitis (ischemic stroke)

## Backbone e7

- S2 n=56 gold_rank=None
  - clusters: gold=0 near=11 other=45
- S3 shortlist (5):
  - [near] Acute Disseminated Encephalomyelitis
  - [other] Cerebral Vasculitis
  - [other] Rasmussen Encephalitis
  - [other] Herpes Simplex Encephalitis
  - [near] Acute Hemorrhagic Leukoencephalitis
    - why_kept(Acute Disseminated Encephalomyelitis): Matches the acute neurological syndrome with fever and focal neurological deficits, and is consistent with the CSF examination showing pleocytosis with slightly increased protein
    - why_kept(Cerebral Vasculitis): Explains the multifocal smooth stenosis of intracranial arteries and the presence of fever and focal neurological deficits
    - why_kept(Rasmussen Encephalitis): Consistent with the progressive weakness on one side of the body, seizures, and the presence of fever
    - why_kept(Herpes Simplex Encephalitis): A possible cause of acute neurological syndrome with fever, and the presence of focal neurological deficits and CSF pleocytosis
    - why_kept(Acute Hemorrhagic Leukoencephalitis): Could explain the acute onset of neurological symptoms, fever, and the presence of multifocal discrete and confluent hypodensities on the brain CT
- S4 champion: **Acute Disseminated Encephalomyelitis** cluster=near jaccard=0.08
- S4 rationale: The patient's symptoms, including high-grade fever, throbbing headache, vomiting, progressive weakness on one side of the body, and the presence of pleocytosis with slightly increased protein in the CSF, along with multifocal discrete and confluent hypodensities in the brain CT, are consistent with Acute Disseminated Encephalomyelitis (ADEM), especially given the recent SARS-CoV-2 infection which can trigger ADEM.
- S4 rejected:
  - [other] Cerebral Vasculitis: While the patient has multifocal smooth stenosis of intracranial arteries, the overall clinical and imaging findings are more suggestive of an inflammatory process like ADEM rather than a primary vasculitis.
  - [other] Rasmussen Encephalitis: Rasmussen Encephalitis typically presents with more chronic and progressive symptoms, often with a history of seizures, which are not mentioned in the vignette.
  - [other] Herpes Simplex Encephalitis: The CSF examination did not specifically indicate the presence of herpes simplex virus, and the imaging findings, although suggestive of encephalitis, do not specifically point towards herpes simplex encephalitis.
  - [near] Acute Hemorrhagic Leukoencephalitis: The patient's imaging studies do not show the characteristic hemorrhagic components that are typical of Acute Hemorrhagic Leukoencephalitis.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Cerebral Vasculitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Cerebral Vasculitis', 'Acute Hemorrhagic Leukoencephalitis', 'Stroke due to COVID-19', 'Central Nervous System Vasculitis', 'Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Cerebral Vasculitis', 'Acute Hemorrhagic Leukoencephalitis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['COVID-19 associated cerebral vasculitis', 'Moyamoya syndrome']
- diagnose: ['COVID-19 associated cerebral vasculitis', 'Moyamoya syndrome']
- queries: ['Moyamoya disease in children', 'COVID-19 associated vasculitis', 'Pediatric cerebral vasculitis', 'Multifocal cerebral vasculopathy']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

