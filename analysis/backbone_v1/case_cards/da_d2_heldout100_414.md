# DA / d2_heldout100 / case 414

- **gold**: Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations
- **layer**: `e7_win_recall`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=1 v0=0 B06=0 B07=0
- **auto_tags**: entrance_breadth, aphhm_prune_loss
- **manual_tag**: `mapper_rescue`
- **one_liner**: e7 S2召回金标但S3/S4丢掉；DA option@1仍对→mapper捡漏，非入口广度

## Backbone e7
- S2 pool n=50 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Weill-Marchesani syndrome, Homocystinuria, Marfan syndrome, LTBP2-related ocular syndrome, Ehlers-Danlos syndrome; gold_in_s3=False
- S4 champion: **LTBP2-related ocular syndrome**; gold_match=False
- S2 gold matches: Glaucoma

## Backbone v0
- S2 pool n=20 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Weill-Marchesani syndrome, Homocystinuria, Ehlers-Danlos syndrome, Marfan syndrome, Ectopia lentis; gold_in_s3=False
- S4 champion: **Weill-Marchesani syndrome**; gold_match=False

## Baseline B06 MAC
- pred: Weill-Marchesani syndrome; Homocystinuria
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Weill-Marchesani syndrome', 'Homocystinuria']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Weill-Marchesani syndrome; Homocystinuria
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Weill-Marchesani syndrome', 'Homocystinuria']
- cand_recall=False

## APHHM
- tree_n=26 tree_recall=True
- final_n=1 final_recall=False fail_mode=prune_loss
- final_ranking: Weill-Marchesani syndrome
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
