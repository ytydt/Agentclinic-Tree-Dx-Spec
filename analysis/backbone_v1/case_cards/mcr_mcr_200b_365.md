# MCR / mcr_200b / case 365

- **gold**: thyroglossal duct cyst
- **layer**: `e7_win_recall`  aphhm_layer=``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: entrance_breadth
- **manual_tag**: `entrance_breadth`
- **one_liner**: e7 S2召回且S4命中；基线候选未召回→入口/覆盖优势

## Backbone e7
- S2 pool n=45 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Thyroglossal duct cyst, Ranula, Dermoid cyst, Lingual thyroid, Base of tongue lymphangioma; gold_in_s3=True
- S4 champion: **Thyroglossal duct cyst**; gold_match=True
- S2 gold matches: Thyroglossal duct cyst

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Thyroglossal duct cyst, Lingual thyroid, Ranula, Dermoid cyst, Teratoma; gold_in_s3=True
- S4 champion: **Thyroglossal duct cyst**; gold_match=True
- S2 gold matches: Thyroglossal duct cyst

## Baseline B06 MAC
- pred: Base of tongue cyst; Obstructive sleep apnea
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Base of tongue cyst', 'Obstructive sleep apnea']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Vallecular cyst; Obstructive sleep apnea due to other base of tongue lesions
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Vallecular cyst', 'Obstructive sleep apnea due to other base of tongue lesions']
- cand_recall=False

## Baseline B01 CoT-RAG
- pred: Ranula; Cystic hygroma
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Ranula', 'Cystic hygroma']
- cand_recall=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
