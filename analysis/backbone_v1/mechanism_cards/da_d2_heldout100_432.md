# DA / d2_heldout100 / case 432

- **gold**: Bullous lichen planus of the nails
- **layer**: `base_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A man in his 60s presented with painful swelling of the proximal nail folds, dripping of blood from his fingernails and toenails for the last year, and occasional pus discharge. There was no history of preceding trauma or drug intake. Oral mucosa showed lichenoid plaques on the right angle of mouth, bilateral buccal mucosa, and erosions covered with hemorrhagic crusts on the upper and lower lips.

The proximal nail folds were found to be swollen and showed violaceous discoloration of 7 fingernails and 3 toenails. The index fingernails demonstrated longitudinal ridging, thinning, and focal fragmentation of the nail plate, while the remaining fingernails and involved toenails showed partial to complete loss of nail plate with oozing of blood resulting in hemorrhagic crusting of the nail beds and folds.

- Laboratory tests: Revealed raised liver enzyme levels and positive anti–hepatitis C virus antibody status.

- Histopathology:
Biopsy from proximal nail fold of right index finger showed:
- Hyperkeratosis
- Hypergranulosis
- Acanthosis
- Basal cell degeneration
- Numerous apoptotic keratinocytes in the epidermis
- Dense bandlike lymphohistiocytic infiltrate in the papillary dermis

-…

## Options
- A: Erosive lichen planus
- B: Hepatitis C-associated nail lichen planus
- C: Lichen planus **←gold**
- D: Bullous lichen planus of the nails **←gold**

## Backbone e7

- S2 n=53 gold_rank=2
  - clusters: gold=1 near=5 other=47
- S3 shortlist (5):
  - [gold] Lichen planus
  - [other] Hepatitis C-associated porphyria cutanea tarda
  - [near] Hepatitis C-associated lichen planus
  - [other] Necrolytic acral erythema
  - [other] Mixed cryoglobulinemia
    - why_kept(Lichen planus): Clinical presentation of lichenoid plaques on oral mucosa, histopathology showing hyperkeratosis, hypergranulosis, acanthosis, and basal cell degeneration
    - why_kept(Hepatitis C-associated porphyria cutanea tarda): Positive anti-hepatitis C virus antibody status and symptoms consistent with porphyria cutanea tarda
    - why_kept(Hepatitis C-associated lichen planus): Positive anti-hepatitis C virus antibody status and clinical presentation of lichen planus
    - why_kept(Necrolytic acral erythema): Clinical presentation of violaceous discoloration and necrolytic lesions on the proximal nail folds
    - why_kept(Mixed cryoglobulinemia): Positive anti-hepatitis C virus antibody status and symptoms consistent with cryoglobulinemia
- S4 champion: **Hepatitis C-associated lichen planus** cluster=near jaccard=0.29
- S4 rationale: The patient's symptoms, including painful swelling of the proximal nail folds, lichenoid plaques on the oral mucosa, and histopathology showing hyperkeratosis, hypergranulosis, acanthosis, and basal cell degeneration, are consistent with lichen planus. Additionally, the patient's positive anti-hepatitis C virus antibody status and raised liver enzyme levels suggest a connection to hepatitis C, making hepatitis C-associated lichen planus the most likely diagnosis.
- S4 rejected:
  - [gold] Lichen planus: While the patient's symptoms are consistent with lichen planus, the presence of hepatitis C infection suggests a more specific diagnosis is warranted.
  - [other] Hepatitis C-associated porphyria cutanea tarda: The patient's symptoms do not include the characteristic blistering skin lesions and scarring seen in porphyria cutanea tarda.
  - [other] Necrolytic acral erythema: The patient's symptoms do not include the characteristic well-demarcated erythematous plaques on the feet and hands seen in necrolytic acral erythema.
  - [other] Mixed cryoglobulinemia: While hepatitis C infection is a risk factor for mixed cryoglobulinemia, the patient's symptoms do not include the characteristic palpable purpura, arthralgias, and glomerulonephritis seen in this condition.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Lichen Planus', 'Hepatitis C Virus Associated Skin Disorder']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lichen Planus', 'Psoriasis', 'Dermatomyositis', 'Hepatitis C Virus Associated Skin Disorder', 'Necrolytic Acral Erythema', 'Lichen Planus', 'Hepatitis C Virus Associated Skin Disorder', 'Psoriasis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lichen Planus', 'Hepatitis C Virus Infection']
- diagnose: ['Lichen Planus', 'Hepatitis C Virus Infection']
- queries: ['nail disorders with liver enzyme abnormalities', 'hepatitis C virus and nail manifestations', 'lichen planus and nail involvement', 'nail fold biopsy and bandlike lymphohistiocytic infiltrate']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=44 final_n=2
- final: ['Hepatitis C-associated Lichen Planus', 'psoriasis']
- tree gold_cluster_n=3 final gold=False

