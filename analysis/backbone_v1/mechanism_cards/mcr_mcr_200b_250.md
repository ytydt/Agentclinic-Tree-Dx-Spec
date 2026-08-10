# MCR / mcr_200b / case 250

- **gold**: Toxocariasis
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 9-year-old girl with a small muscular ventricular septal defect presented with chest pain and dyspnea one week after recovering from an upper respiratory infection and after minor anterior chest trauma in a fall. She was afebrile. Heart rate was 104 beats/min, respiratory rate 28 breaths/min, blood pressure 113/66 mm Hg, and oxygen saturation normal. Physical examination revealed mild tenderness over the sternum and normal cardiac auscultation. 

Chest radiography showed mild cardiomediastinal silhouette enlargement and a focal opacity in the right middle lung. ECG was normal. Transthoracic echocardiography demonstrated a moderate circumferential pericardial effusion with right atrial collapse, normal biventricular systolic function, and no ventricular septal defect. 

Laboratory studies revealed a leukocyte count of 12,000 cells/µL with an absolute eosinophil count of 1,570 cells/µL (normal 40–190), C-reactive protein 1.94 mg/dL (normal <0.5), erythrocyte sedimentation rate 45 mm/hr (normal 0–30), and troponin T 0.25 ng/mL (normal <0.1). Cardiac magnetic resonance imaging showed elevated global myocardial T2 (70 ms) and T1 (1150 ms) values, increased left ventricular wall thickn…

## Backbone e7

- S2 n=51 gold_rank=None
  - clusters: gold=0 near=0 other=51
- S3 shortlist (5):
  - [other] Eosinophilic pericarditis
  - [other] Hypereosinophilic syndrome
  - [other] Viral myopericarditis
  - [other] Churg-Strauss syndrome
  - [other] Eosinophilic granulomatosis with polyangiitis
    - why_kept(Eosinophilic pericarditis): Elevated absolute eosinophil count and pericardial effusion
    - why_kept(Hypereosinophilic syndrome): Markedly elevated absolute eosinophil count and multi-organ involvement
    - why_kept(Viral myopericarditis): Recent upper respiratory infection and pericardial effusion
    - why_kept(Churg-Strauss syndrome): Eosinophilia, pericardial effusion, and pulmonary nodules
    - why_kept(Eosinophilic granulomatosis with polyangiitis): Eosinophilia, pericardial effusion, and pulmonary nodules with ground-glass opacities
- S4 champion: **Eosinophilic pericarditis** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation with pericardial effusion, elevated eosinophil count, and resolution of symptoms with ibuprofen and colchicine treatment supports this diagnosis, and the absence of other systemic symptoms or findings suggestive of a more complex syndrome like Churg-Strauss or eosinophilic granulomatosis with polyangiitis makes this the most straightforward explanation for the key facts
- S4 rejected:
  - [other] Hypereosinophilic syndrome: While the patient has a high eosinophil count, the syndrome typically involves more systemic symptoms and organ damage beyond what is described
  - [other] Viral myopericarditis: Although initially considered, the lack of fever and the specific laboratory findings, particularly the marked eosinophilia, do not support a typical viral etiology
  - [other] Churg-Strauss syndrome: The patient lacks the typical asthma and other systemic manifestations that are characteristic of this condition
  - [other] Eosinophilic granulomatosis with polyangiitis: Similar to Churg-Strauss, this condition involves more widespread systemic symptoms and specific types of organ involvement not described in the vignette

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Toxocara infection', 'Eosinophilic pneumonia']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Viral myopericarditis', 'Toxocara infection', 'Mycoplasma pneumoniae infection', 'Eosinophilic pneumonia', 'Acute pericarditis', 'Toxocara infection', 'Eosinophilic pneumonia', 'Viral myopericarditis']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Loeffler syndrome', 'Toxocariasis']
- diagnose: ['Loeffler syndrome', 'Toxocariasis']
- queries: ['viral myopericarditis diagnosis', 'eosinophilia causes in children', 'Toxocara serology interpretation', 'myopericarditis vs. loeffler syndrome']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Hypereosinophilic syndrome', 'Toxocara infection']
- queries: ['eosinophilia with pericardial effusion and pulmonary nodules', 'viral myopericarditis with elevated eosinophil count', 'differential diagnosis of hypereosinophilia with cardiac involvement', 'Toxocara infection presenting with cardiac and pulmonary symptoms']
- n_chunks=12

## APHHM
_na_

