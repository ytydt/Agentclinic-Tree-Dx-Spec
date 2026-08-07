# MCR / mcr_v2 / case 173

- **gold**: Chronic subdural hematoma
- **layer**: `e7_win_rank`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=48 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Subdural hematoma, Spontaneous intracranial hypotension, Posterior reversible encephalopathy syndrome, Cerebral venous sinus thrombosis, Chronic subdural hematoma; gold_in_s3=True
- S4 champion: **Chronic subdural hematoma**; gold_match=True
- S2 gold matches: Subdural hematoma, Chronic subdural hematoma

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Subdural hematoma, Spontaneous intracranial hypotension, Chronic subdural hematoma, Reversible cerebral vasoconstriction syndrome, Cerebral venous sinus thrombosis; gold_in_s3=True
- S4 champion: **Chronic subdural hematoma**; gold_match=True
- S2 gold matches: Subdural hematoma, Chronic subdural hematoma

## Baseline B06 MAC
- pred: Subdural hematoma; Pseudomeningocele
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Subdural hematoma', 'Pseudomeningocele']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Subdural Hematoma; Post-Dural Puncture Headache (PDPH)
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Subdural Hematoma', 'Post-Dural Puncture Headache (PDPH)']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Epidural Hematoma; Post-Dural Puncture Headache
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Epidural Hematoma', 'Post-Dural Puncture Headache']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
