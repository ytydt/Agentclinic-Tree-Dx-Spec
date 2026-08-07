# MCR / mcr_200b / case 431

- **gold**: congenital cytomegalovirus infection
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=1 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=52 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Porencephaly, Congenital cytomegalovirus infection, Fetal stroke, Schizencephaly, Congenital disorder of glycosylation; gold_in_s3=True
- S4 champion: **Porencephaly**; gold_match=False
- S2 gold matches: Congenital cytomegalovirus infection

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Porencephaly, Congenital cytomegalovirus infection, Fetal stroke, Schizencephaly, Perinatal stroke; gold_in_s3=True
- S4 champion: **Porencephaly**; gold_match=False
- S2 gold matches: Congenital cytomegalovirus infection

## Baseline B06 MAC
- pred: Intracranial hemorrhage; Porencephaly
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Intracranial hemorrhage', 'Porencephaly']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Porencephaly; Schizencephaly
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Porencephaly', 'Schizencephaly']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Congenital Cytomegalovirus Infection; Prenatal Intracranial Hemorrhage
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Congenital Cytomegalovirus Infection', 'Prenatal Intracranial Hemorrhage']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
