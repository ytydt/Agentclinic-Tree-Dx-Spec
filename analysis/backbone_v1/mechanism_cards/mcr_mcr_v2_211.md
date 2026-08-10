# MCR / mcr_v2 / case 211

- **gold**: Ewing sarcoma
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 54-year-old woman with a history of stage III invasive ductal breast carcinoma treated with mastectomy and chemoradiation 4 years earlier presented with urinary frequency, worsening right-sided pelvic pain, and weight loss. MRI of the pelvis showed multiple fibroids and a heterogeneous 9.4 cm lesion involving the right uterine fundus/cornua. Intraoperatively, the mass was found in the right retroperitoneal space, tracking along the broad ligament and encasing the right external iliac artery; it was transected from the right uterine cornua. Grossly, the specimen was a detached, fragmented, ill-defined mass (14 × 12 × 4 cm) with fleshy solid and cystic components, central hemorrhage, and necrosis. Microscopically, the tumor invaded from the serosal surface into the myometrium and comprised sheets of small, round hyperchromatic cells with high nuclear-to-cytoplasmic ratios, frequent mitoses (32 per 10 high-power fields), pseudo-rosette formation, foci of cytoplasmic clearing, and necrosis. Immunohistochemical stains showed diffuse positivity for CD99, KIT, and cyclin D1 and negativity for keratin, DOG1, synaptophysin, desmin, myogenin, WT-1, CD45, inhibin, GATA-3, and SOX-10.

What …

## Backbone e7

- S2 n=49 gold_rank=5
  - clusters: gold=1 near=11 other=37
- S3 shortlist (5):
  - [other] Uterine leiomyosarcoma
  - [near] Endometrial stromal sarcoma
  - [other] Uterine carcinosarcoma
  - [gold] Ewing sarcoma
  - [other] Desmoplastic small round cell tumor
    - why_kept(Uterine leiomyosarcoma): High-grade tumor with serosal involvement and high mitotic rate
    - why_kept(Endometrial stromal sarcoma): Involvement of the myometrium and presence of high-grade features
    - why_kept(Uterine carcinosarcoma): Presence of a large pelvic mass with heterogeneous components
    - why_kept(Ewing sarcoma): Diffuse positivity for CD99 and small, round, hyperchromatic cells
    - why_kept(Desmoplastic small round cell tumor): Small, round, hyperchromatic cells with high nuclear-to-cytoplasmic ratios and desmoplastic stroma
- S4 champion: **Endometrial stromal sarcoma** cluster=near jaccard=0.25
- S4 rationale: The tumor's location in the uterine fundus/cornua, invasion from the serosal surface into the myometrium, and immunohistochemical stains showing diffuse positivity for CD99, KIT, and cyclin D1 are consistent with Endometrial stromal sarcoma
- S4 rejected:
  - [other] Uterine leiomyosarcoma: Lack of specific immunohistochemical markers and different morphological features
  - [other] Uterine carcinosarcoma: Absence of epithelial component and keratin negativity
  - [gold] Ewing sarcoma: Although CD99 positivity is shared, the clinical context and other immunohistochemical stains do not support this diagnosis
  - [other] Desmoplastic small round cell tumor: Typically involves the abdominal cavity and has a distinct desmoplastic stroma, which is not described in this case

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ["Ewing's Sarcoma", 'High-grade Endometrial Stromal Sarcoma']
  clusters: {'gold': 0, 'near': 2, 'other': 0, 'empty': 0}
- discussion labels (n=15): ["Ewing's Sarcoma", 'Uterine Leiomyosarcoma', 'High-grade Endometrial Stromal Sarcoma', 'Undifferentiated Uterine Sarcoma', 'Solitary Fibrous Tumor', "Ewing's Sarcoma", 'High-grade Endometrial Stromal Sarcoma', 'Uterine Leiomyosarcoma']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET)', 'Desmoplastic Small Round Cell Tumor (DSRCT)']
- diagnose: ['Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET)', 'Desmoplastic Small Round Cell Tumor (DSRCT)']
- queries: ['Ewing sarcoma vs other small round cell tumors', 'CD99 positive tumors', 'KIT and cyclin D1 positive uterine tumors']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Desmoplastic small round cell tumor', 'Endometrial stromal sarcoma']
- queries: ['small round cell tumors in adults', 'CD99 positive uterine tumors', 'high grade sarcomas with pseudo-rosette formation', 'KIT and cyclin D1 positive pelvic masses']
- n_chunks=12

## APHHM
_na_

