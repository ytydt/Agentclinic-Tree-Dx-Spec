# DA / d2_heldout100 / case 252

- **gold**: Folliculocentric lichen sclerosus et atrophicus
- **layer**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **loci**: e7=`s2_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`na` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=244; gold_words=5; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_win; primary loci above.

## Vignette (trunc)
A woman in her 60s presented with numerous whitish papules on the back of more than 10 years' duration. The lesions previously resolved with topical corticosteroids but flared soon after treatment discontinuation. Some papules became pruritic and extended to the waist and anterior trunk in the past month. No family history of similar lesions was recorded.  Multiple hypopigmented, flat-topped papules on the back, waist, and inframammary area without genital involvement. Most lesions were follicul...

## Options
  - A: Lichen Sclerosus
  - B: Lichen sclerosus et atrophicus
  - C: Folliculocentric lichen sclerosus et atrophicus
  - D: Follicular lichen planus

## Backbone e7
- S1 key_facts: Woman in her 60s presented with skin lesions; Lesions previously resolved with topical corticosteroids but flared after treatm; No family history of similar lesions; Multiple hypopigmented, flat-topped papules on the back, waist, and inframammary; Most lesions were folliculocentric under close inspection; Dermoscopy revealed central keratin plugs and structureless, whitish, and homoge; Antinuclear antibody and hyperglobulinemia tests were negative; Biopsy specimen showed central follicular plug and epidermal atrophy
- S2 mode=complement k=3 pool_n=37 gold_in_s2=False
  - call1: ['Keratosis Pilaris', 'Phrynoderma', 'Lichen Spinulosus', 'Keratosis Follicularis', 'Darier Disease', 'Grover Disease', 
  - call2: ['Flegel Disease', 'Kyrle Disease', 'Trichoepithelioma', 'Multiple Familial Trichoepithelioma', 'Rombo Syndrome', 'Naevo
  - call3: ['Flegel Disease', 'Kyrle Disease', 'Trichoepithelioma', 'Multiple Familial Trichoepithelioma', 'Rombo Syndrome', 'Naevo
- S3 shortlist n=5 gold=False: Keratosis Pilaris, Lichen Spinulosus, Keratosis Follicularis, Follicular Lichenoid Dermatitis, Darier Disease
- S4 champion: **Lichen Spinulosus** gold=False
- S4 raw (trunc): {"champion": "Lichen Spinulosus", "rationale": "The presence of multiple hypopigmented, flat-topped papules that are folliculocentric, along with dermoscopic findings of central keratin plugs and structureless, whitish, and homogenous areas, supports the diagnosis of Lichen Spinu

## Backbone v0 (compact)
- S1 key_facts: Woman in her 60s presented with skin lesions; Lesions previously resolved with topical corticosteroids but flared after treatm; No family history of similar lesions; Multiple hypopigmented, flat-topped papules on the back, waist, and inframammary; Most lesions were folliculocentric under close inspection; Dermoscopy revealed central keratin plugs and structureless, whitish, and homoge; Antinuclear antibody and hyperglobulinemia tests were negative; Biopsy specimen from back showed central follicular plug and epidermal atrophy
- S2 mode=single k=1 pool_n=15 gold_in_s2=False
  - call1: ['Keratosis Pilaris', 'Phrynoderma', 'Lichen Spinulosus', 'Keratosis Follicularis', 'Darier Disease', 'Grover Disease', 
- S3 shortlist n=5 gold=False: Keratosis Pilaris, Lichen Spinulosus, Keratosis Follicularis, Grover Disease, Phrynoderma
- S4 champion: **Lichen Spinulosus** gold=False
- S4 raw (trunc): {"champion": "Lichen Spinulosus", "rationale": "The presence of multiple hypopigmented, flat-topped papules that are folliculocentric, along with dermoscopic findings of central keratin plugs and histopathologic evidence of central follicular plugs and epidermal atrophy, supports

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The clinical presentation and histopathologic findings suggest a follicular keratotic disorder, with lichen spinulosus being the most likely diagnosis due to th
  - turn1 gold_mention=True diag=
    The clinical presentation and histopathologic findings align with Doctor A's assessment, supporting lichen spinulosus as the primary diagnosis due to the charac
  - turn2 gold_mention=True diag=
    The clinical presentation of numerous whitish papules with central keratin plugs and folliculocentric distribution, along with histopathologic findings of epide
- supervisor votes=3 top2=['Lichen spinulosus', 'Keratosis pilaris'] gold=False

## Baseline B07
- draft=['Lichen spinulosus', 'Keratosis pilaris'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['folliculocentric papules', 'hypopigmented papules with central keratin plugs', 'dermoscopy of follicular keratosis', 'histopathology of lichen spinulosus']
- diagnose=['Lichen spinulosus', 'Keratosis pilaris'] gold=False

## APHHM
- tree_n=23 tree_recall=False
- gold_leaf=None
- final_n=3 final_recall=False ranking=['Keratosis pilaris', 'Lichen planopilaris', 'Lichen planus']
- human_at1=False fail_mode=tree_miss

