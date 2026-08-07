# MCR / mcr_v2 / case 209

- **gold**: melanoma
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=46 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Ewing sarcoma, Primitive neuroectodermal tumor, Plasmacytoma, Chondrosarcoma, Osteosarcoma; gold_in_s3=False
- S4 champion: **Ewing sarcoma**; gold_match=False
- S2 gold matches: Melanoma metastasis

## Backbone v0
- S2 pool n=15 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Ewing sarcoma, Primitive neuroectodermal tumor, Plasmacytoma, Chondrosarcoma, Melanoma metastasis; gold_in_s3=True
- S4 champion: **Ewing sarcoma**; gold_match=False
- S2 gold matches: Melanoma metastasis

## Baseline B06 MAC
- pred: Metastatic melanoma; Ewing sarcoma/primitive neuroectodermal tumor (PNET)
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Metastatic melanoma', 'Ewing sarcoma/primitive neuroectodermal tumor (PNET)']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET); Desmoplastic Small Round Cell Tumor (DSRCT)
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET)', 'Desmoplastic Small Round Cell Tumor (DSRCT)']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Ewing sarcoma; Desmoplastic small round cell tumor
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Ewing sarcoma', 'Desmoplastic small round cell tumor']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
