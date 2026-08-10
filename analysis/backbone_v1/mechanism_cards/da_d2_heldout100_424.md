# DA / d2_heldout100 / case 424

- **gold**: Hyperkeratosis lenticularis perstans (HLP), unilateral presentation
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A man in his 60s presented with a 10-year history of a slowly progressive, asymptomatic cutaneous eruption on his left leg. He had a 16-year history of diabetes mellitus that was being treated with metformin. There was no history of another endocrine disorder or malignant neoplasm. There was no family history of similar cutaneous findings.

Reddish brown hyperkeratotic papules 1 to 10 mm wide were present on the front and back of the left leg from knee to ankle. Removal of the scales caused slight bleeding. The rest of the physical examination findings were unremarkable.

{'Laboratory Tests': 'Hematological and biochemical test results were unremarkable.', 'Pathology': {'Test': 'Lesional skin biopsy', 'Images': [{'Title': 'Figure 1A', 'Description': 'Clinical image of the reddish brown hyperkeratotic papules on the front of the left leg'}, {'Title': 'Figure 1B and C', 'Description': 'Hematoxylin-eosin–stained lesional skin biopsy specimens revealing compact hyperkeratosis, epidermal atrophy, and bandlike lymphocyte infiltrate in the superficial dermis'}]}}

What is the most likely diagnosis?

Options:
A. Psoriasis
B. Necrobiosis lipoidica diabeticorum
C. Hypertrophic lichen planus
…

## Options
- A: Psoriasis
- B: Necrobiosis lipoidica diabeticorum
- C: Hypertrophic lichen planus
- D: Hyperkeratosis lenticularis perstans (HLP), unilateral presentation **←gold**

## Backbone e7

- S2 n=45 gold_rank=None
  - clusters: gold=0 near=0 other=45
- S3 shortlist (5):
  - [other] Lichen planus
  - [other] Psoriasis
  - [other] Lichenoid keratosis
  - [other] Discoid lupus erythematosus
  - [other] Granuloma faciale
    - why_kept(Lichen planus): Clinical presentation of reddish brown hyperkeratotic papules and bandlike lymphocyte infiltrate in the superficial dermis is consistent with lichen planus
    - why_kept(Psoriasis): Hyperkeratotic papules and epidermal atrophy are also seen in psoriasis, and the patient's 16-year history of diabetes mellitus may be relevant
    - why_kept(Lichenoid keratosis): Lesional skin biopsy showing compact hyperkeratosis and bandlike lymphocyte infiltrate is also consistent with lichenoid keratosis
    - why_kept(Discoid lupus erythematosus): Clinical presentation and histopathological findings could also be consistent with discoid lupus erythematosus, although the lack of other systemic symptoms makes this less likely
    - why_kept(Granuloma faciale): The presence of bandlike lymphocyte infiltrate and hyperkeratosis could also suggest granuloma faciale, although the location and morphology of the lesions are not typical
- S4 champion: **Lichenoid keratosis** cluster=other jaccard=0.00
- S4 rationale: The presence of compact hyperkeratosis, epidermal atrophy, and bandlike lymphocyte infiltrate in the superficial dermis on lesional skin biopsy, along with the clinical presentation of reddish brown hyperkeratotic papules, is most consistent with lichenoid keratosis, which is a benign skin condition that can present with these specific histopathological and clinical features.
- S4 rejected:
  - [other] Lichen planus: Lichen planus typically presents with pruritic, flat-topped papules and can involve mucous membranes, which is not mentioned in the case.
  - [other] Psoriasis: Psoriasis is characterized by well-demarcated erythematous plaques with silvery scales, and the biopsy would typically show parakeratosis and elongation of rete ridges, which is not described here.
  - [other] Discoid lupus erythematosus: Discoid lupus erythematosus is an autoimmune condition that typically presents with scarring lesions and can be associated with systemic lupus erythematosus, which is not indicated in the case.
  - [other] Granuloma faciale: Granuloma faciale is a rare condition that typically presents with brownish plaques on the face, which does not match the location described in the case.
  - [other] Psoriasis: Psoriasis typically involves the elbows, knees, scalp, and lower back, and the biopsy findings do not match those described for this patient.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Necrobiosis lipoidica', 'Granuloma annulare']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Necrobiosis lipoidica', 'Granuloma annulare', 'Stasis dermatitis', 'Porphyria cutanea tarda', 'Diabetic dermopathy', 'Necrobiosis lipoidica', 'Granuloma annulare', 'Stasis dermatitis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Necrobiosis Lipoidica Diabeticorum', 'Piezogenic Pedal Papules']
- diagnose: ['Necrobiosis Lipoidica Diabeticorum', 'Piezogenic Pedal Papules']
- queries: ['diagnosis of hyperkeratotic papules on leg', 'cutaneous eruption in diabetes', 'skin biopsy showing compact hyperkeratosis and bandlike lymphocyte infiltrate']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=69 final_n=5
- final: ['Necrolytic Migratory Erythema', 'psoriasis', 'Lichenoid Keratosis', 'Pityriasis Rubra Pilaris', 'Necrobiosis lipoidica']
- tree gold_cluster_n=3 final gold=False

