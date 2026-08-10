# DA / d2_heldout100 / case 372

- **gold**: Elevated Lipoprotein(a) causing discordance between direct and calculated LDL cholesterol measurements
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 47-year-old African American man with a medical history significant for hypertension, type 2 diabetes, and gastroesophageal reflux disease. He had been previously tried on various statins but experienced hip pain and elevated liver enzymes.

No specific physical examination findings were reported in the case.

- Laboratory Tests (December 2013):    * Fasting lipid profile with LDL-C: 232 mg/dL (off lipid-lowering agents)      - Serial Laboratory Tests:    * June 2014: Direct LDL-C: 113 mg/dL    * October 2015: Direct LDL-C: 115 mg/dL    * December 2015: Calculated LDL-C: 170 mg/dL      - Additional Laboratory Tests (April & June 2016):    * Fasting lipid profiles    * Direct and calculated LDL-C measurements    * Apolipoprotein B (Apo B)    * Lipoprotein (a) [Lp(a)]      Table Reference: The case mentions a table showing lipid values demonstrating marked difference between direct and calculated LDL-C levels

What is the most likely diagnosis?

Options:
A. Heterozygous familial hypercholesterolemia
B. Elevated Lipoprotein(a) causing discordance between direct and calculated LDL cholesterol measurements
C. Familial combined hyperlipidemia
D. Lipoprotein(a) Hyperlipoproteinemia


## Options
- A: Heterozygous familial hypercholesterolemia
- B: Elevated Lipoprotein(a) causing discordance between direct and calculated LDL cholesterol measurements **←gold**
- C: Familial combined hyperlipidemia
- D: Lipoprotein(a) Hyperlipoproteinemia

## Backbone e7

- S2 n=47 gold_rank=None
  - clusters: gold=0 near=3 other=44
- S3 shortlist (5):
  - [other] Familial hypercholesterolemia
  - [near] Lipoprotein(a) hyperlipoproteinemia
  - [other] Familial combined hyperlipidemia
  - [other] Polygenic hypercholesterolemia
  - [other] Secondary hyperlipidemia due to hypothyroidism
    - why_kept(Familial hypercholesterolemia): Elevated LDL-C levels and variable response to statins
    - why_kept(Lipoprotein(a) hyperlipoproteinemia): Measured Lipoprotein (a) [Lp(a)] and elevated LDL-C levels
    - why_kept(Familial combined hyperlipidemia): Combined hyperlipidemia and variable response to treatment
    - why_kept(Polygenic hypercholesterolemia): Elevated LDL-C levels and family history of hyperlipidemia
    - why_kept(Secondary hyperlipidemia due to hypothyroidism): Potential secondary cause of hyperlipidemia given patient's medical history
- S4 champion: **Lipoprotein(a) hyperlipoproteinemia** cluster=near jaccard=0.08
- S4 rationale: The patient's significantly elevated LDL-C levels despite normal direct measurements, along with the measurement of Lipoprotein (a) [Lp(a)] in 2016, suggest the presence of Lipoprotein(a) hyperlipoproteinemia, which is characterized by elevated Lp(a) levels and can lead to elevated calculated LDL-C levels due to the inclusion of Lp(a) in the calculation.
- S4 rejected:
  - [other] Familial hypercholesterolemia: While the patient has high LDL-C levels, the presence of other lipid abnormalities and the specific pattern of LDL-C elevation, particularly the discrepancy between direct and calculated LDL-C, does not strongly support this diagnosis alone.
  - [other] Familial combined hyperlipidemia: This condition typically involves a combination of elevated LDL-C and triglycerides, but the information provided focuses primarily on LDL-C and does not give a clear picture of triglyceride levels or other lipid abnormalities characteristic of this condition.
  - [other] Polygenic hypercholesterolemia: While this could be a consideration given the patient's elevated LDL-C, the specific details about the discrepancy between direct and calculated LDL-C levels and the measurement of Lp(a) point more directly to another diagnosis.
  - [other] Secondary hyperlipidemia due to hypothyroidism: There is no mention of hypothyroidism in the patient's medical history or laboratory findings, making this diagnosis less likely without further evidence of thyroid dysfunction.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Familial Hypercholesterolemia', 'Lipid Profile Disorder']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Familial Hypercholesterolemia', 'Statins Intolerance', 'Homozygous Hypercholesterolemia', 'Lipid Profile Disorder', 'Mixed Hyperlipidemia', 'Familial Hypercholesterolemia', 'Lipid Profile Disorder', 'Mixed Hyperlipidemia']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Familial Hypercholesterolemia', 'Polygenic Hypercholesterolemia']
- diagnose: ['Familial Hypercholesterolemia', 'Polygenic Hypercholesterolemia']
- queries: ['LDL-C measurement discrepancies', 'elevated LDL-C causes', 'lipid profile interpretation', 'Apo B and Lp(a) significance']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=20 final_n=2
- final: ['Familial Hypercholesterolemia', 'Dysbetalipoproteinemia']
- tree gold_cluster_n=0 final gold=False

