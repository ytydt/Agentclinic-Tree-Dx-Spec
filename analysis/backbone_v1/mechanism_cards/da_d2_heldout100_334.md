# DA / d2_heldout100 / case 334

- **gold**: Phaeohyphomycosis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaques within 10 years. There was involvement of the upper respiratory tract, causing palatal perforation and stridor, necessitating a tracheostomy a year ago. History of wheezing and breathlessness. No history of preceding trauma, fever, malaise, joint pain, cough, epistaxis, hemoptysis, or hematuria.

Multiple well-defined brown erythematous scaly plaques with central scarring measuring 2 × 1 to 8 × 7 cm on the face, arm, and thighs. Saddle nose deformity, perforation of the hard palate, and necrotic plaques on the ear with destruction of ear cartilage. Cervical lymphadenopathy: multiple, nontender, discrete nodes, ranging from 1.5 to 2 cm without surface changes. Sensory examination and peripheral nerve examination within normal limits. Respiratory examination normal.

- Laboratory Tests:
  - Hemogram: anemia (hemoglobin 10.1 g/dL)
  - Kidney function test: normal
  - Liver function test: normal
  - Fasting blood glucose: normal
  - Urinalysis: normal
  - Serologic analysis for HIV-1/2,…

## Options
- A: Granulomatosis with polyangiitis (Wegener’s)
- B: Chromoblastomycosis
- C: Phaeohyphomycosis **←gold**
- D: Disseminated cutaneous fungal infection

## Backbone e7

- S2 n=61 gold_rank=None
  - clusters: gold=0 near=0 other=61
- S3 shortlist (5):
  - [other] Chromoblastomycosis
  - [other] Leprosy
  - [other] Rhinoscleroma
  - [other] Mycetoma
  - [other] Exophiala infection
    - why_kept(Chromoblastomycosis): Clinical presentation of chronic progressive skin lesions with central scarring and histopathology showing pseudoepitheliomatous hyperplasia, parakeratosis, and dense dermal infiltrate of histiocytes, along with the presence of pigmented hyphae, are consistent with this diagnosis
    - why_kept(Leprosy): The patient's skin lesions, upper respiratory tract involvement, and cervical lymphadenopathy are consistent with leprosy, although the absence of nerve involvement and negative serologic tests make it less likely
    - why_kept(Rhinoscleroma): The patient's upper respiratory tract involvement, including palatal perforation and stridor, and the presence of chronic progressive skin lesions are consistent with this diagnosis
    - why_kept(Mycetoma): The patient's chronic progressive skin lesions with central scarring and the presence of cervical lymphadenopathy are consistent with this diagnosis, although the lack of a clear history of trauma or exposure to a specific organism makes it less likely
    - why_kept(Exophiala infection): The presence of black yeastlike colonies characteristic of Exophiala spinifera species on fungal skin culture and the patient's clinical presentation are consistent with this diagnosis
- S4 champion: **Chromoblastomycosis** cluster=other jaccard=0.00
- S4 rationale: The presence of well-defined brown erythematous scaly plaques with central scarring, pseudoepitheliomatous hyperplasia, parakeratosis, and dense dermal infiltrate of histiocytes in the histopathology, along with the isolation of a black yeastlike fungus, are characteristic of Chromoblastomycosis
- S4 rejected:
  - [other] Leprosy: Leprosy typically presents with sensory loss and peripheral nerve involvement, which is not seen in this case
  - [other] Rhinoscleroma: Rhinoscleroma primarily affects the nasal mucosa and is caused by Klebsiella rhinoscleromatis, which does not match the fungal culture results
  - [other] Mycetoma: Mycetoma typically presents with a triad of a painless subcutaneous mass, multiple sinuses, and discharge containing grains, which is not consistent with the clinical presentation
  - [other] Exophiala infection: While the fungal culture identified Exophiala spinifera, the clinical and histopathological features are more consistent with Chromoblastomycosis, which can be caused by various fungi including those in the Dematiaceae family

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Chromoblastomycosis', 'Phaeohyphomycosis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Chromoblastomycosis', 'Leprosy', 'Sarcoidosis', "Wegener's granulomatosis", 'Lupus vulgaris', 'Chromoblastomycosis', 'Phaeohyphomycosis', 'Leprosy']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Eumycetoma', 'Chromoblastomycosis']
- diagnose: ['Eumycetoma', 'Chromoblastomycosis']
- queries: ['A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaqu', 'differential diagnosis A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaqu', 'clinical manifestations diagnosis  × 1 to 8 × 7 cm on the face, arm, and thighs. Saddle nose deformity, perforation of the hard palate, and necrotic plaques on the ear with destruction of ear ca']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=19 final_n=4
- final: ['Chromoblastomycosis', 'Relapsing Polychondritis', 'Chronic Granulomatous Disease', 'Sarcoidosis']
- tree gold_cluster_n=0 final gold=False

