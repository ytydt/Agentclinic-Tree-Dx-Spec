# MCR / mcr_200b / case 322

- **gold**: Factitious disorder
- **layer**: `base_win_recall`  aphhm_layer=``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01=1 APHHM=
- **recall**: e7=0 v0=1 B06=1 B07=1
- **auto_tags**: multiagent_vote, kb_or_rag_hit
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=51 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Mast Cell Activation Syndrome, Idiopathic Anaphylaxis, Vocal Cord Dysfunction, Eosinophilic Esophagitis, Autoimmune Angioedema; gold_in_s3=False
- S4 champion: **Vocal Cord Dysfunction**; gold_match=False

## Backbone v0
- S2 pool n=20 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Vocal Cord Dysfunction, Factitious Disorder, Panic Disorder, Asthma, Somatoform Disorder; gold_in_s3=True
- S4 champion: **Factitious Disorder**; gold_match=True
- S2 gold matches: Factitious Disorder

## Baseline B06 MAC
- pred: Factitious disorder; Somatoform disorder
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Factitious disorder', 'Somatoform disorder']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Factitious Disorder Imposed on Self; Somatoform Disorder
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Factitious Disorder Imposed on Self', 'Somatoform Disorder']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Factitious disorder; Munchausen syndrome
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Factitious disorder', 'Munchausen syndrome']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
