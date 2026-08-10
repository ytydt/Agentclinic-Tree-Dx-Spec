# DA / d2_heldout100 / case 411

- **gold**: Left posterior fascicular ventricular tachycardia (FVT)
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A woman in her 60s with a 20-year history of palpitations and shortness of breath. Episodes were previously controlled with verapamil but sustained symptoms recurred 6 months before presentation, not responding to amiodarone therapy.

- Heart rate: 122 beats per minute- Blood pressure: 135/85 mm Hg- Cardiovascular exam: Regular rhythm with cannon A waves in the jugular venous waveform

- ECG: Regular tachycardia at 130 beats per minute with incomplete right bundle branch block morphology, QRS duration of 118 milliseconds, and left-axis deviation. QRS complexes outnumber P waves with 3:2 relationship. P-wave morphology shows negative deflection in leads II and aVF.  Image Title: Figure 1A - Electrocardiographic Findings  Image Description: Regular relatively narrow-complex tachycardia with right bundle branch block and left-axis deviation. 3:2 relationship between ventricular and atrial activations.- 24-hour Holter monitor: Sustained tachycardia throughout monitoring period- Echocardiogram: Results within normal limits- Electrophysiology study: Confirmed origin of tachycardia

What is the most likely diagnosis?

Options:
A. Atrioventricular reentrant tachycardia
B. Atrial tachycardi…

## Options
- A: Atrioventricular reentrant tachycardia
- B: Atrial tachycardia
- C: AV nodal reentrant tachycardia
- D: Left posterior fascicular ventricular tachycardia (FVT) **←gold**

## Backbone e7

- S2 n=44 gold_rank=10
  - clusters: gold=2 near=38 other=4
- S3 shortlist (5):
  - [near] Atrioventricular Nodal Reentrant Tachycardia
  - [near] Orthodromic Atrioventricular Reentrant Tachycardia
  - [other] Atrial Flutter
  - [near] Supraventricular Tachycardia with Aberrancy
  - [other] Wolff-Parkinson-White Syndrome
    - why_kept(Atrioventricular Nodal Reentrant Tachycardia): Regular tachycardia with 3:2 relationship between ventricular and atrial activations, consistent with AVNRT
    - why_kept(Orthodromic Atrioventricular Reentrant Tachycardia): Sustained tachycardia with left-axis deviation and incomplete right bundle branch block morphology, suggestive of orthodromic AVRT
    - why_kept(Atrial Flutter): Regular tachycardia with negative deflection in leads II and aVF, consistent with atrial flutter
    - why_kept(Supraventricular Tachycardia with Aberrancy): Tachycardia with aberrant conduction, as evidenced by the 3:2 relationship and left-axis deviation
    - why_kept(Wolff-Parkinson-White Syndrome): History of palpitations and shortness of breath, with ECG findings consistent with pre-excitation syndrome
- S4 champion: **Atrioventricular Nodal Reentrant Tachycardia** cluster=near jaccard=0.11
- S4 rationale: The patient's ECG shows a regular tachycardia with a 3:2 relationship between ventricular and atrial activations, and the presence of cannon A waves in the jugular venous waveform, which is consistent with Atrioventricular Nodal Reentrant Tachycardia. The patient's history of response to verapamil also supports this diagnosis.
- S4 rejected:
  - [near] Orthodromic Atrioventricular Reentrant Tachycardia: This condition typically involves an accessory pathway and would likely show pre-excitation on the ECG, which is not mentioned.
  - [other] Atrial Flutter: Atrial Flutter typically shows a sawtooth pattern on the ECG, which is not described in the vignette.
  - [near] Supraventricular Tachycardia with Aberrancy: This condition would likely show a wider QRS complex due to the aberrancy, but the QRS duration is 118 milliseconds, which is not significantly wide.
  - [other] Wolff-Parkinson-White Syndrome: This condition typically shows pre-excitation on the ECG, which is not mentioned in the vignette.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Atrial Flutter', 'Atrioventricular Nodal Reentrant Tachycardia']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Atrial Flutter', 'Atrioventricular Nodal Reentrant Tachycardia', 'Atrioventricular Reentrant Tachycardia', 'Junctional Tachycardia', 'Ectopic Atrial Tachycardia', 'Atrial Flutter', 'Atrioventricular Nodal Reentrant Tachycardia', 'Junctional Tachycardia']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Atrial Tachycardia with 3:2 Block', 'Supraventricular Tachycardia with Incomplete Right Bundle Branch Block']
- diagnose: ['Atrial Tachycardia with 3:2 Block', 'Supraventricular Tachycardia with Incomplete Right Bundle Branch Block']
- queries: ['atrial tachycardia with 3:2 block', 'supraventricular tachycardia with incomplete right bundle branch block', 'verapamil-resistant tachycardia']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=58 final_n=2
- final: ['Atrioventricular Nodal Reentrant Tachycardia', 'dilated cardiomyopathy']
- tree gold_cluster_n=4 final gold=False

