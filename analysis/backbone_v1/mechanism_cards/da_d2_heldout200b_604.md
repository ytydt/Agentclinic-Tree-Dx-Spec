# DA / d2_heldout200b / case 604

- **gold**: Lymphomatoid Granulomatosis (LYG) Grade 3 (EBV+ B-cell lymphoma)
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 64-year-old man with a medical history of chronic obstructive pulmonary disease, hypothyroidism, and hypertension presented with a 1-month onset of worsening dyspnea and unintentional 10-lb weight loss.

Patient was afebrile, had a blood pressure of 100/60 mm Hg, respiratory rate of 42/min, heart rate of 110 beats/min, and oxygen saturation 77% on room air. Physical examination revealed bilateral vesicular breathing with diffuse rhonchi on lung auscultation; no lymphadenopathy was identified.

- Laboratory Tests:    * Hemoglobin: 11.2 g/dL    * Leukocyte: 10.2 ×10³/mcL    * Platelets: 410 ×10³/mcL    * C-reactive protein: 23.4 mg/dL    * Lactate dehydrogenase: 280 EnzU/L    * Other tests: Respiratory viral panel, SARS-CoV-2 PCR, fungal pneumonia work-up were negative. QuantiFERON TB test, hepatitis panel, and HIV were nonreactive.  - Imaging Studies:    * CT Chest: Showed innumerable ill-defined nodular opacities within both lungs, air bronchogram pattern, superimposed pneumonia, and an ill-defined 6.3 × 5.8-cm right hilar mass narrowing the right central bronchi    * CT Abdomen/Pelvis: Showed splenomegaly    * PET scan: Showed marked FDG-avid uptake at the lung lesion, right nec…

## Options
- A: Pulmonary lymphoma
- B: Diffuse large B-cell lymphoma (non-Hodgkin lymphoma)
- C: Granulomatosis with Polyangiitis (Wegener’s Granulomatosis)
- D: Lymphomatoid Granulomatosis (LYG) Grade 3 (EBV+ B-cell lymphoma) **←gold**

## Backbone e7

- S2 n=54 gold_rank=1
  - clusters: gold=1 near=16 other=37
- S3 shortlist (5):
  - [near] Diffuse large B-cell lymphoma
  - [gold] Lymphomatoid granulomatosis
  - [near] Primary pulmonary lymphoma
  - [near] Anaplastic large cell lymphoma
  - [near] Angioimmunoblastic T-cell lymphoma
    - why_kept(Diffuse large B-cell lymphoma): Patchy areas of large atypical lymphoid cells with necrosis on CT-guided lung biopsy, consistent with lymphoma
    - why_kept(Lymphomatoid granulomatosis): Infiltration of lung parenchyma by malignant neoplasm with mixed inflammatory infiltrate and vascular involvement on VATS wedge resection
    - why_kept(Primary pulmonary lymphoma): Marked FDG-avid uptake at the lung lesion on PET scan, suggestive of malignant process
    - why_kept(Anaplastic large cell lymphoma): Presence of large atypical lymphoid cells with necrosis on CT-guided lung biopsy, consistent with high-grade lymphoma
    - why_kept(Angioimmunoblastic T-cell lymphoma): Systemic inflammation and weight loss, with lymph node involvement on PET scan, raising suspicion for T-cell lymphoma
- S4 champion: **Diffuse large B-cell lymphoma** cluster=near jaccard=0.22
- S4 rationale: The patient's presentation with worsening dyspnea, unintentional weight loss, and a lung biopsy showing large atypical lymphoid cells with necrosis, along with systemic symptoms and imaging findings of a hilar mass and splenomegaly, are most consistent with diffuse large B-cell lymphoma, a common and aggressive type of non-Hodgkin lymphoma.
- S4 rejected:
  - [gold] Lymphomatoid granulomatosis: While it can present with lung involvement and systemic symptoms, the biopsy findings and imaging studies do not specifically suggest this diagnosis.
  - [near] Primary pulmonary lymphoma: This diagnosis typically presents with more localized lung involvement and does not usually have the systemic symptoms and widespread disease seen in this patient.
  - [near] Anaplastic large cell lymphoma: The biopsy findings do not specifically mention the characteristic hallmarks of anaplastic large cell lymphoma, such as CD30 positivity or a uniform population of large anaplastic cells.
  - [near] Angioimmunoblastic T-cell lymphoma: This diagnosis typically presents with a distinct clinical picture that includes fever, rash, and lymphadenopathy, which are not prominent in this patient's presentation.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Lymphoma', 'Lung Cancer']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lymphoma', 'Lung Cancer', 'Sarcoidosis', 'Tuberculosis', 'Pneumonia', 'Lymphoma', 'Lung Cancer', 'Sarcoidosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lymphoma', 'Lung Cancer']
- diagnose: ['Lymphoma', 'Lung Cancer']
- queries: ['differential diagnosis for worsening dyspnea and weight loss in a patient with COPD', 'causes of ill-defined nodular opacities on CT chest', 'diagnosis of atypical lymphoid cells with necrosis on lung biopsy', 'association between splenomegaly and lung malignancy']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

