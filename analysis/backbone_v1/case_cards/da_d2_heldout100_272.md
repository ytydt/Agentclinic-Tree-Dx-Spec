# DA / d2_heldout100 / case 272

- **gold**: Window-Period Acute Myocardial Infarction
- **layer**: `all_miss_but_recalled`  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **recall**: e7=1 v0=1 B06=1 B07=1
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=46 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Acute myocardial infarction, Unstable angina, Prinzmetal's angina, Acute coronary syndrome, Variant angina; gold_in_s3=True
- S4 champion: **Acute coronary syndrome**; gold_match=False
- S2 gold matches: Acute myocardial infarction

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Acute myocardial infarction, Unstable angina, Variant angina, Acute coronary syndrome, Spontaneous coronary artery dissection; gold_in_s3=True
- S4 champion: **Acute coronary syndrome**; gold_match=False
- S2 gold matches: Acute myocardial infarction

## Baseline B06 MAC
- pred: Acute Coronary Syndrome; Myocardial Infarction
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Acute Coronary Syndrome', 'Myocardial Infarction']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Acute Myocardial Infarction (NSTEMI); Unstable Angina
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Acute Myocardial Infarction (NSTEMI)', 'Unstable Angina']
- cand_recall=True

## APHHM
- tree_n=41 tree_recall=True
- final_n=4 final_recall=True fail_mode=final_ok
- final_ranking: myocardial infarction, acute coronary syndrome, Unstable Angina, Myocardial Ischemia
- human_adjudication.at1=True

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
