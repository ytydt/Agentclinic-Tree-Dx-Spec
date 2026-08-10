# DA / d2_heldout200b / case 605

- **gold**: Congenital Thrombotic Thrombocytopenic Purpura (cTTP)
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 25-year-old woman presented to her local emergency department with right-sided weakness, right-sided facial droop, left gaze deviation, and aphasia. She was last seen at baseline about 6 hours prior. Three years prior, she had experienced a similar event requiring mechanical thrombectomy, with the cause remaining unknown. Medical history included well-controlled hypertension, obesity, migraines, and recurrent immune thrombocytopenia in childhood. Current medications were aspirin, lisinopril, and atorvastatin. She had a history of tobacco use, which stopped after her first event. Family history was notable for a similar condition in her older sister in her early 20s.

Vital signs: Temperature 37.6°C, respiratory rate 14, heart rate 78 beats/min, blood pressure 179/98 mm Hg, body mass index 38.9 kg/m². Patient was alert but nonverbal and did not follow commands. Neurologic examination revealed left gaze preference, right facial droop, right upper- and lower-extremity weakness, and intact sensation throughout. Initial National Institutes of Health Stroke Scale score was 22. Cardiovascular, pulmonary, and abdominal examinations were unremarkable.

Laboratory Tests:- Leukocytes: 11.1 …

## Options
- A: Antiphospholipid syndrome
- B: Thrombotic Thrombocytopenic Purpura (TTP) **←gold**
- C: Acquired (immune) thrombotic thrombocytopenic purpura
- D: Congenital Thrombotic Thrombocytopenic Purpura (cTTP) **←gold**

## Backbone e7

- S2 n=49 gold_rank=12
  - clusters: gold=1 near=1 other=47
- S3 shortlist (5):
  - [other] Cardioembolic stroke
  - [other] Moyamoya disease
  - [other] Central nervous system vasculitis
  - [other] Antiphospholipid syndrome
  - [other] Takayasu arteritis
    - why_kept(Cardioembolic stroke): Patient has a history of similar event requiring mechanical thrombectomy and current presentation of acute onset of focal neurological deficits with evidence of cerebral infarction
    - why_kept(Moyamoya disease): Patient's age, presentation, and lack of traditional atherosclerotic risk factors make this a plausible diagnosis
    - why_kept(Central nervous system vasculitis): Patient's recurrent events and lack of clear atherosclerotic or cardioembolic source make this a possible diagnosis
    - why_kept(Antiphospholipid syndrome): Patient's history of recurrent thrombocytopenia and current thrombocytopenia make this a possible diagnosis
    - why_kept(Takayasu arteritis): Patient's age, sex, and presentation of stroke with no clear atherosclerotic source make this a possible diagnosis
- S4 champion: **Moyamoya disease** cluster=other jaccard=0.00
- S4 rationale: The patient's recurrent strokes at a young age, family history of a similar condition, and lack of traditional cardiovascular risk factors suggest a non-atherosclerotic cause, with Moyamoya disease being a strong candidate given its tendency to cause strokes in young adults and its familial occurrence
- S4 rejected:
  - [other] Cardioembolic stroke: The patient's age and lack of traditional cardiovascular risk factors make this less likely
  - [other] Central nervous system vasculitis: There is no clear evidence of inflammation or vasculitis on laboratory tests or imaging studies
  - [other] Antiphospholipid syndrome: The patient's history of recurrent immune thrombocytopenia and low platelet count could suggest an alternative thrombophilic condition, but the lack of other specific criteria for antiphospholipid syndrome makes this less likely
  - [other] Takayasu arteritis: The patient's lack of systemic symptoms such as fever, arthralgias, or abdominal pain, and the absence of specific findings on imaging studies, make this diagnosis less likely

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Ischemic Stroke']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Ischemic Stroke', 'Thromboembolic Event', 'Cerebral Vasculitis', 'Recurrent Arterial Ischemic Stroke', 'Thrombotic Thrombocytopenic Purpura (TTP)', 'Ischemic Stroke', 'Thromboembolic Event']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Stroke (Ischemic)']
- diagnose: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Stroke (Ischemic)']
- queries: ['Thrombotic thrombocytopenic purpura (TTP) diagnosis', 'Stroke in young adults', 'ADAMTS13 deficiency', 'Thrombectomy outcomes']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

