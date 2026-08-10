# DA / d2_heldout100 / case 261

- **gold**: Cutaneous malakoplakia
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=1

## Vignette
A man in his 60s presented with a 3-month history of intertrigo involving his groin that he had been treating with a combination of clotrimazole cream, 1%, and hydrocortisone cream, 1%. The condition improved, but he then developed bright red, burning and painful nodules around his scrotum. Medical history included prostate cancer, hypertension, anxiety disorder, hyperlipidemia, gastroesophageal reflux disease, and diverticulosis. Current medications included omeprazole, alprazolam, amlodipine besylate, atenolol, simvastatin, and valsartan.

Two symmetrical solitary erythematous nodules were present in the right and left inguinal folds adjacent to the scrotum.

- Histopathological examination:     - Epidermal ulceration overlying a diffuse dermal proliferation composed of sheets of histiocytes with eosinophilic granular cytoplasm    - Intracytoplasmic Michaelis-Gutmann bodies present as basophilic, somewhat laminated intracytoplasmic inclusion bodies measuring 5-8 μm in diameter    - Bodies highlighted with iron (Prussian blue) and calcium (Von Kossa) stains    - Background population of many plasma cells and few neutrophils noted  - Tissue Culture:    - Fungus culture: Negative   …

## Options
- A: Granulomatous dermatitis secondary to E. coli infection
- B: Granuloma inguinale (donovanosis)
- C: Malakoplakia **←gold**
- D: Cutaneous malakoplakia **←gold**

## Backbone e7

- S2 n=54 gold_rank=1
  - clusters: gold=1 near=3 other=50
- S3 shortlist (5):
  - [gold] Malakoplakia
  - [other] Erdheim-Chester disease
  - [other] Necrobiotic xanthogranuloma
  - [other] Granuloma inguinale
  - [other] Histiocytosis X
    - why_kept(Malakoplakia): Presence of Michaelis-Gutmann bodies and histiocytic proliferation in the histopathological examination
    - why_kept(Erdheim-Chester disease): Diffuse dermal proliferation composed of sheets of histiocytes and presence of intracytoplasmic inclusions
    - why_kept(Necrobiotic xanthogranuloma): Calcium deposits and histiocytic proliferation with background plasma cells and neutrophils
    - why_kept(Granuloma inguinale): Ulcerated nodule with sheeted dermal proliferation and presence of plasma cells and neutrophils
    - why_kept(Histiocytosis X): Histiocytic proliferation with eosinophilic granular cytoplasm and presence of intracytoplasmic inclusions
- S4 champion: **Malakoplakia** cluster=gold jaccard=0.50
- S4 rationale: The presence of Michaelis-Gutmann bodies, which are pathognomonic for Malakoplakia, in the histopathological examination is a key evidence-based reason for this diagnosis. The clinical presentation of erythematous nodules in the inguinal folds and the positive bacterial culture for E. coli also support this diagnosis, as Malakoplakia is often associated with chronic bacterial infections.
- S4 rejected:
  - [other] Erdheim-Chester disease: Erdheim-Chester disease is a rare form of histiocytosis that typically presents with systemic symptoms and multi-organ involvement, which is not consistent with the localized presentation in this case.
  - [other] Necrobiotic xanthogranuloma: Necrobiotic xanthogranuloma is a rare skin condition characterized by the presence of necrobiotic granulomas, which are not described in the histopathological examination of this case.
  - [other] Granuloma inguinale: Granuloma inguinale is a sexually transmitted infection caused by Klebsiella granulomatis, which is not consistent with the positive bacterial culture for E. coli in this case.
  - [other] Histiocytosis X: Histiocytosis X, also known as Langerhans cell histiocytosis, is a rare disorder characterized by the proliferation of Langerhans cells, which are not described in the histopathological examination of this case.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Malacoplakia', 'Calcinosis cutis']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Calcinosis cutis', 'Malacoplakia', 'Sarcoidosis', 'Foreign body granuloma', 'Eczema', 'Malacoplakia', 'Calcinosis cutis', 'Sarcoidosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Calcinosis Cutis', 'Malakoplakia']
- diagnose: ['Calcinosis Cutis', 'Malakoplakia']
- queries: ['calcinosis cutis', 'Michaelis-Gutmann bodies', 'histiocytic granuloma', 'erythematous nodules with basophilic inclusions']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=33 final_n=0
- final: []
- tree gold_cluster_n=5 final gold=False

