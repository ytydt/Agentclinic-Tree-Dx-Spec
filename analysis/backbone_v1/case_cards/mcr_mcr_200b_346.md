# MCR / mcr_200b / case 346

- **gold**: myxoinflammatory fibroblastic sarcoma
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=44 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Myxoinflammatory fibroblastic sarcoma, Acral myxoinflammatory fibroblastic sarcoma, Myxoid liposarcoma, Inflammatory myofibroblastic tumor, Hodgkin lymphoma; gold_in_s3=True
- S4 champion: **Acral myxoinflammatory fibroblastic sarcoma**; gold_match=True
- S2 gold matches: Myxoinflammatory fibroblastic sarcoma, Acral myxoinflammatory fibroblastic sarcoma

## Backbone v0
- S2 pool n=15 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Myxoinflammatory fibroblastic sarcoma, Myxoid liposarcoma, Inflammatory myofibroblastic tumor, Liposarcoma, Myxofibrosarcoma; gold_in_s3=True
- S4 champion: **Myxoinflammatory fibroblastic sarcoma**; gold_match=True
- S2 gold matches: Myxoinflammatory fibroblastic sarcoma

## Baseline B06 MAC
- pred: Myxoid liposarcoma; Lipoblastoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Myxoid liposarcoma', 'Lipoblastoma']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Myxoid liposarcoma; Hodgkin lymphoma
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Hodgkin lymphoma', 'Myxoid liposarcoma']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Hodgkin lymphoma; Myxoid tumor
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Hodgkin lymphoma', 'Myxoid tumor']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
