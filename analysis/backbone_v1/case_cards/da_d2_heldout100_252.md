# DA / d2_heldout100 / case 252

- **gold**: Folliculocentric lichen sclerosus et atrophicus
- **layer**: ``  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **recall**: e7=0 v0=0 B06=0 B07=0
- **auto_tags**: hard_miss
- **manual_tag**: `hard_miss`
- **one_liner**: APHHM独占正确，其他臂未召回→稀有/细粒度标签

## Backbone e7
- S2 pool n=37 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Keratosis Pilaris, Lichen Spinulosus, Keratosis Follicularis, Follicular Lichenoid Dermatitis, Darier Disease; gold_in_s3=False
- S4 champion: **Lichen Spinulosus**; gold_match=False

## Backbone v0
- S2 pool n=15 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Keratosis Pilaris, Lichen Spinulosus, Keratosis Follicularis, Grover Disease, Phrynoderma; gold_in_s3=False
- S4 champion: **Lichen Spinulosus**; gold_match=False

## Baseline B06 MAC
- pred: Lichen spinulosus; Keratosis pilaris
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Lichen spinulosus', 'Keratosis pilaris']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Lichen spinulosus; Keratosis pilaris
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Lichen spinulosus', 'Keratosis pilaris']
- cand_recall=False

## APHHM
- tree_n=23 tree_recall=False
- final_n=3 final_recall=False fail_mode=tree_miss
- final_ranking: Keratosis pilaris, Lichen planopilaris, Lichen planus
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
