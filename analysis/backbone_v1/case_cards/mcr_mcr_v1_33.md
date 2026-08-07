# MCR / mcr_v1 / case 33

- **gold**: Dyke-Davidoff-Masson syndrome
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=1
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=52 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Rasmussen's encephalitis, Hemimegalencephaly, Dyke-Davidoff-Masson syndrome, Sturge-Weber syndrome, Porencephaly; gold_in_s3=True
- S4 champion: **Dyke-Davidoff-Masson syndrome**; gold_match=True
- S2 gold matches: Dyke-Davidoff-Masson syndrome

## Backbone v0
- S2 pool n=18 mode=None k=None; gold_in_s2=True
- S3 shortlist (5): Rasmussen's encephalitis, Hemimegalencephaly, Dyke-Davidoff-Masson syndrome, Sturge-Weber syndrome, Porencephaly; gold_in_s3=True
- S4 champion: **Dyke-Davidoff-Masson syndrome**; gold_match=True
- S2 gold matches: Dyke-Davidoff-Masson syndrome

## Baseline B06 MAC
- pred: Rasmussen's Encephalitis; Hemispheric Epilepsy Surgery Candidate
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ["Rasmussen's Encephalitis", 'Hemispheric Epilepsy Surgery Candidate']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Rasmussen's Encephalitis; Sturge-Weber Syndrome
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ["Rasmussen's Encephalitis", 'Sturge-Weber Syndrome']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Rasmussen's encephalitis; Hemiconvulsive-hemiplegic epilepsy
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ["Rasmussen's encephalitis", 'Hemiconvulsive-hemiplegic epilepsy']
- cand_recall=False

## APHHM
- tree_n=33 tree_recall=True
- final_n=5 final_recall=True fail_mode=final_ok
- final_ranking: Dyke-Davidoff-Masson syndrome, Rasmussen encephalitis, Hemimegalencephaly, Cerebral hemiatrophy-hemiplegia-epilepsy syndrome, Rasmussen's encephalitis
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
