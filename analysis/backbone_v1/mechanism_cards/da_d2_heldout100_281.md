# DA / d2_heldout100 / case 281

- **gold**: Stage IIA Malignant Melanoma with subsequent development of metastasis and a second primary melanoma
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A man in his 30s (phototype 3, occupational sun exposure, fewer than 50 nevi) with no relevant medical history presented with a left cervical lesion. A few months after initial treatment, a lymph node metastasis with extracapsular extension was detected. Five months later, another locoregional recurrence with skin metastasis was observed.

Patient had fewer than 50 nevi on examination.

{'Initial Staging': '- CT scan, ultrasonography, lactate dehydrogenase and S-100 protein levels revealed nothing abnormal\n- Selective sentinel node biopsy findings were negative', 'Histopathology': '- Initial lesion: Breslow depth 2.6 mm, no ulceration, 7 mitoses/mm2\n- BRAF V600E mutation positive', 'Imaging Studies': {'Title': 'Dermoscopic and Histopathological Images', 'Description': '- Figure A & B: Dermoscopic evolution of preexisting pigmented lesion showing involutive characteristics (5 month interval, 7mm diameter)\n- Figure C & D: Compound nevus with abundant melanophages and BRAF V600E immunohistochemical staining\n- Figure E & F: Dermoscopic changes in preexisting pigmented lesion showing broadened network, darkening and eccentric growth\n- Figure G & H: Histopathological study showing i…

## Options
- A: Stage IIA Malignant Melanoma with subsequent development of metastasis and a second primary melanoma **←gold**
- B: Nodular Melanoma
- C: Metastatic cutaneous melanoma
- D: Multiple primary melanoma

## Backbone e7

- S2 n=49 gold_rank=1
  - clusters: gold=1 near=19 other=29
- S3 shortlist (5):
  - [gold] Melanoma
  - [near] Desmoplastic Melanoma
  - [near] Nodular Melanoma
  - [near] Metastatic Melanoma
  - [near] Primary Mucosal Melanoma
    - why_kept(Melanoma): Patient has a history of a left cervical lesion with subsequent lymph node metastasis and locoregional recurrence, and BRAF V600E mutation was detected
    - why_kept(Desmoplastic Melanoma): Patient has a history of a left cervical lesion with subsequent lymph node metastasis and locoregional recurrence, and desmoplastic melanoma is a subtype of melanoma
    - why_kept(Nodular Melanoma): Patient has a history of a left cervical lesion with subsequent lymph node metastasis and locoregional recurrence, and nodular melanoma is a subtype of melanoma
    - why_kept(Metastatic Melanoma): Patient has a history of lymph node metastasis with extracapsular extension and locoregional recurrence with skin metastasis
    - why_kept(Primary Mucosal Melanoma): Although less likely, primary mucosal melanoma can present with cervical metastasis, and it is a rare but plausible diagnosis
- S4 champion: **Metastatic Melanoma** cluster=near jaccard=0.08
- S4 rationale: The patient had lymph node metastasis with extracapsular extension and locoregional recurrence with skin metastasis, indicating the spread of melanoma beyond the initial site.
- S4 rejected:
  - [gold] Melanoma: Too general, as it does not account for the metastasis
  - [near] Desmoplastic Melanoma: No specific mention of desmoplastic features in the histopathology
  - [near] Nodular Melanoma: The initial lesion's characteristics do not specifically suggest nodular melanoma
  - [near] Primary Mucosal Melanoma: The lesion is described as a skin lesion, not mucosal

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Melanoma', 'Squamous Cell Carcinoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Melanoma', 'Squamous Cell Carcinoma', 'Basal Cell Carcinoma', 'Dermatofibrosarcoma protuberans', 'Merkel Cell Carcinoma', 'Melanoma', 'Squamous Cell Carcinoma', 'Basal Cell Carcinoma']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Metastatic Melanoma', 'Locoregional Recurrence of Melanoma']
- diagnose: ['Metastatic Melanoma', 'Locoregional Recurrence of Melanoma']
- queries: ['metastatic melanoma diagnosis', 'BRAF V600E mutation melanoma', 'melanoma recurrence after treatment']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=27 final_n=1
- final: ['metastatic melanoma']
- tree gold_cluster_n=1 final gold=False

