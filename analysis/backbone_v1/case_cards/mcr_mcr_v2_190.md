# MCR / mcr_v2 / case 190

- **gold**: Primary signet-ring cell carcinoma of the bladder
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=0 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Urinary bladder adenocarcinoma, Primary bladder adenocarcinoma, Metastatic adenocarcinoma to the bladder, Mucinous adenocarcinoma of the bladder, Signet-ring cell carcinoma of the bladder; gold_in_s3=True
- S4 champion: **Primary bladder adenocarcinoma**; gold_match=False
- S2 gold matches: Signet-ring cell carcinoma of the bladder

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Primary bladder adenocarcinoma, Urachal adenocarcinoma, Metastatic breast cancer, Metastatic gastric cancer, Sarcomatoid carcinoma of the bladder; gold_in_s3=False
- S4 champion: **Primary bladder adenocarcinoma**; gold_match=False

## Baseline B06 MAC
- pred: Primary adenocarcinoma of the bladder; Secondary adenocarcinoma of the bladder
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Primary adenocarcinoma of the bladder', 'Secondary adenocarcinoma of the bladder']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Primary adenocarcinoma of the bladder; Secondary adenocarcinoma of the bladder
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Primary adenocarcinoma of the bladder', 'Secondary adenocarcinoma of the bladder']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Primary adenocarcinoma of the bladder; Secondary adenocarcinoma of the bladder
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Primary adenocarcinoma of the bladder', 'Secondary adenocarcinoma of the bladder']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
