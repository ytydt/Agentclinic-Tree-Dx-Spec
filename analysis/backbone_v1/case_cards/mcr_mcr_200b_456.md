# MCR / mcr_200b / case 456

- **gold**: Ureteroarterial fistula
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **recall**: e7=0 v0=0 B06=1 B07=0
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=48 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Radiation cystitis, Ureteroenteric fistula, Arteriovenous fistula, Pseudoaneurysm, Ureteral stricture; gold_in_s3=False
- S4 champion: **Radiation cystitis**; gold_match=False

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Radiation cystitis, Ureteroenteric fistula, Arteriovenous fistula, Pseudoaneurysm, Ureteral stricture; gold_in_s3=False
- S4 champion: **Radiation cystitis**; gold_match=False

## Baseline B06 MAC
- pred: Ureteroarterial fistula; Ureteroileal fistula
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Ureteroarterial fistula', 'Ureteroileal fistula']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Radiation-induced ureteral damage; Ureteroileal fistula with recurrent hematuria
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Radiation-induced ureteral damage', 'Ureteroileal fistula with recurrent hematuria']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Radiation Cystitis; Ureteroileal Fistula
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Radiation Cystitis', 'Ureteroileal Fistula']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
