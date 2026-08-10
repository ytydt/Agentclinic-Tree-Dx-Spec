# DA / d2_heldout100 / case 252

- **gold**: Folliculocentric lichen sclerosus et atrophicus
- **layer**: `aphhm_win` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A woman in her 60s presented with numerous whitish papules on the back of more than 10 years' duration. The lesions previously resolved with topical corticosteroids but flared soon after treatment discontinuation. Some papules became pruritic and extended to the waist and anterior trunk in the past month. No family history of similar lesions was recorded.

Multiple hypopigmented, flat-topped papules on the back, waist, and inframammary area without genital involvement. Most lesions were folliculocentric under close inspection. Dermoscopy revealed central keratin plugs and some foci of structureless, whitish, and homogenous areas with surrounding erythema.

- Laboratory tests: Antinuclear antibody and hyperglobulinemia tests were negative.- Histopathologic examination:   - Biopsy specimen from back showed central follicular plug and epidermal atrophy covered by orthokeratotic stratum corneum  - Papillary dermis was markedly thickened with homogenized collagens, areas of edema, and sparse bandlike lymphocytic infiltration  - Some eosinophils in infiltrate and red blood cell extravasation  - Congo red and mucicarmine stains were negative for amyloid and mucin- Images:  Image A Title: …

## Options
- A: Lichen Sclerosus **←gold**
- B: Lichen sclerosus et atrophicus **←gold**
- C: Folliculocentric lichen sclerosus et atrophicus **←gold**
- D: Follicular lichen planus

## Backbone e7

- S2 n=37 gold_rank=None
  - clusters: gold=0 near=3 other=34
- S3 shortlist (5):
  - [other] Keratosis Pilaris
  - [near] Lichen Spinulosus
  - [other] Keratosis Follicularis
  - [other] Follicular Lichenoid Dermatitis
  - [other] Darier Disease
    - why_kept(Keratosis Pilaris): Folliculocentric papules and central keratin plugs on dermoscopy
    - why_kept(Lichen Spinulosus): Multiple hypopigmented, flat-topped papules with follicular involvement
    - why_kept(Keratosis Follicularis): Follicular plugs and epidermal atrophy on histopathology
    - why_kept(Follicular Lichenoid Dermatitis): Sparse bandlike lymphocytic infiltration and eosinophils on histopathology
    - why_kept(Darier Disease): Keratotic papules and follicular involvement with negative family history
- S4 champion: **Lichen Spinulosus** cluster=near jaccard=0.20
- S4 rationale: The presence of multiple hypopigmented, flat-topped papules that are folliculocentric, along with dermoscopic findings of central keratin plugs and structureless, whitish, and homogenous areas, supports the diagnosis of Lichen Spinulosus. The histopathologic examination showing central follicular plug and epidermal atrophy also aligns with this condition.
- S4 rejected:
  - [other] Keratosis Pilaris: While Keratosis Pilaris involves folliculocentric lesions, it typically presents with rough, dry skin and does not fully match the described histopathologic and dermoscopic findings.
  - [other] Keratosis Follicularis: This condition is less likely as it does not fully align with the combination of clinical, dermoscopic, and histopathologic findings presented in the case.
  - [other] Follicular Lichenoid Dermatitis: The specific combination of clinical and histopathologic findings, including the presence of central keratin plugs and the pattern of inflammation, does not perfectly match Follicular Lichenoid Dermatitis.
  - [other] Darier Disease: Darier Disease typically involves greasy, crusted papules in seborrheic areas and characteristic suprabasal acantholysis on histology, which does not match the provided case details.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Lichen spinulosus', 'Keratosis pilaris']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lichen spinulosus', 'Keratosis pilaris', 'Phrynoderma', 'Lichen planus', "Darier's disease", 'Lichen spinulosus', 'Keratosis pilaris', 'Phrynoderma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Lichen spinulosus', 'Keratosis pilaris']
- diagnose: ['Lichen spinulosus', 'Keratosis pilaris']
- queries: ['folliculocentric papules', 'hypopigmented papules with central keratin plugs', 'dermoscopy of follicular keratosis', 'histopathology of lichen spinulosus']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=23 final_n=3
- final: ['Keratosis pilaris', 'Lichen planopilaris', 'Lichen planus']
- tree gold_cluster_n=0 final gold=False

