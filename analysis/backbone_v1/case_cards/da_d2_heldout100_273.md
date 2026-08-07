# DA / d2_heldout100 / case 273

- **gold**: Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis
- **layer**: `e7_win_rank`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, aphhm_prune_loss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=47 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Atopic dermatitis, Allergic contact dermatitis, Dyshidrotic eczema, Irritant contact dermatitis, Nummular dermatitis; gold_in_s3=True
- S4 champion: **Atopic dermatitis**; gold_match=True
- S2 gold matches: Atopic dermatitis

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Atopic dermatitis, Allergic contact dermatitis, Dyshidrotic eczema, Irritant contact dermatitis, Nummular dermatitis; gold_in_s3=True
- S4 champion: **Atopic dermatitis**; gold_match=True
- S2 gold matches: Atopic dermatitis

## Baseline B06 MAC
- pred: Allergic Contact Dermatitis; Atopic Dermatitis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Allergic Contact Dermatitis', 'Atopic Dermatitis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Allergic Contact Dermatitis; Atopic Dermatitis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Allergic Contact Dermatitis', 'Atopic Dermatitis']
- cand_recall=True

## APHHM
- tree_n=29 tree_recall=True
- final_n=1 final_recall=False fail_mode=prune_loss
- final_ranking: allergic contact dermatitis
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
