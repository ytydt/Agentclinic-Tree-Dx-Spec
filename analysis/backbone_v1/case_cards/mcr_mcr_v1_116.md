# MCR / mcr_v1 / case 116

- **gold**: systemic sclerosis sine scleroderma
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=1
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Systemic Sclerosis, Limited Systemic Sclerosis, CREST Syndrome, Mixed Connective Tissue Disease, Pulmonary Arterial Hypertension associated with Connective Tissue Disease; gold_in_s3=True
- S4 champion: **Limited Systemic Sclerosis**; gold_match=False
- S2 gold matches: Systemic Sclerosis, Scleroderma

## Backbone v0
- S2 pool n=17 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Systemic Sclerosis, Limited Systemic Sclerosis, CREST Syndrome, Pulmonary Hypertension associated with Connective Tissue Disease, Mixed Connective Tissue Disease; gold_in_s3=True
- S4 champion: **Limited Systemic Sclerosis**; gold_match=False
- S2 gold matches: Systemic Sclerosis, Scleroderma

## Baseline B06 MAC
- pred: Systemic Sclerosis; Mixed Connective Tissue Disease
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Systemic Sclerosis', 'Mixed Connective Tissue Disease']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Limited Systemic Sclerosis (CREST syndrome); Systemic Sclerosis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Limited Systemic Sclerosis (CREST syndrome)', 'Systemic Sclerosis']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Limited Systemic Sclerosis; Systemic Sclerosis
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Limited Systemic Sclerosis', 'Systemic Sclerosis']
- cand_recall=True

## APHHM
- tree_n=38 tree_recall=True
- final_n=1 final_recall=True fail_mode=final_ok
- final_ranking: Systemic Sclerosis
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
