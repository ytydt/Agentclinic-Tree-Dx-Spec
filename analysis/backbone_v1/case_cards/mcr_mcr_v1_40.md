# MCR / mcr_v1 / case 40

- **gold**: hepatocellular carcinoma
- **layer**: `e7_win_rank`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=45 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Hepatocellular carcinoma metastasis, Liposarcoma, Leiomyosarcoma, Undifferentiated pleomorphic sarcoma, Synovial sarcoma; gold_in_s3=True
- S4 champion: **Hepatocellular carcinoma metastasis**; gold_match=True
- S2 gold matches: Hepatocellular carcinoma metastasis

## Backbone v0
- S2 pool n=16 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Hepatocellular carcinoma metastasis, Dermatofibrosarcoma protuberans, Liposarcoma, Leiomyosarcoma, Soft tissue metastasis from other primary sites; gold_in_s3=True
- S4 champion: **Hepatocellular carcinoma metastasis**; gold_match=True
- S2 gold matches: Hepatocellular carcinoma metastasis

## Baseline B06 MAC
- pred: Hepatocellular carcinoma with extrahepatic metastasis; Soft tissue sarcoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Hepatocellular carcinoma with extrahepatic metastasis', 'Soft tissue sarcoma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Extrahepatic metastasis of hepatocellular carcinoma (HCC); Primary soft tissue sarcoma
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Extrahepatic metastasis of hepatocellular carcinoma (HCC)', 'Primary soft tissue sarcoma']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Metastatic Hepatocellular Carcinoma; Soft Tissue Sarcoma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Metastatic Hepatocellular Carcinoma', 'Soft Tissue Sarcoma']
- cand_recall=True

## APHHM
- tree_n=20 tree_recall=True
- final_n=2 final_recall=True fail_mode=final_ok
- final_ranking: Hepatocellular Carcinoma with Extrahepatic Metastasis, Undifferentiated Pleomorphic Sarcoma
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
