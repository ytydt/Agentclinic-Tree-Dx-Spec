# DA / d2_heldout200b / case 631

- **gold**: Primary Cardiac Angiosarcoma
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 31-year-old active duty man with no significant medical history presented with:- One week of worsening fatigue- Dyspnea- Hemoptysis- Nausea- Ataxia- Acute-onset headache

Initial vital signs:- Blood pressure: 110/56 mm Hg- Heart rate: 104 beats/min- Respiratory rate: 29 breaths/min- Oxygen saturation: 83% to 87% on 6 L nasal cannulaPhysical findings:- Tachycardic- Shallow respirations- Diffuse crackles in the upper and lower lung fields

Laboratory Tests:- Hemoglobin: 9.3 g/dL (showing anemia)- Platelets: 81,000 mcL (showing thrombocytopenia)- Lactate dehydrogenase: 2764 U/L (markedly elevated)Imaging Studies:1. Chest Radiograph:- Diffuse nodular pulmonary opacities- Right medial lung base opacities- Enlarged cardiac silhouette2. CT Chest, Abdomen, and Pelvis with contrast:- 2.0-cm right atrial mass- 7.8-cm left adrenal mass- 3.8-cm pelvic mass- Multiple pulmonary nodules- Pleural effusion3. Head CT (without contrast):- 3.4 cm subacute hemorrhage within right parietal lobe- Incidental pulmonary emboli noted4. Transthoracic Echocardiogram:- Left ventricle: small and underfilled, ejection fraction 60% to 65%- Right atrial mass with prolapse across tricuspid valve- Trace tricuspid a…

## Options
- A: Primary Cardiac Angiosarcoma **←gold**
- B: Primary cardiac lymphoma
- C: Metastatic angiosarcoma with pulmonary and central nervous system involvement
- D: Metastatic melanoma

## Backbone e7

- S2 n=54 gold_rank=None
  - clusters: gold=0 near=2 other=52
- S3 shortlist (5):
  - [other] Intravascular lymphoma
  - [near] Angiosarcoma of the heart
  - [other] Epithelioid hemangioendothelioma
  - [other] Intravascular large B-cell lymphoma
  - [other] Kaposi's sarcoma with pulmonary involvement
    - why_kept(Intravascular lymphoma): Malignant cells lining vascular spaces and multi-organ involvement
    - why_kept(Angiosarcoma of the heart): Right atrial mass with prolapse across tricuspid valve and malignant cells on biopsy
    - why_kept(Epithelioid hemangioendothelioma): Malignant cells lining vascular spaces and involvement of multiple organs
    - why_kept(Intravascular large B-cell lymphoma): Malignant cells lining vascular spaces and acute onset of symptoms
    - why_kept(Kaposi's sarcoma with pulmonary involvement): Malignant cells and multi-organ involvement including pulmonary nodules
- S4 champion: **Intravascular large B-cell lymphoma** cluster=other jaccard=0.00
- S4 rationale: The presence of malignant cells lining vascular spaces on biopsy, along with symptoms such as worsening fatigue, dyspnea, hemoptysis, and markedly elevated lactate dehydrogenase, are consistent with intravascular large B-cell lymphoma, a rare and aggressive form of lymphoma that often presents with systemic symptoms and multi-organ involvement.
- S4 rejected:
  - [near] Angiosarcoma of the heart: While the cardiac mass is consistent with angiosarcoma, the biopsy findings of malignant cells lining vascular spaces and the presence of systemic symptoms are more suggestive of intravascular lymphoma.
  - [other] Epithelioid hemangioendothelioma: This is a rare vascular tumor that can present with similar symptoms, but the biopsy findings and the presence of a right atrial mass with prolapse across the tricuspid valve are more consistent with intravascular lymphoma.
  - [other] Intravascular lymphoma: This is a broader category that includes intravascular large B-cell lymphoma, but the specific diagnosis of intravascular large B-cell lymphoma is more precise and consistent with the biopsy findings and clinical presentation.
  - [other] Kaposi's sarcoma with pulmonary involvement: While Kaposi's sarcoma can present with pulmonary involvement and systemic symptoms, the biopsy findings of malignant cells lining vascular spaces and the presence of a right atrial mass are not typical of Kaposi's sarcoma.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Angiosarcoma', 'Choriocarcinoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Angiosarcoma', 'Choriocarcinoma', 'Lymphoma', 'Metastatic disease', "Kaposi's sarcoma", 'Angiosarcoma', 'Choriocarcinoma', 'Lymphoma']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Angiosarcoma', 'Metastatic disease']
- diagnose: ['Angiosarcoma', 'Metastatic disease']
- queries: ['hemoptysis and fatigue and hemoglobin 9.3', 'elevated lactate dehydrogenase and thrombocytopenia', 'right atrial mass and pulmonary nodules', 'subacute hemorrhage and pulmonary emboli']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

