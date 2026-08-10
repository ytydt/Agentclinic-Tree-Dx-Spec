# MCR / mcr_200b / case 272

- **gold**: sclerosing hemangioma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 48-year-old man with no prior medical history underwent routine abdominal ultrasonography, which revealed three well-defined hypoechoic hepatic masses in segments 1 (67×53 mm), 6 (13 mm), and 2 (9 mm). He was asymptomatic. Laboratory studies showed normal total bilirubin (0.6 mg/dL) and albumin (4.2 g/dL), with mildly elevated AST (37 IU/L), ALT (70 IU/L), ALP (176 U/L), and GGT (170 IU/L). Tumor markers, including alpha-fetoprotein (2.9 ng/mL), PIVKA-II (11 mAU/mL), and CA19-9 (4.0 IU/L), were within normal limits. 

Dynamic contrast-enhanced CT demonstrated a 65 mm low-density mass with an irregular margin in the caudate lobe, showing peripheral early ring enhancement in the arterial phase and heterogeneous internal enhancement in the delayed phase. EOB-MRI revealed a hypointense mass on T1-weighted images containing several hyperintense areas on T2-weighted images, and the lesion remained hypointense in the hepatobiliary phase. On diffusion-weighted imaging (b = 1000), the lesion was hyperintense relative to liver, with ADC values of 2.11×10^−3 mm^2/s peripherally and 2.45×10^−3 mm^2/s centrally (mean 2.33×10^−3 mm^2/s). FDG-PET showed no radiotracer accumulation in any of the…

## Backbone e7

- S2 n=46 gold_rank=4
  - clusters: gold=2 near=1 other=43
- S3 shortlist (5):
  - [other] Hepatocellular carcinoma
  - [other] Hepatic adenoma
  - [other] Focal nodular hyperplasia
  - [gold] Hemangioma
  - [other] Intrahepatic cholangiocarcinoma
    - why_kept(Hepatocellular carcinoma): Malignant tumor with characteristic imaging findings and abnormal liver function tests
    - why_kept(Hepatic adenoma): Benign tumor with potential for malignancy and similar imaging characteristics
    - why_kept(Focal nodular hyperplasia): Benign tumor with characteristic imaging findings and potential for growth
    - why_kept(Hemangioma): Common benign tumor with characteristic imaging findings and potential for growth
    - why_kept(Intrahepatic cholangiocarcinoma): Malignant tumor with abnormal liver function tests and characteristic imaging findings
- S4 champion: **Hepatocellular carcinoma** cluster=other jaccard=0.00
- S4 rationale: The patient has multiple hepatic masses with heterogeneous internal enhancement on dynamic contrast-enhanced CT and hypervascular masses on hepatic arteriography, which are characteristic features of hepatocellular carcinoma. Although tumor markers are within normal limits, imaging findings are suggestive of this diagnosis.
- S4 rejected:
  - [other] Hepatic adenoma: Hepatic adenomas typically show homogeneous enhancement on CT and are less likely to have multiple lesions.
  - [other] Focal nodular hyperplasia: Focal nodular hyperplasia typically shows a central scar and homogeneous enhancement on CT, which is not seen in this case.
  - [gold] Hemangioma: Hemangiomas typically show peripheral nodular enhancement with progressive fill-in on delayed phase imaging, which is not consistent with the imaging findings in this case.
  - [other] Intrahepatic cholangiocarcinoma: Intrahepatic cholangiocarcinoma typically shows a more aggressive appearance with irregular margins and peripheral enhancement, but the lack of significant bile duct obstruction and normal tumor markers make this diagnosis less likely.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Hepatocellular adenoma', 'Focal nodular hyperplasia']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Hepatocellular adenoma', 'Focal nodular hyperplasia', 'Hemangioma', 'Hepatocellular carcinoma', 'Intrahepatic cholangiocarcinoma', 'Hepatocellular adenoma', 'Focal nodular hyperplasia', 'Hemangioma']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Hepatocellular Adenoma', 'Hemangioma']
- diagnose: ['Hepatocellular Adenoma', 'Hemangioma']
- queries: ['hepatic masses with peripheral early ring enhancement and heterogeneous internal enhancement', 'hypoechoic hepatic masses with normal tumor markers', 'hepatic lesions with hypointense signal on T1-weighted images and hyperintense areas on T2-weighted images', 'hepatic masses with no radiotracer accumulation on FDG-PET']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Hepatocellular carcinoma', 'Hepatic angiosarcoma']
- queries: ['hepatic masses with peripheral early ring enhancement on CT', 'hypoechoic hepatic masses with normal alpha-fetoprotein levels', 'hypointense mass on T1-weighted images with heterogeneous internal enhancement on MRI', 'hepatic lesions with no radiotracer accumulation on FDG-PET']
- n_chunks=12

## APHHM
_na_

