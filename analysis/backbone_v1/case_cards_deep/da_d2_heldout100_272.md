# DA / d2_heldout100 / case 272

- **gold**: Window-Period Acute Myocardial Infarction
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`na` APHHM=`final_ok`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=196; gold_words=5; eponym=True; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A patient in their 60s presented to the emergency department with approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizziness, and sweating. The patient's medical history was notable for hypertension, cerebral infarction, diabetes, and nicotine addiction.  Vital signs showed blood pressure of 188/101 mm Hg, heart rate at 84 beats/min, and respiratory rate at 20 breaths/min.  - Laboratory tests:   - Serum cardiac troponin...

## Options
  - A: Non-ST-segment elevation myocardial infarction (NSTEMI)
  - B: ST-segment elevation myocardial infarction (STEMI)
  - C: Non–ST-segment elevation myocardial infarction (NSTEMI)
  - D: Window-Period Acute Myocardial Infarction

## Backbone e7
- S1 key_facts: Patient presented with approximately 20 minutes of acute, severe precordial ches; Chest pain radiated to the left arm; Patient experienced dyspnea, dizziness, and sweating; Patient has a medical history of hypertension, cerebral infarction, diabetes, an; Blood pressure was 188/101 mm Hg; Heart rate was 84 beats/min; Respiratory rate was 20 breaths/min; Serum cardiac troponin I level was <0.05 ng/mL
- S2 mode=complement k=3 pool_n=46 gold_in_s2=True
  - call1: ['Acute myocardial infarction', 'Unstable angina', 'Pulmonary embolism', 'Aortic dissection', 'Pneumothorax', 'Pericardi
  - call2: ['Variant angina', 'Microvascular angina', 'Syphilitic aortitis', 'Atherosclerotic aortic aneurysm', 'Infective endocard
  - call3: ['Arrhythmogenic right ventricular cardiomyopathy', 'Catecholaminergic polymorphic ventricular tachycardia', 'Long QT sy
- S3 shortlist n=5 gold=True: Acute myocardial infarction, Unstable angina, Prinzmetal's angina, Acute coronary syndrome, Variant angina
- S4 champion: **Acute coronary syndrome** gold=False
- S4 raw (trunc): {"champion": "Acute coronary syndrome", "rationale": "The patient presented with acute, severe precordial chest pain radiating to the left arm, accompanied by dyspnea, dizziness, and sweating, which are classic symptoms of acute coronary syndrome. The initial ECG showed broad-bas

## Backbone v0 (compact)
- S1 key_facts: Patient presented with approximately 20 minutes of acute, severe precordial ches; Chest pain radiated to the left arm; Patient experienced dyspnea, dizziness, and sweating; Patient has a medical history of hypertension, cerebral infarction, diabetes, an; Blood pressure was 188/101 mm Hg; Heart rate was 84 beats/min; Respiratory rate was 20 breaths/min; Serum cardiac troponin I level was <0.05 ng/mL
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['Acute myocardial infarction', 'Unstable angina', 'Variant angina', "Prinzmetal's angina", 'Aortic dissection', 'Pulmon
- S3 shortlist n=5 gold=True: Acute myocardial infarction, Unstable angina, Variant angina, Acute coronary syndrome, Spontaneous coronary artery dissection
- S4 champion: **Acute coronary syndrome** gold=False
- S4 raw (trunc): {"champion": "Acute coronary syndrome", "rationale": "The patient presented with acute, severe precordial chest pain radiating to the left arm, accompanied by dyspnea, dizziness, and sweating, which are classic symptoms of acute coronary syndrome. The initial ECG showed broad-bas

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of acute, severe precordial chest pain radiating to the left arm, accompanied by dyspnea, dizziness, and sweating, is highly suggesti
  - turn1 gold_mention=True diag=
    The patient's symptoms and diagnostic findings, including ECG changes and coronary angiography results, align with Doctor A's assessment, supporting the likelih
  - turn2 gold_mention=True diag=
    The patient's symptoms and diagnostic findings, including ECG changes and coronary angiography results, are consistent with an acute coronary event, supporting 
- supervisor votes=3 top2=['Acute Coronary Syndrome', 'Myocardial Infarction'] gold=True

## Baseline B07
- draft=['Acute Myocardial Infarction (NSTEMI)', 'Unstable Angina'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['A patient in their 60s presented to the emergency department with approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizzines', 'differential diagnosis A patient in their 60s presented to the emergency department with approximately 20 minutes of acute, severe precordial chest pain radiating to their left arm at night, accompanied by dyspnea, dizzines', 'clinical manifestations diagnosis ressure of 188/101 mm Hg, heart rate at 84 beats/min, and respiratory rate at 20 breaths/min. - Laboratory tests: - Serum cardiac troponin I level: <0.05 ng/mL ']
- diagnose=['Acute Myocardial Infarction (NSTEMI)', 'Unstable Angina'] gold=True

## APHHM
- tree_n=41 tree_recall=True
- gold_leaf=B1.1:myocardial infarction parent=B1
- final_n=4 final_recall=True ranking=['myocardial infarction', 'acute coronary syndrome', 'Unstable Angina', 'Myocardial Ischemia']
- human_at1=True fail_mode=final_ok

