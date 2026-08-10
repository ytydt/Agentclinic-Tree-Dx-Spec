# MCR / mcr_200b / case 381

- **gold**: lipoma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 40-year-old woman from southern Nepal presented with a 5-year history of progressive, painless enlargement of her left breast. She denied nipple discharge, skin changes, fever, weight loss, trauma, hormonal medication, and had no family history of breast cancer. Menstrual cycles were regular. On examination, the left breast contained a well-defined, soft mass measuring 34×26×6 cm with dilated surface veins; the overlying skin, nipple, and areola were normal, and there was no axillary lymphadenopathy. The right breast was unremarkable. Ultrasonography showed a homogeneously hyperechoic mass deep to the breast and pectoralis major muscle without cystic areas, calcifications, or internal vascularity, and no axillary lymph node enlargement. Mammography revealed a heterogeneous lucent mass in the left retromammary region involving the pectoralis muscle, with benign calcifications in both breasts. Magnetic resonance imaging demonstrated a well-defined, homogeneous T1- and T2-hyperintense mass measuring approximately 15×13×10.2 cm that suppressed on fat-suppressed sequences, was encapsulated with multiple thin septa, and showed no thoracic extension or bony erosion. A core biopsy was no…

## Backbone e7

- S2 n=48 gold_rank=1
  - clusters: gold=14 near=0 other=34
- S3 shortlist (5):
  - [gold] Breast Lipoma
  - [other] Hamartoma of the Breast
  - [other] Fibroadenoma
  - [other] Phyllodes Tumor
  - [other] Pseudoangiomatous Stromal Hyperplasia (PASH)
    - why_kept(Breast Lipoma): The patient's presentation of a well-defined, soft mass with dilated surface veins and the imaging findings of a homogeneously hyperechoic mass and a heterogeneous lucent mass are consistent with a lipoma.
    - why_kept(Hamartoma of the Breast): The patient's age and the presence of a well-defined, soft mass with a 5-year history of progressive enlargement are consistent with a hamartoma.
    - why_kept(Fibroadenoma): The patient's age and the presence of a well-defined, soft mass are consistent with a fibroadenoma, although the size of the mass is larger than typical for this condition.
    - why_kept(Phyllodes Tumor): The patient's presentation of a large, well-defined mass with a 5-year history of progressive enlargement is consistent with a phyllodes tumor, although the lack of skin changes or nipple discharge makes this less likely.
    - why_kept(Pseudoangiomatous Stromal Hyperplasia (PASH)): The patient's presentation of a well-defined, soft mass with dilated surface veins and the imaging findings of a homogeneously hyperechoic mass and a heterogeneous lucent mass are consistent with PASH.
- S4 champion: **Hamartoma of the Breast** cluster=other jaccard=0.00
- S4 rationale: The clinical and imaging findings, including a well-defined, soft mass with dilated surface veins, a homogeneously hyperechoic mass on ultrasonography, and a heterogeneous lucent mass on mammography, are consistent with a hamartoma of the breast. The MRI findings of a well-defined, homogeneous T1- and T2-hyperintense mass with multiple thin septa also support this diagnosis.
- S4 rejected:
  - [gold] Breast Lipoma: Lipomas are typically smaller and less well-defined than the mass described in this case
  - [other] Fibroadenoma: Fibroadenomas are usually smaller and more mobile than the mass in this case, and are less likely to have dilated surface veins
  - [other] Phyllodes Tumor: Phyllodes tumors can be large, but often have a more heterogeneous appearance on imaging and may have a more irregular border
  - [other] Pseudoangiomatous Stromal Hyperplasia (PASH): PASH typically presents as a diffuse or nodular area of stromal hyperplasia, rather than a well-defined mass

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Lipoma', 'Hamartoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lipoma', 'Fibroadenoma', 'Hamartoma', 'Hematoma', 'Seroma', 'Lipoma', 'Hamartoma', 'Fibroadenoma']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lipoma', 'Fibroadenoma']
- diagnose: ['Lipoma', 'Fibroadenoma']
- queries: ['breast mass characteristics', 'benign breast lesions', 'lipoma vs fibroadenoma', 'breast ultrasonography findings']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Lipoma', 'Fibroadenoma']
- queries: ['breast mass with homogeneous T1- and T2-hyperintense signal on MRI', 'benign breast lesions with well-defined margins and septations', 'progressive breast enlargement without skin changes or nipple discharge', 'hyperechoic breast mass on ultrasonography with no internal vascularity']
- n_chunks=12

## APHHM
_na_

