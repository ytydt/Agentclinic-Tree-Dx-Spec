# DA / d2_heldout100 / case 381

- **gold**: Good syndrome
- **layer**: ``  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **recall**: e7=0 v0=0 B06=0 B07=0
- **auto_tags**: hard_miss
- **manual_tag**: `hard_miss`
- **one_liner**: APHHM独占正确，其他臂未召回→稀有/细粒度标签

## Backbone e7
- S2 pool n=55 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Thymoma, Paraneoplastic pemphigus, Good's syndrome, Mucous membrane pemphigoid, Autoimmune lymphoproliferative syndrome; gold_in_s3=False
- S4 champion: **Paraneoplastic pemphigus**; gold_match=False

## Backbone v0
- S2 pool n=20 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Paraneoplastic pemphigus, Pemphigus vulgaris, Thymoma, Mycosis fungoides, Sjogren's syndrome; gold_in_s3=False
- S4 champion: **Paraneoplastic pemphigus**; gold_match=False

## Baseline B06 MAC
- pred: Paraneoplastic Pemphigus; Thymoma-associated multiorgan autoimmunity
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Paraneoplastic Pemphigus', 'Thymoma-associated multiorgan autoimmunity']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Paraneoplastic Pemphigus; Thymoma-associated Mucocutaneous Disorder
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Paraneoplastic Pemphigus', 'Thymoma-associated Mucocutaneous Disorder']
- cand_recall=False

## APHHM
- tree_n=25 tree_recall=True
- final_n=2 final_recall=False fail_mode=prune_loss
- final_ranking: Thymoma-associated Immunodeficiency, Paraneoplastic Pemphigus
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
