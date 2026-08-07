# DA / d2_heldout100 / case 334

- **gold**: Phaeohyphomycosis
- **layer**: `all_miss_but_recalled`  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **recall**: e7=0 v0=0 B06=1 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `hard_miss|s3_s4_ranking`
- **one_liner**: 并集召回但终值全错

## Backbone e7
- S2 pool n=61 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Chromoblastomycosis, Leprosy, Rhinoscleroma, Mycetoma, Exophiala infection; gold_in_s3=False
- S4 champion: **Chromoblastomycosis**; gold_match=False

## Backbone v0
- S2 pool n=22 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Leprosy, Relapsing polychondritis, Granulomatosis with polyangiitis, Lupus vulgaris, Chronic cutaneous lupus erythematosus; gold_in_s3=False
- S4 champion: **Lupus vulgaris**; gold_match=False

## Baseline B06 MAC
- pred: Chromoblastomycosis; Phaeohyphomycosis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Chromoblastomycosis', 'Phaeohyphomycosis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Eumycetoma; Chromoblastomycosis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Eumycetoma', 'Chromoblastomycosis']
- cand_recall=False

## APHHM
- tree_n=19 tree_recall=False
- final_n=4 final_recall=False fail_mode=tree_miss
- final_ranking: Chromoblastomycosis, Relapsing Polychondritis, Chronic Granulomatous Disease, Sarcoidosis
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
