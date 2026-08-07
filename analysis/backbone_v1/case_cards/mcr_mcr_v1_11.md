# MCR / mcr_v1 / case 11

- **gold**: Multisystem inflammatory syndrome in children
- **layer**: `base_win_recall`  aphhm_layer=`aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=0
- **recall**: e7=0 v0=0 B06=1 B07=1
- **auto_tags**: multiagent_vote, kb_or_rag_hit
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=65 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Streptococcal toxic shock syndrome, Kawasaki disease, Hemophagocytic lymphohistiocytosis, Meningococcemia, Sepsis syndrome; gold_in_s3=False
- S4 champion: **Streptococcal toxic shock syndrome**; gold_match=False

## Backbone v0
- S2 pool n=17 mode=None k=None; gold_in_s2=False
- S3 shortlist (5): Kawasaki disease, Meningococcemia, Hemophagocytic lymphohistiocytosis, Rickettsial disease, Brucellosis; gold_in_s3=False
- S4 champion: **Meningococcemia**; gold_match=False

## Baseline B06 MAC
- pred: Antiphospholipid syndrome; Multisystem inflammatory syndrome
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Antiphospholipid syndrome', 'Multisystem inflammatory syndrome']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Multisystem Inflammatory Syndrome; Antiphospholipid Syndrome (APS)
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Multisystem Inflammatory Syndrome', 'Antiphospholipid Syndrome (APS)']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Multisystem Inflammatory Syndrome in Children (MIS-C); Kawasaki Disease
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Kawasaki Disease']
- cand_recall=True

## APHHM
- tree_n=16 tree_recall=True
- final_n=4 final_recall=True fail_mode=final_ok
- final_ranking: Antiphospholipid syndrome, Systemic Lupus Erythematosus, Multisystem Inflammatory Syndrome in Children, Kawasaki Disease
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
