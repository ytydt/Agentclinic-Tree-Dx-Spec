# MCR / mcr_200b / case 250

- **gold**: Toxocariasis
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **recall**: e7=0 v0=0 B06=0 B07=1
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Eosinophilic pericarditis, Hypereosinophilic syndrome, Viral myopericarditis, Churg-Strauss syndrome, Eosinophilic granulomatosis with polyangiitis; gold_in_s3=False
- S4 champion: **Eosinophilic pericarditis**; gold_match=False

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Viral myopericarditis, Eosinophilic pericarditis, Hypereosinophilic syndrome, Churg-Strauss syndrome, Postcardiac injury syndrome; gold_in_s3=False
- S4 champion: **Eosinophilic pericarditis**; gold_match=False

## Baseline B06 MAC
- pred: Toxocara infection; Eosinophilic pneumonia
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Toxocara infection', 'Eosinophilic pneumonia']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Loeffler syndrome; Toxocariasis
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Loeffler syndrome', 'Toxocariasis']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Hypereosinophilic syndrome; Toxocara infection
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Hypereosinophilic syndrome', 'Toxocara infection']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
