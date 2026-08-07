# DA / d2_heldout100 / case 262

- **gold**: IBD-associated neutrophilic dermatosis with ulcerative colitis
- **layer**: `e7_win_recall`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `mapper_rescue`
- **one_liner**: e7 S2召回金标但S3/S4丢掉；DA option@1仍对→mapper捡漏，非入口广度

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Sweet syndrome, Pyoderma gangrenosum, Neutrophilic dermatosis, Inflammatory bowel disease, Bowel-associated dermatosis-arthritis syndrome; gold_in_s3=True
- S4 champion: **Sweet syndrome**; gold_match=False
- S2 gold matches: Neutrophilic dermatosis

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Sweet syndrome, Pyoderma gangrenosum, Inflammatory bowel disease, Neutrophilic dermatosis, Behçet's disease; gold_in_s3=True
- S4 champion: **Sweet syndrome**; gold_match=False
- S2 gold matches: Neutrophilic dermatosis

## Baseline B06 MAC
- pred: Sweet syndrome; Inflammatory bowel disease
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Sweet syndrome', 'Inflammatory bowel disease']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Sweet Syndrome; Inflammatory Bowel Disease (IBD)
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Sweet Syndrome', 'Inflammatory Bowel Disease (IBD)']
- cand_recall=False

## APHHM
- tree_n=26 tree_recall=True
- final_n=3 final_recall=True fail_mode=final_ok
- final_ranking: Sweet syndrome, Neutrophilic dermatosis, Pyoderma Gangrenosum
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
