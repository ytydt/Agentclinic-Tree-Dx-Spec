# MCR / mcr_v1 / case 35

- **gold**: Petersen’s hernia
- **layer**: ``  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **recall**: e7=0 v0=0 B06=0 B07=0
- **auto_tags**: hard_miss
- **manual_tag**: `hard_miss`
- **one_liner**: APHHM独占正确，其他臂未召回→稀有/细粒度标签

## Backbone e7
- S2 pool n=47 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Internal Hernia, Small Bowel Obstruction, Roux-en-Y Gastric Bypass Complication, Mesenteric Ischemia, Adhesional Band Syndrome; gold_in_s3=False
- S4 champion: **Internal Hernia**; gold_match=False

## Backbone v0
- S2 pool n=16 mode=None k=None; gold_in_s2=False
- S3 shortlist (5): Internal hernia, Adhesive bowel obstruction, Intestinal obstruction, Mesenteric ischemia, Small bowel strangulation; gold_in_s3=False
- S4 champion: **Internal hernia**; gold_match=False

## Baseline B06 MAC
- pred: Internal Hernia; Adhesive Bowel Obstruction
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Internal Hernia', 'Adhesive Bowel Obstruction']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Internal Herniation; Adhesive Bowel Obstruction
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Internal Herniation', 'Adhesive Bowel Obstruction']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Internal Hernia; Adhesive Small Bowel Obstruction
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Internal Hernia', 'Adhesive Small Bowel Obstruction']
- cand_recall=False

## APHHM
- tree_n=29 tree_recall=False
- final_n=1 final_recall=False fail_mode=tree_miss
- final_ranking: Internal Hernia after Roux-en-Y Gastric Bypass
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
