# MCR / mcr_v2 / case 187

- **gold**: Schwannoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 23-year-old man presented with a 1-year history of a gradually enlarging mass on the anterior aspect of his right wrist, along the radial edge. On examination, Phalen’s maneuver and Durkan’s test were positive, indicating median nerve compression. Magnetic resonance imaging of the wrist demonstrated a well-defined, encapsulated mass on the radial side of the wrist that exhibited biphasic (central and peripheral) contrast enhancement (target sign).

What is the most likely diagnosis?

Options:
A. Schwannoma
B. Carpal tunnel syndrome
C. Ganglion cysts
D. Lipomas
E. Neurofibroma
F. Sarcomas and metastases
G. None
H. None


## Backbone e7

- S2 n=45 gold_rank=6
  - clusters: gold=1 near=0 other=44
- S3 shortlist (5):
  - [other] Giant Cell Tumor of Tendon Sheath
  - [other] Ganglion Cyst
  - [other] Targetoid Hemosiderotic Hemangioma
  - [other] Glomus Tumor
  - [other] Nodular Tenosynovitis
    - why_kept(Giant Cell Tumor of Tendon Sheath): Common cause of a gradually enlarging mass on the wrist with median nerve compression
    - why_kept(Ganglion Cyst): Typical presentation of a well-defined, encapsulated mass on the wrist with biphasic contrast enhancement
    - why_kept(Targetoid Hemosiderotic Hemangioma): Characterized by a target sign on MRI, consistent with the patient's imaging findings
    - why_kept(Glomus Tumor): Can cause median nerve compression and present as a well-defined mass on the wrist
    - why_kept(Nodular Tenosynovitis): May present with a gradually enlarging mass and median nerve compression, similar to the patient's symptoms
- S4 champion: **Ganglion Cyst** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of a gradually enlarging mass on the wrist with positive Phalen's and Durkan's tests indicating median nerve compression, along with MRI findings of a well-defined, encapsulated mass with biphasic contrast enhancement (target sign), is most consistent with a ganglion cyst.
- S4 rejected:
  - [other] Giant Cell Tumor of Tendon Sheath: While possible, the biphasic contrast enhancement and specific location are more characteristic of a ganglion cyst.
  - [other] Targetoid Hemosiderotic Hemangioma: This condition is less common and the clinical presentation does not specifically suggest this diagnosis over ganglion cyst.
  - [other] Glomus Tumor: Glomus tumors are typically very painful and have a distinct blue color, which was not mentioned in the vignette.
  - [other] Nodular Tenosynovitis: The clinical and imaging findings do not align closely with nodular tenosynovitis, which typically involves the tendon sheath and does not exhibit the target sign on MRI.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Ganglion cyst', 'Giant cell tumor of tendon sheath']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Ganglion cyst', 'Giant cell tumor of tendon sheath', 'Lipoma', 'Neurofibroma', 'Schwannoma', 'Ganglion cyst', 'Giant cell tumor of tendon sheath', 'Schwannoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Ganglion cyst', 'Giant cell tumor of the tendon sheath']
- diagnose: ['Ganglion cyst', 'Giant cell tumor of the tendon sheath']
- queries: ['wrist mass with target sign on MRI', 'median nerve compression causes', 'biphasic contrast enhancement wrist mass']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Ganglion cyst', 'Neuroma']
- queries: ['wrist mass with median nerve compression', 'target sign on MRI wrist', 'radial wrist mass with biphasic contrast enhancement', 'encapsulated wrist mass with nerve compression']
- n_chunks=12

## APHHM
_na_

