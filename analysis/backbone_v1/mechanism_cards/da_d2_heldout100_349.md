# DA / d2_heldout100 / case 349

- **gold**: Cutaneous histoplasmosis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `option_echo_da`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A man in his 70s presented with 2 progressively enlarging, painless nodular lesions on the forehead and right cheek, initially observed as erythematous nodules 3 months prior. The lesions gradually increased in size with subsequent central ulceration and blackish crusting. No fever, pain, or discharge from the lesions was noted. Patient had history of kidney transplant in 2004 causing immunocompromised status.

Two distinct lesions measuring 2 × 2 cm each were identified over the glabella and right cheek. The lesions were firm with central ulceration with hemorrhagic crusting. Dermoscopy showed arborizing telangiectasias, central ulceration with crusting, and peripheral pigment. No additional lesions or abnormalities were found on examination of surrounding skin and general systemic evaluation.

- Histopathological examination:    Image Title: Figure 1B    Image Description: Extensive dermal collection of lymphocytes, histiocytes, and macrophages. Intracellular yeasts with surrounding halos were identified (hematoxylin-eosin staining, original magnification ×40)      - Molecular Testing:    Polymerase chain reaction analysis of tissue specimen was performed      - Imaging Studies: …

## Options
- A: Cutaneous histoplasmosis **←gold**
- B: Cutaneous cryptococcosis
- C: Histoplasmosis **←gold**
- D: Cutaneous blastomycosis

## Backbone e7

- S2 n=57 gold_rank=7
  - clusters: gold=1 near=6 other=50
- S3 shortlist (5):
  - [other] Cryptococcosis
  - [other] Blastomycosis
  - [gold] Histoplasmosis
  - [other] Kaposi's sarcoma
  - [near] Cutaneous lymphoma
    - why_kept(Cryptococcosis): Immunocompromised patient with progressively enlarging, painless, ulcerated skin lesions and histopathological evidence of intracellular yeasts
    - why_kept(Blastomycosis): Similar clinical presentation and histopathological findings, including intracellular yeasts with surrounding halos
    - why_kept(Histoplasmosis): Clinical presentation and histopathological findings consistent with this fungal infection, which can affect immunocompromised individuals
    - why_kept(Kaposi's sarcoma): Immunocompromised patient with skin lesions, although the presence of intracellular yeasts is not typical for this condition
    - why_kept(Cutaneous lymphoma): Immunocompromised patient with skin lesions, and lymphoma can present with a wide range of skin manifestations
- S4 champion: **Cryptococcosis** cluster=other jaccard=0.00
- S4 rationale: The presence of intracellular yeasts with surrounding halos on histopathological examination is characteristic of Cryptococcosis, particularly in an immunocompromised patient.
- S4 rejected:
  - [other] Blastomycosis: While Blastomycosis can present with similar skin lesions, the histopathological findings do not match, as Blastomycosis typically shows broad-based budding yeasts.
  - [gold] Histoplasmosis: Histoplasmosis usually presents with smaller intracellular yeasts without halos, and the clinical presentation does not typically include the described skin lesions.
  - [other] Kaposi's sarcoma: Kaposi's sarcoma is a type of cancer that can present with skin lesions in immunocompromised patients, but the histopathological findings and dermoscopy results do not support this diagnosis.
  - [near] Cutaneous lymphoma: Cutaneous lymphoma can present with a variety of skin lesions, but the histopathological findings of intracellular yeasts with halos are not consistent with this diagnosis.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Cryptococcosis', 'Basal cell carcinoma']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Cryptococcosis', 'Basal cell carcinoma', 'Squamous cell carcinoma', 'Mycobacterium infection', 'Lymphoma', 'Cryptococcosis', 'Basal cell carcinoma', 'Squamous cell carcinoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Cutaneous Leishmaniasis', 'Cryptococcosis']
- diagnose: ['Cutaneous Leishmaniasis', 'Cryptococcosis']
- queries: ['cutaneous leishmaniasis in immunocompromised patients', 'skin lesions with intracellular yeasts and halos', 'differential diagnosis for umbilicated skin lesions with central ulceration']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=32 final_n=2
- final: ['Cryptococcosis', "Kaposi's sarcoma"]
- tree gold_cluster_n=5 final gold=False

