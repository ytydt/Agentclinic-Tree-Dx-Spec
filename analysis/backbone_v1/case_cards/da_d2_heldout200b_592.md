# DA / d2_heldout200b / case 592

- **gold**: Pulmonary Reperfusion Injury after catheter-directed thrombectomy for acute pulmonary embolism
- **layer**: `e7_win_rank`  aphhm_layer=``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 双方都召回，e7排对而基线排错→选择/裁决差异

## Backbone e7
- S2 pool n=45 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Pulmonary Embolism, Acute Cor Pulmonale, Pulmonary Hypertension Crisis, Cardiogenic Shock, Acute Respiratory Distress Syndrome; gold_in_s3=True
- S4 champion: **Pulmonary Embolism**; gold_match=True
- S2 gold matches: Pulmonary Embolism

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Pulmonary Embolism, Acute Cor Pulmonale, Acute Right Ventricular Failure, Cardiogenic Shock, Submassive Pulmonary Embolism; gold_in_s3=True
- S4 champion: **Pulmonary Embolism**; gold_match=True
- S2 gold matches: Pulmonary Embolism

## Baseline B06 MAC
- pred: Pulmonary Embolism; Heart Failure
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Pulmonary Embolism', 'Heart Failure']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Acute Pulmonary Embolism (PE); Right Ventricular Dysfunction
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Acute Pulmonary Embolism (PE)', 'Right Ventricular Dysfunction']
- cand_recall=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
