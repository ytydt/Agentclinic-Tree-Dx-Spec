# MCR / mcr_v1 / case 2

- **gold**: 5-oxoprolinemia
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=0 B01=0 APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_miss_but_scored_ok` B07=`draft_miss` B01=`rag_miss` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=318; gold_words=2; eponym=False; subtype=False; e7_s2_rank=21; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 75-year-old Caucasian woman was admitted with a prosthetic hip infection 10 days after revision surgery. Her medical history included chronic kidney disease (baseline creatinine 130–150 μmol/L), hypertension, type 2 diabetes, heart failure, chronic obstructive pulmonary disease, and folate deficiency. Home medications included aspirin, bisoprolol, atorvastatin, furosemide, gliclazide, pantoprazole, folic acid, inhaled bronchodilators, and as-needed oxycodone. On admission she began intravenous...

## Backbone e7
- S1 key_facts: 75-year-old woman with multiple comorbidities; Recent prosthetic hip infection and revision surgery; Developed altered mental status on hospital day 10; Glasgow Coma Scale score of 12; Vital signs: temperature 36.2°C, blood pressure 145/66 mmHg, pulse 80/min, respi; Laboratory studies: sodium 142 mmol/L, potassium 3.5 mmol/L, chloride 118 mmol/L; Arterial blood gas: pH 7.18, pCO2 1.7 kPa, pO2 16.7 kPa, bicarbonate 8.3 mmol/L,; Corrected anion gap of 25 mmol/L
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Lactic acidosis', 'Diabetic ketoacidosis', 'Alcoholic ketoacidosis', 'Salicylate toxicity', 'Ethylene glycol poisoning
  - call2: ['5-Oxoprolinemia', 'Glycolic acid poisoning', 'D-Lactic acidosis', 'Fructose-1,6-bisphosphatase deficiency', 'Phenformi
  - call3: ['Krebs cycle disorder', 'Fatty acid oxidation disorder', 'Mitochondrial trifunctional protein deficiency', 'Very long-c
- S3 shortlist n=5 gold=False: Lactic acidosis, Sepsis-induced acidosis, Uremic acidosis, Diabetic ketoacidosis, Pyroglutamic acidemia
- S4 champion: **Pyroglutamic acidemia** gold=False
- S4 raw (trunc): {"champion": "Pyroglutamic acidemia", "rationale": "The patient's high anion gap metabolic acidosis with a corrected anion gap of 25 mmol/L, low bicarbonate levels, and normal lactic acid levels, along with the use of acetaminophen and the presence of a mildly elevated osmolar ga

## Backbone v0 (compact)
- S1 key_facts: 75-year-old woman with prosthetic hip infection; Recent revision surgery; Chronic kidney disease with baseline creatinine 130-150 μmol/L; Hypertension, type 2 diabetes, heart failure, chronic obstructive pulmonary dise; Home medications included aspirin, bisoprolol, atorvastatin, furosemide, gliclaz; Intravenous vancomycin and acetaminophen started on admission; Glasgow Coma Scale score of 12; Temperature 36.2°C, blood pressure 145/66 mmHg, pulse 80/min, respiratory rate 2
- S2 mode=None k=None pool_n=18 gold_in_s2=False
  - pool gold matches: []
  - pool head: Lactic acidosis, Diabetic ketoacidosis, Alcoholic ketoacidosis, Salicylate toxicity, Ethylene glycol poisoning, Methanol poisoning, Uremic acidosis, Severe sepsis
- S3 shortlist n=5 gold=False: Lactic acidosis, Pyroglutamic acidemia, Uremic acidosis, Severe sepsis, Vancomycin-induced nephrotoxicity
- S4 champion: **Pyroglutamic acidemia** gold=False
- S4 raw (trunc): {"champion": "Pyroglutamic acidemia", "rationale": "The patient's high anion gap metabolic acidosis with a corrected anion gap of 25 mmol/L, low bicarbonate level, and normal lactate level is suggestive of pyroglutamic acidemia, especially given the patient's history of chronic k

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation with drowsiness, confusion, disorientation, and hyperventilation, along with the laboratory findings of severe metabolic acidosis, su
  - turn1 gold_mention=False diag=
    The patient's severe metabolic acidosis with a high anion gap, elevated osmolar gap, and absence of significant lactic acid elevation or ketosis, along with rec
  - turn2 gold_mention=False diag=
    The patient's presentation and laboratory findings, including severe metabolic acidosis with a high anion gap and elevated osmolar gap, in the context of recent
- supervisor votes=3 top2=['Pyroglutamic acidemia', 'Lactic acidosis'] gold=False

## Baseline B07
- draft=['Metabolic Acidosis due to Vancomycin-Induced D-Lactic Acidosis', 'Metabolic Acidosis due to Other Causes of High Anion Gap (e.g., Methanol or Ethylene Glycol Toxicity)'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['causes of high anion gap metabolic acidosis', 'vancomycin side effects', 'lactic acidosis differential diagnosis', 'elevated osmolar gap causes']
- diagnose=['Metabolic Acidosis due to Vancomycin-Induced D-Lactic Acidosis', 'Metabolic Acidosis due to Other Causes of High Anion Gap (e.g., Methanol or Ethylene Glycol Toxicity)'] gold=False

## Baseline B01
- queries=['causes of high anion gap metabolic acidosis in elderly patients', 'vancomycin-induced metabolic acidosis', 'lactic acidosis differential diagnosis', 'causes of elevated osmolar gap in critically ill patients']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Lactic acidosis', 'Diabetic ketoacidosis'] gold=False

## APHHM
- tree_n=18 tree_recall=False
- gold_leaf=None
- final_n=2 final_recall=False ranking=['Lactic acidosis', 'Metabolic Acidosis']
- human_at1=False fail_mode=tree_miss

