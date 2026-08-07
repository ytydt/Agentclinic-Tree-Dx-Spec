# MCR / mcr_v1 / case 38

- **gold**: trigeminal schwannoma
- **layer**: `e7_win_rank`  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=0
- **auto_tags**: s3_s4_ranking, aphhm_prune_loss, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Vestibular schwannoma, Meningioma, Trigeminal schwannoma, Chordoma, Epidermoid cyst; gold_in_s3=True
- S4 champion: **Trigeminal schwannoma**; gold_match=True
- S2 gold matches: Trigeminal schwannoma

## Backbone v0
- S2 pool n=18 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Vestibular schwannoma, Meningioma, Trigeminal schwannoma, Cystic meningioma, Epidermoid cyst; gold_in_s3=True
- S4 champion: **Trigeminal schwannoma**; gold_match=True
- S2 gold matches: Trigeminal schwannoma

## Baseline B06 MAC
- pred: Schwannoma; Meningioma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Schwannoma', 'Meningioma']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Chordoma; Chondrosarcoma
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Chordoma', 'Chondrosarcoma']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Chordoma; Schwannoma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Chordoma', 'Schwannoma']
- cand_recall=True

## APHHM
- tree_n=34 tree_recall=True
- final_n=5 final_recall=False fail_mode=prune_loss
- final_ranking: Meningioma, Meningioma, Chordoma, Meningioma, Meningioma
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
