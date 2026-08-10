# DA / d2_heldout200b / case 740

- **gold**: Secondary cutaneous endometriosis (SCE)
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 39-year-old female teacher from Southwest China presented with a subcutaneous mass in the lower-left abdominal region. The patient had a history of chronic urticaria (relieved by occasional use of loratadine), cesarean section eight years ago, and myomectomy to remove a myoma six months ago. She denied a history of dysmenorrhea and abortion. The mass was accompanied by slight pain that worsened around menstruation.

Heart, lungs, and abdomen showed no obvious abnormalities. No palpable swelling of superficial lymph nodes was noted. A subcutaneous nodule of approximately 1 cm diameter was present under the hypogastrium. The nodule's surface was normal, without ulceration or bleeding. A linear scar was observed in the lower-left abdominal region.

- Ultrasonography:    Image Title: Ultrasonic image    Image Description: Showed a hybrid echo-mass about 1.1 × 1.0 cm, with an irregular shape, well-defined border, located 3 mm from the body surface in the subcutaneous soft tissue    - Histopathology:    Image Title: Hematoxylin-eosin staining (×40 and ×200)    Image Description: Revealed endometrial glands consisting of a single layer of monomorphous cuboidal cells with an endometrial …

## Options
- A: Subcutaneous endometriosis
- B: Secondary cutaneous endometriosis (SCE) **←gold**
- C: Scar (abdominal wall) endometriosis
- D: Abdominal wall endometriosis

## Backbone e7

- S2 n=52 gold_rank=1
  - clusters: gold=1 near=2 other=49
- S3 shortlist (5):
  - [near] Abdominal wall endometriosis
  - [near] Scar endometriosis
  - [gold] Endometriosis
  - [other] Endometrioma
  - [other] Nodular fasciitis with endometrial-like features
    - why_kept(Abdominal wall endometriosis): Histopathology revealed endometrial glands and stroma, and the mass is accompanied by cyclical pain
    - why_kept(Scar endometriosis): Patient has a history of cesarean section and myomectomy, and the mass is located near the linear scar
    - why_kept(Endometriosis): Patient's symptoms and histopathology results are consistent with endometriosis, and the mass is located in the subcutaneous tissue
    - why_kept(Endometrioma): Histopathology revealed endometrial glands and stroma, and the mass is a hybrid echo-mass on ultrasonography
    - why_kept(Nodular fasciitis with endometrial-like features): Histopathology revealed endometrial-like features, and the mass is a subcutaneous nodule with a well-defined border
- S4 champion: **Scar endometriosis** cluster=near jaccard=0.20
- S4 rationale: The patient has a history of cesarean section and myomectomy, and the subcutaneous mass is located near the linear scar in the lower-left abdominal region, which is consistent with scar endometriosis. The histopathology also revealed endometrial glands and stroma, supporting this diagnosis.
- S4 rejected:
  - [near] Abdominal wall endometriosis: While possible, the specific location near a scar and the patient's surgical history make scar endometriosis more likely
  - [gold] Endometriosis: Too broad, as it does not specify the location or type of endometriosis
  - [other] Endometrioma: Typically refers to a type of endometriosis that forms a cyst, which is not indicated by the ultrasonography or histopathology results
  - [other] Nodular fasciitis with endometrial-like features: The histopathology results specifically identify endometrial glands and stroma, which is more consistent with endometriosis than a condition with endometrial-like features

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Endometriosis', 'Lipoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Endometriosis', 'Lipoma', 'Dermatofibroma', 'Epidermal inclusion cyst', 'Subcutaneous granuloma', 'Endometriosis', 'Lipoma', 'Dermatofibroma']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Abdominal wall endometriosis', 'Desmoid tumor']
- diagnose: ['Abdominal wall endometriosis', 'Desmoid tumor']
- queries: ['subcutaneous endometriosis', 'abdominal wall endometriosis', 'endometriosis diagnosis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

