# MCR / mcr_v1 / case 19

- **gold**: Leiomyosarcoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_ok` code=`aphhm_ok` prune_e7_ok=0

## Vignette
A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass behind the ear over one month. She had no neurological deficits or systemic symptoms. Laboratory studies, including complete blood counts, metabolic panel, and viral serology for HIV and Epstein-Barr virus, were all normal or negative. Noncontrast CT of the head revealed a 5-cm hyperdense meningeal mass with parietal bone invasion. Gadolinium-enhanced MRI showed a heterogeneously enhancing lesion in the right parietal region. Cerebral angiography demonstrated a vascular tumor supplied by the middle meningeal artery. Thus, a clinical diagnosis of osteoblastic meningioma was made, and the differential diagnosis included primary lymphoma, metastasis, and sarcoma. The patient underwent endovascular embolization of the feeding artery followed by surgical resection. Intraoperatively, the tumor was extradural, caused skull destruction, and had no intradural involvement. Histology showed a malignant spindle cell neoplasm with positive immunostaining for α-smooth muscle actin, vimentin, and desmin, and negative staining for Epstein-…

## Backbone e7

- S2 n=44 gold_rank=11
  - clusters: gold=1 near=0 other=43
- S3 shortlist (5):
  - [other] Meningioma
  - [other] Hemangiopericytoma
  - [other] Solitary fibrous tumor
  - [gold] Leiomyosarcoma
  - [other] Sarcomatoid meningioma
    - why_kept(Meningioma): Clinical diagnosis and histology consistent with meningioma
    - why_kept(Hemangiopericytoma): Vascular tumor supplied by the middle meningeal artery, consistent with hemangiopericytoma
    - why_kept(Solitary fibrous tumor): Histology showed a malignant spindle cell neoplasm, consistent with solitary fibrous tumor
    - why_kept(Leiomyosarcoma): Positive immunostaining for α-smooth muscle actin, vimentin, and desmin, consistent with leiomyosarcoma
    - why_kept(Sarcomatoid meningioma): Malignant spindle cell neoplasm with features of meningioma, consistent with sarcomatoid meningioma
- S4 champion: **Sarcomatoid meningioma** cluster=other jaccard=0.00
- S4 rationale: The tumor's extradural location, skull destruction, and lack of intradural involvement, combined with its malignant spindle cell histology and positive immunostaining for α-smooth muscle actin, vimentin, and desmin, are most consistent with a sarcomatoid meningioma.
- S4 rejected:
  - [other] Meningioma: While the initial diagnosis was osteoblastic meningioma, the malignant spindle cell histology and specific immunostaining pattern suggest a more aggressive variant, such as sarcomatoid meningioma.
  - [other] Hemangiopericytoma: The tumor's vascular supply and extradural location could suggest hemangiopericytoma, but the immunostaining pattern and histology are more consistent with sarcomatoid meningioma.
  - [other] Solitary fibrous tumor: The tumor's malignant histology and aggressive behavior are not typical of solitary fibrous tumors, which are usually benign.
  - [gold] Leiomyosarcoma: While the tumor's spindle cell histology and positive immunostaining for α-smooth muscle actin could suggest leiomyosarcoma, the clinical presentation and imaging findings are more consistent with a primary meningeal tumor, such as sarcomatoid meningioma.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Sarcoma', 'Hemangiopericytoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Meningioma', 'Sarcoma', 'Lymphoma', 'Metastasis', 'Hemangiopericytoma', 'Sarcoma', 'Meningioma', 'Hemangiopericytoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Solitary Fibrous Tumor/Hemangiopericytoma', 'Meningeal Sarcoma']
- diagnose: ['Solitary Fibrous Tumor/Hemangiopericytoma', 'Meningeal Sarcoma']
- queries: ['A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass behind the ear over one month. She had no neurological deficits or systemic symptoms. Laboratory studies, including com', 'differential diagnosis A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass', 'clinical manifestations diagnosis plete blood counts, metabolic panel, and viral serology for HIV and Epstein-Barr virus, were all normal or negative. Noncontrast CT of the head revealed a 5-cm ']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Meningeal Sarcoma', 'Osteosarcoma']
- queries: ['malignant spindle cell neoplasm of the meninges', 'differential diagnosis of extradural skull tumors', 'immunohistochemical markers for meningioma vs sarcoma', 'vascular tumors of the skull with parietal bone invasion']
- n_chunks=12

## APHHM
- tree_n=32 final_n=3
- final: ['Leiomyosarcoma', 'Hemangiopericytoma', 'Meningioma']
- tree gold_cluster_n=5 final gold=True

