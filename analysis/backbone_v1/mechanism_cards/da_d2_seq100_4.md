# DA / d2_seq100 / case 4

- **gold**: Microvenular hemangioma (MVH)
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=1
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_near_crowd_out`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_ok` code=`aphhm_ok` prune_e7_ok=0

## Vignette
A female patient in her late 20s presented with a 2-year history of multiple, slowly growing, infiltrated erythematous-violaceous patches and plaques, with occasional slight pain extending from her left upper arm to the left side of her chest. No triggers such as local infection, insect bite, or trauma occurred before lesion appearance. She denied fever, weight loss, or fatigue.

Multiple firm, nonscaly, purple erythematous patches and plaques with irregular borders on her left axilla, medial upper arm, and lateral thoracic region. No extracutaneous involvement was observed.

- Histopathological examination:    - Thin-walled, irregularly branched blood vessels dispersed between thickened collagen bundles    - Endothelial cells were plump but displayed no significant cytologic atypia      - Immunohistochemistry results:    - Positive for: CD31, CD34, Ki-67 (<1%)    - Negative for: podoplanin (D2-40), human herpesvirus 8 (HHV-8)      - Images:    Image A Title: Clinical presentation    Image A Description: Multiple nonscaly, erythematous-violaceous patches and plaques with irregular borders on the patient's left axilla, medial upper arm, and lateral thoracic region        Image B Tit…

## Options
- A: Epithelioid hemangioma
- B: Morpheaform hemangioma
- C: Microvenular hemangioma (MVH) **←gold**
- D: Tufted angioma

## Backbone e7

- S2 n=40 gold_rank=3
  - clusters: gold=2 near=6 other=32
- S3 shortlist (5):
  - [other] Kaposi's sarcoma
  - [other] Tufted angioma
  - [other] Kaposiform hemangioendothelioma
  - [other] Retiform hemangioendothelioma
  - [near] Targetoid hemosiderotic hemangioma
    - why_kept(Kaposi's sarcoma): Histopathological examination showed irregularly branched, thin-walled blood vessels, and immunohistochemistry results were positive for CD31 and CD34, which are consistent with Kaposi's sarcoma
    - why_kept(Tufted angioma): Clinical presentation of slowly growing, infiltrated erythematous-violaceous patches and plaques, and histopathological examination showed irregularly branched, thin-walled blood vessels
    - why_kept(Kaposiform hemangioendothelioma): Similar clinical and histopathological features to Kaposi's sarcoma, and immunohistochemistry results were positive for CD31 and CD34
    - why_kept(Retiform hemangioendothelioma): Histopathological examination showed irregularly branched, thin-walled blood vessels, and clinical presentation of slowly growing, infiltrated erythematous-violaceous patches and plaques
    - why_kept(Targetoid hemosiderotic hemangioma): Clinical presentation of erythematous-violaceous patches and plaques, and histopathological examination showed irregularly branched, thin-walled blood vessels
- S4 champion: **Retiform hemangioendothelioma** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of slowly growing, infiltrated erythematous-violaceous patches and plaques with irregular borders, combined with the histopathological findings of irregularly branched, thin-walled blood vessels and positive immunohistochemistry results for CD31 and CD34, is most consistent with retiform hemangioendothelioma.
- S4 rejected:
  - [other] Kaposi's sarcoma: Negative immunohistochemistry results for human herpesvirus 8 (HHV-8) and lack of systemic symptoms or extracutaneous involvement make Kaposi's sarcoma less likely.
  - [other] Tufted angioma: The clinical presentation and histopathological findings do not match the characteristic tufted or cannonball pattern of blood vessels seen in tufted angioma.
  - [other] Kaposiform hemangioendothelioma: The absence of significant cytologic atypia and the negative immunohistochemistry results for podoplanin (D2-40) make kaposiform hemangioendothelioma less likely.
  - [near] Targetoid hemosiderotic hemangioma: The clinical presentation and histopathological findings do not match the characteristic targetoid appearance and hemosiderin deposition seen in targetoid hemosiderotic hemangioma.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Targetoid hemosiderotic hemangioma', 'Kaposiform hemangioendothelioma']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ["Kaposi's sarcoma", 'Angiosarcoma', 'Kaposiform hemangioendothelioma', 'Tufted angioma', 'Targetoid hemosiderotic hemangioma', 'Targetoid hemosiderotic hemangioma', 'Kaposiform hemangioendothelioma', 'Tufted angioma']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ["Kaposi's Sarcoma", 'Hemangioma']
- diagnose: ["Kaposi's Sarcoma", 'Hemangioma']
- queries: ['erythematous-violaceous patches and plaques diagnosis', 'irregularly branched blood vessels in skin histopathology', 'CD31 and CD34 positive skin lesion']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ["Kaposi's sarcoma", "Jessner's lymphocytic infiltration of the skin"]
- queries: ['erythematous-violaceous patches and plaques with irregular borders', 'irregularly branched thin-walled blood vessels in skin histopathology', 'CD31 and CD34 positive skin lesions with negative podoplanin and HHV-8', 'slowly growing infiltrated skin lesions with occasional slight pain']
- n_chunks=12

## APHHM
- tree_n=27 final_n=2
- final: ['angioma', 'Arteriovenous Malformation']
- tree gold_cluster_n=5 final gold=True

