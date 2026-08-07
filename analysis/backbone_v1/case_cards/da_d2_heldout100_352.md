# DA / d2_heldout100 / case 352

- **gold**: Neurocysticercosis
- **layer**: `all_miss_but_recalled`  aphhm_layer=``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=0
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=45 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Idiopathic Intracranial Hypertension, Pseudotumor Cerebri, Posterior Fossa Arachnoid Cyst, Dandy-Walker Malformation, Chiari Malformation; gold_in_s3=False
- S4 champion: **Posterior Fossa Arachnoid Cyst**; gold_match=False
- S2 gold matches: Cysticercosis, Neurocysticercosis

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Idiopathic Intracranial Hypertension, Arachnoid Cyst, Dandy-Walker Malformation, Pseudotumor Cerebri, Optic Neuritis; gold_in_s3=False
- S4 champion: **Idiopathic Intracranial Hypertension**; gold_match=False
- S2 gold matches: Cysticercosis

## Baseline B06 MAC
- pred: Idiopathic Intracranial Hypertension; Pseudotumor Cerebri
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Idiopathic Intracranial Hypertension', 'Pseudotumor Cerebri']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Idiopathic Intracranial Hypertension (IIH); Space-Occupying Lesion (e.g., Tumor)
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Idiopathic Intracranial Hypertension (IIH)', 'Space-Occupying Lesion (e.g., Tumor)']
- cand_recall=False

## APHHM
- tree_n=21 tree_recall=False
- final_n=1 final_recall=False fail_mode=tree_miss
- final_ranking: Idiopathic Intracranial Hypertension
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
