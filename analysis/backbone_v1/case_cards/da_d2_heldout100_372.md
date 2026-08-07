# DA / d2_heldout100 / case 372

- **gold**: Elevated Lipoprotein(a) causing discordance between direct and calculated LDL cholesterol measurements
- **layer**: ``  aphhm_layer=`aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=0 v0=0 B06=0 B07=0
- **auto_tags**: hard_miss
- **manual_tag**: `aphhm_prune_loss|hard_miss`
- **one_liner**: APHHM独错；他臂正确

## Backbone e7
- S2 pool n=47 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Familial hypercholesterolemia, Lipoprotein(a) hyperlipoproteinemia, Familial combined hyperlipidemia, Polygenic hypercholesterolemia, Secondary hyperlipidemia due to hypothyroidism; gold_in_s3=False
- S4 champion: **Lipoprotein(a) hyperlipoproteinemia**; gold_match=False

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Familial Hypercholesterolemia, Familial Defective Apolipoprotein B, Lipoprotein(a) Hyperlipoproteinemia, Familial Combined Hyperlipidemia, Polygenic Hypercholesterolemia; gold_in_s3=False
- S4 champion: **Familial Defective Apolipoprotein B**; gold_match=False

## Baseline B06 MAC
- pred: Familial Hypercholesterolemia; Lipid Profile Disorder
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Familial Hypercholesterolemia', 'Lipid Profile Disorder']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Familial Hypercholesterolemia; Polygenic Hypercholesterolemia
- method=MEDDx; queries=4; has_refine=True; draft_n=2
- diagnose top2: ['Familial Hypercholesterolemia', 'Polygenic Hypercholesterolemia']
- cand_recall=False

## APHHM
- tree_n=20 tree_recall=False
- final_n=2 final_recall=False fail_mode=tree_miss
- final_ranking: Familial Hypercholesterolemia, Dysbetalipoproteinemia
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
