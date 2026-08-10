# DA / d2_heldout100 / case 428

- **gold**: Alcohol-induced Prinzmetal variant angina
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A patient in their 50s presented with recurrent abdominal pain and syncope after drinking alcohol, with symptoms persisting for 2 years but worsening on admission. The symptoms usually occurred 6-20 hours after alcohol ingestion and lasted 5-10 minutes. Syncope occurred only after large alcohol intake. Past medical history included hypertension diagnosed 3 months prior. Social history notable for smoking and alcohol overconsumption (250g/week) for about 20 years.

No specific physical examination findings were documented in the case report.

- Laboratory Tests:
  - High-sensitivity troponin I: 0.01 ng/mL (normal)
  - Serum potassium: 4.6 mEq/L (normal)

- ECG/Holter Findings:
  Image Title: ECG Recording A
  Image Description: High-degree atrioventricular block and premature ventricular contractions. ST segments elevated 4-6 mm in leads II, III and aVF, with ST depression in leads V2-V6

  Image Title: ECG Recording B
  Image Description: Sinus rhythm with short bursts of ventricular tachycardia. Widespread ST-segment elevations (4-15 mm) in leads II, III, aVF, and V2-V6

- Coronary Angiography:
  Results showed 10% stenosis in proximal left anterior descending artery (LAD) and rig…

## Options
- A: Alcohol-induced Coronary Vasospasm (Vasospastic Angina)
- B: Coronary vasospastic angina (Prinzmetal’s angina)
- C: Coronary artery vasospasm (Prinzmetal angina)
- D: Alcohol-induced Prinzmetal variant angina **←gold**

## Backbone e7

- S2 n=49 gold_rank=11
  - clusters: gold=1 near=5 other=43
- S3 shortlist (5):
  - [other] Alcoholic cardiomyopathy
  - [other] Vasovagal syncope
  - [gold] Variant angina
  - [near] Alcohol-induced autonomic dysfunction
  - [other] Takotsubo cardiomyopathy
    - why_kept(Alcoholic cardiomyopathy): History of long-term alcohol overconsumption and symptoms consistent with cardiac dysfunction
    - why_kept(Vasovagal syncope): Recurrent syncope triggered by large alcohol intake, consistent with vasovagal response
    - why_kept(Variant angina): ECG findings of ST segment elevations and patient's history of alcohol ingestion triggering symptoms
    - why_kept(Alcohol-induced autonomic dysfunction): History of long-term alcohol overconsumption and symptoms consistent with autonomic dysfunction
    - why_kept(Takotsubo cardiomyopathy): ECG findings and symptoms consistent with stress-induced cardiomyopathy, potentially triggered by alcohol ingestion
- S4 champion: **Alcoholic cardiomyopathy** cluster=other jaccard=0.00
- S4 rationale: The patient's long history of alcohol overconsumption and symptoms of recurrent abdominal pain and syncope after alcohol ingestion, along with ECG findings of high-degree atrioventricular block and premature ventricular contractions, support this diagnosis.
- S4 rejected:
  - [other] Vasovagal syncope: While syncope is a symptom, the presence of abdominal pain and specific ECG findings suggest a more complex cardiac issue.
  - [gold] Variant angina: The coronary angiography showed only 10% stenosis in proximal LAD and RCA, which is not significant enough to cause variant angina.
  - [near] Alcohol-induced autonomic dysfunction: This condition could contribute to some symptoms, but it does not fully explain the cardiac findings on the ECG and coronary angiography.
  - [other] Takotsubo cardiomyopathy: There is no mention of the typical triggers or echocardiographic findings of takotsubo cardiomyopathy, such as a balloon-like appearance of the left ventricle.
  - [near] Alcohol-induced autonomic dysfunction: This diagnosis does not fully account for the cardiac abnormalities seen on ECG and coronary angiography.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Alcoholic Cardiomyopathy', 'Arrhythmogenic Right Ventricular Cardiomyopathy']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Alcoholic Cardiomyopathy', 'Obstructive Sleep Apnea', 'Hypertrophic Cardiomyopathy', 'Arrhythmogenic Right Ventricular Cardiomyopathy', 'Coronary Artery Disease', 'Alcoholic Cardiomyopathy', 'Arrhythmogenic Right Ventricular Cardiomyopathy', 'Hypertrophic Cardiomyopathy']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Alcoholic Cardiomyopathy', 'Arrhythmia (e.g. Atrial Fibrillation or Ventricular Tachycardia) induced by Alcohol']
- diagnose: ['Alcoholic Cardiomyopathy', 'Arrhythmia (e.g. Atrial Fibrillation or Ventricular Tachycardia) induced by Alcohol']
- queries: ['alcohol-induced high-degree atrioventricular block', 'recurrent syncope after alcohol ingestion', 'ST segment elevation and ventricular tachycardia']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=19 final_n=1
- final: ['Alcoholic Cardiomyopathy']
- tree gold_cluster_n=1 final gold=False

