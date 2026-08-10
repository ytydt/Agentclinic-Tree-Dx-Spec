# DA / d2_heldout100 / case 330

- **gold**: Trifascicular block (Right bundle-branch block with alternating left anterior and left posterior fascicular block)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A patient in their 80s with a history of hypertension controlled with Dyazide presented with 1 episode of syncope. The patient reported feeling hot and light-headed, felt they should lie down but suddenly awoke on the floor with considerable head and left shoulder pain. The patient also had a few near-fainting spells in the week prior to this index syncopal event.

Vital signs were stable without considerable orthostatic changes in blood pressure and heart rate.

- Laboratory tests: Serum electrolyte levels and cardiac enzymes were normal.- Imaging studies:  - Cranial CT: No acute pathologic changes  - Echocardiogram: Mild concentric left ventricular hypertrophy with preserved left ventricular systolic function  - ECG findings:  First ECG (on admission):  - Sinus rhythm with right bundle-branch block   - Left anterior fascicular block  - PR interval of 204 milliseconds  - Premature atrial complex at rate of 64 beats per minute  - QRS axis deviation to -72°    Second ECG (following day):  - Sinus rhythm with right bundle-branch block  - Left posterior fascicular block   - PR interval of 210 milliseconds  - Rate of 58 beats per minute  - QRS axis deviation to +124°

What is the most …

## Options
- A: Cardiac arrhythmia (other than heart block)
- B: Trifascicular block (Right bundle-branch block with alternating left anterior and left posterior fascicular block) **←gold**
- C: Intermittent complete heart block (e.g., trifascicular block progression)
- D: High-grade atrioventricular (AV) block

## Backbone e7

- S2 n=52 gold_rank=None
  - clusters: gold=0 near=2 other=50
- S3 shortlist (5):
  - [other] Vasovagal syncope
  - [other] Cardiac sarcoidosis
  - [near] Atrioventricular block
  - [other] Sick sinus syndrome
  - [other] Orthostatic hypotension
    - why_kept(Vasovagal syncope): Patient experienced syncope with preceding hot and light-headed feelings, consistent with vasovagal syncope
    - why_kept(Cardiac sarcoidosis): Patient has history of hypertension and presented with syncope, with ECG findings of right bundle-branch block and fascicular block, which could be related to cardiac sarcoidosis
    - why_kept(Atrioventricular block): Patient's ECG showed PR interval of 204 milliseconds, indicating possible atrioventricular block
    - why_kept(Sick sinus syndrome): Patient's ECG showed sinus rhythm with right bundle-branch block and fascicular block, which could be related to sick sinus syndrome
    - why_kept(Orthostatic hypotension): Patient had a few near-fainting spells in the week prior to the index event, which could be related to orthostatic hypotension
- S4 champion: **Atrioventricular block** cluster=near jaccard=0.08
- S4 rationale: The patient's ECG findings, including a PR interval of 204 milliseconds and later 210 milliseconds, indicate a first-degree atrioventricular (AV) block, which can cause syncope due to impaired cardiac conduction.
- S4 rejected:
  - [other] Vasovagal syncope: While the patient felt hot and light-headed before the syncopal event, the presence of structural heart disease and conduction abnormalities makes vasovagal syncope less likely.
  - [other] Cardiac sarcoidosis: There is no evidence of cardiac sarcoidosis in the provided laboratory tests or imaging studies.
  - [other] Sick sinus syndrome: The patient's ECG shows a stable sinus rhythm, which does not support a diagnosis of sick sinus syndrome.
  - [other] Orthostatic hypotension: The patient's vital signs were stable without considerable orthostatic changes in blood pressure and heart rate, making orthostatic hypotension unlikely.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Cardiac Conduction Disease', 'Cardiac Arrhythmia']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Cardiac Arrhythmia', 'Orthostatic Hypotension', 'Vasovagal Syncope', 'Cardiac Conduction Disease', 'Cerebrovascular Accident', 'Cardiac Conduction Disease', 'Cardiac Arrhythmia', 'Vasovagal Syncope']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Bifascicular Block with Syncope', 'Cardiovascular Syncope']
- diagnose: ['Bifascicular Block with Syncope', 'Cardiovascular Syncope']
- queries: ['syncope causes in elderly', 'bundle branch block and syncope', 'bifascicular block and syncope']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=34 final_n=2
- final: ['Hypertrophic Cardiomyopathy', 'Left Ventricular Hypertrophy']
- tree gold_cluster_n=0 final gold=False

