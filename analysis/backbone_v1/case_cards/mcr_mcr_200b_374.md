# MCR / mcr_200b / case 374

- **gold**: cryptogenic organizing pneumonia
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=53 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): sarcoidosis, lymphangitic carcinomatosis, bronchoalveolar cell carcinoma, organizing pneumonia, Wegener's granulomatosis; gold_in_s3=True
- S4 champion: **organizing pneumonia**; gold_match=True
- S2 gold matches: organizing pneumonia

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Sarcoidosis, Lymphangitic carcinomatosis, Bronchoalveolar cell carcinoma, Organizing pneumonia, Hypersensitivity pneumonitis; gold_in_s3=True
- S4 champion: **Organizing pneumonia**; gold_match=True
- S2 gold matches: Organizing pneumonia

## Baseline B06 MAC
- pred: Lung Cancer; Sarcoidosis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Lung Cancer', 'Sarcoidosis']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Lung Cancer; Sarcoidosis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lung Cancer', 'Sarcoidosis']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Sarcoidosis; Lipoid Pneumonia
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Sarcoidosis', 'Lipoid Pneumonia']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
