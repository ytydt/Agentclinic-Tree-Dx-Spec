# MCR / mcr_v1 / case 40

- **gold**: hepatocellular carcinoma
- **layer**: `e7_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A 52-year-old man presented with a progressively enlarging, mildly tender right-flank subcutaneous nodule noted over two years. He had a history of HBV-positive hepatocellular carcinoma (HCC) treated with partial hepatectomy, entecavir, transarterial chemoembolization, sorafenib, regorafenib, and pembrolizumab over the preceding two years. On admission, vital signs were: temperature 37.2°C, pulse 112/min, respiratory rate 19/min, blood pressure 114/78 mmHg. He denied alcohol or tobacco use.

Physical examination revealed an ~8×4 cm subcutaneous mass over the right hypochondriac and flank regions; the remainder of the examination was unremarkable. Laboratory studies showed: white blood cell count 8.93×10^3/µl, hemoglobin 13.8 g/dl, AST 55.7 U/l, ALT 55.7 U/l, lactate dehydrogenase 201 U/l, alpha-fetoprotein 157 ng/ml, CEA 7.99 ng/ml, CA19-9 21.6 U/ml, HBsAg reactive, HCV-PCR negative. 

Contrast-enhanced CT of the chest revealed multiple bilateral pulmonary nodules. Abdominal CT showed multiple nodules in liver segments 5 and 7 (largest 3.5 cm) and a right-flank soft tissue mass invading the 12th rib measuring 8×4×4 cm. Based on the clinical history and imaging, extrahepatic metasta…

## Backbone e7

- S2 n=45 gold_rank=1
  - clusters: gold=1 near=0 other=44
- S3 shortlist (5):
  - [gold] Hepatocellular carcinoma metastasis
  - [other] Liposarcoma
  - [other] Leiomyosarcoma
  - [other] Undifferentiated pleomorphic sarcoma
  - [other] Synovial sarcoma
    - why_kept(Hepatocellular carcinoma metastasis): History of HBV-positive hepatocellular carcinoma and imaging showing multiple nodules in liver segments and a soft tissue mass
    - why_kept(Liposarcoma): Progressively enlarging subcutaneous nodule with possible metastasis or primary soft tissue tumor
    - why_kept(Leiomyosarcoma): Mildly tender nodule and possible metastasis or primary soft tissue tumor
    - why_kept(Undifferentiated pleomorphic sarcoma): Large subcutaneous mass and possible metastasis or primary soft tissue tumor
    - why_kept(Synovial sarcoma): Progressively enlarging subcutaneous nodule and possible metastasis or primary soft tissue tumor
- S4 champion: **Hepatocellular carcinoma metastasis** cluster=gold jaccard=0.67
- S4 rationale: The patient has a history of HBV-positive hepatocellular carcinoma and the presence of a subcutaneous nodule with elevated alpha-fetoprotein levels, which is a tumor marker often associated with HCC, suggests metastasis.
- S4 rejected:
  - [other] Liposarcoma: No specific evidence of liposarcoma, such as characteristic imaging findings or specific tumor markers, is mentioned in the case.
  - [other] Leiomyosarcoma: The clinical presentation and laboratory findings do not specifically suggest leiomyosarcoma, which typically arises from smooth muscle cells.
  - [other] Undifferentiated pleomorphic sarcoma: While the subcutaneous mass could be a soft tissue sarcoma, the patient's history of HCC and elevated alpha-fetoprotein levels make HCC metastasis more likely.
  - [other] Synovial sarcoma: There is no specific evidence, such as the presence of SS18-SSX fusion genes or characteristic imaging findings, to support synovial sarcoma in this case.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Hepatocellular carcinoma with extrahepatic metastasis', 'Soft tissue sarcoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Hepatocellular carcinoma with extrahepatic metastasis', 'Soft tissue sarcoma', 'Metastatic disease from another primary site', 'Chronic abscess or granuloma', 'Soft tissue metastasis from another malignancy', 'Hepatocellular carcinoma with extrahepatic metastasis', 'Soft tissue sarcoma', 'Metastatic disease from another primary site']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Extrahepatic metastasis of hepatocellular carcinoma (HCC)', 'Primary soft tissue sarcoma']
- diagnose: ['Extrahepatic metastasis of hepatocellular carcinoma (HCC)', 'Primary soft tissue sarcoma']
- queries: ['hepatocellular carcinoma metastasis', 'soft tissue sarcoma', 'extrahepatic metastasis of HCC', 'subcutaneous nodule differential diagnosis']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Metastatic Hepatocellular Carcinoma', 'Soft Tissue Sarcoma']
- queries: ['subcutaneous nodule with history of hepatocellular carcinoma', 'differential diagnosis of soft tissue masses in cancer patients', 'imaging characteristics of extrahepatic metastasis of HCC', 'primary soft tissue sarcoma vs metastatic disease in flank region']
- n_chunks=12

## APHHM
- tree_n=20 final_n=2
- final: ['Hepatocellular Carcinoma with Extrahepatic Metastasis', 'Undifferentiated Pleomorphic Sarcoma']
- tree gold_cluster_n=3 final gold=True

