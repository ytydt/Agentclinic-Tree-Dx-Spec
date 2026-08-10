# MCR / mcr_v2 / case 170

- **gold**: T-cell lymphoblastic lymphoma
- **layer**: `e7_win_rank` · **layer_aphhm**: ``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 6-year-old girl presented with a 1-week history of dyspnea and pleuritic chest pain that was worse when supine, associated with orthopnea, mild agitation, and fever. Her parents also reported intermittent fever over the preceding 3 months. There was no significant past medical history and no known contact with COVID-19 patients. On examination, she was febrile, alert, and in mild respiratory distress. Lung auscultation was clear except for decreased breath sounds at the right lower zone. Cardiac examination revealed muffled heart sounds; peripheral pulses were normal. Vital signs: blood pressure 100/65 mm Hg, heart rate 120 beats/min, respiratory rate 30 breaths/min. Abdominal examination showed hepatomegaly.

Initial investigations included:
- Chest radiograph: mediastinal widening  
- ECG: sinus tachycardia with low-voltage QRS and electrical alternans  
- Laboratory studies: WBC 11.4×10^9/L, hemoglobin 12.6 g/dL, platelets 565×10^9/L, LDH 1061 U/L, CRP 66 mg/L, ESR 57 mm/h; electrolytes, renal and liver function tests, troponin I, and COVID-19 PCR were unremarkable.

Further evaluation with transthoracic echocardiography showed a large pericardial effusion without signs of tam…

## Backbone e7

- S2 n=49 gold_rank=33
  - clusters: gold=1 near=6 other=42
- S3 shortlist (5):
  - [near] Hodgkin lymphoma
  - [near] Non-Hodgkin lymphoma
  - [other] Thymoma
  - [other] Castleman disease
  - [gold] Lymphoblastic lymphoma
    - why_kept(Hodgkin lymphoma): Mediastinal mass and symptoms consistent with lymphoma
    - why_kept(Non-Hodgkin lymphoma): Mediastinal mass and systemic symptoms such as fever and weight loss
    - why_kept(Thymoma): Anterior mediastinal mass and pericardial effusion
    - why_kept(Castleman disease): Mediastinal mass and systemic inflammatory symptoms
    - why_kept(Lymphoblastic lymphoma): Mediastinal mass and symptoms consistent with aggressive lymphoma
- S4 champion: **Lymphoblastic lymphoma** cluster=gold jaccard=0.67
- S4 rationale: The presence of an anterior mediastinal mass, large pericardial effusion, and pleural effusions, along with systemic symptoms such as fever and hepatomegaly, are highly suggestive of lymphoblastic lymphoma, which is a type of non-Hodgkin lymphoma that often presents with a mediastinal mass and can cause pericardial and pleural effusions.
- S4 rejected:
  - [near] Hodgkin lymphoma: While Hodgkin lymphoma can also present with a mediastinal mass, the presence of a large pericardial effusion and pleural effusions, along with the patient's age and symptoms, make lymphoblastic lymphoma a more likely diagnosis.
  - [near] Non-Hodgkin lymphoma: This is a broad category that includes lymphoblastic lymphoma, but is too general to be the champion diagnosis.
  - [other] Thymoma: Thymoma can present with a mediastinal mass, but it is less likely to cause large pericardial and pleural effusions, and is more commonly seen in older adults.
  - [other] Castleman disease: Castleman disease can present with systemic symptoms and lymphadenopathy, but it is less likely to cause a large anterior mediastinal mass and pericardial and pleural effusions.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Lymphoma', 'Mediastinal germ cell tumor']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lymphoma', 'Mediastinal germ cell tumor', 'Thymoma', 'Pericarditis', 'Hodgkin lymphoma', 'Lymphoma', 'Mediastinal germ cell tumor', 'Thymoma']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Lymphoma', 'Germ Cell Tumor']
- diagnose: ['Lymphoma', 'Germ Cell Tumor']
- queries: ['pediatric anterior mediastinal mass', 'pericardial effusion and mediastinal mass in children', 'causes of intermittent fever and dyspnea in a 6-year-old']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Lymphoma', 'Germ Cell Tumor']
- queries: ['pediatric pericardial effusion with mediastinal mass', 'causes of orthopnea and pleuritic chest pain in children', 'differential diagnosis of anterior mediastinal mass in pediatric patients', 'pericardial effusion with electrical alternans in pediatric patients']
- n_chunks=12

## APHHM
_na_

