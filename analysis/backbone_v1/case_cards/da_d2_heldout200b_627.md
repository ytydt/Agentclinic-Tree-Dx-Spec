# DA / d2_heldout200b / case 627

- **gold**: Complete pancreatic divisum with pancreatic-pleural fistula
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=1 v0=0 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=45 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Acute Pancreatitis, Pancreatic Pseudocyst, Pancreatic Ductal Disruption, Gastric Outlet Obstruction, Pancreaticopleural Fistula; gold_in_s3=False
- S4 champion: **Acute Pancreatitis**; gold_match=False
- S2 gold matches: Pancreatic Divisum

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Acute Pancreatitis, Pancreatic Pseudocyst, Pancreaticopleural Fistula, Chronic Pancreatitis, Alcoholic Pancreatitis; gold_in_s3=False
- S4 champion: **Acute Pancreatitis**; gold_match=False

## Baseline B06 MAC
- pred: Acute Pancreatitis; Pancreatic Pseudocyst
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Acute Pancreatitis', 'Pancreatic Pseudocyst']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Acute Pancreatitis; Chronic Pancreatitis
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Acute Pancreatitis', 'Chronic Pancreatitis']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
