# MCR / mcr_v1 / case 111

- **gold**: Giant cell tumor of bone
- **layer**: `e7_win_recall` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=1

## Vignette
A 29-year-old man presented with a 6-month history of progressive neck pain radiating to his left hand. The pain was described as electrical in nature and was associated with numbness in the C8–T1 dermatomes. Over the preceding week, he noted weakness in fine movements and a weak grip of the left hand. His medical and surgical history was unremarkable.

On examination, there was marked atrophy of the hypothenar and interosseous muscles of the left hand. Motor testing of the left hand revealed muscle strength of 3/5.

Preoperative computed tomography of the cervical spine showed marked osteolysis and collapse of the T1 vertebra, with an extensive paravertebral soft tissue component. Magnetic resonance imaging demonstrated that the lesion was intermediate to low signal on T1-weighted images, intermediate on T2-weighted images, and showed heterogeneous enhancement after gadolinium administration. The lesion involved the anterior and posterior longitudinal ligaments but did not significantly compromise the thecal sac.

What is the most likely diagnosis?

Options:
A. Giant cell tumor of bone
B. Primary spinal aneurysmal bone cyst was considered because of similar imaging and histologic …

## Backbone e7

- S2 n=49 gold_rank=4
  - clusters: gold=1 near=5 other=43
- S3 shortlist (5):
  - [other] Chordoma
  - [other] Osteolytic metastasis
  - [gold] Giant cell tumor
  - [other] Plasmacytoma
  - [other] Multiple myeloma
    - why_kept(Chordoma): Matches clinical presentation of progressive neck pain with radiating symptoms and osteolytic lesion on imaging
    - why_kept(Osteolytic metastasis): Common cause of osteolytic lesions and could explain neurological deficits
    - why_kept(Giant cell tumor): Known to cause osteolytic lesions and could lead to neurological symptoms due to spinal involvement
    - why_kept(Plasmacytoma): Could explain osteolytic lesion and associated neurological symptoms, especially given the age of the patient
    - why_kept(Multiple myeloma): Systemic disease that could explain osteolytic lesions and associated neurological symptoms
- S4 champion: **Giant cell tumor** cluster=gold jaccard=0.75
- S4 rationale: The presence of marked osteolysis and collapse of the T1 vertebra, along with the involvement of the anterior and posterior longitudinal ligaments, is consistent with a giant cell tumor. The tumor's location in the spine and its effects on the surrounding structures, including the nerves, also align with this diagnosis.
- S4 rejected:
  - [other] Chordoma: Chordomas are typically midline and more commonly found in the clivus or sacrum
  - [other] Osteolytic metastasis: Metastases are more common in older adults and would not typically cause such localized destruction without other systemic symptoms
  - [other] Plasmacytoma: Plasmacytomas are typically associated with multiple myeloma and would likely have other systemic symptoms and findings
  - [other] Multiple myeloma: Multiple myeloma would likely have other systemic symptoms, such as anemia, renal failure, and hypercalcemia, which are not mentioned in the vignette

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Metastatic disease', 'Primary bone tumor']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Metastatic disease', 'Multiple myeloma', 'Osteolytic tumor', 'Infection', 'Primary bone tumor', 'Metastatic disease', 'Primary bone tumor', 'Multiple myeloma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Vertebral Osteomyelitis', 'Vertebral Tumor']
- diagnose: ['Vertebral Osteomyelitis', 'Vertebral Tumor']
- queries: ['cervical spine osteolysis causes', 'T1 vertebra collapse differential diagnosis', 'paravertebral soft tissue mass with osteolysis']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Metastatic spinal tumor', 'Vertebral osteomyelitis']
- queries: ['causes of progressive neck pain with radiating pain to the arm', 'differential diagnosis of osteolysis and collapse of the vertebra', 'neoplastic versus infectious causes of vertebral destruction', 'diagnostic criteria for spinal tumors with neurological deficits']
- n_chunks=12

## APHHM
- tree_n=24 final_n=3
- final: ['Chordoma', 'Pancoast tumor', 'Tuberculous spondylitis']
- tree gold_cluster_n=1 final gold=False

