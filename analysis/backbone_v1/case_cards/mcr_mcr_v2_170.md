# MCR / mcr_v2 / case 170

- **gold**: T-cell lymphoblastic lymphoma
- **layer**: `e7_win_rank`  aphhm_layer=``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=0 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Hodgkin lymphoma, Non-Hodgkin lymphoma, Thymoma, Castleman disease, Lymphoblastic lymphoma; gold_in_s3=True
- S4 champion: **Lymphoblastic lymphoma**; gold_match=True
- S2 gold matches: Lymphoblastic lymphoma

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Hodgkin lymphoma, Non-Hodgkin lymphoma, Tuberculous pericarditis, Castleman disease, Lymphomatoid granulomatosis; gold_in_s3=False
- S4 champion: **Hodgkin lymphoma**; gold_match=False

## Baseline B06 MAC
- pred: Lymphoma; Mediastinal germ cell tumor
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Lymphoma', 'Mediastinal germ cell tumor']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Lymphoma; Germ Cell Tumor
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lymphoma', 'Germ Cell Tumor']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Lymphoma; Germ Cell Tumor
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Lymphoma', 'Germ Cell Tumor']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
