# MCR / mcr_v1 / case 95

- **gold**: Tuberculosis
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `hard_miss|s3_s4_ranking`
- **one_liner**: 并集召回但终值全错

## Backbone e7
- S2 pool n=55 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Disseminated tuberculosis, Pneumocystis jirovecii pneumonia, Cytomegalovirus infection, Mycobacterium avium complex infection, Cryptococcosis; gold_in_s3=True
- S4 champion: **Disseminated tuberculosis**; gold_match=True
- S2 gold matches: Disseminated tuberculosis

## Backbone v0
- S2 pool n=18 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Disseminated tuberculosis, Pneumocystis jirovecii pneumonia, Cytomegalovirus infection, Cryptococcosis, Mycobacterium avium complex infection; gold_in_s3=True
- S4 champion: **Disseminated tuberculosis**; gold_match=True
- S2 gold matches: Disseminated tuberculosis

## Baseline B06 MAC
- pred: Disseminated tuberculosis; Cryptococcal meningitis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Disseminated tuberculosis', 'Cryptococcal meningitis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Disseminated Tuberculosis; Sepsis due to an opportunistic infection
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Disseminated Tuberculosis', 'Sepsis due to an opportunistic infection']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Disseminated histoplasmosis; Pneumocystis jirovecii pneumonia
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Disseminated histoplasmosis', 'Pneumocystis jirovecii pneumonia']
- cand_recall=False

## APHHM
- tree_n=27 tree_recall=True
- final_n=1 final_recall=False fail_mode=prune_loss
- final_ranking: Disseminated Mycobacterium avium complex
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
