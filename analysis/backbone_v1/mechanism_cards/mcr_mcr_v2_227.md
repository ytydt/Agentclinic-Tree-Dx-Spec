# MCR / mcr_v2 / case 227

- **gold**: pulmonary embolism
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 37-year-old woman with no past medical history presented with continuous chest pain for two hours. She denied dyspnea, syncope, or prior similar episodes. There was no personal or family history of cardiovascular or thromboembolic disease. Vital signs were: pulse 110/min, blood pressure 100/65 mmHg, respiratory rate 20/min, temperature 37 °C, oxygen saturation 95% on room air (99% on 2 L/min nasal cannula). Cardiac auscultation was normal, and neck veins were not distended. Initial ECG showed sinus rhythm with 2 mm of ST-segment elevation in leads V2 and V3. She was given aspirin, clopidogrel, and intravenous heparin and taken to the catheterization laboratory. Twenty minutes later, a second ECG showed a new right bundle branch block and resolution of the precordial ST-segment elevations. Forty-five minutes after presentation, coronary angiography revealed normal coronary arteries without stenosis. Transthoracic echocardiography demonstrated right ventricular dilatation and an estimated pulmonary arterial pressure of 60 mmHg.

What is the most likely diagnosis?

Options:
A. pulmonary embolism
B. elevation of the ST segment is wide including conditions with secondary of the myocar…

## Backbone e7

- S2 n=48 gold_rank=6
  - clusters: gold=1 near=1 other=46
- S3 shortlist (5):
  - [other] Acute coronary syndrome
  - [other] Myocardial infarction with normal coronary arteries
  - [other] Takotsubo cardiomyopathy
  - [gold] Pulmonary embolism
  - [other] Spontaneous coronary artery dissection
    - why_kept(Acute coronary syndrome): Initial ECG showed ST-segment elevation and patient presented with chest pain
    - why_kept(Myocardial infarction with normal coronary arteries): Patient had normal coronary arteries on angiography but presented with signs of myocardial infarction
    - why_kept(Takotsubo cardiomyopathy): Patient had right ventricular dilatation and estimated pulmonary arterial pressure of 60 mmHg, which could be indicative of stress cardiomyopathy
    - why_kept(Pulmonary embolism): Patient had right ventricular dilatation and elevated pulmonary arterial pressure, which could be indicative of a pulmonary embolism
    - why_kept(Spontaneous coronary artery dissection): Patient had normal coronary arteries on angiography but presented with signs of myocardial infarction, which could be indicative of a spontaneous coronary artery dissection
- S4 champion: **Myocardial infarction with normal coronary arteries** cluster=other jaccard=0.00
- S4 rationale: The patient presented with chest pain and initial ECG changes (ST-segment elevation) consistent with myocardial infarction, but coronary angiography revealed normal coronary arteries without stenosis, which is characteristic of myocardial infarction with normal coronary arteries.
- S4 rejected:
  - [other] Acute coronary syndrome: While the patient presented with symptoms and ECG changes consistent with acute coronary syndrome, the normal coronary arteries on angiography make this less likely.
  - [other] Takotsubo cardiomyopathy: Although the patient had right ventricular dilatation, the initial ECG changes and the lack of a clear stressor make this diagnosis less likely.
  - [gold] Pulmonary embolism: The patient's symptoms and diagnostic findings, such as the ECG changes and normal oxygen saturation, do not strongly support pulmonary embolism.
  - [other] Spontaneous coronary artery dissection: The coronary angiography showed normal coronary arteries, which does not support the diagnosis of spontaneous coronary artery dissection.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Pulmonary Embolism', 'Right Ventricular Infarction']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Pulmonary Embolism', 'Acute Coronary Syndrome', 'Myopericarditis', 'Pulmonary Hypertension', 'Right Ventricular Infarction', 'Pulmonary Embolism', 'Right Ventricular Infarction', 'Acute Coronary Syndrome']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Acute Cor Pulmonale', 'Myopericarditis']
- diagnose: ['Acute Cor Pulmonale', 'Myopericarditis']
- queries: ['acute coronary syndrome differential diagnosis', 'ST-segment elevation causes', 'normal coronary arteries with ST-segment elevation', 'right ventricular dilatation causes']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Acute Cor Pulmonale', 'Pulmonary Embolism']
- queries: ['acute chest pain with ST-segment elevation in leads V2 and V3', 'normal coronary arteries with right ventricular dilatation', 'pulmonary arterial pressure elevation with normal cardiac auscultation', 'differential diagnosis for chest pain with transient ST-segment elevation']
- n_chunks=12

## APHHM
_na_

