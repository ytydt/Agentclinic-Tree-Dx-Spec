# MCR / mcr_200b / case 346

- **gold**: myxoinflammatory fibroblastic sarcoma
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 25-year-old man with a history of Hodgkin lymphoma presented with a 2-month history of a gradually enlarging mass over the dorsum of his left hand. Six years earlier, he had been diagnosed with Hodgkin lymphoma on the basis of mediastinal lymphadenopathy and systemic symptoms, and he received 13 courses of chemotherapy. Physical examination at this visit revealed a soft-tissue mass over the second metacarpal dorsum, approximately 4 cm in greatest dimension, with mild tenderness and no limitation of movement. The patient underwent surgical excision of the lesion, and two specimens were submitted to pathology. The larger specimen consisted of gray, gelatinous tissue measuring 4 × 2.5 × 0.8 cm and 0.5 × 0.5 × 0.5 cm. Microscopic examination showed a mixture of inflammatory cells, abundant myxoid stroma, epithelioid and spindle-shaped cells, lipoblast-like cells, and occasional Reed–Sternberg–like cells. Given the presence of Reed–Sternberg–like cells in an inflammatory background, the pathologist recommended immunohistochemical staining to distinguish among possible diagnoses.

What is the most likely diagnosis?

Options:
A. myxoinflammatory fibroblastic sarcoma
B. recurrent Hodgkin…

## Backbone e7

- S2 n=44 gold_rank=17
  - clusters: gold=2 near=7 other=35
- S3 shortlist (5):
  - [gold] Myxoinflammatory fibroblastic sarcoma
  - [gold] Acral myxoinflammatory fibroblastic sarcoma
  - [other] Myxoid liposarcoma
  - [other] Inflammatory myofibroblastic tumor
  - [other] Hodgkin lymphoma
    - why_kept(Myxoinflammatory fibroblastic sarcoma): Matches the clinical presentation of a gradually enlarging soft-tissue mass with a mixture of inflammatory cells and myxoid stroma
    - why_kept(Acral myxoinflammatory fibroblastic sarcoma): Specific subtype of myxoinflammatory fibroblastic sarcoma that matches the acral location of the mass
    - why_kept(Myxoid liposarcoma): Presence of myxoid stroma and lipoblast-like cells in the microscopic examination
    - why_kept(Inflammatory myofibroblastic tumor): Matches the clinical presentation of a soft-tissue mass with a mixture of inflammatory cells
    - why_kept(Hodgkin lymphoma): Patient's history of Hodgkin lymphoma and presence of Reed-Sternberg-like cells in the microscopic examination
- S4 champion: **Acral myxoinflammatory fibroblastic sarcoma** cluster=gold jaccard=0.75
- S4 rationale: The mass is located over the dorsum of the hand, which is a characteristic location for acral myxoinflammatory fibroblastic sarcoma, and the microscopic examination shows a mixture of inflammatory cells, myxoid stroma, and Reed–Sternberg–like cells, consistent with this diagnosis
- S4 rejected:
  - [gold] Myxoinflammatory fibroblastic sarcoma: While similar, the specific location on the hand makes acral myxoinflammatory fibroblastic sarcoma more specific
  - [other] Myxoid liposarcoma: Lack of specific liposarcoma features and presence of Reed–Sternberg–like cells
  - [other] Inflammatory myofibroblastic tumor: The presence of myxoid stroma and Reed–Sternberg–like cells is not typical for this tumor
  - [other] Hodgkin lymphoma: The patient's history of Hodgkin lymphoma and the presence of Reed–Sternberg–like cells could suggest recurrence, but the clinical and microscopic features are more consistent with a soft tissue tumor

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Myxoid liposarcoma', 'Lipoblastoma']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Myxoid liposarcoma', 'Hodgkin lymphoma', 'Lipoblastoma', 'Inflammatory myofibroblastic tumor', 'Metastatic disease', 'Myxoid liposarcoma', 'Lipoblastoma', 'Inflammatory myofibroblastic tumor']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Hodgkin lymphoma', 'Myxoid liposarcoma']
- diagnose: ['Hodgkin lymphoma', 'Myxoid liposarcoma']
- queries: ['Reed-Sternberg-like cells diagnosis', 'myxoid stroma and lipoblast-like cells', 'Hodgkin lymphoma and soft tissue mass', 'inflammatory background and epithelioid cells']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Hodgkin lymphoma', 'Myxoid tumor']
- queries: ['Reed-Sternberg-like cells in soft tissue tumors', 'Inflammatory myxoid tumors of the hand', 'Immunohistochemical staining for Hodgkin lymphoma vs other lymphomas', 'Differential diagnosis of soft tissue masses with Reed-Sternberg-like cells']
- n_chunks=12

## APHHM
_na_

