# MCR / mcr_v1 / case 40

- **gold**: hepatocellular carcinoma
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=diagnose_hit_judge_miss
- **covariates**: vig_words=230; gold_words=2; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: layer=e7_win_rank; primary loci above.

## Vignette (trunc)
A 52-year-old man presented with a progressively enlarging, mildly tender right-flank subcutaneous nodule noted over two years. He had a history of HBV-positive hepatocellular carcinoma (HCC) treated with partial hepatectomy, entecavir, transarterial chemoembolization, sorafenib, regorafenib, and pembrolizumab over the preceding two years. On admission, vital signs were: temperature 37.2°C, pulse 112/min, respiratory rate 19/min, blood pressure 114/78 mmHg. He denied alcohol or tobacco use.  Phy...

## Backbone e7
- S1 key_facts: 52-year-old man; Right-flank subcutaneous nodule; Mildly tender nodule; Nodule size approximately 8×4 cm; History of HBV-positive hepatocellular carcinoma; Treated with partial hepatectomy, entecavir, transarterial chemoembolization, so; Temperature 37.2°C; Pulse 112/min
- S2 mode=complement k=3 pool_n=45 gold_in_s2=True
  - call1: ['Hepatocellular carcinoma metastasis', 'Liposarcoma', 'Leiomyosarcoma', 'Malignant fibrous histiocytoma', 'Dermatofibro
  - call2: ['Alveolar soft part sarcoma', 'Granular cell tumor', 'Malignant peripheral nerve sheath tumor', 'Myxofibrosarcoma', 'Pl
  - call3: ['Inflammatory myofibroblastic tumor', 'Low-grade myofibroblastic sarcoma', 'Sclerotic fibroma', 'Nodular fasciitis', 'P
- S3 shortlist n=5 gold=True: Hepatocellular carcinoma metastasis, Liposarcoma, Leiomyosarcoma, Undifferentiated pleomorphic sarcoma, Synovial sarcoma
- S4 champion: **Hepatocellular carcinoma metastasis** gold=True
- S4 raw (trunc): {"champion": "Hepatocellular carcinoma metastasis", "rationale": "The patient has a history of HBV-positive hepatocellular carcinoma and the presence of a subcutaneous nodule with elevated alpha-fetoprotein levels, which is a tumor marker often associated with HCC, suggests metas

## Backbone v0 (compact)
- S1 key_facts: 52-year-old man; Presented with a progressively enlarging right-flank subcutaneous nodule; Nodule is mildly tender; History of HBV-positive hepatocellular carcinoma; Treated with partial hepatectomy, entecavir, transarterial chemoembolization, so; Temperature 37.2°C; Pulse 112/min; Respiratory rate 19/min
- S2 mode=None k=None pool_n=16 gold_in_s2=True
  - pool gold matches: ['Hepatocellular carcinoma metastasis']
  - pool head: Dermatofibrosarcoma protuberans, Liposarcoma, Leiomyosarcoma, Malignant fibrous histiocytoma, Hepatocellular carcinoma metastasis, Soft tissue metastasis from other primary sites, Desmoid tumor, Solitary fibrous tumor
- S3 shortlist n=5 gold=True: Hepatocellular carcinoma metastasis, Dermatofibrosarcoma protuberans, Liposarcoma, Leiomyosarcoma, Soft tissue metastasis from other primary sites
- S4 champion: **Hepatocellular carcinoma metastasis** gold=True
- S4 raw (trunc): {"champion": "Hepatocellular carcinoma metastasis", "rationale": "The patient has a history of HBV-positive hepatocellular carcinoma and the presence of a subcutaneous nodule with elevated alpha-fetoprotein levels, which is a tumor marker often associated with HCC, suggests metas

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's history of HBV-positive hepatocellular carcinoma and the presence of multiple nodules in the liver and lung, hepatocellular carcinoma with e
  - turn1 gold_mention=True diag=
    The patient's history of HBV-positive hepatocellular carcinoma and imaging findings support the likelihood of hepatocellular carcinoma with extrahepatic metasta
  - turn2 gold_mention=True diag=
    The patient's history and imaging findings align with prior opinions, suggesting hepatocellular carcinoma with extrahepatic metastasis as the most likely diagno
- supervisor votes=3 top2=['Hepatocellular carcinoma with extrahepatic metastasis', 'Soft tissue sarcoma'] gold=True

## Baseline B07
- draft=['Extrahepatic metastasis of hepatocellular carcinoma (HCC)', 'Primary soft tissue sarcoma'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['hepatocellular carcinoma metastasis', 'soft tissue sarcoma', 'extrahepatic metastasis of HCC', 'subcutaneous nodule differential diagnosis']
- diagnose=['Extrahepatic metastasis of hepatocellular carcinoma (HCC)', 'Primary soft tissue sarcoma'] gold=True

## Baseline B01
- queries=['subcutaneous nodule with history of hepatocellular carcinoma', 'differential diagnosis of soft tissue masses in cancer patients', 'imaging characteristics of extrahepatic metastasis of HCC', 'primary soft tissue sarcoma vs metastatic disease in flank region']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Metastatic Hepatocellular Carcinoma', 'Soft Tissue Sarcoma'] gold=True

## APHHM
- tree_n=20 tree_recall=True
- gold_leaf=B1.1:Hepatocellular Carcinoma with Extrahepatic Metastasis parent=B1
- final_n=2 final_recall=True ranking=['Hepatocellular Carcinoma with Extrahepatic Metastasis', 'Undifferentiated Pleomorphic Sarcoma']
- human_at1=True fail_mode=final_ok

