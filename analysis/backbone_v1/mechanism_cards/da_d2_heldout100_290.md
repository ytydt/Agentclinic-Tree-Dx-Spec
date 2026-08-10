# DA / d2_heldout100 / case 290

- **gold**: Wellens syndrome with critical left anterior descending coronary artery stenosis
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A patient in their 50s presented with intermittent compression-like chest pain of 1 day's duration, lasting several minutes each time, occurring during activities and relieved by rest. Medical history includes hypertension and diabetes for 8 years with irregular medication compliance.

Blood pressure: 181/93 mm HgHeart rate: 81 beats per minute Respiratory rate: 20 breaths per minuteBlood oxygen saturation: 96% on room airOther physical examination findings were normal

- ECG Findings:  First ECG (without chest pain):    - Sinus rhythm (72 beats per minute)    - Deeply inverted T-waves in leads V2 to V4    - No ST segment elevation    - Abnormal Q-waves    Second ECG (during chest pain):    - T-waves became upright in V2 to V4    - Inverted U-waves in leads V2 to V5      - Laboratory Tests:    - Initial workup largely unremarkable    - Creatinine and high-sensitivity troponin levels within normal limits    - Serum electrolytes (K+ and Ca2+) grossly normal      - Coronary Angiography:    Total occlusion at the ostium of the left anterior descending coronary artery

What is the most likely diagnosis?

Options:
A. Myocardial Ischemia due to Hypertensive Heart Disease
B. Coronary Arter…

## Options
- A: Myocardial Ischemia due to Hypertensive Heart Disease
- B: Coronary Artery Disease with Prior Myocardial Infarction
- C: Wellens syndrome with critical left anterior descending coronary artery stenosis **←gold**
- D: Unstable Angina

## Backbone e7

- S2 n=48 gold_rank=None
  - clusters: gold=0 near=14 other=34
- S3 shortlist (5):
  - [near] Acute Coronary Syndrome
  - [other] Unstable Angina
  - [other] Non-ST-Elevation Myocardial Infarction
  - [other] Variant Angina
  - [near] Coronary Artery Thrombosis
    - why_kept(Acute Coronary Syndrome): Patient presents with exertional chest pain, ECG changes, and significant coronary artery occlusion
    - why_kept(Unstable Angina): Chest pain occurs during activities and is relieved by rest, with ECG findings of deeply inverted T-waves and abnormal Q-waves
    - why_kept(Non-ST-Elevation Myocardial Infarction): Patient has risk factors for coronary artery disease, including hypertension and diabetes, and ECG changes during chest pain
    - why_kept(Variant Angina): ECG changes during chest pain, including upright T-waves and inverted U-waves, suggest coronary artery spasm
    - why_kept(Coronary Artery Thrombosis): Total occlusion at the ostium of the left anterior descending coronary artery, with normal troponin levels
- S4 champion: **Variant Angina** cluster=other jaccard=0.00
- S4 rationale: The patient's chest pain is characterized by intermittent compression-like pain during activities, relieved by rest, and ECG changes during pain, including upright T-waves and inverted U-waves, which are consistent with variant angina, also known as Prinzmetal's angina. The total occlusion at the ostium of the left anterior descending coronary artery on coronary angiography supports this diagnosis.
- S4 rejected:
  - [near] Acute Coronary Syndrome: While the patient has risk factors and symptoms suggestive of acute coronary syndrome, the specific ECG changes and the nature of the chest pain are more indicative of variant angina.
  - [other] Unstable Angina: Unstable angina typically presents with more persistent and severe chest pain, often at rest, and is not as closely associated with the specific ECG changes seen in this patient.
  - [other] Non-ST-Elevation Myocardial Infarction: The normal high-sensitivity troponin levels and the lack of ST segment elevation make this diagnosis less likely.
  - [near] Coronary Artery Thrombosis: While the patient does have a total occlusion of a coronary artery, the clinical presentation and ECG findings are more characteristic of variant angina than a thrombotic event alone.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Acute Coronary Syndrome', 'Myocardial Infarction']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Acute Coronary Syndrome', 'Stable Angina', 'Unstable Angina', 'Myocardial Infarction', 'Variant Angina', 'Acute Coronary Syndrome', 'Myocardial Infarction', 'Unstable Angina']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Coronary Artery Disease (CAD) with Angina Pectoris', 'Vasospastic or Variant Angina']
- diagnose: ['Coronary Artery Disease (CAD) with Angina Pectoris', 'Vasospastic or Variant Angina']
- queries: ['chest pain diagnosis', 'ECG T-wave inversion', 'coronary artery occlusion symptoms']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=40 final_n=5
- final: ['Myocardial Infarction', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome']
- tree gold_cluster_n=0 final gold=False

