# MCR / mcr_v1 / case 62

- **gold**: Lipoblastoma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=0 B07=1 B01=0 APHHM=1
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_ok` code=`aphhm_ok` prune_e7_ok=0

## Vignette
An 18-month-old girl was brought for evaluation of a swelling in her left medial thigh. Over the past six months, the mass had enlarged gradually and was painless, with no history of trauma or infection. On examination, there was a firm, nonpulsatile mass measuring approximately 10 cm, fixed to underlying tissues but mobile relative to the overlying skin. There were no signs of inflammation, neurovascular impairment, or inguinal lymphadenopathy.

Laboratory tests were unremarkable. A CT scan of the thigh showed a well-defined, lobulated, hypodense mass in the left anteromedial compartment of the proximal thigh, extending toward the inguinal area. The lesion exhibited internal septations and a density similar to subcutaneous fat, displacing the common and superficial femoral vessels anterolaterally without signs of invasion; it abutted the proximal femoral bone but did not erode it.

An MRI confirmed a fatty-appearing, well-circumscribed mass with internal septations and no encasement of neurovascular structures.

What is the most likely diagnosis?

Options:
A. Lipoblastoma
B. myxoid liposarcoma
C. lipoma
D. teratoma or dermoid cyst
E. involuting hemangioma
F. hibernoma
G. None
H. N…

## Backbone e7

- S2 n=39 gold_rank=32
  - clusters: gold=2 near=0 other=37
- S3 shortlist (5):
  - [other] Lipoma
  - [other] Liposarcoma
  - [other] Fibrolipomatous hamartoma
  - [other] Pleomorphic lipoma
  - [other] Atypical lipomatous tumor
    - why_kept(Lipoma): Fatty-appearing mass with internal septations on MRI, consistent with lipoma characteristics
    - why_kept(Liposarcoma): Although less likely due to lack of aggressive features, liposarcoma remains a consideration given the large size of the mass
    - why_kept(Fibrolipomatous hamartoma): Presence of a firm, nonpulsatile mass with fatty appearance on imaging, which could be consistent with fibrolipomatous hamartoma
    - why_kept(Pleomorphic lipoma): Given the mass's size and location, pleomorphic lipoma is a plausible diagnosis, although less common
    - why_kept(Atypical lipomatous tumor): The mass's characteristics, such as being well-circumscribed and having a fatty appearance, could also suggest an atypical lipomatous tumor
- S4 champion: **Fibrolipomatous hamartoma** cluster=other jaccard=0.00
- S4 rationale: The presence of a firm, nonpulsatile mass with internal septations and a density similar to subcutaneous fat, as well as the location in the medial thigh and the patient's age, are consistent with fibrolipomatous hamartoma, a benign tumor that typically presents in the thigh of young children.
- S4 rejected:
  - [other] Lipoma: While lipomas can present as fatty masses, the presence of internal septations and the specific location in the thigh are more suggestive of fibrolipomatous hamartoma.
  - [other] Liposarcoma: Liposarcomas are malignant tumors that are rare in children and would be expected to show more aggressive features, such as invasion of surrounding tissues or lymphadenopathy, which are not present in this case.
  - [other] Pleomorphic lipoma: Pleomorphic lipomas are rare and typically occur in older adults, making them an unlikely diagnosis for an 18-month-old child.
  - [other] Atypical lipomatous tumor: Atypical lipomatous tumors are malignant and would be expected to show more aggressive features, such as invasion of surrounding tissues or lymphadenopathy, which are not present in this case.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Lipoma', 'Liposarcoma']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Lipoma', 'Liposarcoma', 'Fibromatosis', 'Hemangioma', 'Neurofibroma', 'Lipoma', 'Liposarcoma', 'Fibromatosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lipoma', 'Lipoblastoma']
- diagnose: ['Lipoma', 'Lipoblastoma']
- queries: ['soft tissue tumors in children', 'fatty tumors of the thigh', 'lipomatous tumors in pediatric population']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Lipoma', 'Atypical Lipomatous Tumor']
- queries: ['fatty tumor in thigh of child', 'benign soft tissue tumors in pediatric population', 'lipomatous tumors with internal septations', 'subcutaneous fatty masses in lower extremities']
- n_chunks=12

## APHHM
- tree_n=33 final_n=2
- final: ['Lipoblastoma', 'Lipoma']
- tree gold_cluster_n=5 final gold=True

