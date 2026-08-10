# MCR / mcr_v1 / case 82

- **gold**: Euglycemic diabetic ketoacidosis
- **layer**: `base_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A 74-year-old man with type 2 diabetes mellitus, hypertension, ischemic stroke, peripheral arterial disease, bilateral nonobstructive renal artery stenosis, chronic right internal carotid occlusion, seizures, and vascular dementia was transferred from a nursing home because of decreased oral intake and dehydration for at least one week. En route, his blood pressure was 94/49 mmHg, and he received 1 L of intravenous normal saline. On arrival, he was somnolent and oriented only to self. His vital signs were: temperature 37.1 °C, blood pressure 101/59 mmHg, heart rate 105 beats per minute, respiratory rate 17 breaths per minute, and oxygen saturation 100% on room air. Examination revealed a sarcopenic-appearing man with dry mucous membranes and no acute distress.

Initial laboratory results were notable for acute renal failure and severe metabolic acidosis: sodium 145 mEq/L, potassium 6.6 mEq/L, blood urea nitrogen 207 mg/dL, creatinine 10.2 mg/dL (baseline 1.1 mg/dL), glucose 185 mg/dL, chloride 106 mEq/L, bicarbonate 8 mEq/L, anion gap 31, venous pH 7.09, and lactate 4.4 mmol/L. A urinary catheter revealed trace ketones on repeat urinalysis. A β-hydroxybutyrate level was elevated at…

## Backbone e7

- S2 n=48 gold_rank=1
  - clusters: gold=1 near=2 other=45
- S3 shortlist (5):
  - [gold] Diabetic ketoacidosis
  - [other] Lactic acidosis
  - [other] Uremic acidosis
  - [other] Severe dehydration
  - [other] Hyperglycemic hyperosmolar nonketotic syndrome
    - why_kept(Diabetic ketoacidosis): Patient has type 2 diabetes mellitus and severe metabolic acidosis with elevated β-hydroxybutyrate level
    - why_kept(Lactic acidosis): Patient has severe metabolic acidosis with elevated lactate level and acute renal failure
    - why_kept(Uremic acidosis): Patient has acute renal failure with elevated creatinine and blood urea nitrogen levels
    - why_kept(Severe dehydration): Patient was transferred from a nursing home due to decreased oral intake and dehydration
    - why_kept(Hyperglycemic hyperosmolar nonketotic syndrome): Patient has type 2 diabetes mellitus and severe hyperglycemia with hyperosmolar state
- S4 champion: **Lactic acidosis** cluster=other jaccard=0.00
- S4 rationale: The patient's high lactate level (4.4 mmol/L) and severe metabolic acidosis (venous pH 7.09, anion gap 31) are more indicative of lactic acidosis, especially given the context of decreased oral intake, dehydration, and the lack of significant ketones in the urine.
- S4 rejected:
  - [gold] Diabetic ketoacidosis: The patient has only trace ketones in the urine and a β-hydroxybutyrate level, while elevated, does not fully explain the severity of the metabolic acidosis.
  - [other] Uremic acidosis: Although the patient has acute renal failure, the high lactate level and the presence of other signs such as dry mucous membranes and tachycardia point more towards lactic acidosis as the primary cause of metabolic acidosis.
  - [other] Severe dehydration: While dehydration is present, it does not directly cause the severe metabolic acidosis observed in this patient.
  - [other] Hyperglycemic hyperosmolar nonketotic syndrome: The patient's glucose level, although elevated, is not high enough to be the primary cause of the observed metabolic disturbances, and the presence of significant lactic acidosis points away from this diagnosis.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Diabetic Ketoacidosis', 'Lactic Acidosis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Diabetic Ketoacidosis', 'Severe Dehydration', 'Acute Renal Failure', 'Lactic Acidosis', 'Sepsis', 'Diabetic Ketoacidosis', 'Lactic Acidosis', 'Severe Dehydration']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis']
- diagnose: ['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis']
- queries: ['diabetic ketoacidosis vs. euglycemic diabetic ketoacidosis', 'lactic acidosis in diabetic patients', 'empagliflozin side effects', 'severe metabolic acidosis causes']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis']
- queries: ['diabetic ketoacidosis vs. starvation ketoacidosis in elderly patients', 'euglycemic diabetic ketoacidosis diagnosis and treatment', 'lactic acidosis and acute renal failure in patients with type 2 diabetes', 'SGLT2 inhibitor-associated ketoacidosis']
- n_chunks=12

## APHHM
- tree_n=25 final_n=1
- final: ['Diabetic Ketoacidosis']
- tree gold_cluster_n=5 final gold=True

