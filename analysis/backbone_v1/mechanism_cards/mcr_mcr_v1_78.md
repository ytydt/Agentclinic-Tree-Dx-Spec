# MCR / mcr_v1 / case 78

- **gold**: schwannoma
- **layer**: `base_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A 35-year-old woman presented with an 8-month history of radicular pain radiating from her lower back down the left leg, with occasional tingling. The pain progressively worsened and was particularly severe by August. She denied any weakness, autonomic symptoms, history of trauma, or injury. On examination, she had mild hypesthesia in the left L5–S1 dermatome but normal muscle strength, normal abduction and adduction, and negative Lasègue, Kernig, Bragard, and Sicard signs. Electromyography showed neuropathic irritation of the left L4, L5, S1, and S2 roots, most severe at L5, with no denervation. Lumbosacral gadolinium-enhanced MRI revealed a solitary, completely cystic mass in the left L5–S1 foraminal zone extending along the course of the sciatic nerve into the left ischial groove, measuring approximately 13.9 cm in length and 1.9 cm in maximal diameter. The lesion was hypointense on T1-weighted images, hyperintense on T2-weighted images, and demonstrated peripheral rim enhancement, causing severe foraminal stenosis without attachment to pelvic organs. MR neurography confirmed that the mass arose from the sciatic nerve at the left ischial groove.

What is the most likely diagnosi…

## Backbone e7

- S2 n=44 gold_rank=2
  - clusters: gold=6 near=0 other=38
- S3 shortlist (5):
  - [gold] Schwannoma
  - [other] Neurofibroma
  - [other] Tarlov cyst
  - [other] Ganglion cyst
  - [other] Plexiform neurofibroma
    - why_kept(Schwannoma): The patient's symptoms and imaging findings, including a solitary, completely cystic mass in the left L5–S1 foraminal zone, are consistent with a schwannoma, a type of benign nerve sheath tumor.
    - why_kept(Neurofibroma): The patient's presentation and imaging findings could also be consistent with a neurofibroma, another type of benign nerve sheath tumor, although the lack of multiple lesions or other signs of neurofibromatosis type 1 makes this less likely.
    - why_kept(Tarlov cyst): The cystic nature of the mass and its location in the nerve root foramen are also consistent with a Tarlov cyst, a type of nerve root cyst that can cause radicular pain and neuropathic symptoms.
    - why_kept(Ganglion cyst): The patient's symptoms and imaging findings could also be consistent with a ganglion cyst, a type of cyst that can occur in the nerve root foramen and cause radicular pain and neuropathic symptoms.
    - why_kept(Plexiform neurofibroma): Although less likely, the patient's presentation and imaging findings could also be consistent with a plexiform neurofibroma, a type of benign nerve sheath tumor that can cause neuropathic symptoms and has a more complex, plexiform morphology.
- S4 champion: **Tarlov cyst** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of radicular pain and the imaging findings of a solitary, completely cystic mass in the left L5–S1 foraminal zone that is hypointense on T1-weighted images and hyperintense on T2-weighted images, with peripheral rim enhancement, are most consistent with a Tarlov cyst, which is a type of nerve root cyst that can cause nerve irritation and pain.
- S4 rejected:
  - [gold] Schwannoma: Schwannomas are typically solid tumors, not cystic, and may show heterogeneous enhancement on MRI.
  - [other] Neurofibroma: Neurofibromas are also typically solid and may have a more heterogeneous appearance on MRI, with areas of low signal intensity on T2-weighted images.
  - [other] Ganglion cyst: Ganglion cysts are more commonly associated with joints and tendons, rather than nerve roots, and may not typically cause the same degree of nerve irritation and pain as seen in this patient.
  - [other] Plexiform neurofibroma: Plexiform neurofibromas are complex, multinodular tumors that involve multiple nerve roots and may have a more extensive and heterogeneous appearance on MRI, which is not consistent with the solitary, cystic mass seen in this patient.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Schwannoma', 'Neurofibroma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Neurofibroma', 'Schwannoma', 'Perineurioma', 'Malignant Peripheral Nerve Sheath Tumor', 'Ganglion Cyst', 'Schwannoma', 'Neurofibroma', 'Perineurioma']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Peripheral Nerve Sheath Tumor (PNST)', 'Neurofibroma']
- diagnose: ['Peripheral Nerve Sheath Tumor (PNST)', 'Neurofibroma']
- queries: ['solitary cystic mass in foraminal zone', 'sciatic nerve tumor', 'peripheral nerve sheath tumor', 'neuropathic irritation of nerve roots']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Peroneal nerve sheath tumor', 'Neurofibroma']
- queries: ['cystic masses in the lumbar spine', 'sciatic nerve tumors', 'peripheral nerve sheath tumors', 'foraminal cystic lesions causing radiculopathy']
- n_chunks=12

## APHHM
- tree_n=25 final_n=2
- final: ['intraneural ganglion cyst', 'sciatic schwannoma']
- tree gold_cluster_n=7 final gold=True

