# DA / d2_heldout100 / case 318

- **gold**: Dual tachycardia: Atrial flutter with accelerated idioventricular rhythm (AIVR)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A patient in their 60s with history of ischemic cardiomyopathy (ejection fraction 25%) and single-chamber primary prevention implantable cardioverter-defibrillator presented with worsening shortness of breath and New York Heart Association functional class IV symptoms. Patient had been on amiodarone treatment previously.

Heart rate: 106 beats/minBlood pressure: 96/58 mm Hg- Elevated jugular venous pressure- Bilateral lung crackles on auscultation - Prominent S3 on cardiac auscultation- Signs of substantial volume overload

- Laboratory Tests:  * Markedly elevated N-terminal pro-brain natriuretic peptide  * Elevated creatinine levels- Imaging:  * Echocardiogram showed ejection fraction of 10% (decreased from baseline)- ECG Findings:  Image Title: 12-Lead electrocardiogram before electrophysiology study  Image Description: Shows relatively slow, wide QRS rhythm at ~100 beats/min, QRS duration ~140ms, atypical left bundle-branch block morphology in V1/V2, early R/S transition in V3, regular atrial tachycardia at cycle length 320ms, variable PR intervals indicating AV dissociation- Electrophysiology Study:  * Confirmed dual tachycardia

What is the most likely diagnosis?

Options:
A. …

## Options
- A: Ventricular tachycardia
- B: Dual tachycardia: Atrial flutter with accelerated idioventricular rhythm (AIVR) **←gold**
- C: Atrial tachycardia
- D: Dual tachyarrhythmias (atrial tachycardia plus slow ventricular tachycardia)

## Backbone e7

- S2 n=49 gold_rank=None
  - clusters: gold=0 near=5 other=44
- S3 shortlist (5):
  - [near] Tachycardia-induced cardiomyopathy
  - [other] Ischemic cardiomyopathy
  - [other] Dilated cardiomyopathy
  - [near] Ventricular tachycardia
  - [other] Cardiac tamponade
    - why_kept(Tachycardia-induced cardiomyopathy): Patient has a history of ischemic cardiomyopathy, low ejection fraction, and is experiencing tachycardia
    - why_kept(Ischemic cardiomyopathy): Patient has a history of ischemic cardiomyopathy and low ejection fraction
    - why_kept(Dilated cardiomyopathy): Patient has a low ejection fraction and signs of volume overload
    - why_kept(Ventricular tachycardia): Electrophysiology study confirmed dual tachycardia and patient has a wide QRS rhythm
    - why_kept(Cardiac tamponade): Patient has elevated jugular venous pressure and signs of substantial volume overload
- S4 champion: **Tachycardia-induced cardiomyopathy** cluster=near jaccard=0.09
- S4 rationale: The patient's worsening symptoms, decreased ejection fraction, and markedly elevated N-terminal pro-brain natriuretic peptide, combined with the ECG findings of a wide QRS rhythm and the electrophysiology study confirming dual tachycardia, suggest that the patient's cardiomyopathy is being exacerbated by the tachycardia.
- S4 rejected:
  - [other] Ischemic cardiomyopathy: While the patient has a history of ischemic cardiomyopathy, the current presentation suggests an acute exacerbation due to tachycardia rather than a pure ischemic cause.
  - [other] Dilated cardiomyopathy: The patient's ejection fraction and symptoms are consistent with a cardiomyopathy, but the specific diagnosis of dilated cardiomyopathy is not as directly supported by the tachycardia and electrophysiology findings as tachycardia-induced cardiomyopathy.
  - [near] Ventricular tachycardia: Ventricular tachycardia is a possible cause of the patient's symptoms, but it does not fully explain the decreased ejection fraction and other signs of cardiomyopathy.
  - [other] Cardiac tamponade: There is no mention of specific findings suggestive of cardiac tamponade, such as a pericardial effusion on imaging or pulsus paradoxus, making this diagnosis less likely.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Heart Failure with Reduced Ejection Fraction (HFrEF)', 'Atrial Tachycardia']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Heart Failure with Reduced Ejection Fraction (HFrEF)', 'Atrial Tachycardia', 'Ventricular Tachycardia', 'Cardiac Arrest', 'Sudden Cardiac Death', 'Heart Failure with Reduced Ejection Fraction (HFrEF)', 'Atrial Tachycardia', 'Ventricular Tachycardia']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Ventricular Tachycardia (VT)', 'Decompensated Heart Failure']
- diagnose: ['Ventricular Tachycardia (VT)', 'Decompensated Heart Failure']
- queries: ['ischemic cardiomyopathy complications', 'elevated N-terminal pro-brain natriuretic peptide diagnosis', 'wide QRS rhythm with atypical left bundle-branch block morphology', 'AV dissociation causes']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=28 final_n=2
- final: ['Heart Failure with Reduced Ejection Fraction', 'Ischemic Cardiomyopathy']
- tree gold_cluster_n=0 final gold=False

