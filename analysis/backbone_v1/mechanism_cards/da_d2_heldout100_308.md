# DA / d2_heldout100 / case 308

- **gold**: Periorbital Discoid Lupus Erythematosus (DLE)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=1 B01= APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=1

## Vignette
A woman in her 70s presented with a pruritic and painful periorbital eruption that had lasted 1 month. Her medical history included lupus nephritis requiring hemodialysis, immune thrombocytopenia, acute myeloid leukemia, chemotherapy-induced peripheral neuropathy, deep vein thrombosis, diverticulitis, and postcolectomy diarrhea. Past treatments included hydroxychloroquine (resulted in retinal toxic effects) and lenalidomide (severely worsened platelet count, with a nadir of 28 ×103/μL).

Physical examination demonstrated scaly, crusted pink plaques that involved the periorbital skin.

- Biopsy Results: Punch biopsy from the left upper eyelid demonstrated vacuolar interface dermatitis with follicular involvement and epidermal atrophy.- Images:  Image Title: Figure 1. Frontal View of Periorbital Lesions Before and After 2 Months of Treatment  Image Description: Frontal view showing periorbital involvement    Image Title: Figure 2. Views of Periorbital Lesions Before and After 2 Months of Treatment  Image Description: Views from the right and left sides

What is the most likely diagnosis?

Options:
A. Chronic cutaneous lupus erythematosus (CCLE)
B. Cutaneous lupus erythematosus
C. Per…

## Options
- A: Chronic cutaneous lupus erythematosus (CCLE)
- B: Cutaneous lupus erythematosus
- C: Periorbital Discoid Lupus Erythematosus (DLE) **←gold**
- D: Subacute cutaneous lupus erythematosus

## Backbone e7

- S2 n=49 gold_rank=1
  - clusters: gold=1 near=7 other=41
- S3 shortlist (5):
  - [gold] Discoid lupus erythematosus
  - [near] Subacute cutaneous lupus erythematosus
  - [near] Lupus erythematosus tumidus
  - [other] Rowell's syndrome
  - [near] Cutaneous lupus erythematosus
    - why_kept(Discoid lupus erythematosus): Patient has a history of lupus nephritis and the biopsy showed vacuolar interface dermatitis, which is consistent with discoid lupus erythematosus
    - why_kept(Subacute cutaneous lupus erythematosus): Patient has a history of lupus nephritis and the presentation of scaly, crusted pink plaques is consistent with subacute cutaneous lupus erythematosus
    - why_kept(Lupus erythematosus tumidus): Patient has a history of lupus nephritis and the presentation of periorbital eruption is consistent with lupus erythematosus tumidus
    - why_kept(Rowell's syndrome): Patient has a history of lupus nephritis and the presentation of scaly, crusted pink plaques with follicular involvement is consistent with Rowell's syndrome
    - why_kept(Cutaneous lupus erythematosus): Patient has a history of lupus nephritis and the biopsy showed vacuolar interface dermatitis, which is consistent with cutaneous lupus erythematosus
- S4 champion: **Discoid lupus erythematosus** cluster=gold jaccard=0.60
- S4 rationale: The patient's presentation of scaly, crusted pink plaques on the periorbital skin, along with biopsy results showing vacuolar interface dermatitis, follicular involvement, and epidermal atrophy, is most consistent with discoid lupus erythematosus, especially given her history of lupus nephritis.
- S4 rejected:
  - [near] Subacute cutaneous lupus erythematosus: This condition typically presents with papulosquamous or annular polycyclic lesions in a photodistributed pattern, which does not match the patient's periorbital eruption.
  - [near] Lupus erythematosus tumidus: This condition is characterized by urticaria-like lesions without epidermal involvement, which does not fit the patient's scaly, crusted plaques and biopsy findings.
  - [other] Rowell's syndrome: This is a rare condition characterized by the coexistence of lupus erythematosus and erythema multiforme, which does not align with the patient's presentation of periorbital plaques and biopsy results.
  - [near] Cutaneous lupus erythematosus: This is a broader category that includes discoid lupus erythematosus, but the specific presentation and biopsy findings in this case point more directly to discoid lupus erythematosus as the most accurate diagnosis.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Cutaneous Lupus Erythematosus', 'Discoid Lupus Erythematosus']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Cutaneous Lupus Erythematosus', 'Discoid Lupus Erythematosus', 'Lupus Erythematosus Tumidus', 'Subacute Cutaneous Lupus Erythematosus', 'Chronic Cutaneous Lupus Erythematosus', 'Cutaneous Lupus Erythematosus', 'Discoid Lupus Erythematosus', 'Subacute Cutaneous Lupus Erythematosus']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Cutaneous Lupus Erythematosus', 'Drug Eruption']
- diagnose: ['Cutaneous Lupus Erythematosus', 'Drug Eruption']
- queries: ['lupus nephritis skin manifestations', 'vacuolar interface dermatitis causes', 'periorbital eruption in immunocompromised patients']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=28 final_n=1
- final: ['Subacute Cutaneous Lupus Erythematosus']
- tree gold_cluster_n=3 final gold=False

