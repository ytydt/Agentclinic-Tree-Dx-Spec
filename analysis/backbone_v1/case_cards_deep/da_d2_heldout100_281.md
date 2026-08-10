# DA / d2_heldout100 / case 281

- **gold**: Stage IIA Malignant Melanoma with subsequent development of metastasis and a second primary melanoma
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: APHHM=tree_hit_final_drop
- **covariates**: vig_words=202; gold_words=14; eponym=False; subtype=True; e7_s2_rank=1; mapper_rescue=True
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A man in his 30s (phototype 3, occupational sun exposure, fewer than 50 nevi) with no relevant medical history presented with a left cervical lesion. A few months after initial treatment, a lymph node metastasis with extracapsular extension was detected. Five months later, another locoregional recurrence with skin metastasis was observed.  Patient had fewer than 50 nevi on examination.  {'Initial Staging': '- CT scan, ultrasonography, lactate dehydrogenase and S-100 protein levels revealed nothi...

## Options
  - A: Stage IIA Malignant Melanoma with subsequent development of metastasis and a second primary melanoma
  - B: Nodular Melanoma
  - C: Metastatic cutaneous melanoma
  - D: Multiple primary melanoma

## Backbone e7
- S1 key_facts: Patient is a man in his 30s; Patient has phototype 3 skin; Patient has occupational sun exposure; Patient has fewer than 50 nevi; Initial lesion had Breslow depth of 2.6 mm; Initial lesion had no ulceration; Initial lesion had 7 mitoses/mm2; Patient had lymph node metastasis with extracapsular extension
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Melanoma', 'Squamous Cell Carcinoma', 'Basal Cell Carcinoma', 'Merkel Cell Carcinoma', 'Lymphoma', 'Leiomyosarcoma', '
  - call2: ['Epithelioid Sarcoma', 'Clear Cell Sarcoma', 'Alveolar Soft Part Sarcoma', 'Granular Cell Tumor', 'Plexiform Fibrohisti
  - call3: ['Primary Mucosal Melanoma', 'Melanoma of Unknown Primary Origin', 'Ocular Melanoma with Metastasis', 'Clear Cell Melano
- S3 shortlist n=5 gold=True: Melanoma, Desmoplastic Melanoma, Nodular Melanoma, Metastatic Melanoma, Primary Mucosal Melanoma
- S4 champion: **Metastatic Melanoma** gold=False
- S4 raw (trunc): {"champion": "Metastatic Melanoma", "rationale": "The patient had lymph node metastasis with extracapsular extension and locoregional recurrence with skin metastasis, indicating the spread of melanoma beyond the initial site.", "rejected": [{"label": "Melanoma", "why": "Too gener

## Backbone v0 (compact)
- S1 key_facts: Patient is a man in his 30s; Patient has phototype 3 skin; Patient has occupational sun exposure; Patient has fewer than 50 nevi; Patient presented with a left cervical lesion; Initial treatment was given, but specifics are not provided; Lymph node metastasis with extracapsular extension was detected a few months aft; Locoregional recurrence with skin metastasis was observed five months later
- S2 mode=single k=1 pool_n=21 gold_in_s2=True
  - call1: ['Melanoma', 'Squamous Cell Carcinoma', 'Basal Cell Carcinoma', 'Merkel Cell Carcinoma', 'Dermatofibrosarcoma protuberan
- S3 shortlist n=5 gold=True: Melanoma, Squamous Cell Carcinoma, Merkel Cell Carcinoma, Lymphoma, Metastatic carcinoma
- S4 champion: **Melanoma** gold=True
- S4 raw (trunc): {"champion": "Melanoma", "rationale": "The presence of a BRAF V600E mutation, a Breslow depth of 2.6 mm, and 7 mitoses/mm2 in the initial lesion, along with lymph node metastasis and locoregional recurrence, are all consistent with melanoma.", "rejected": [{"label": "Squamous Cel

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    Given the patient's history of a left cervical lesion with lymph node metastasis and skin metastasis, along with the presence of a BRAF V600E mutation, melanoma
  - turn1 gold_mention=False diag=
    Agree with Doctor A, given the patient's history and presence of BRAF V600E mutation, melanoma is the most likely diagnosis.
  - turn2 gold_mention=False diag=
    Agree with prior opinions, melanoma is the most likely diagnosis given the patient's history of a left cervical lesion with lymph node metastasis and skin metas
- supervisor votes=3 top2=['Melanoma', 'Squamous Cell Carcinoma'] gold=True

## Baseline B07
- draft=['Metastatic Melanoma', 'Locoregional Recurrence of Melanoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['metastatic melanoma diagnosis', 'BRAF V600E mutation melanoma', 'melanoma recurrence after treatment']
- diagnose=['Metastatic Melanoma', 'Locoregional Recurrence of Melanoma'] gold=False

## APHHM
- tree_n=27 tree_recall=True
- gold_leaf=B1.1:Melanoma parent=B1
- final_n=1 final_recall=False ranking=['metastatic melanoma']
- human_at1=False fail_mode=prune_loss

