# DA / d2_heldout200b / case 555

- **gold**: Euglycemic Diabetic Ketoacidosis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 74-year-old woman with hypertension, diabetes mellitus, and chronic kidney disease presented with severe exertional dyspnea. She underwent aortic and mitral valve–replacement surgery. On postoperative day 5, she experienced a bradycardic episode leading to cardiac arrest requiring resuscitation and intubation. She developed progressive acute worsening of renal function complicated by pulmonary edema and hyperkalemia refractory to medical therapy (peak creatinine, 4.42; baseline, 1.5). The patient had not received adequate enteral feeding for 48 hours.

Initial physical examination findings were not explicitly stated in the case report.

Laboratory Tests:
- Serum β-hydroxybutyrate elevated to 1.81 mmol/L from 0.7 mmol/L
- Blood glucose level between 130 and 160 mmol/L
- Normal lactate level
- Normalized blood urea nitrogen
- Persistent anion-gap metabolic acidosis

Imaging Studies:
- Transesophageal echocardiogram
  Title: Initial Cardiac Assessment
  Description: Showed severe mitral regurgitation and moderate aortic stenosis (mean gradient: 23 mm Hg)

Detailed Laboratory Values (Table 1):
- Sodium: 131-137 mmol/L
- Potassium: 4.1-5.2 mmol/L
- Chloride: 97-103 mmol/L
- Bicarbonat…

## Options
- A: Euglycemic Diabetic Ketoacidosis **←gold**
- B: Metabolic Acidosis (Mixed origin)
- C: Starvation ketoacidosis
- D: Starvation Ketosis

## Backbone e7

- S2 n=53 gold_rank=1
  - clusters: gold=2 near=3 other=48
- S3 shortlist (5):
  - [gold] Diabetic ketoacidosis
  - [other] Acute tubular necrosis
  - [near] Starvation ketoacidosis
  - [other] Cardiogenic shock
  - [other] Sepsis
    - why_kept(Diabetic ketoacidosis): Elevated serum β-hydroxybutyrate and blood glucose level, consistent with diabetic ketoacidosis
    - why_kept(Acute tubular necrosis): Progressive acute worsening of renal function and peak creatinine level of 4.42 mg/dL
    - why_kept(Starvation ketoacidosis): Patient had not received adequate enteral feeding for 48 hours, which can lead to starvation ketoacidosis
    - why_kept(Cardiogenic shock): Postoperative cardiac patient with severe mitral regurgitation and moderate aortic stenosis, which can lead to cardiogenic shock
    - why_kept(Sepsis): Patient developed pulmonary edema and hyperkalemia refractory to medical therapy, which can be indicative of sepsis
- S4 champion: **Starvation ketoacidosis** cluster=near jaccard=0.25
- S4 rationale: The patient had not received adequate enteral feeding for 48 hours, and the elevated serum β-hydroxybutyrate level with normal lactate and blood glucose levels between 130 and 160 mmol/L supports this diagnosis
- S4 rejected:
  - [gold] Diabetic ketoacidosis: Blood glucose levels were not high enough to typically cause diabetic ketoacidosis
  - [other] Acute tubular necrosis: While the patient developed acute worsening of renal function, the elevated β-hydroxybutyrate and metabolic acidosis point more towards a diagnosis of starvation ketoacidosis
  - [other] Cardiogenic shock: The patient's cardiac issues, including the bradycardic episode and cardiac arrest, do not fully explain the metabolic derangements
  - [other] Sepsis: There is no clear indication of infection in the provided case report

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Starvation Ketoacidosis', 'Diabetic Ketoacidosis']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Diabetic Ketoacidosis', 'Starvation Ketoacidosis', 'Lactic Acidosis', 'Acute Kidney Injury', 'Metabolic Acidosis', 'Starvation Ketoacidosis', 'Diabetic Ketoacidosis', 'Acute Kidney Injury']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Diabetic Ketoacidosis (DKA) or Starvation Ketoacidosis', 'Acute Kidney Injury (AKI) with Pulmonary Edema and Hyperkalemia']
- diagnose: ['Diabetic Ketoacidosis (DKA) or Starvation Ketoacidosis', 'Acute Kidney Injury (AKI) with Pulmonary Edema and Hyperkalemia']
- queries: ['causes of severe exertional dyspnea in a 74-year-old woman with hypertension, diabetes mellitus, and chronic kidney disease', 'complications of aortic and mitral valve replacement surgery', 'causes of bradycardic episode leading to cardiac arrest', 'causes of progressive acute worsening of renal function complicated by pulmonary edema and hyperkalemia']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

