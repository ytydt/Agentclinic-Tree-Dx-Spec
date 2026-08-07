# DA / d2_heldout200b / case 486

- **gold**: Histoid leprosy
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=0
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=47 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Lepromatous leprosy, Borderline leprosy, Lupus vulgaris, Erythema nodosum leprosum, Histoid leprosy; gold_in_s3=True
- S4 champion: **Lepromatous leprosy**; gold_match=False
- S2 gold matches: Histoid leprosy

## Backbone v0
- S2 pool n=15 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Leprosy, Lepromatous leprosy, Borderline leprosy, Lucio leprosy, Mycobacterium leprae infection; gold_in_s3=True
- S4 champion: **Lepromatous leprosy**; gold_match=False
- S2 gold matches: Leprosy, Histoid leprosy

## Baseline B06 MAC
- pred: Leprosy; Lupus vulgaris
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Leprosy', 'Lupus vulgaris']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Lupus vulgaris; Other granulomatous disease (e.g., sarcoidosis)
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lupus vulgaris', 'Other granulomatous disease (e.g., sarcoidosis)']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
