# MCR / mcr_v2 / case 166

- **gold**: Contrast-induced encephalopathy
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **recall**: e7=0 v0=0 B06=1 B07=1
- **auto_tags**: multiagent_vote, kb_or_rag_hit
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=50 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Hypoxic-Ischemic Encephalopathy, Cerebral Edema, Seizure Disorder, Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS), Neonatal Encephalopathy with Seizures in Term Newborns; gold_in_s3=False
- S4 champion: **Hypoxic-Ischemic Encephalopathy**; gold_match=False

## Backbone v0
- S2 pool n=19 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Hypoxic-Ischemic Encephalopathy, Cerebral Edema, Seizure Disorder, Arterial Ischemic Stroke, Reversible Posterior Leukoencephalopathy Syndrome; gold_in_s3=False
- S4 champion: **Hypoxic-Ischemic Encephalopathy**; gold_match=False

## Baseline B06 MAC
- pred: Contrast-Induced Encephalopathy; Cerebral Edema
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Contrast-Induced Encephalopathy', 'Cerebral Edema']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Contrast-induced encephalopathy; Cerebral complication related to complex congenital heart disease
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Contrast-induced encephalopathy', 'Cerebral complication related to complex congenital heart disease']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Contrast-induced encephalopathy; Hypoxic-ischemic encephalopathy
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Contrast-induced encephalopathy', 'Hypoxic-ischemic encephalopathy']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
