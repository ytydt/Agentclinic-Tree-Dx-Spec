# MCR / mcr_200b / case 344

- **gold**: sarcoidosis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 50-year-old Romanian woman with a history of intravenous drug use and active smoking was receiving a 48-week course of interferon alfa-2a plus ribavirin for hepatitis C. Thirty weeks into therapy, she presented with a 3-week history of progressive shortness of breath and hemoptysis.  
On examination, she was afebrile with normal vital signs. A chest radiograph demonstrated bilateral hilar lymphadenopathy. Contrast-enhanced computed tomography of the chest revealed enlarged hilar lymph nodes and diffuse nodules throughout both lungs. A positron emission tomography–CT scan showed increased fluorodeoxyglucose uptake in the hilar lymph nodes and lung parenchyma.

What is the most likely diagnosis?

Options:
A. sarcoidosis
B. lung sarcoidosis should be made with… other interstitial lung diseases
C. given the radiographic nodules and lymphadenopathy
D. Pulmonary neoplasm was initially suspected given the radiographic nodules and lymphadenopathy
E. Tuberculosis was considered in the pulmonary differential but excluded by negative acid
F. Fungal infection was considered in the pulmonary differential but excluded by negative fungal stains
G. Berylliosis was considered in the pulmonary dif…

## Backbone e7

- S2 n=50 gold_rank=1
  - clusters: gold=1 near=0 other=49
- S3 shortlist (5):
  - [gold] Sarcoidosis
  - [other] Lymphoma
  - [other] Tuberculosis
  - [other] Interferon-induced pulmonary sarcoid-like reaction
  - [other] Wegener's granulomatosis
    - why_kept(Sarcoidosis): Bilateral hilar lymphadenopathy and lung nodules are characteristic of sarcoidosis
    - why_kept(Lymphoma): Progressive shortness of breath, hemoptysis, and lymphadenopathy are consistent with lymphoma
    - why_kept(Tuberculosis): History of intravenous drug use and active smoking increase the risk of tuberculosis
    - why_kept(Interferon-induced pulmonary sarcoid-like reaction): Patient is receiving interferon alfa-2a, which can cause a sarcoid-like reaction
    - why_kept(Wegener's granulomatosis): Respiratory symptoms, lymphadenopathy, and lung nodules are consistent with Wegener's granulomatosis
- S4 champion: **Interferon-induced pulmonary sarcoid-like reaction** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms and radiographic findings, including bilateral hilar lymphadenopathy and diffuse lung nodules, are consistent with sarcoidosis, but the temporal relationship with interferon alfa-2a plus ribavirin therapy suggests an interferon-induced reaction.
- S4 rejected:
  - [gold] Sarcoidosis: While the radiographic findings are consistent with sarcoidosis, the patient's recent initiation of interferon therapy suggests a possible drug-induced cause.
  - [other] Lymphoma: There is no clear evidence of lymphoma, such as significant lymphadenopathy or a mass, and the patient's symptoms and radiographic findings are more suggestive of an inflammatory or granulomatous process.
  - [other] Tuberculosis: The patient's symptoms and radiographic findings are not typical for tuberculosis, and there is no mention of a positive purified protein derivative test or acid-fast bacilli on sputum smear.
  - [other] Wegener's granulomatosis: The patient's symptoms and radiographic findings do not suggest Wegener's granulomatosis, which typically presents with a combination of upper and lower respiratory tract symptoms, renal involvement, and positive anti-neutrophil cytoplasmic antibodies.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Sarcoidosis', 'Lymphoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Sarcoidosis', 'Lymphoma', 'Tuberculosis', 'Histiocytosis', 'Pneumonia', 'Sarcoidosis', 'Lymphoma', 'Tuberculosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Sarcoidosis', 'Pulmonary lymphangitic carcinomatosis']
- diagnose: ['Sarcoidosis', 'Pulmonary lymphangitic carcinomatosis']
- queries: ['hepatitis C treatment side effects', 'interferon alfa-2a plus ribavirin complications', 'bilateral hilar lymphadenopathy causes', 'diffuse nodules in lungs causes']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Sarcoidosis', 'Pneumonitis']
- queries: ['interferon alfa-2a side effects', 'ribavirin pulmonary toxicity', 'hepatitis C treatment complications', 'bilateral hilar lymphadenopathy causes']
- n_chunks=12

## APHHM
_na_

