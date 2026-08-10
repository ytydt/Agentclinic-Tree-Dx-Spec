# MCR / mcr_v2 / case 152

- **gold**: Squamous cell carcinoma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 60‐year‐old tailor with no significant medical history presented with a 3‐year history of macerated skin between his toes. He complained of a painful, fissured ulcer at the base of the fourth interdigital space of the right foot, which had been progressively enlarging over the past 18 months. He had received multiple antifungal regimens—including topical sertaconazole for 6 weeks and oral terbinafine 250 mg daily for 6 weeks—without improvement. On examination, there was a verrucous, infected ulceration with infiltrated, hyperkeratotic edges and a whitish, fissured base measuring 3 cm in diameter, extending onto the dorsum of the foot. Dermoscopy revealed unstructured whitish areas and hyperkeratosis. Popliteal and inguinal lymph nodes were not palpable, and the remainder of the examination was unremarkable.

What is the most likely diagnosis?

Options:
A. Squamous cell carcinoma
B. typical warts
C. Persistent fungal intertrigo
D. Wart
E. Keratoacanthoma
F. Corns, inverse psoriasis, chronic hyperkeratosis
G. None
H. None


## Backbone e7

- S2 n=48 gold_rank=1
  - clusters: gold=1 near=5 other=42
- S3 shortlist (5):
  - [gold] Squamous cell carcinoma
  - [near] Verrucous carcinoma
  - [other] Chronic pyoderma gangrenosum
  - [other] Keratoacanthoma
  - [other] Mycetoma
    - why_kept(Squamous cell carcinoma): Chronic ulcerative skin lesion with hyperkeratotic edges
    - why_kept(Verrucous carcinoma): Verrucous, infected ulceration with hyperkeratotic edges
    - why_kept(Chronic pyoderma gangrenosum): Progressively enlarging ulcer with unstructured whitish areas
    - why_kept(Keratoacanthoma): Rapidly growing, hyperkeratotic lesion
    - why_kept(Mycetoma): Chronic, deep-seated infection with possible fungal etiology
- S4 champion: **Verrucous carcinoma** cluster=near jaccard=0.25
- S4 rationale: The patient's presentation of a verrucous, infected ulceration with infiltrated, hyperkeratotic edges and a whitish, fissured base, along with the lack of response to antifungal treatments, is most consistent with verrucous carcinoma, a type of low-grade malignancy that can resemble a wart and is known for its local destruction and minimal metastatic potential.
- S4 rejected:
  - [gold] Squamous cell carcinoma: While possible, the description of the ulcer as verrucous and the lack of lymph node involvement make verrucous carcinoma a more specific diagnosis.
  - [other] Chronic pyoderma gangrenosum: Typically presents with painful ulcers but does not usually have the verrucous appearance described.
  - [other] Keratoacanthoma: Usually has a more rapid growth phase and often resolves on its own, which does not fit the 18-month progression of the ulcer.
  - [other] Mycetoma: Involves deeper tissue and typically includes sinus tracts and discharge, not described in this case.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Squamous Cell Carcinoma', 'Keratoacanthoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Squamous Cell Carcinoma', 'Keratoacanthoma', 'Chronic Ulcer', 'Fungal Infection', "Bowler's Foot", 'Squamous Cell Carcinoma', 'Keratoacanthoma', 'Chronic Ulcer']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Squamous Cell Carcinoma', 'Keratoacanthoma']
- diagnose: ['Squamous Cell Carcinoma', 'Keratoacanthoma']
- queries: ['verrucous ulcer foot treatment', 'interdigital space ulcer diagnosis', 'skin ulcer with hyperkeratotic edges']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Squamous cell carcinoma', 'Keratoacanthoma']
- queries: ['chronic interdigital foot ulcers', 'verrucous ulceration with hyperkeratotic edges', 'recalcitrant foot ulcers not responding to antifungal treatment', 'differential diagnosis of foot ulcers with hyperkeratosis']
- n_chunks=12

## APHHM
_na_

