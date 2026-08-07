# MCR / mcr_v1 / case 62

- **gold**: Lipoblastoma
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=1 B06=0 B07=1 B01=0 APHHM=1
- **recall**: e7=1 v0=1 B06=0 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7 S2有金标但S3剪掉；基线排对→骨干剪枝/排序弱点

## Backbone e7
- S2 pool n=39 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Lipoma, Liposarcoma, Fibrolipomatous hamartoma, Pleomorphic lipoma, Atypical lipomatous tumor; gold_in_s3=False
- S4 champion: **Fibrolipomatous hamartoma**; gold_match=False
- S2 gold matches: Lipoblastoma, Lipoblastomatosis

## Backbone v0
- S2 pool n=17 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Lipoma, Lipoblastoma, Atypical lipomatous tumor, Well-differentiated liposarcoma, Myxoid liposarcoma; gold_in_s3=True
- S4 champion: **Lipoblastoma**; gold_match=True
- S2 gold matches: Lipoblastoma

## Baseline B06 MAC
- pred: Lipoma; Liposarcoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Lipoma', 'Liposarcoma']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Lipoblastoma; Lipoma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lipoma', 'Lipoblastoma']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Lipoma; Atypical Lipomatous Tumor
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Lipoma', 'Atypical Lipomatous Tumor']
- cand_recall=False

## APHHM
- tree_n=33 tree_recall=True
- final_n=2 final_recall=True fail_mode=final_ok
- final_ranking: Lipoblastoma, Lipoma
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
