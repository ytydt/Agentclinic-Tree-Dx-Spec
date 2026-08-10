# MCR / mcr_v2 / case 156

- **gold**: Angiomyolipoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `label_drift`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 66-year-old woman with a history of endometrioid endometrial carcinoma presented with abdominal and pelvic pain. Physical examination was unremarkable, and laboratory studies, including a creatinine level of 0.81 mg dl–1, were within normal limits. Contrast-enhanced CT of the abdomen and pelvis demonstrated a right renal mass with areas of fat attenuation located in the upper pole, creating a defect in the renal parenchyma. The lesion contained visible vessels extending into the renal cortex, a finding known as a “renal parenchymal vascular pedicle.” Additionally, there was a fatty tumor thrombus within the right renal vein extending to its confluence with the inferior vena cava. No other masses or enlarged lymph nodes were identified.

What is the most likely diagnosis?

Options:
A. Angiomyolipoma
B. perirenal liposarcoma
C. renal cell carcinoma
D. renal oncocytoma
E. perirenal liposarcoma typically reveals a renal hilar vascular pedicle, with tumour vessels extending from the fatty
F. on the basis of … presence of calcifications; large, irregular tumour invading the perirenal or sinus fat; large
G. None
H. None


## Backbone e7

- S2 n=44 gold_rank=2
  - clusters: gold=3 near=0 other=41
- S3 shortlist (5):
  - [other] Renal cell carcinoma with vascular extension
  - [gold] Angiomyolipoma with renal vein thrombosis
  - [other] Clear cell renal cell carcinoma
  - [other] Papillary renal cell carcinoma
  - [other] Chromophobe renal cell carcinoma
    - why_kept(Renal cell carcinoma with vascular extension): Renal mass with vascular involvement and thrombus in the renal vein
    - why_kept(Angiomyolipoma with renal vein thrombosis): Presence of a fatty tumor thrombus in the renal vein
    - why_kept(Clear cell renal cell carcinoma): Most common type of renal cell carcinoma, consistent with the patient's age and sex
    - why_kept(Papillary renal cell carcinoma): Second most common type of renal cell carcinoma, possible with the patient's presentation
    - why_kept(Chromophobe renal cell carcinoma): Less common type of renal cell carcinoma, but still a possibility given the patient's age and renal mass
- S4 champion: **Renal cell carcinoma with vascular extension** cluster=other jaccard=0.00
- S4 rationale: The presence of a renal mass with areas of fat attenuation, visible vessels extending into the renal cortex, and a fatty tumor thrombus within the right renal vein extending to the inferior vena cava are highly suggestive of renal cell carcinoma with vascular extension.
- S4 rejected:
  - [gold] Angiomyolipoma with renal vein thrombosis: Although angiomyolipomas can contain fat and potentially cause thrombosis, the presence of visible vessels extending into the renal cortex and the patient's history of endometrioid endometrial carcinoma make renal cell carcinoma more likely.
  - [other] Clear cell renal cell carcinoma: This is a subtype of renal cell carcinoma, but the provided information does not specifically suggest clear cell characteristics over other types of renal cell carcinoma with vascular extension.
  - [other] Papillary renal cell carcinoma: Papillary renal cell carcinoma does not typically present with the combination of fat attenuation and vascular extension seen in this case.
  - [other] Chromophobe renal cell carcinoma: Chromophobe renal cell carcinoma is less likely given the presence of fat attenuation and vascular invasion, which are not characteristic features of this subtype.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Renal Cell Carcinoma', 'Angiomyolipoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Renal Cell Carcinoma', 'Angiomyolipoma', 'Liposarcoma', 'Renal Vein Thrombosis', 'Endometrial Cancer Metastasis', 'Renal Cell Carcinoma', 'Angiomyolipoma', 'Liposarcoma']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Renal Cell Carcinoma with Tumor Thrombus', 'Angiomyolipoma']
- diagnose: ['Renal Cell Carcinoma with Tumor Thrombus', 'Angiomyolipoma']
- queries: ['renal mass with fat attenuation', 'renal parenchymal vascular pedicle', 'fatty tumor thrombus in renal vein']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Renal cell carcinoma', 'Angiomyolipoma']
- queries: ['renal mass with fat attenuation', 'renal parenchymal vascular pedicle', 'fatty tumor thrombus in renal vein', 'endometrial carcinoma with renal metastasis']
- n_chunks=12

## APHHM
_na_

