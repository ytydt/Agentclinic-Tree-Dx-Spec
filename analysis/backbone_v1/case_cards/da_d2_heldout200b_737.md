# DA / d2_heldout200b / case 737

- **gold**: Leiomyomatosis peritonealis disseminata (LPD) with endometriosis
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=0 v0=1 B06=0 B07=1
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `hard_miss|s3_s4_ranking`
- **one_liner**: 并集召回但终值全错

## Backbone e7
- S2 pool n=55 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Leiomyosarcoma, Desmoid tumor, Aggressive angiomyxoma, Uterine carcinosarcoma, Ovarian cancer; gold_in_s3=False
- S4 champion: **Aggressive angiomyxoma**; gold_match=False

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Uterine leiomyosarcoma, Gastrointestinal stromal tumor, Desmoid tumor, Aggressive angiomyxoma, Solitary fibrous tumor; gold_in_s3=False
- S4 champion: **Aggressive angiomyxoma**; gold_match=False
- S2 gold matches: Endometriosis

## Baseline B06 MAC
- pred: Leiomyosarcoma; Uterine leiomyoma (recurrence)
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Leiomyosarcoma', 'Uterine leiomyoma (recurrence)']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Leiomyoma; Leiomyosarcoma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Leiomyoma', 'Leiomyosarcoma']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
