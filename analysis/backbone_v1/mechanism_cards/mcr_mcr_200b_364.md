# MCR / mcr_200b / case 364

- **gold**: acute interstitial nephritis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 81-year-old Asian man with erectile dysfunction, CKD stage 3a (baseline creatinine 1.4 mg/dL, eGFR 47 mL/min/1.73 m2), hypertension, hyperlipidemia, coronary artery disease, gout on long-term allopurinol, and osteoarthritis presented with one month of generalized edema and a 9.1 kg weight gain. Two weeks before admission his creatinine rose to 1.9 mg/dL with nephrotic-range proteinuria (14.7 mg/mg). He noted an acute increase in peripheral and facial edema four days after a single sildenafil dose. His only new medication was sildenafil; he denied recent NSAID use.  

On admission: BP 144/70 mmHg, exam notable for diffuse bilateral lower extremity edema; cardiac and lung exams unremarkable. Chest radiograph showed small bilateral pleural effusions. Renal ultrasound was normal without hydronephrosis. Echocardiogram: EF 68% with normal structure.  

Laboratory studies: WBC 5.4 × 10^9/L with 5.6% eosinophils; serum BUN 48 mg/dL; creatinine 3.7 mg/dL; albumin 2.6 g/dL. Urinalysis: specific gravity 1.020, 4+ blood, 4+ protein. Sediment: 0–2 granular casts/high-power field, 0–5 RBCs/hpf, 0–1 WBC/hpf.

What is the most likely diagnosis?

Options:
A. acute interstitial nephritis
B. Multi…

## Backbone e7

- S2 n=47 gold_rank=13
  - clusters: gold=2 near=1 other=44
- S3 shortlist (5):
  - [other] Nephrotic Syndrome due to Sildenafil
  - [gold] Allopurinol-induced Acute Interstitial Nephritis
  - [other] Minimal Change Disease
  - [other] Focal Segmental Glomerulosclerosis
  - [other] Membranous Nephropathy
    - why_kept(Nephrotic Syndrome due to Sildenafil): Recent sildenafil use and development of nephrotic-range proteinuria
    - why_kept(Allopurinol-induced Acute Interstitial Nephritis): Long-term allopurinol use and acute kidney injury
    - why_kept(Minimal Change Disease): Nephrotic-range proteinuria and generalized edema
    - why_kept(Focal Segmental Glomerulosclerosis): Nephrotic-range proteinuria and chronic kidney disease
    - why_kept(Membranous Nephropathy): Nephrotic-range proteinuria and presence of granular casts in urinalysis
- S4 champion: **Nephrotic Syndrome due to Sildenafil** cluster=other jaccard=0.00
- S4 rationale: The patient's recent use of sildenafil and the subsequent development of nephrotic-range proteinuria and acute increase in edema suggest a causal relationship between sildenafil use and the patient's renal symptoms.
- S4 rejected:
  - [gold] Allopurinol-induced Acute Interstitial Nephritis: The patient has been on long-term allopurinol without previous issues, making it less likely to be the cause of the current renal symptoms.
  - [other] Minimal Change Disease: There is no specific evidence in the vignette to support this diagnosis, such as a history of allergies or recent infections.
  - [other] Focal Segmental Glomerulosclerosis: This condition is a common cause of nephrotic syndrome, but the temporal relationship between sildenafil use and the onset of symptoms makes it a less likely explanation.
  - [other] Membranous Nephropathy: There is no specific evidence in the vignette to support this diagnosis, such as a history of autoimmune disorders or infections.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Acute Interstitial Nephritis', 'Minimal Change Disease']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Minimal Change Disease', 'Focal Segmental Glomerulosclerosis', 'Membranous Nephropathy', 'Nephrotic Syndrome', 'Acute Interstitial Nephritis', 'Acute Interstitial Nephritis', 'Minimal Change Disease', 'Focal Segmental Glomerulosclerosis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Sildenafil-induced nephrotic syndrome', 'Minimal change disease']
- diagnose: ['Sildenafil-induced nephrotic syndrome', 'Minimal change disease']
- queries: ['mineralocorticoid receptor antagonist and sildenafil interaction', 'sildenafil-induced nephrotic syndrome', 'minimal change disease and sildenafil', 'acute kidney injury and sildenafil']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Minimal Change Disease', 'Acute Interstitial Nephritis']
- queries: ['sildenafil-induced nephrotic syndrome', 'acute kidney injury with nephrotic-range proteinuria', 'minimal change disease in adults with CKD', 'drug-induced acute interstitial nephritis with eosinophilia']
- n_chunks=12

## APHHM
_na_

