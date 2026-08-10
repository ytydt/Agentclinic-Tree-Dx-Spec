# MCR / mcr_v1 / case 82

- **gold**: Euglycemic diabetic ketoacidosis
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_ok` B01=`gen_ok` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=s3_hit_s4_miss; B07=diagnose_ok
- **covariates**: vig_words=300; gold_words=3; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 74-year-old man with type 2 diabetes mellitus, hypertension, ischemic stroke, peripheral arterial disease, bilateral nonobstructive renal artery stenosis, chronic right internal carotid occlusion, seizures, and vascular dementia was transferred from a nursing home because of decreased oral intake and dehydration for at least one week. En route, his blood pressure was 94/49 mmHg, and he received 1 L of intravenous normal saline. On arrival, he was somnolent and oriented only to self. His vital ...

## Backbone e7
- S1 key_facts: Patient has type 2 diabetes mellitus; Patient has hypertension; Patient has ischemic stroke and peripheral arterial disease; Patient has chronic right internal carotid occlusion; Patient has seizures and vascular dementia; Patient was transferred from a nursing home due to decreased oral intake and deh; Patient received 1 L of intravenous normal saline en route; Patient's blood pressure was 94/49 mmHg initially and 101/59 mmHg on arrival
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Diabetic ketoacidosis', 'Lactic acidosis', 'Uremic acidosis', 'Starvation ketosis', 'Alcoholic ketoacidosis', 'Salicyl
  - call2: ['Chronic kidney disease-mineral and bone disorder', 'Tumor lysis syndrome', '5-Oxoprolinuria', 'Methylmalonic acidemia'
  - call3: ['Ketosis due to growth hormone deficiency', 'Ketosis due to glucagonoma', 'Ketosis due to pheochromocytoma', 'Acidosis 
- S3 shortlist n=5 gold=True: Diabetic ketoacidosis, Lactic acidosis, Uremic acidosis, Severe dehydration, Hyperglycemic hyperosmolar nonketotic syndrome
- S4 champion: **Lactic acidosis** gold=False
- S4 raw (trunc): {"champion": "Lactic acidosis", "rationale": "The patient's high lactate level (4.4 mmol/L) and severe metabolic acidosis (venous pH 7.09, anion gap 31) are more indicative of lactic acidosis, especially given the context of decreased oral intake, dehydration, and the lack of sig

## Backbone v0 (compact)
- S1 key_facts: Patient has type 2 diabetes mellitus; Patient has hypertension; Patient has ischemic stroke and peripheral arterial disease; Patient has chronic right internal carotid occlusion; Patient has seizures and vascular dementia; Patient was transferred from a nursing home due to decreased oral intake and deh; Patient received 1 L of intravenous normal saline en route; Patient's blood pressure was 94/49 mmHg initially and 101/59 mmHg on arrival
- S2 mode=None k=None pool_n=19 gold_in_s2=True
  - pool gold matches: ['Diabetic ketoacidosis']
  - pool head: Diabetic ketoacidosis, Lactic acidosis, Uremic acidosis, Starvation ketosis, Alcoholic ketoacidosis, Salicylate toxicity, Methanol toxicity, Ethylene glycol toxicity
- S3 shortlist n=5 gold=True: Diabetic ketoacidosis, Lactic acidosis, Uremic acidosis, Prerenal acute kidney injury, Starvation ketosis
- S4 champion: **Uremic acidosis** gold=False
- S4 raw (trunc): {"champion": "Uremic acidosis", "rationale": "The patient's severe metabolic acidosis with an anion gap of 31, elevated creatinine of 10.2 mg/dL, and hyperkalemia are more consistent with uremic acidosis, especially given the context of acute renal failure and dehydration.", "rej

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with severe metabolic acidosis, elevated anion gap, and elevated β-hydroxybutyrate level is highly suggestive of diabetic ketoacidosi
  - turn1 gold_mention=True diag=
    The patient's severe metabolic acidosis, elevated anion gap, and elevated β-hydroxybutyrate level support the top diagnosis of diabetic ketoacidosis, with lacti
  - turn2 gold_mention=True diag=
    The patient's presentation with severe metabolic acidosis, elevated anion gap, and elevated β-hydroxybutyrate level, along with recent empagliflozin initiation,
- supervisor votes=3 top2=['Diabetic Ketoacidosis', 'Lactic Acidosis'] gold=True

## Baseline B07
- draft=['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['diabetic ketoacidosis vs. euglycemic diabetic ketoacidosis', 'lactic acidosis in diabetic patients', 'empagliflozin side effects', 'severe metabolic acidosis causes']
- diagnose=['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis'] gold=True

## Baseline B01
- queries=['diabetic ketoacidosis vs. starvation ketoacidosis in elderly patients', 'euglycemic diabetic ketoacidosis diagnosis and treatment', 'lactic acidosis and acute renal failure in patients with type 2 diabetes', 'SGLT2 inhibitor-associated ketoacidosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Euglycemic Diabetic Ketoacidosis', 'Lactic Acidosis'] gold=True

## APHHM
- tree_n=25 tree_recall=True
- gold_leaf=B1.1:Diabetic Ketoacidosis parent=B1
- final_n=1 final_recall=True ranking=['Diabetic Ketoacidosis']
- human_at1=True fail_mode=final_ok

