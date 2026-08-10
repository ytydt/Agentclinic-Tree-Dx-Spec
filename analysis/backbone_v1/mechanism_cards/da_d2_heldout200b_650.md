# DA / d2_heldout200b / case 650

- **gold**: PVC-induced Idiopathic Ventricular Fibrillation
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 34-year-old White woman with a history of obesity presented after an unwitnessed cardiac arrest. She was found unresponsive, and bystander cardiopulmonary resuscitation was initiated. She had mechanical intubation for airway protection and developed atrial fibrillation with a rapid ventricular response. Soon after transfer, she experienced frequent premature ventricular contractions triggering polymorphic ventricular tachycardia and resultant hemodynamic collapse.

Patient was hemodynamically stable initially after transfer. No other specific physical examination findings were documented in the case report.

{'Laboratory Tests': ['- Laboratory data showed no electrolyte derangements', '- Troponin T: 0.847 µg/L (normal, ≤0.01 µg/L)', '- Troponin I: 0.13 ng/mL (normal, ≤0.04)', '- Urine toxicology, alcohol, and acetaminophen screening results were negative'], 'Cardiac Studies': ['- ECG showed sinus tachycardia with heart rate 101 beats/min, QTc 443 ms', '- Follow-up ECG showed normal sinus rhythm with low-voltage QRS complexes, nonspecific T-wave changes, QTc 433 ms, absence of early repolarization pattern', '- High precordial ECG did not demonstrate Brugada pattern'], 'Imaging Stu…

## Options
- A: PVC-induced Idiopathic Ventricular Fibrillation **←gold**
- B: Concealed (Borderline) Long QT Syndrome
- C: Catecholaminergic Polymorphic Ventricular Tachycardia
- D: Short-Coupled Torsade de Pointes

## Backbone e7

- S2 n=50 gold_rank=6
  - clusters: gold=1 near=7 other=42
- S3 shortlist (5):
  - [near] Catecholaminergic polymorphic ventricular tachycardia
  - [other] Long QT syndrome
  - [gold] Idiopathic ventricular fibrillation
  - [near] Arrhythmogenic right ventricular cardiomyopathy
  - [other] Hypertrophic cardiomyopathy
    - why_kept(Catecholaminergic polymorphic ventricular tachycardia): Patient experienced frequent premature ventricular contractions triggering polymorphic ventricular tachycardia
    - why_kept(Long QT syndrome): ECG showed QTc 443 ms, which is a risk factor for torsades de pointes and ventricular tachycardia
    - why_kept(Idiopathic ventricular fibrillation): Patient had ventricular fibrillation with no clear underlying cause
    - why_kept(Arrhythmogenic right ventricular cardiomyopathy): Patient had ventricular tachycardia and fibrillation, which can be associated with this condition
    - why_kept(Hypertrophic cardiomyopathy): Although not directly implicated, it is a common cause of sudden cardiac death and ventricular tachycardia in young adults
- S4 champion: **Catecholaminergic polymorphic ventricular tachycardia** cluster=near jaccard=0.12
- S4 rationale: The patient experienced frequent premature ventricular contractions triggering polymorphic ventricular tachycardia, which is a hallmark of catecholaminergic polymorphic ventricular tachycardia. The normal cardiac structure and function, as well as the absence of other clear causes of ventricular arrhythmias, also support this diagnosis.
- S4 rejected:
  - [other] Long QT syndrome: The QTc interval was mildly prolonged but not significantly long enough to be diagnostic of Long QT syndrome, and the clinical presentation does not strongly suggest this condition.
  - [gold] Idiopathic ventricular fibrillation: While the patient did experience ventricular fibrillation, the presence of triggering premature ventricular contractions suggests a more specific underlying condition like catecholaminergic polymorphic ventricular tachycardia.
  - [near] Arrhythmogenic right ventricular cardiomyopathy: The cardiac magnetic resonance imaging showed mild left ventricular and left atrial dilation but no significant right ventricular involvement or fibrofatty replacement, which is characteristic of arrhythmogenic right ventricular cardiomyopathy.
  - [other] Hypertrophic cardiomyopathy: The transthoracic echocardiogram and cardiac magnetic resonance imaging did not show significant left ventricular hypertrophy, which is a key feature of hypertrophic cardiomyopathy.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Catecholaminergic Polymorphic Ventricular Tachycardia (CPVT)', 'Ventricular Fibrillation due to Unknown Cause']
  clusters: {'gold': 0, 'near': 2, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Catecholaminergic Polymorphic Ventricular Tachycardia (CPVT)', 'Long QT Syndrome', 'Ventricular Fibrillation due to Unknown Cause', 'Myocardial Infarction with Normal Coronary Arteries', 'Idiopathic Ventricular Fibrillation', 'Catecholaminergic Polymorphic Ventricular Tachycardia (CPVT)', 'Ventricular Fibrillation due to Unknown Cause', 'Idiopathic Ventricular Fibrillation']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Catecholaminergic Polymorphic Ventricular Tachycardia (CPVT)', 'Arrhythmogenic Right Ventricular Cardiomyopathy (ARVC)']
- diagnose: ['Catecholaminergic Polymorphic Ventricular Tachycardia (CPVT)', 'Arrhythmogenic Right Ventricular Cardiomyopathy (ARVC)']
- queries: ['cardiac arrest causes in obesity', 'premature ventricular contractions triggering polymorphic ventricular tachycardia', 'troponin elevation without coronary artery disease']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

