# DA / d2_heldout100 / case 411

- **gold**: Left posterior fascicular ventricular tachycardia (FVT)
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=44 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Atrioventricular Nodal Reentrant Tachycardia, Orthodromic Atrioventricular Reentrant Tachycardia, Atrial Flutter, Supraventricular Tachycardia with Aberrancy, Wolff-Parkinson-White Syndrome; gold_in_s3=False
- S4 champion: **Atrioventricular Nodal Reentrant Tachycardia**; gold_match=False
- S2 gold matches: Ventricular Tachycardia, Fascicular Ventricular Tachycardia

## Backbone v0
- S2 pool n=17 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Atrioventricular Nodal Reentrant Tachycardia, Orthodromic Atrioventricular Reentrant Tachycardia, Atrial Flutter, Supraventricular Tachycardia with Aberrancy, Focal Atrial Tachycardia; gold_in_s3=False
- S4 champion: **Atrioventricular Nodal Reentrant Tachycardia**; gold_match=False
- S2 gold matches: Ventricular Tachycardia

## Baseline B06 MAC
- pred: Atrial Flutter; Atrioventricular Nodal Reentrant Tachycardia
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Atrial Flutter', 'Atrioventricular Nodal Reentrant Tachycardia']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Atrial Tachycardia with 3:2 Block; Supraventricular Tachycardia with Incomplete Right Bundle Branch Block
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Atrial Tachycardia with 3:2 Block', 'Supraventricular Tachycardia with Incomplete Right Bundle Branch Block']
- cand_recall=False

## APHHM
- tree_n=58 tree_recall=True
- final_n=2 final_recall=False fail_mode=prune_loss
- final_ranking: Atrioventricular Nodal Reentrant Tachycardia, dilated cardiomyopathy
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
