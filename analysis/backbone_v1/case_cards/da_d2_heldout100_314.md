# DA / d2_heldout100 / case 314

- **gold**: Peeling skin disease (PSD)
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=1
- **recall**: e7=1 v0=1 B06=0 B07=1
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7 S2有金标但S3剪掉；基线排对→骨干剪枝/排序弱点

## Backbone e7
- S2 pool n=58 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Peeling skin syndrome, Acral peeling skin syndrome, CDSN-related peeling skin syndrome, Samira type peeling skin syndrome, Generalized peeling skin syndrome; gold_in_s3=False
- S4 champion: **CDSN-related peeling skin syndrome**; gold_match=False
- S2 gold matches: Peeling skin disease, Peeling skin disease type C

## Backbone v0
- S2 pool n=21 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Peeling skin syndrome, Acral peeling skin syndrome, Samira type peeling skin syndrome, Keratolysis exfoliativa, Generalized peeling skin syndrome; gold_in_s3=False
- S4 champion: **Peeling skin syndrome**; gold_match=False
- S2 gold matches: Peeling skin disease

## Baseline B06 MAC
- pred: Peeling Skin Syndrome; Keratosis Pilaris
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Peeling Skin Syndrome', 'Keratosis Pilaris']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Peeling Skin Disease; Dermatitis Artefacta
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Peeling Skin Disease', 'Dermatitis Artefacta']
- cand_recall=True

## APHHM
- tree_n=23 tree_recall=False
- final_n=1 final_recall=False fail_mode=tree_miss
- final_ranking: Acral Peeling Skin Syndrome
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
