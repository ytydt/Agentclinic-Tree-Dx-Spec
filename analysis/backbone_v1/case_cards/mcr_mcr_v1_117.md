# MCR / mcr_v1 / case 117

- **gold**: Antiphospholipid syndrome
- **layer**: ``  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **recall**: e7=0 v0=0 B06=1 B07=1
- **auto_tags**: hard_miss
- **manual_tag**: `aphhm_prune_loss|hard_miss`
- **one_liner**: APHHM独错；他臂正确

## Backbone e7
- S2 pool n=53 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Antiphospholipid syndrome, Leukocytoclastic vasculitis, Granulomatosis with polyangiitis, Eosinophilic granuloma with polyangiitis, Henoch-Schönlein purpura; gold_in_s3=True
- S4 champion: **Antiphospholipid syndrome**; gold_match=True

## Backbone v0
- S2 pool n=19 mode=None k=None; gold_in_s2=False
- S3 shortlist (5): Infectious vasculitis, Henoch-Schönlein purpura, Microscopic polyangiitis, Wegener's granulomatosis, Churg-Strauss syndrome; gold_in_s3=False
- S4 champion: **Infectious vasculitis**; gold_match=False

## Baseline B06 MAC
- pred: Antiphospholipid syndrome; Infectious mononucleosis due to Epstein-Barr virus
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Antiphospholipid syndrome', 'Infectious mononucleosis due to Epstein-Barr virus']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Antiphospholipid Syndrome; Respiratory Syncytial Virus Infection
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Antiphospholipid Syndrome', 'Respiratory Syncytial Virus Infection']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Antiphospholipid syndrome; Respiratory syncytial virus pneumonia
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Antiphospholipid syndrome', 'Respiratory syncytial virus pneumonia']
- cand_recall=True

## APHHM
- tree_n=83 tree_recall=False
- final_n=3 final_recall=False fail_mode=tree_miss
- final_ranking: Cryoglobulinemic vasculitis, Systemic Lupus Erythematosus, Hemophagocytic lymphohistiocytosis
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
