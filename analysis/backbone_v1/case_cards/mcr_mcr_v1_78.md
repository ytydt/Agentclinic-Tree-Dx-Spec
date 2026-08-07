# MCR / mcr_v1 / case 78

- **gold**: schwannoma
- **layer**: `base_win_rank`  aphhm_layer=`aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=0
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=44 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Schwannoma, Neurofibroma, Tarlov cyst, Ganglion cyst, Plexiform neurofibroma; gold_in_s3=True
- S4 champion: **Tarlov cyst**; gold_match=False
- S2 gold matches: Schwannoma, Ancient schwannoma, Cellular schwannoma, Melanotic schwannoma, Plexiform schwannoma

## Backbone v0
- S2 pool n=16 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Schwannoma, Neurofibroma, Tarlov cyst, Plexiform neurofibroma, Intraneural ganglion cyst; gold_in_s3=True
- S4 champion: **Intraneural ganglion cyst**; gold_match=False
- S2 gold matches: Schwannoma

## Baseline B06 MAC
- pred: Schwannoma; Neurofibroma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Schwannoma', 'Neurofibroma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Peripheral Nerve Sheath Tumor (PNST); Neurofibroma
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Peripheral Nerve Sheath Tumor (PNST)', 'Neurofibroma']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Peroneal nerve sheath tumor; Neurofibroma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Peroneal nerve sheath tumor', 'Neurofibroma']
- cand_recall=False

## APHHM
- tree_n=25 tree_recall=True
- final_n=2 final_recall=True fail_mode=final_ok
- final_ranking: intraneural ganglion cyst, sciatic schwannoma
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
