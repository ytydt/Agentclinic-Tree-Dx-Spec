# DA / d2_heldout100 / case 424

- **gold**: Hyperkeratosis lenticularis perstans (HLP), unilateral presentation
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`agents_miss` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: APHHM=tree_hit_final_drop
- **covariates**: vig_words=177; gold_words=6; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=True
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A man in his 60s presented with a 10-year history of a slowly progressive, asymptomatic cutaneous eruption on his left leg. He had a 16-year history of diabetes mellitus that was being treated with metformin. There was no history of another endocrine disorder or malignant neoplasm. There was no family history of similar cutaneous findings.  Reddish brown hyperkeratotic papules 1 to 10 mm wide were present on the front and back of the left leg from knee to ankle. Removal of the scales caused slig...

## Options
  - A: Psoriasis
  - B: Necrobiosis lipoidica diabeticorum
  - C: Hypertrophic lichen planus
  - D: Hyperkeratosis lenticularis perstans (HLP), unilateral presentation

## Backbone e7
- S1 key_facts: 10-year history of slowly progressive cutaneous eruption; Asymptomatic; Location: front and back of the left leg from knee to ankle; Papules 1 to 10 mm wide; 16-year history of diabetes mellitus; Treated with metformin; No history of another endocrine disorder or malignant neoplasm; No family history of similar cutaneous findings
- S2 mode=complement k=3 pool_n=45 gold_in_s2=False
  - call1: ['Necrobiotic xanthogranuloma', 'Granuloma faciale', 'Discoid lupus erythematosus', 'Lichen planus', 'Lichenoid keratosi
  - call2: ['Lichen nitidus', 'Pityriasis rubra pilaris', 'Grover disease', 'Darier disease', 'Hailey-Hailey disease', 'Dowling-Deg
  - call3: ['Lichen sclerosus', 'Scleromyxedema', 'Erythema gyratum repens', 'Pityriasis lichenoides chronica', 'Mucha-Habermann di
- S3 shortlist n=5 gold=False: Lichen planus, Psoriasis, Lichenoid keratosis, Discoid lupus erythematosus, Granuloma faciale
- S4 champion: **Lichenoid keratosis** gold=False
- S4 raw (trunc): {"champion": "Lichenoid keratosis", "rationale": "The presence of compact hyperkeratosis, epidermal atrophy, and bandlike lymphocyte infiltrate in the superficial dermis on lesional skin biopsy, along with the clinical presentation of reddish brown hyperkeratotic papules, is most

## Backbone v0 (compact)
- S1 key_facts: 10-year history of slowly progressive cutaneous eruption; Eruption located on the front and back of the left leg; Papules are 1 to 10 mm wide; Patient has a 16-year history of diabetes mellitus; Diabetes is being treated with metformin; No history of another endocrine disorder or malignant neoplasm; No family history of similar cutaneous findings; Hematological and biochemical test results are unremarkable
- S2 mode=single k=1 pool_n=20 gold_in_s2=False
  - call1: ['Necrobiotic xanthogranuloma', 'Granuloma faciale', 'Discoid lupus erythematosus', 'Lichen planus', 'Lichenoid keratosi
- S3 shortlist n=5 gold=False: Porokeratosis, Lichenoid keratosis, Psoriasis, Discoid lupus erythematosus, Lichen planus
- S4 champion: **Porokeratosis** gold=False
- S4 raw (trunc): {"champion": "Porokeratosis", "rationale": "The patient's presentation of slowly progressive, asymptomatic cutaneous eruption with reddish brown hyperkeratotic papules and the histopathological findings of compact hyperkeratosis, epidermal atrophy, and bandlike lymphocyte infiltr

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's 10-year history of a slowly progressive, asymptomatic cutaneous eruption on his left leg, along with the presence of reddish brown hyperkeratotic 
  - turn1 gold_mention=False diag=
    The patient's long history of diabetes and the presence of characteristic skin lesions support the primary diagnosis, with the provided pathology results furthe
  - turn2 gold_mention=False diag=
    The patient's clinical presentation and histopathological findings are consistent with Necrobiosis lipoidica, a condition commonly associated with diabetes mell
- supervisor votes=3 top2=['Necrobiosis lipoidica', 'Granuloma annulare'] gold=False

## Baseline B07
- draft=['Necrobiosis Lipoidica Diabeticorum', 'Piezogenic Pedal Papules'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['diagnosis of hyperkeratotic papules on leg', 'cutaneous eruption in diabetes', 'skin biopsy showing compact hyperkeratosis and bandlike lymphocyte infiltrate']
- diagnose=['Necrobiosis Lipoidica Diabeticorum', 'Piezogenic Pedal Papules'] gold=False

## APHHM
- tree_n=69 tree_recall=True
- gold_leaf=B1.14:hyperkeratosis parent=B1
- final_n=5 final_recall=False ranking=['Necrolytic Migratory Erythema', 'psoriasis', 'Lichenoid Keratosis', 'Pityriasis Rubra Pilaris', 'Necrobiosis lipoidica']
- human_at1=False fail_mode=prune_loss

