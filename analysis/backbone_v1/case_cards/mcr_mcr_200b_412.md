# MCR / mcr_200b / case 412

- **gold**: External cervical resorption
- **layer**: `e7_win_rank`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=54 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): External Cervical Resorption, Asymptomatic Irreversible Pulpitis, Periodontitis, Internal Cervical Resorption, Pulpal Necrosis; gold_in_s3=True
- S4 champion: **External Cervical Resorption**; gold_match=True
- S2 gold matches: External Cervical Resorption

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): External Cervical Resorption, Chronic Periodontitis, Asymptomatic Irreversible Pulpitis, Internal Cervical Resorption, Periodontal Abscess; gold_in_s3=True
- S4 champion: **External Cervical Resorption**; gold_match=True
- S2 gold matches: External Cervical Resorption

## Baseline B06 MAC
- pred: Asymptomatic Irreversible Pulpitis; External Cervical Resorption
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Asymptomatic Irreversible Pulpitis with Normal Apical Tissues; External Cervical Resorption
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Asymptomatic Irreversible Pulpitis with Normal Apical Tissues', 'External Cervical Resorption']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Asymptomatic Irreversible Pulpitis; External Cervical Resorption
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
