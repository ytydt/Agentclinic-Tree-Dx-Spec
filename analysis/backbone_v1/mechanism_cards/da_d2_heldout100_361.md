# DA / d2_heldout100 / case 361

- **gold**: Slow-fast atrioventricular nodal reentry tachycardia (AVNRT)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A young adult patient presented with palpitations associated with chest pain and lightheadedness. The patient's history revealed no previous arrhythmic episodes or family history of sudden cardiac death.

Physical examination results were unremarkable.

- Laboratory tests: Results were normal.- ECG: Initial 12-lead electrocardiogram was normal.- Echocardiography: Transthoracic echocardiography was normal.- Smartwatch Recording:  Image Title: Single-Lead Electrocardiogram Captured by Patient's Smartwatch  Image Description: Recording showed a narrow QRS regular tachycardia triggering a nonsustained phase of wide complex irregular tachycardia, followed by wide complex configuration until spontaneous termination.- Treadmill Stress Test: Negative for exercise-induced myocardial ischemia or arrhythmias at maximum heart rate.- Electrophysiology Study: Revealed tachycardia with a cycle length of 250 ms. Programmed ventricular stimulation at 2 ventricular sites with up to 3 premature beats was performed.

What is the most likely diagnosis?

Options:
A. Atrioventricular Nodal Reentrant Tachycardia
B. Slow-fast atrioventricular nodal reentry tachycardia (AVNRT)
C. Atrioventricular Reentrant …

## Options
- A: Atrioventricular Nodal Reentrant Tachycardia
- B: Slow-fast atrioventricular nodal reentry tachycardia (AVNRT) **←gold**
- C: Atrioventricular Reentrant Tachycardia
- D: Paroxysmal Supraventricular Tachycardia (e.g., AV Nodal Reentrant Tachycardia)

## Backbone e7

- S2 n=47 gold_rank=None
  - clusters: gold=0 near=30 other=17
- S3 shortlist (5):
  - [near] Supraventricular Tachycardia with Aberrancy
  - [near] Atrioventricular Nodal Reentrant Tachycardia
  - [near] Orthodromic Atrioventricular Reentrant Tachycardia
  - [near] Ventricular Tachycardia
  - [near] Catecholaminergic Polymorphic Ventricular Tachycardia
    - why_kept(Supraventricular Tachycardia with Aberrancy): Narrow QRS regular tachycardia triggering a nonsustained phase of wide complex irregular tachycardia
    - why_kept(Atrioventricular Nodal Reentrant Tachycardia): Palpitations with chest pain and lightheadedness, normal physical examination and laboratory results
    - why_kept(Orthodromic Atrioventricular Reentrant Tachycardia): Tachycardia with a cycle length of 250 ms, normal echocardiography
    - why_kept(Ventricular Tachycardia): Wide complex configuration until spontaneous termination, negative treadmill stress test
    - why_kept(Catecholaminergic Polymorphic Ventricular Tachycardia): Palpitations and lightheadedness, normal initial 12-lead electrocardiogram
- S4 champion: **Supraventricular Tachycardia with Aberrancy** cluster=near jaccard=0.10
- S4 rationale: The patient's smartwatch recording showed a narrow QRS regular tachycardia triggering a nonsustained phase of wide complex irregular tachycardia, which is consistent with supraventricular tachycardia with aberrancy. The electrophysiology study also revealed tachycardia with a cycle length of 250 ms, which supports this diagnosis.
- S4 rejected:
  - [near] Atrioventricular Nodal Reentrant Tachycardia: While possible, the presence of wide complex irregular tachycardia suggests aberrancy rather than a typical AVNRT
  - [near] Orthodromic Atrioventricular Reentrant Tachycardia: The patient's ECG and electrophysiology study results do not specifically suggest an accessory pathway, making this diagnosis less likely
  - [near] Ventricular Tachycardia: The initial narrow QRS regular tachycardia and the patient's overall clinical presentation make ventricular tachycardia a less likely diagnosis
  - [near] Catecholaminergic Polymorphic Ventricular Tachycardia: There is no mention of the patient experiencing emotions or physical stress that could trigger CPVT, and the ECG results do not show the characteristic polymorphic ventricular tachycardia

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Supraventricular Tachycardia', 'Atrioventricular Nodal Reentrant Tachycardia']
  clusters: {'gold': 0, 'near': 2, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Supraventricular Tachycardia', 'Ventricular Tachycardia', 'Atrioventricular Nodal Reentrant Tachycardia', 'Orthodromic Atrioventricular Reentrant Tachycardia', 'Atrial Fibrillation', 'Supraventricular Tachycardia', 'Atrioventricular Nodal Reentrant Tachycardia', 'Orthodromic Atrioventricular Reentrant Tachycardia']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Supraventricular Tachycardia (SVT)', 'Ventricular Tachycardia (VT)']
- diagnose: ['Supraventricular Tachycardia (SVT)', 'Ventricular Tachycardia (VT)']
- queries: ['narrow QRS regular tachycardia', 'wide complex irregular tachycardia', 'supraventricular tachycardia vs ventricular tachycardia', 'electrophysiology study results interpretation']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=63 final_n=1
- final: ['Ventricular Tachycardia']
- tree gold_cluster_n=0 final gold=False

