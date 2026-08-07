# MCR / mcr_v1 / case 126

- **gold**: Extranodal natural killer/T-cell lymphoma nasal type
- **layer**: `base_win_rank`  aphhm_layer=`aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7 S2有金标但S3剪掉；基线排对→骨干剪枝/排序弱点

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Subcutaneous panniculitis-like T-cell lymphoma, Wegener's granulomatosis, Polyarteritis nodosa, Takayasu arteritis, Erdheim-Chester disease; gold_in_s3=False
- S4 champion: **Subcutaneous panniculitis-like T-cell lymphoma**; gold_match=False
- S2 gold matches: Lymphoma

## Backbone v0
- S2 pool n=19 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Lymphoma, Leukemia cutis, Granulomatosis with polyangiitis, Panniculitis, Lymphomatoid granulomatosis; gold_in_s3=True
- S4 champion: **Lymphoma**; gold_match=True
- S2 gold matches: Lymphoma

## Baseline B06 MAC
- pred: Lymphoma; Sarcoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Lymphoma', 'Sarcoma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Lymphoma; Mantle Cell Lymphoma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lymphoma', 'Mantle Cell Lymphoma']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Lymphoma; Dermatomyositis
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Lymphoma', 'Dermatomyositis']
- cand_recall=True

## APHHM
- tree_n=48 tree_recall=True
- final_n=4 final_recall=True fail_mode=final_ok
- final_ranking: Lymphoma, Castleman disease, Immune-Mediated Necrotizing Myopathy, Rosai-Dorfman disease
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
