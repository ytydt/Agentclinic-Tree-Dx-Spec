# MCR / mcr_v2 / case 197

- **gold**: Pseudoseptic arthritis
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=50 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Septic arthritis, Viscosupplementation-related inflammatory reaction, Crystal-induced arthritis, Pseudogout, Hypersensitivity reaction to Synvisc; gold_in_s3=True
- S4 champion: **Viscosupplementation-related inflammatory reaction**; gold_match=False
- S2 gold matches: Septic arthritis

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Septic arthritis, Viscosupplementation-related inflammatory reaction, Crystal-induced arthritis, Gonococcal arthritis, Pseudogout; gold_in_s3=True
- S4 champion: **Viscosupplementation-related inflammatory reaction**; gold_match=False
- S2 gold matches: Septic arthritis

## Baseline B06 MAC
- pred: Pseudoseptic Arthritis; Septic Arthritis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Pseudoseptic Arthritis', 'Septic Arthritis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Aseptic inflammatory reaction to Synvisc injections; Septic arthritis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Aseptic inflammatory reaction to Synvisc injections', 'Septic arthritis']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Septic Arthritis; Aseptic Inflammatory Reaction
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Septic Arthritis', 'Aseptic Inflammatory Reaction']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
