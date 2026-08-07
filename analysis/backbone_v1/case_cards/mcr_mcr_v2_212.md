# MCR / mcr_v2 / case 212

- **gold**: Neurofibromatosis type 2
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **recall**: e7=0 v0=0 B06=1 B07=1
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Neurofibromatosis type 1, Paracentral acute middle maculopathy, Optic neuritis, Neurofibroma-related optic glioma, Multiple sclerosis; gold_in_s3=False
- S4 champion: **Neurofibromatosis type 1**; gold_match=False

## Backbone v0
- S2 pool n=18 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Neurofibromatosis type 1, Paracentral acute middle maculopathy, Optic neuritis, Acute posterior multifocal placoid pigment epitheliopathy, Neuromyelitis optica; gold_in_s3=False
- S4 champion: **Neurofibromatosis type 1**; gold_match=False

## Baseline B06 MAC
- pred: Neurofibromatosis type 2; Paracentral acute middle maculopathy
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Neurofibromatosis type 2', 'Paracentral acute middle maculopathy']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Neurofibromatosis Type 1; Neurofibromatosis Type 2
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Neurofibromatosis Type 2', 'Neurofibromatosis Type 1']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Neurofibromatosis type 1; Paracentral acute middle maculopathy
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Neurofibromatosis type 1', 'Paracentral acute middle maculopathy']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
