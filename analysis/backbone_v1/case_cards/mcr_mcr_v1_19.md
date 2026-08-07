# MCR / mcr_v1 / case 19

- **gold**: Leiomyosarcoma
- **layer**: `all_miss_but_recalled`  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **recall**: e7=1 v0=1 B06=1 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=44 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Meningioma, Hemangiopericytoma, Solitary fibrous tumor, Leiomyosarcoma, Sarcomatoid meningioma; gold_in_s3=True
- S4 champion: **Sarcomatoid meningioma**; gold_match=False
- S2 gold matches: Leiomyosarcoma

## Backbone v0
- S2 pool n=18 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Meningioma, Hemangiopericytoma, Solitary fibrous tumor, Leiomyosarcoma, Lymphoma; gold_in_s3=True
- S4 champion: **Hemangiopericytoma**; gold_match=False
- S2 gold matches: Leiomyosarcoma

## Baseline B06 MAC
- pred: Sarcoma; Hemangiopericytoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Sarcoma', 'Hemangiopericytoma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Solitary Fibrous Tumor/Hemangiopericytoma; Meningeal Sarcoma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Solitary Fibrous Tumor/Hemangiopericytoma', 'Meningeal Sarcoma']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Meningeal Sarcoma; Osteosarcoma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Meningeal Sarcoma', 'Osteosarcoma']
- cand_recall=False

## APHHM
- tree_n=32 tree_recall=True
- final_n=3 final_recall=True fail_mode=final_ok
- final_ranking: Leiomyosarcoma, Hemangiopericytoma, Meningioma
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
