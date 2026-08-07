# DA / d2_heldout200b / case 530

- **gold**: Calcinosis cutis in Sjögren syndrome
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `mapper_rescue`
- **one_liner**: e7 S2召回金标但S3/S4丢掉；DA option@1仍对→mapper捡漏，非入口广度

## Backbone e7
- S2 pool n=52 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Limited systemic scleroderma, Sjögren's syndrome, Mixed connective tissue disease, Calcinosis cutis, CREST syndrome; gold_in_s3=True
- S4 champion: **CREST syndrome**; gold_match=False
- S2 gold matches: Calcinosis cutis

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Limited systemic scleroderma, Sjögren's syndrome, Mixed connective tissue disease, CREST syndrome, Calcinosis cutis; gold_in_s3=True
- S4 champion: **CREST syndrome**; gold_match=False
- S2 gold matches: Calcinosis cutis

## Baseline B06 MAC
- pred: Limited Systemic Sclerosis; Sjögren's Syndrome
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Limited Systemic Sclerosis', "Sjögren's Syndrome"]
- cand_recall=False

## Baseline B07 MEDDx
- pred: Limited Systemic Scleroderma (CREST Syndrome); Sjögren's Syndrome
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Limited Systemic Scleroderma (CREST Syndrome)', "Sjögren's Syndrome"]
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
