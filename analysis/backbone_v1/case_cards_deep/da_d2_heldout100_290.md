# DA / d2_heldout100 / case 290

- **gold**: Wellens syndrome with critical left anterior descending coronary artery stenosis
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=197; gold_words=10; eponym=False; subtype=True; e7_s2_rank=None; mapper_rescue=True
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A patient in their 50s presented with intermittent compression-like chest pain of 1 day's duration, lasting several minutes each time, occurring during activities and relieved by rest. Medical history includes hypertension and diabetes for 8 years with irregular medication compliance.  Blood pressure: 181/93 mm HgHeart rate: 81 beats per minute Respiratory rate: 20 breaths per minuteBlood oxygen saturation: 96% on room airOther physical examination findings were normal  - ECG Findings:  First EC...

## Options
  - A: Myocardial Ischemia due to Hypertensive Heart Disease
  - B: Coronary Artery Disease with Prior Myocardial Infarction
  - C: Wellens syndrome with critical left anterior descending coronary artery stenosis
  - D: Unstable Angina

## Backbone e7
- S1 key_facts: Patient in their 50s; Chest pain duration of 1 day; Chest pain lasts several minutes and occurs during activities; Chest pain relieved by rest; History of hypertension and diabetes for 8 years; Irregular medication compliance; Blood pressure: 181/93 mm Hg; Heart rate: 81 beats per minute
- S2 mode=complement k=3 pool_n=48 gold_in_s2=False
  - call1: ['Acute Coronary Syndrome', 'ST-Elevation Myocardial Infarction', 'Non-ST-Elevation Myocardial Infarction', 'Unstable An
  - call2: ['Coronary Artery Embolism', 'Spontaneous Coronary Artery Dissection', 'Fibromuscular Dysplasia', 'Ehlers-Danlos Syndrom
  - call3: ['Coronary Artery Thrombosis', 'Cardiac Sarcoidosis', 'Churg-Strauss Syndrome', 'Hypertrophic Cardiomyopathy', 'Left Ven
- S3 shortlist n=5 gold=False: Acute Coronary Syndrome, Unstable Angina, Non-ST-Elevation Myocardial Infarction, Variant Angina, Coronary Artery Thrombosis
- S4 champion: **Variant Angina** gold=False
- S4 raw (trunc): {"champion": "Variant Angina", "rationale": "The patient's chest pain is characterized by intermittent compression-like pain during activities, relieved by rest, and ECG changes during pain, including upright T-waves and inverted U-waves, which are consistent with variant angina,

## Backbone v0 (compact)
- S1 key_facts: Patient in their 50s; Chest pain duration of 1 day; Chest pain lasts several minutes and occurs during activities; Chest pain relieved by rest; History of hypertension and diabetes for 8 years; Irregular medication compliance; Blood pressure 181/93 mm Hg; Heart rate 81 beats per minute
- S2 mode=single k=1 pool_n=16 gold_in_s2=False
  - call1: ['Acute Coronary Syndrome', 'Myocardial Infarction', 'Unstable Angina', 'Variant Angina', "Prinzmetal's Angina", 'Cardia
- S3 shortlist n=5 gold=False: Acute Coronary Syndrome, Myocardial Infarction, Unstable Angina, Variant Angina, Vasospastic Angina
- S4 champion: **Variant Angina** gold=False
- S4 raw (trunc): {"champion": "Variant Angina", "rationale": "The patient's chest pain is characterized by intermittent compression-like pain that occurs during activities and is relieved by rest, with ECG changes showing deeply inverted T-waves at baseline that become upright during chest pain, 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms of intermittent chest pain, ECG changes, and total occlusion at the ostium of the left anterior descending coronary artery are highly sug
  - turn1 gold_mention=True diag=
    The patient's presentation of intermittent chest pain, significant ECG changes, and the finding of total occlusion at the ostium of the left anterior descending
  - turn2 gold_mention=True diag=
    The patient's symptoms and diagnostic findings, including total occlusion of the left anterior descending coronary artery and dynamic ECG changes, align with th
- supervisor votes=3 top2=['Acute Coronary Syndrome', 'Myocardial Infarction'] gold=False

## Baseline B07
- draft=['Coronary Artery Disease (CAD) with Angina Pectoris', 'Vasospastic or Variant Angina'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['chest pain diagnosis', 'ECG T-wave inversion', 'coronary artery occlusion symptoms']
- diagnose=['Coronary Artery Disease (CAD) with Angina Pectoris', 'Vasospastic or Variant Angina'] gold=False

## APHHM
- tree_n=40 tree_recall=False
- gold_leaf=None
- final_n=5 final_recall=False ranking=['Myocardial Infarction', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome', 'Acute Coronary Syndrome']
- human_at1=False fail_mode=tree_miss

