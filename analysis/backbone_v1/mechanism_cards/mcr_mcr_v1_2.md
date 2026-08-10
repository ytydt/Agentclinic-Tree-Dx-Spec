# MCR / mcr_v1 / case 2

- **gold**: 5-oxoprolinemia
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=0 B01=0 APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 75-year-old Caucasian woman was admitted with a prosthetic hip infection 10 days after revision surgery. Her medical history included chronic kidney disease (baseline creatinine 130–150 μmol/L), hypertension, type 2 diabetes, heart failure, chronic obstructive pulmonary disease, and folate deficiency. Home medications included aspirin, bisoprolol, atorvastatin, furosemide, gliclazide, pantoprazole, folic acid, inhaled bronchodilators, and as-needed oxycodone. On admission she began intravenous vancomycin and acetaminophen for pain.

On hospital day 10 she developed drowsiness, confusion, disorientation, and hyperventilation. Examination showed a Glasgow Coma Scale score of 12. Temperature was 36.2°C, blood pressure 145/66 mmHg, pulse 80/min, respiratory rate 24/min, and oxygen saturation 99% on room air. Cardiopulmonary and neurologic examinations were otherwise unremarkable.

Laboratory studies revealed:  
- Sodium 142 mmol/L, potassium 3.5 mmol/L, chloride 118 mmol/L, bicarbonate 5 mmol/L  
- Blood urea nitrogen 8 mmol/L, creatinine 150 μmol/L (baseline)  
- Hemoglobin 10.0 g/dL, neutrophils 16.5×10^9/L, platelets 485×10^9/L  
- Albumin 17 g/L  
Arterial blood gas: pH 7.18, pCO…

## Backbone e7

- S2 n=48 gold_rank=21
  - clusters: gold=1 near=0 other=47
- S3 shortlist (5):
  - [other] Lactic acidosis
  - [other] Sepsis-induced acidosis
  - [other] Uremic acidosis
  - [other] Diabetic ketoacidosis
  - [other] Pyroglutamic acidemia
    - why_kept(Lactic acidosis): Elevated anion gap and metabolic acidosis
    - why_kept(Sepsis-induced acidosis): Recent prosthetic hip infection and revision surgery
    - why_kept(Uremic acidosis): Chronic kidney disease and elevated creatinine
    - why_kept(Diabetic ketoacidosis): Type 2 diabetes and metabolic acidosis
    - why_kept(Pyroglutamic acidemia): Elevated anion gap and metabolic acidosis, potential for acetaminophen-related toxicity
- S4 champion: **Pyroglutamic acidemia** cluster=other jaccard=0.00
- S4 rationale: The patient's high anion gap metabolic acidosis with a corrected anion gap of 25 mmol/L, low bicarbonate levels, and normal lactic acid levels, along with the use of acetaminophen and the presence of a mildly elevated osmolar gap, are consistent with pyroglutamic acidemia, especially given the patient's receipt of acetaminophen which can lead to this condition through its metabolite
- S4 rejected:
  - [other] Lactic acidosis: Lactic acid level is normal at 0.7 mmol/L
  - [other] Sepsis-induced acidosis: There is no clear evidence of sepsis, and the patient's temperature and white blood cell count do not strongly support this diagnosis
  - [other] Uremic acidosis: The patient's renal function, as indicated by creatinine levels, does not appear to have worsened significantly enough to explain the degree of acidosis
  - [other] Diabetic ketoacidosis: Blood ketones are <0.2 mmol/L, which does not support this diagnosis

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Pyroglutamic acidemia', 'Lactic acidosis']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Diabetic ketoacidosis', 'Lactic acidosis', 'Chronic kidney disease with metabolic acidosis', 'Salicylate toxicity', 'Pyroglutamic acidemia', 'Pyroglutamic acidemia', 'Lactic acidosis', 'Chronic kidney disease with metabolic acidosis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Metabolic Acidosis due to Vancomycin-Induced D-Lactic Acidosis', 'Metabolic Acidosis due to Other Causes of High Anion Gap (e.g., Methanol or Ethylene Glycol Toxicity)']
- diagnose: ['Metabolic Acidosis due to Vancomycin-Induced D-Lactic Acidosis', 'Metabolic Acidosis due to Other Causes of High Anion Gap (e.g., Methanol or Ethylene Glycol Toxicity)']
- queries: ['causes of high anion gap metabolic acidosis', 'vancomycin side effects', 'lactic acidosis differential diagnosis', 'elevated osmolar gap causes']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Lactic acidosis', 'Diabetic ketoacidosis']
- queries: ['causes of high anion gap metabolic acidosis in elderly patients', 'vancomycin-induced metabolic acidosis', 'lactic acidosis differential diagnosis', 'causes of elevated osmolar gap in critically ill patients']
- n_chunks=12

## APHHM
- tree_n=18 final_n=2
- final: ['Lactic acidosis', 'Metabolic Acidosis']
- tree gold_cluster_n=0 final gold=False

