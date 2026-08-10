# DA / d2_heldout100 / case 314

- **gold**: Peeling skin disease (PSD)
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=1
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 2-year-old girl presented with skin fragility since early infancy. She had 2 older brothers, and the family had no medical history of note. Symptoms improved in winter and worsened in summer. Physical and mental developments were normal. The mother reported finding the child peeling off skin with marked facility.

Physical examination revealed:- Mild xerosis with superficial skin erosions- Erythematous residual macules from previous erosions- Some lesions had unusual linear geographic contour- Lesions predominantly located at areas of friction- Hair, nails, and mucous membranes were normal- No history of blistering

1. Laboratory Tests:- Serological markers for celiac disease were negative2. Skin Biopsy Findings:- Hematoxylin-eosin staining showed:  * Complete separation of the stratum corneum  * Clean split just above the stratum granulosum  * Faint psoriasiform hyperplasia  * Mild perivascular and interstitial mononuclear infiltrate in upper dermis3. Immunofluorescence Mapping:- Normal results for:  * Collagen IV and VII  * α6 and β4 integrines  * Laminine-3324. Genetic Study:- Revealed 2 heterozygous mutations in exon 2 of the CDSN geneImages:- Figure A Title: Clinical photogr…

## Options
- A: Acral Peeling Skin Syndrome
- B: Peeling skin disease (PSD) **←gold**
- C: Peeling skin syndrome
- D: Peeling Skin Syndrome Type B (Acral)

## Backbone e7

- S2 n=58 gold_rank=9
  - clusters: gold=2 near=17 other=39
- S3 shortlist (5):
  - [near] Peeling skin syndrome
  - [near] Acral peeling skin syndrome
  - [near] CDSN-related peeling skin syndrome
  - [near] Samira type peeling skin syndrome
  - [near] Generalized peeling skin syndrome
    - why_kept(Peeling skin syndrome): Clinical presentation of skin fragility, superficial erosions, and seasonal variation match this condition
    - why_kept(Acral peeling skin syndrome): Lesions predominantly located at areas of friction and seasonal variation are consistent with this diagnosis
    - why_kept(CDSN-related peeling skin syndrome): Genetic study revealed 2 heterozygous mutations in exon 2 of the CDSN gene, which is associated with this condition
    - why_kept(Samira type peeling skin syndrome): Clinical features such as mild xerosis, superficial skin erosions, and erythematous residual macules are similar to this condition
    - why_kept(Generalized peeling skin syndrome): Widespread skin involvement and superficial erosions are consistent with this diagnosis
- S4 champion: **CDSN-related peeling skin syndrome** cluster=near jaccard=0.29
- S4 rationale: The genetic study revealed 2 heterozygous mutations in exon 2 of the CDSN gene, which is a strong evidence for CDSN-related peeling skin syndrome
- S4 rejected:
  - [near] Peeling skin syndrome: Too general, as the vignette provides specific genetic information pointing to CDSN-related peeling skin syndrome
  - [near] Acral peeling skin syndrome: Lesions are not limited to acral areas, but are predominantly located at areas of friction
  - [near] Samira type peeling skin syndrome: No specific information in the vignette suggests this rare subtype
  - [near] Generalized peeling skin syndrome: While the peeling is widespread, the genetic findings specifically implicate CDSN-related peeling skin syndrome

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Peeling Skin Syndrome', 'Keratosis Pilaris']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Peeling Skin Syndrome', 'Erythema Toxicum Neonatorum', 'Keratosis Pilaris', 'Ichthyosis Vulgaris', 'Pityriasis Rubra Pilaris', 'Peeling Skin Syndrome', 'Keratosis Pilaris', 'Ichthyosis Vulgaris']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Peeling Skin Disease', 'Dermatitis Artefacta']
- diagnose: ['Peeling Skin Disease', 'Dermatitis Artefacta']
- queries: ['peeling skin disease', 'CDSN gene mutations', 'skin fragility in children']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=23 final_n=1
- final: ['Acral Peeling Skin Syndrome']
- tree gold_cluster_n=0 final gold=False

