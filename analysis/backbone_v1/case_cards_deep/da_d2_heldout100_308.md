# DA / d2_heldout100 / case 308

- **gold**: Periorbital Discoid Lupus Erythematosus (DLE)
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=1 B01= APHHM=0
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: APHHM=tree_hit_final_drop
- **covariates**: vig_words=170; gold_words=5; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A woman in her 70s presented with a pruritic and painful periorbital eruption that had lasted 1 month. Her medical history included lupus nephritis requiring hemodialysis, immune thrombocytopenia, acute myeloid leukemia, chemotherapy-induced peripheral neuropathy, deep vein thrombosis, diverticulitis, and postcolectomy diarrhea. Past treatments included hydroxychloroquine (resulted in retinal toxic effects) and lenalidomide (severely worsened platelet count, with a nadir of 28 ×103/μL).  Physica...

## Options
  - A: Chronic cutaneous lupus erythematosus (CCLE)
  - B: Cutaneous lupus erythematosus
  - C: Periorbital Discoid Lupus Erythematosus (DLE)
  - D: Subacute cutaneous lupus erythematosus

## Backbone e7
- S1 key_facts: female patient in her 70s; periorbital eruption lasted 1 month; pruritic and painful eruption; scaly, crusted pink plaques on physical examination; biopsy showed vacuolar interface dermatitis; follicular involvement and epidermal atrophy on biopsy; patient has a history of lupus nephritis; patient has a history of immune thrombocytopenia
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Discoid lupus erythematosus', 'Cutaneous lupus erythematosus', 'Subacute cutaneous lupus erythematosus', 'Lichen planu
  - call2: ['Lupus erythematosus tumidus', "Rowell's syndrome", 'Chilblain lupus', 'Neutrophilic dermatosis of lupus erythematosus'
  - call3: ["Sjögren's syndrome-associated cutaneous lymphoid dyscrasia", 'Lupus erythematosus panniculitis', 'Nephrogenic systemic
- S3 shortlist n=5 gold=True: Discoid lupus erythematosus, Subacute cutaneous lupus erythematosus, Lupus erythematosus tumidus, Rowell's syndrome, Cutaneous lupus erythematosus
- S4 champion: **Discoid lupus erythematosus** gold=True
- S4 raw (trunc): {"champion": "Discoid lupus erythematosus", "rationale": "The patient's presentation of scaly, crusted pink plaques on the periorbital skin, along with biopsy results showing vacuolar interface dermatitis, follicular involvement, and epidermal atrophy, is most consistent with dis

## Backbone v0 (compact)
- S1 key_facts: female patient in her 70s; periorbital eruption lasted 1 month; pruritic and painful eruption; scaly, crusted pink plaques on physical examination; biopsy showed vacuolar interface dermatitis; follicular involvement and epidermal atrophy on biopsy; patient has a history of lupus nephritis; patient has a history of immune thrombocytopenia
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['Discoid lupus erythematosus', 'Cutaneous lupus erythematosus', 'Subacute cutaneous lupus erythematosus', 'Lichen planu
- S3 shortlist n=5 gold=True: Discoid lupus erythematosus, Cutaneous lupus erythematosus, Subacute cutaneous lupus erythematosus, Lichen planus, Dermatomyositis
- S4 champion: **Cutaneous lupus erythematosus** gold=False
- S4 raw (trunc): {"champion": "Cutaneous lupus erythematosus", "rationale": "The patient's history of lupus nephritis and the presence of vacuolar interface dermatitis on biopsy, along with follicular involvement and epidermal atrophy, are consistent with cutaneous lupus erythematosus. The perior

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of lupus nephritis and the biopsy results showing vacuolar interface dermatitis with follicular involvement and epidermal atrophy are high
  - turn1 gold_mention=True diag=
    The patient's history of lupus nephritis and the biopsy results are consistent with Doctor A's assessment, suggesting a cutaneous manifestation of lupus, with C
  - turn2 gold_mention=True diag=
    The patient's history of lupus nephritis and the biopsy results showing vacuolar interface dermatitis with follicular involvement and epidermal atrophy are cons
- supervisor votes=3 top2=['Cutaneous Lupus Erythematosus', 'Discoid Lupus Erythematosus'] gold=True

## Baseline B07
- draft=['Cutaneous Lupus Erythematosus', 'Drug Eruption'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['lupus nephritis skin manifestations', 'vacuolar interface dermatitis causes', 'periorbital eruption in immunocompromised patients']
- diagnose=['Cutaneous Lupus Erythematosus', 'Drug Eruption'] gold=False

## APHHM
- tree_n=28 tree_recall=True
- gold_leaf=B1.2:Discoid Lupus Erythematosus parent=B1
- final_n=1 final_recall=False ranking=['Subacute Cutaneous Lupus Erythematosus']
- human_at1=False fail_mode=prune_loss

