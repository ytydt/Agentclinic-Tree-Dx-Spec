# DA / d2_heldout100 / case 349

- **gold**: Cutaneous histoplasmosis
- **layer**: `all_miss_but_recalled`  aphhm_layer=`aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **recall**: e7=1 v0=1 B06=0 B07=0
- **auto_tags**: s3_s4_ranking, hard_miss
- **manual_tag**: `s3_s4_ranking`
- **one_liner**: 至少一臂召回金标但无人Acc@1→排序天花板

## Backbone e7
- S2 pool n=57 mode=complement k=3; gold_in_s2=True
- S3 shortlist (5): Cryptococcosis, Blastomycosis, Histoplasmosis, Kaposi's sarcoma, Cutaneous lymphoma; gold_in_s3=True
- S4 champion: **Cryptococcosis**; gold_match=False
- S2 gold matches: Histoplasmosis

## Backbone v0
- S2 pool n=21 mode=single k=1; gold_in_s2=True
- S3 shortlist (5): Cryptococcosis, Blastomycosis, Histoplasmosis, Basal cell carcinoma, Squamous cell carcinoma; gold_in_s3=True
- S4 champion: **Cryptococcosis**; gold_match=False
- S2 gold matches: Histoplasmosis

## Baseline B06 MAC
- pred: Cryptococcosis; Basal cell carcinoma
- method=MAC; discussion_turns=3; votes=3
- supervisor top2: ['Cryptococcosis', 'Basal cell carcinoma']
- cand_recall=False

## Baseline B07 MEDDx
- pred: Cutaneous Leishmaniasis; Cryptococcosis
- method=MEDDx; queries=3; has_refine=True; draft_n=2
- diagnose top2: ['Cutaneous Leishmaniasis', 'Cryptococcosis']
- cand_recall=False

## APHHM
- tree_n=32 tree_recall=True
- final_n=2 final_recall=False fail_mode=prune_loss
- final_ranking: Cryptococcosis, Kaposi's sarcoma
- human_adjudication.at1=False

## Notes
- DA mapper modes: backbone/baselines=`typed_llm_disagreement_rag`; APHHM=`typed_llm` (do not over-read DA exclusive hits).
