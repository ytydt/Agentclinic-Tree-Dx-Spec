# MCR / mcr_v2 / case 152

- **gold**: Squamous cell carcinoma
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=48 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Squamous cell carcinoma, Verrucous carcinoma, Chronic pyoderma gangrenosum, Keratoacanthoma, Mycetoma; gold_in_s3=True
- S4 champion: **Verrucous carcinoma**; gold_match=False
- S2 gold matches: Squamous cell carcinoma

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Squamous cell carcinoma, Verrucous carcinoma, Chronic pyoderma gangrenosum, Keratoacanthoma, Basal cell carcinoma; gold_in_s3=True
- S4 champion: **Verrucous carcinoma**; gold_match=False
- S2 gold matches: Squamous cell carcinoma

## Baseline B06 MAC
- pred: Squamous Cell Carcinoma; Keratoacanthoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Squamous Cell Carcinoma', 'Keratoacanthoma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Squamous Cell Carcinoma; Keratoacanthoma
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Squamous Cell Carcinoma', 'Keratoacanthoma']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Squamous cell carcinoma; Keratoacanthoma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Squamous cell carcinoma', 'Keratoacanthoma']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
