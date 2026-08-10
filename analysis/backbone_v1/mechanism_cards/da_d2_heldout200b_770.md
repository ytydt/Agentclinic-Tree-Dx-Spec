# DA / d2_heldout200b / case 770

- **gold**: Leptospirosis with severe pneumonia, acute kidney injury, and acute liver injury
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 64-year-old man presented to the Emergency Department with complaints of hemoptysis, fever, and difficulty exhaling that stretched for five days. The patient had previous history of hypertension and field work.

Upon admission:- Temperature: 37.8°C- Respiratory rate: 22/min- Blood pressure: 144/88 mmHg- Dyspnea presentSix hours after initial treatment:- Temperature increased to 40°C- Respiratory rate increased to 28/min- Blood pressure dropped to 80/50 mmHg- Patient required intubation

Laboratory Tests:- Complete blood count, liver function, and kidney function tests were performed (specific values available in Table 1)- Blood gas analysis showed type II respiratory failure- Next Generation Sequencing (mNGS) testing performed on blood samplesImaging Studies:1. Initial Chest CT:- Title: High-resolution CT images on admission- Description: Both lungs scattered with exudative lesions2. Chest X-ray Series:- First day: Showed diffuse inflammatory changes in both lungs- Tenth day: Follow-up chest X-ray- Follow-up CT: Showed resolution of exudative fociOther Diagnostic Procedures:- Fibronchoscopy findings: Copious amount of bloody sputum in each lung segment

What is the most likely di…

## Options
- A: Leptospirosis with pulmonary involvement
- B: Severe Pneumonia with Septic Shock
- C: Severe Community-Acquired Pneumonia
- D: Leptospirosis with severe pneumonia, acute kidney injury, and acute liver injury **←gold**

## Backbone e7

- S2 n=56 gold_rank=21
  - clusters: gold=1 near=23 other=32
- S3 shortlist (5):
  - [near] Influenza pneumonia
  - [near] Pneumococcal pneumonia
  - [other] Goodpasture syndrome
  - [other] Pulmonary embolism
  - [near] Severe acute respiratory syndrome
    - why_kept(Influenza pneumonia): Patient presented with fever, hemoptysis, and difficulty exhaling, which are consistent with influenza pneumonia
    - why_kept(Pneumococcal pneumonia): Patient's symptoms and laboratory results, such as type II respiratory failure, are consistent with pneumococcal pneumonia
    - why_kept(Goodpasture syndrome): Patient's hemoptysis and renal function tests suggest a possible autoimmune component, making Goodpasture syndrome a plausible diagnosis
    - why_kept(Pulmonary embolism): Patient's sudden deterioration and requirement for intubation could be indicative of a pulmonary embolism
    - why_kept(Severe acute respiratory syndrome): Patient's symptoms, such as fever and difficulty exhaling, are consistent with severe acute respiratory syndrome, and the recent history of field work could be a risk factor
- S4 champion: **Goodpasture syndrome** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms of hemoptysis, fever, and difficulty exhaling, along with the presence of copious amounts of bloody sputum in each lung segment, are consistent with Goodpasture syndrome, an autoimmune disease that can cause pulmonary hemorrhage and renal failure.
- S4 rejected:
  - [near] Influenza pneumonia: While influenza pneumonia can cause respiratory symptoms, it does not typically cause hemoptysis or the rapid deterioration seen in this patient.
  - [near] Pneumococcal pneumonia: Pneumococcal pneumonia can cause respiratory symptoms and fever, but the presence of hemoptysis and bloody sputum is not typical.
  - [other] Pulmonary embolism: Pulmonary embolism can cause difficulty exhaling and respiratory distress, but it does not typically cause hemoptysis or fever.
  - [near] Severe acute respiratory syndrome: Severe acute respiratory syndrome can cause respiratory symptoms and fever, but it does not typically cause hemoptysis or the specific pattern of lung lesions seen in this patient.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)', 'Influenza', 'Tuberculosis', 'Pulmonary Embolism', 'Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)', 'Influenza']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)']
- diagnose: ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)']
- queries: ['hemoptysis and fever differential diagnosis', 'exudative lesions on chest CT causes', 'type II respiratory failure causes', 'mNGS testing in respiratory infections']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

