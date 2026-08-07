# MCR / mcr_200b / case 458

- **gold**: Lymphangioleiomyomatosis
- **layer**: `base_win_rank`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=1 APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, near_synonym_judge
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: e7召回并进短表但S4选错；基线排对

## Backbone e7
- S2 pool n=46 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Lymphangioleiomyomatosis, Birt-Hogg-Dube syndrome, Ehlers-Danlos syndrome, Pulmonary Langerhans cell histiocytosis, Tuberous sclerosis complex; gold_in_s3=True
- S4 champion: **Birt-Hogg-Dube syndrome**; gold_match=False
- S2 gold matches: Lymphangioleiomyomatosis

## Backbone v0
- S2 pool n=15 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Birt-Hogg-Dube syndrome, Lymphangioleiomyomatosis, Ehlers-Danlos syndrome, Alpha-1 antitrypsin deficiency, Pulmonary Langerhans cell histiocytosis; gold_in_s3=True
- S4 champion: **Birt-Hogg-Dube syndrome**; gold_match=False
- S2 gold matches: Lymphangioleiomyomatosis

## Baseline B06 MAC
- pred: Birt-Hogg-Dube syndrome; lymphangioleiomyomatosis
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Birt-Hogg-Dube syndrome', 'lymphangioleiomyomatosis']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Lymphangioleiomyomatosis (LAM); Birt-Hogg-Dube syndrome
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Lymphangioleiomyomatosis (LAM)', 'Birt-Hogg-Dube syndrome']
- cand_recall=True

## Baseline B01 CoT-RAG
- pred: Lymphangioleiomyomatosis; Pulmonary Langerhans cell histiocytosis
- method=CoT-RAG; retrieval_chunks=12
- top2 raw: ['Lymphangioleiomyomatosis', 'Pulmonary Langerhans cell histiocytosis']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
