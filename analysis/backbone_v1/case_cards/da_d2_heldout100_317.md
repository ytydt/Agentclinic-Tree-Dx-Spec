# DA / d2_heldout100 / case 317

- **gold**: Pyoderma vegetans
- **layer**: `base_win_recall`  aphhm_layer=`aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=0
- **recall**: e7=0 v0=0 B06=1 B07=0
- **auto_tags**: multiagent_vote
- **manual_tag**: `multiagent_vote`
- **one_liner**: e7 S2未召回金标，基线直接命中→基线入口覆盖骨干盲区

## Backbone e7
- S2 pool n=49 mode=complement k=3; gold_in_s2=False
- S3 shortlist (5): Pyoderma gangrenosum, Sweet syndrome, Erythema elevatum diutinum, Generalized pustular psoriasis, Acute febrile neutrophilic dermatosis; gold_in_s3=False
- S4 champion: **Sweet syndrome**; gold_match=False

## Backbone v0
- S2 pool n=16 mode=single k=1; gold_in_s2=False
- S3 shortlist (5): Pyoderma gangrenosum, Sweet syndrome, Generalized pustular psoriasis, Subcorneal pustular dermatosis, Acute generalized exanthematous pustulosis; gold_in_s3=False
- S4 champion: **Pyoderma gangrenosum**; gold_match=False

## Baseline B06 MAC
- pred: Pyoderma gangrenosum; Pyoderma vegetans
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Pyoderma gangrenosum', 'Pyoderma vegetans']
- cand_recall=True

## Baseline B07 MEDDx
- pred: Acute Generalized Exanthematous Pustulosis (AGEP); Eosinophilic Dermatitis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Eosinophilic Dermatitis']
- cand_recall=False

## APHHM
- tree_n=23 tree_recall=False
- final_n=5 final_recall=False fail_mode=tree_miss
- final_ranking: Pyoderma gangrenosum, Sweet syndrome, Sweet syndrome, Sweet syndrome, Acute generalized exanthematous pustulosis
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
