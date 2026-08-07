# DA / d2_heldout200b / case 698

- **gold**: Concurrent pulmonary and cerebral mucormycosis
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `mapper_rescue`
- **one_liner**: e7 S2召回金标但S3/S4丢掉；DA option@1仍对→mapper捡漏，非入口广度

## Backbone e7
- S2 pool n=48 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Lung cancer with brain metastasis, Intracranial fungal infection, Aspergillosis, Cerebral abscess, Glioblastoma; gold_in_s3=False
- S4 champion: **Intracranial fungal infection**; gold_match=False
- S2 gold matches: Mucormycosis

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Brain metastasis from lung cancer, Aspergillosis, Cerebral abscess, Glioblastoma, Lung cancer with brain metastasis and fungal infection; gold_in_s3=False
- S4 champion: **Lung cancer with brain metastasis and fungal infection**; gold_match=False
- S2 gold matches: Mucormycosis

## Baseline B06 MAC
- pred: Cerebral aspergillosis; Brain metastasis from lung cancer
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Cerebral aspergillosis', 'Brain metastasis from lung cancer']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Cerebral aspergillosis with lung aspergillosis; Cerebral mucormycosis with lung cancer
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Cerebral aspergillosis with lung aspergillosis', 'Cerebral mucormycosis with lung cancer']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
