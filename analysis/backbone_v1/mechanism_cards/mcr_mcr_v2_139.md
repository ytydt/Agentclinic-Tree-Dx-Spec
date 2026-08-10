# MCR / mcr_v2 / case 139

- **gold**: type 2 autoimmune pancreatitis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 67‐year‐old man with a 3‐year history of type 2 diabetes mellitus managed with metformin, glimepiride, and a prior percutaneous coronary intervention for acute myocardial infarction 2 months earlier was referred for treatment of newly diagnosed extensive ulcerative colitis. He had a 40‐year smoking history but had quit after his myocardial infarction. He reported four episodes of bloody diarrhea daily but denied abdominal pain or fever. On admission for a 2‐week educational trial of a plant‐based diet, his body weight was 69 kg and physical examination was unremarkable. Initial laboratory studies showed normal white‐cell count, bilirubin, and liver function tests. Ten days after admission, plasma glucose rose from 258 mg/dL to 449 mg/dL and hemoglobin A1c increased from 7.3% to 8.0%. Urinalysis showed no proteinuria but microalbuminuria of 50.7 mg/day. Anti–glutamic acid decarboxylase antibodies were negative. Both serum amylase and lipase were elevated. Contrast‐enhanced CT and MR cholangiopancreatography demonstrated swelling of the pancreas with a peripheral rim and slight narrowing of the main pancreatic duct. Serum IgG4 was 36.0 mg/dL (reference range, 4.5–117 mg/dL).

What …

## Backbone e7

- S2 n=52 gold_rank=5
  - clusters: gold=1 near=9 other=42
- S3 shortlist (5):
  - [gold] Autoimmune pancreatitis
  - [near] IgG4-related pancreatitis
  - [near] Acute pancreatitis
  - [near] Chronic pancreatitis
  - [other] Pancreatic involvement in IgG4-related disease with inflammatory bowel disease
    - why_kept(Autoimmune pancreatitis): Elevated serum IgG4 and pancreatic swelling with duct narrowing
    - why_kept(IgG4-related pancreatitis): Elevated serum IgG4 and recent onset of hyperglycemia
    - why_kept(Acute pancreatitis): Pancreatic swelling and elevated serum amylase and lipase
    - why_kept(Chronic pancreatitis): History of type 2 diabetes mellitus and pancreatic duct narrowing
    - why_kept(Pancreatic involvement in IgG4-related disease with inflammatory bowel disease): Elevated serum IgG4, pancreatic swelling, and history of ulcerative colitis
- S4 champion: **IgG4-related pancreatitis** cluster=near jaccard=0.20
- S4 rationale: Elevated serum IgG4, pancreatic swelling, and duct narrowing on imaging studies are consistent with IgG4-related pancreatitis, and the presence of extensive ulcerative colitis suggests a possible association with IgG4-related disease
- S4 rejected:
  - [gold] Autoimmune pancreatitis: While similar to IgG4-related pancreatitis, the specific diagnosis of autoimmune pancreatitis is not as strongly supported by the combination of elevated IgG4 and imaging findings
  - [near] Acute pancreatitis: The lack of abdominal pain and normal white-cell count do not support a diagnosis of acute pancreatitis
  - [near] Chronic pancreatitis: The absence of long-term pancreatic damage or calcifications on imaging makes chronic pancreatitis less likely
  - [other] Pancreatic involvement in IgG4-related disease with inflammatory bowel disease: While this option considers the patient's inflammatory bowel disease, IgG4-related pancreatitis is a more specific diagnosis that directly addresses the pancreatic findings

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Autoimmune Pancreatitis', 'Chronic Pancreatitis']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Autoimmune Pancreatitis', 'Chronic Pancreatitis', 'Ulcerative Colitis', 'Diabetic Ketoacidosis', 'Pancreatic Cancer', 'Autoimmune Pancreatitis', 'Chronic Pancreatitis', 'Pancreatic Cancer']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Autoimmune Pancreatitis', 'IgG4-related Disease']
- diagnose: ['Autoimmune Pancreatitis', 'IgG4-related Disease']
- queries: ['autoimmune pancreatitis', 'IgG4-related disease', 'ulcerative colitis and pancreatitis association']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['IgG4-related pancreatitis', 'Chronic pancreatitis']
- queries: ['diabetes mellitus and pancreatitis', 'ulcerative colitis and pancreatic swelling', 'elevated serum amylase and lipase in diabetes', 'IgG4-related disease and pancreas']
- n_chunks=12

## APHHM
_na_

