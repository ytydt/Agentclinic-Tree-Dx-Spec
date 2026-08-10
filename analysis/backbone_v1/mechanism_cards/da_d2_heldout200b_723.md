# DA / d2_heldout200b / case 723

- **gold**: Acute pancreatitis with renal failure
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 12-year-old castrated Chihuahua presented for periodic health examination. The dog had been diagnosed with tricuspid regurgitation a year prior, which was left untreated for financial reasons. The owner noted that the dog's stool contained parasites, likely nematodes or tapeworms.

Initial examination showed:- Body weight: 4.1 kg- Rectal temperature: 38.3°C - Heart rate: 120 beats/min- Respiratory rate: 30 breaths/min- Heart murmur heard in right heart regionOn follow-up after medication:- Tenderness noted in upper abdomen- Low rectal temperature (36.6°C)- Heart rate 120 beats/min

Initial tests:- Laboratory findings:  * Elevated platelet count (723,000/μL)  * Increased ALT (221 U/L), ALP (159 U/L), γ-GTP (66 U/L)  * Elevated BUN (34.2 mg/dL)  * High total cholesterol (493 mg/dL) and triglycerides (494 mg/dL)  * Elevated phosphorus (5.7 mg/dL) and cystatin C (0.48 mg/dL)  * Spec cPL slightly elevated at 460 μg/dL  * High total bile acid (38.4 μmol/L)  * Negative heartworm antigen testFollow-up tests:- Imaging:  * Thoracic radiography: Enlarged cardiac silhouette  * Abdominal radiography: Hepatomegaly and increased radiopacity in upper right abdomen  * Abdominal ultrasound: Liver …

## Options
- A: Acute pancreatitis with renal failure **←gold**
- B: Gallbladder mucocele with secondary pancreatitis
- C: Chronic kidney disease
- D: Pancreatitis **←gold**

## Backbone e7

- S2 n=58 gold_rank=13
  - clusters: gold=1 near=1 other=56
- S3 shortlist (5):
  - [near] Congestive heart failure
  - [other] Hepatic cirrhosis
  - [other] Hyperadrenocorticism
  - [other] Polycystic kidney disease
  - [other] Gallbladder mucocele
    - why_kept(Congestive heart failure): Previous diagnosis of tricuspid regurgitation and current signs of heart failure
    - why_kept(Hepatic cirrhosis): Elevated liver enzymes, hepatomegaly, and gallbladder mucocele-like findings
    - why_kept(Hyperadrenocorticism): Enlarged adrenal glands and signs of metabolic disorder
    - why_kept(Polycystic kidney disease): Renal cysts and elevated BUN and creatinine
    - why_kept(Gallbladder mucocele): Gallbladder mucocele-like findings on abdominal ultrasound
- S4 champion: **Hyperadrenocorticism** cluster=other jaccard=0.00
- S4 rationale: The presence of hepatomegaly, elevated liver enzymes, and increased ALP, alongside elevated BUN and creatinine, suggests a systemic disease. The combination of these findings, along with the presence of renal cysts and enlarged adrenal glands, points towards hyperadrenocorticism, which can cause these multi-organ changes.
- S4 rejected:
  - [near] Congestive heart failure: While the dog has a history of tricuspid regurgitation, the key findings of hepatomegaly, gallbladder mucocele-like findings, and renal cysts are not directly explained by congestive heart failure alone.
  - [other] Hepatic cirrhosis: Although liver enzyme elevations and hepatomegaly are present, the presence of renal cysts, enlarged adrenal glands, and other systemic findings suggest a more complex disease process than hepatic cirrhosis alone.
  - [other] Polycystic kidney disease: While renal cysts are present, the disease would not fully explain the hepatomegaly, gallbladder mucocele-like findings, and the significant elevations in liver enzymes and adrenal gland enlargement.
  - [other] Gallbladder mucocele: Although a gallbladder mucocele-like finding is present, it is one part of a broader spectrum of systemic findings that suggest a more complex underlying disease process, such as hyperadrenocorticism, which can cause multiple organ abnormalities.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Chronic Hepatitis', 'Pancreatitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Chronic Hepatitis', 'Congestive Heart Failure', 'Chronic Kidney Disease', 'Hyperadrenocorticism', 'Pancreatitis', 'Chronic Hepatitis', 'Pancreatitis', 'Congestive Heart Failure']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Congestive Heart Failure (CHF) secondary to tricuspid regurgitation', 'Pancreatitis with potential gallbladder mucocele']
- diagnose: ['Congestive Heart Failure (CHF) secondary to tricuspid regurgitation', 'Pancreatitis with potential gallbladder mucocele']
- queries: ['tricuspid regurgitation complications in dogs', 'elevated liver enzymes in dogs', 'gallbladder mucocele in dogs', 'renal cysts and adrenal gland enlargement in dogs']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

