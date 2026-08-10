# MCR / mcr_200b / case 329

- **gold**: urachal cyst
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 26-year-old woman presented with a 2-day history of burning on urination, urinary frequency, nocturia, and constant 5/10 suprapubic pain that did not radiate. She denied fever, nausea, vomiting, changes in bowel movements, weight change, palpitations, heat or cold intolerance, peripheral edema, and abnormal vaginal discharge. Her last menstrual period was one week earlier. Physical examination revealed lower abdominal tenderness, most pronounced in the para-umbilical area, without costovertebral angle tenderness.

Laboratory tests showed a negative serum β-hCG, normal CBC and BMP, and a urinalysis with 10–25 WBCs per high-power field, moderate bacteria, moderate mucus, moderate yeast, and positive nitrites; cervical NAAT was negative for Neisseria gonorrhoeae and Chlamydia trachomatis. A diagnosis of lower urinary tract infection was made, and she received a 10-day course of antibiotics as an outpatient.

Despite treatment, her dysuria, frequency, and burning worsened. She reported chronic constipation, with two hard, non-bloody stools per week managed intermittently with stool softeners. There was no history of abdominal trauma or family gastrointestinal disease. 

Because of pe…

## Backbone e7

- S2 n=54 gold_rank=12
  - clusters: gold=1 near=3 other=50
- S3 shortlist (5):
  - [near] Urachal adenocarcinoma
  - [other] Adenocarcinoma of the urachus
  - [gold] Urachal cyst
  - [near] Urachal diverticulum
  - [other] Bladder adenocarcinoma
    - why_kept(Urachal adenocarcinoma): Multiloculated mass extending from the bladder dome to the posterior surface of the umbilicus, consistent with urachal origin
    - why_kept(Adenocarcinoma of the urachus): Similar to urachal adenocarcinoma, with mass characteristics suggestive of urachal remnant malignancy
    - why_kept(Urachal cyst): Possible benign precursor to urachal adenocarcinoma, with imaging findings consistent with a cystic structure
    - why_kept(Urachal diverticulum): Congenital anomaly that could be associated with the mass, given its location and characteristics
    - why_kept(Bladder adenocarcinoma): Although less likely, the mass's possible invasion into the bladder dome and the patient's symptoms warrant consideration of primary bladder malignancy
- S4 champion: **Urachal adenocarcinoma** cluster=near jaccard=0.33
- S4 rationale: The presence of a large multiloculated mass extending from the dome of the bladder, as seen on the contrast-enhanced CT scan, along with worsening symptoms despite antibiotic treatment, suggests a malignant process. Urachal adenocarcinoma is a rare cancer that originates from the urachus, a remnant of the allantois, which is located near the bladder dome. The location and description of the mass are consistent with this diagnosis.
- S4 rejected:
  - [gold] Urachal cyst: A urachal cyst would not typically cause worsening symptoms despite antibiotic treatment, nor would it usually appear as a large multiloculated mass with surrounding inflammatory changes.
  - [near] Urachal diverticulum: A urachal diverticulum is an outpouching of the bladder that may cause urinary symptoms, but it would not typically present as a large mass or cause the degree of symptoms described.
  - [other] Bladder adenocarcinoma: While bladder adenocarcinoma could present with similar symptoms, the location of the mass extending from the dome of the bladder and the presence of a multiloculated appearance are more suggestive of a urachal origin.
  - [other] Adenocarcinoma of the urachus: This is essentially synonymous with urachal adenocarcinoma, but 'Urachal adenocarcinoma' is chosen as the champion for its specificity and clarity in describing the condition.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Urachal cyst', 'Malignant urachal remnant']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Urachal cyst', 'Urachal sinus', 'Urachal diverticulum', 'Patent urachus', 'Malignant urachal remnant', 'Urachal cyst', 'Malignant urachal remnant', 'Urachal sinus']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Urachal cyst', 'Urachal remnant anomaly with possible malignancy']
- diagnose: ['Urachal cyst', 'Urachal remnant anomaly with possible malignancy']
- queries: ['urachal remnant complications', 'urachal cyst symptoms', 'differential diagnosis of lower abdominal mass in young women']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Urachal adenocarcinoma', 'Urachal cyst']
- queries: ['urachal remnant complications', 'differential diagnosis of multiloculated pelvic masses', 'urinary tract infection with persistent symptoms despite antibiotic treatment', 'imaging characteristics of urachal sinus vs urachal diverticulum vs patent urachus']
- n_chunks=12

## APHHM
_na_

