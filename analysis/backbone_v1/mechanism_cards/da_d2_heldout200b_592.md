# DA / d2_heldout200b / case 592

- **gold**: Pulmonary Reperfusion Injury after catheter-directed thrombectomy for acute pulmonary embolism
- **layer**: `e7_win_rank` · **layer_aphhm**: ``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 82-year-old man was hospitalized with several episodes of dizziness, syncope, and shortness of breath that began one day before admission. Medical history included coronary artery disease with stent placement 10 years ago, and surgically treated colon cancer.

Vital signs on admission:- Heart rate: 114 beats/min- Blood pressure: 94/62 mm Hg- Oxygen saturation: 91% on 4 L/min of supplemental oxygen- Respiratory rate: 28 breaths per minuteInitial 12-lead electrocardiogram showed no evidence of acute myocardial ischemia or arrhythmias.

- Laboratory findings:  * Troponin I level: 0.135 µg/L (peaked at 0.499 µg/L)  * D-dimer level: >109.52 nmol/L  * N-terminal pro brain-type natriuretic peptide level: 562.21 pmol/L- Imaging Studies:  * Transthoracic echocardiogram: Dilated right ventricle with reduced systolic function, flattened interventricular septum, pulmonary hypertension, and small hyperdynamic left ventricle    * CT Angiogram (Initial):    Title: Initial Chest CT Angiogram    Description: Acute extensive partially occlusive pulmonary emboli in distal main pulmonary arteries extending into lobar and segmental branches of upper and lower lobes bilaterally. Dilated right ventric…

## Options
- A: Acute massive pulmonary embolism
- B: Pulmonary Reperfusion Injury after catheter-directed thrombectomy for acute pulmonary embolism **←gold**
- C: Acute pulmonary embolism with right heart strain
- D: Post-procedure pulmonary hemorrhage (alveolar hemorrhage)

## Backbone e7

- S2 n=45 gold_rank=1
  - clusters: gold=1 near=20 other=24
- S3 shortlist (5):
  - [gold] Pulmonary Embolism
  - [near] Acute Cor Pulmonale
  - [near] Pulmonary Hypertension Crisis
  - [other] Cardiogenic Shock
  - [near] Acute Respiratory Distress Syndrome
    - why_kept(Pulmonary Embolism): CT Angiogram showed acute extensive partially occlusive pulmonary emboli
    - why_kept(Acute Cor Pulmonale): Dilated right ventricle with reduced systolic function and pulmonary hypertension
    - why_kept(Pulmonary Hypertension Crisis): Evidence of pulmonary hypertension and right ventricular dysfunction
    - why_kept(Cardiogenic Shock): Hypotension and evidence of cardiac compromise
    - why_kept(Acute Respiratory Distress Syndrome): Hypoxemia and bilateral infiltrates on imaging
- S4 champion: **Pulmonary Embolism** cluster=gold jaccard=0.20
- S4 rationale: The patient's symptoms of dizziness, syncope, and shortness of breath, combined with the CT Angiogram showing acute extensive partially occlusive pulmonary emboli, strongly support this diagnosis. Elevated D-dimer and troponin levels also indicate pulmonary embolism.
- S4 rejected:
  - [near] Acute Cor Pulmonale: While the patient has a dilated right ventricle, this is more likely a consequence of the pulmonary embolism rather than the primary diagnosis.
  - [near] Pulmonary Hypertension Crisis: There is no indication of chronic pulmonary hypertension or a crisis situation beyond the acute effects of the pulmonary embolism.
  - [other] Cardiogenic Shock: The patient's left ventricle is described as hyperdynamic, which does not support cardiogenic shock.
  - [near] Acute Respiratory Distress Syndrome: The follow-up CT showing alveolar filling process could suggest ARDS, but the primary issue is the pulmonary embolism, and ARDS might be a secondary complication.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Pulmonary Embolism', 'Heart Failure']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Pulmonary Embolism', 'Acute Coronary Syndrome', 'Heart Failure', 'Chronic Obstructive Pulmonary Disease', 'Pneumonia', 'Pulmonary Embolism', 'Heart Failure', 'Acute Coronary Syndrome']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Acute Pulmonary Embolism (PE)', 'Right Ventricular Dysfunction']
- diagnose: ['Acute Pulmonary Embolism (PE)', 'Right Ventricular Dysfunction']
- queries: ['An 82-year-old man was hospitalized with several episodes of dizziness, syncope, and shortness of breath that began one day before admission. Medical history included coronary artery disease with sten', 'differential diagnosis An 82-year-old man was hospitalized with several episodes of dizziness, syncope, and shortness of breath that began one day before admission. Medical history included coronary artery disease with sten', 'clinical manifestations diagnosis iogram showed no evidence of acute myocardial ischemia or arrhythmias. - Laboratory findings: * Troponin I level: 0.135 µg/L (peaked at 0.499 µg/L) * D-dimer le']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

