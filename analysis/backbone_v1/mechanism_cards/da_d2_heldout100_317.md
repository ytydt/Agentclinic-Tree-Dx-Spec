# DA / d2_heldout100 / case 317

- **gold**: Pyoderma vegetans
- **layer**: `base_win_recall` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A teenaged male presented with a 2-week history of vegetating, bleeding plaques and pustules on his face, scalp, trunk, and extremities. Lesions began as pustules and developed into painful, itchy plaques. Prior treatment included prednisolone tablet 5 mg twice daily, clindamycin hydrochloride 300 mg daily, and fluconazole 200 mg daily, but patient continued to develop new lesions. Patient reported difficulty walking due to skin lesions.

Pustules and hemorrhagic-crusted plaques were seen on the scalp, legs, arms, and trunk along with keloidal plaques on the face.

- Laboratory Tests:
Enzyme-linked immunosorbent assay testing for HIV was negative

- Histopathology:
Punch biopsy from arm showed:
- Epidermal hyperplasia and exocytosis of neutrophils
- Dense dermal-mixed inflammatory cell infiltration
- Microabscesses scattered with eosinophils
- No granulomas or multinucleated giant cells
- Negative periodic acid–Schiff staining

- Images:
Image A Title: Vegetative plaques on extremities
Description: Extensive vegetative plaques with bleeding and ulceration

Image B Title: Lesions on extremities and trunk
Description: Pustules and ulcerated plaques

Image C Title: Histopathologic exa…

## Options
- A: Pyodermatitis-pyostomatitis vegetans
- B: Pyoderma vegetans **←gold**
- C: Blastomycosis-like pyoderma
- D: Pemphigus vegetans

## Backbone e7

- S2 n=49 gold_rank=None
  - clusters: gold=0 near=1 other=48
- S3 shortlist (5):
  - [near] Pyoderma gangrenosum
  - [other] Sweet syndrome
  - [other] Erythema elevatum diutinum
  - [other] Generalized pustular psoriasis
  - [other] Acute febrile neutrophilic dermatosis
    - why_kept(Pyoderma gangrenosum): Painful, itchy, and bleeding skin lesions with pustules and plaques, consistent with clinical presentation
    - why_kept(Sweet syndrome): Acute onset of painful, itchy, and bleeding skin lesions with a mixture of pustules and plaques, matching the syndrome frame
    - why_kept(Erythema elevatum diutinum): Pustules and plaques on the extremities, with a significant impact on mobility, aligning with the case context
    - why_kept(Generalized pustular psoriasis): Pustular skin lesions with a subacute onset, consistent with the patient's symptoms and histopathology findings
    - why_kept(Acute febrile neutrophilic dermatosis): Neutrophilic dermatosis with fever, consistent with the patient's symptoms and laboratory results
- S4 champion: **Sweet syndrome** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms, including painful and itchy plaques, pustules, and histopathology showing epidermal hyperplasia, exocytosis of neutrophils, and dense dermal-mixed inflammatory cell infiltration, are consistent with Sweet syndrome. The presence of microabscesses scattered with eosinophils and the negative periodic acid-Schiff staining also support this diagnosis.
- S4 rejected:
  - [near] Pyoderma gangrenosum: While pyoderma gangrenosum can present with painful ulcers, the histopathology in this case does not show the characteristic necrotic ulcers and undermining borders typically seen in pyoderma gangrenosum.
  - [other] Erythema elevatum diutinum: Erythema elevatum diutinum is characterized by purple-red plaques and nodules, which are not described in this case. The histopathology also does not show the characteristic fibrinoid necrosis and leukocytoclastic vasculitis seen in erythema elevatum diutinum.
  - [other] Generalized pustular psoriasis: While generalized pustular psoriasis can present with widespread pustules, the histopathology in this case does not show the characteristic parakeratosis and Munro's microabscesses seen in psoriasis.
  - [other] Acute febrile neutrophilic dermatosis: Acute febrile neutrophilic dermatosis is a synonym for Sweet syndrome, so it is not a distinct diagnosis to reject.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Pyoderma gangrenosum', 'Pyoderma vegetans']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Pyoderma gangrenosum', 'Eczema herpeticum', 'Sweet syndrome', 'Pyoderma vegetans', 'Bullous pemphigoid', 'Pyoderma gangrenosum', 'Pyoderma vegetans', 'Sweet syndrome']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Eosinophilic Dermatitis']
- diagnose: ['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Eosinophilic Dermatitis']
- queries: ['vegetating bleeding plaques and pustules diagnosis', 'pseudoepitheliomatous hyperplasia causes', 'dermal neutrophilia and microabscesses with eosinophilia diagnosis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=23 final_n=5
- final: ['Pyoderma gangrenosum', 'Sweet syndrome', 'Sweet syndrome', 'Sweet syndrome', 'Acute generalized exanthematous pustulosis']
- tree gold_cluster_n=0 final gold=False

