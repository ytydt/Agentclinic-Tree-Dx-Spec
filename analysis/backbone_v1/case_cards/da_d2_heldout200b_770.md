# DA / d2_heldout200b / case 770

- **gold**: Leptospirosis with severe pneumonia, acute kidney injury, and acute liver injury
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01= APHHM=
- **recall**: e7=1 v0=0 B06=1 B07=1
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7 S2有金标但S3剪掉；基线排对→骨干剪枝/排序弱点

## Backbone e7
- S2 pool n=56 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Influenza pneumonia, Pneumococcal pneumonia, Goodpasture syndrome, Pulmonary embolism, Severe acute respiratory syndrome; gold_in_s3=False
- S4 champion: **Goodpasture syndrome**; gold_match=False
- S2 gold matches: Leptospirosis

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Influenza pneumonia, Pneumococcal pneumonia, Severe acute respiratory syndrome, COVID-19, Goodpasture syndrome; gold_in_s3=False
- S4 champion: **Influenza pneumonia**; gold_match=False

## Baseline B06 MAC
- pred: Pneumonia; Acute Respiratory Distress Syndrome (ARDS)
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Pneumonia; Acute Respiratory Distress Syndrome (ARDS)
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Pneumonia', 'Acute Respiratory Distress Syndrome (ARDS)']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
