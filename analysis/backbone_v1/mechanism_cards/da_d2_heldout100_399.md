# DA / d2_heldout100 / case 399

- **gold**: Atrioventricular nodal reentrant tachycardia (AVNRT)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A man in his 70s with a history of hypertension, hyperlipidemia, chronic obstructive pulmonary disease, and moderate pulmonary hypertension presented with shortness of breath, increased abdominal girth, and bilateral leg swelling. He reported recurrent palpitations that occurred randomly and were often associated with shortness of breath. His medications included aspirin, atorvastatin, amlodipine, tiotropium, and a budesonide-formoterol inhaler.

No specific physical examination findings were detailed in the case report.

- Echocardiography: Left ventricular ejection fraction of 40% compared with 60% 2 months prior.- Cardiac Catheterization: 25% narrowing of the left anterior descending artery and a distally occluded right coronary artery.- Telemetry and ECG Findings:  Image Title: Figure 1. Initiation, Termination, and Reinitiation of Tachycardia  Image Description: Shows initiation and termination patterns of tachyarrhythmia. In sinus rhythm, RR interval 800ms, PR interval 200ms. First PAC PR interval 200ms, second PAC with prolonged PR interval of 390ms.  Image Title: Figure 2. Electrocardiogram  Image Description: Regular narrow complex supraventricular tachycardia with rate of…

## Options
- A: Atrioventricular Reciprocating Tachycardia (AVRT)
- B: Atrial Tachycardia
- C: Supraventricular tachycardia (SVT) exacerbating heart failure
- D: Atrioventricular nodal reentrant tachycardia (AVNRT) **←gold**

## Backbone e7

- S2 n=46 gold_rank=None
  - clusters: gold=0 near=4 other=42
- S3 shortlist (5):
  - [other] Heart Failure with Reduced Ejection Fraction
  - [near] Supraventricular Tachycardia
  - [other] Coronary Artery Disease
  - [other] Pulmonary Hypertension
  - [other] Cardiomyopathy
    - why_kept(Heart Failure with Reduced Ejection Fraction): Decreased left ventricular ejection fraction from 60% to 40% in 2 months
    - why_kept(Supraventricular Tachycardia): ECG findings of regular narrow complex supraventricular tachycardia with rate of 120 beats per minute
    - why_kept(Coronary Artery Disease): 25% narrowing of the left anterior descending artery and a distally occluded right coronary artery
    - why_kept(Pulmonary Hypertension): History of moderate pulmonary hypertension and symptoms of shortness of breath
    - why_kept(Cardiomyopathy): Decreased left ventricular ejection fraction and history of cardiovascular disease
- S4 champion: **Heart Failure with Reduced Ejection Fraction** cluster=other jaccard=0.00
- S4 rationale: The patient's left ventricular ejection fraction decreased from 60% to 40% in 2 months, indicating a significant decline in cardiac function, which is a key characteristic of heart failure with reduced ejection fraction.
- S4 rejected:
  - [near] Supraventricular Tachycardia: Although the patient has supraventricular tachycardia, it is not the primary diagnosis that explains the patient's overall clinical presentation, including the decline in left ventricular ejection fraction and symptoms of heart failure such as shortness of breath and bilateral leg swelling.
  - [other] Coronary Artery Disease: While the patient has coronary artery disease with 25% narrowing of the left anterior descending artery and a distally occluded right coronary artery, it is not the primary diagnosis that explains the patient's symptoms and decline in cardiac function.
  - [other] Pulmonary Hypertension: The patient has a history of moderate pulmonary hypertension, but it is not the primary diagnosis that explains the decline in left ventricular ejection fraction and the patient's overall clinical presentation.
  - [other] Cardiomyopathy: Although cardiomyopathy could be a possible diagnosis, the patient's clinical presentation and decline in left ventricular ejection fraction are more specifically explained by heart failure with reduced ejection fraction.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Supraventricular Tachycardia', 'Heart Failure with Reduced Ejection Fraction']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Atrial Fibrillation', 'Supraventricular Tachycardia', 'Ventricular Tachycardia', 'Heart Failure with Reduced Ejection Fraction', 'Coronary Artery Disease', 'Supraventricular Tachycardia', 'Heart Failure with Reduced Ejection Fraction', 'Atrial Fibrillation']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Supraventricular Tachycardia (SVT)', 'Heart Failure with Reduced Ejection Fraction (HFrEF)']
- diagnose: ['Supraventricular Tachycardia (SVT)', 'Heart Failure with Reduced Ejection Fraction (HFrEF)']
- queries: ['supraventricular tachycardia causes', 'left ventricular ejection fraction decrease', 'pulmonary hypertension and palpitations', 'narrow complex tachycardia diagnosis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=57 final_n=3
- final: ['Heart Failure with Reduced Ejection Fraction', 'Atrioventricular Nodal Reentrant Tachycardia', 'cardiac arrhythmia']
- tree gold_cluster_n=2 final gold=True

