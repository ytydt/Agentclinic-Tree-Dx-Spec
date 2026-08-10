# MCR / mcr_v2 / case 211

- **gold**: Ewing sarcoma
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_ok` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_miss_but_scored_ok
- **covariates**: vig_words=201; gold_words=2; eponym=False; subtype=False; e7_s2_rank=5; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 54-year-old woman with a history of stage III invasive ductal breast carcinoma treated with mastectomy and chemoradiation 4 years earlier presented with urinary frequency, worsening right-sided pelvic pain, and weight loss. MRI of the pelvis showed multiple fibroids and a heterogeneous 9.4 cm lesion involving the right uterine fundus/cornua. Intraoperatively, the mass was found in the right retroperitoneal space, tracking along the broad ligament and encasing the right external iliac artery; i...

## Backbone e7
- S1 key_facts: 54-year-old woman; History of stage III invasive ductal breast carcinoma; Treated with mastectomy and chemoradiation 4 years earlier; Presenting with urinary frequency; Worsening right-sided pelvic pain; Weight loss; MRI of the pelvis showed multiple fibroids and a heterogeneous 9.4 cm lesion; Mass involved the right uterine fundus/cornua
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Uterine leiomyosarcoma', 'Uterine carcinosarcoma', 'Ovarian cancer', 'Endometrial stromal sarcoma', 'Ewing sarcoma', '
  - call2: ['Myxoid/round-cell liposarcoma', 'Poorly differentiated synovial sarcoma', 'Malignant rhabdoid tumor', 'Extrarenal rhab
  - call3: ['Small cell carcinoma of the uterus', 'Neuroendocrine carcinoma of the uterus', 'Transitional cell carcinoma of the ute
- S3 shortlist n=5 gold=True: Uterine leiomyosarcoma, Endometrial stromal sarcoma, Uterine carcinosarcoma, Ewing sarcoma, Desmoplastic small round cell tumor
- S4 champion: **Endometrial stromal sarcoma** gold=False
- S4 raw (trunc): {"champion": "Endometrial stromal sarcoma", "rationale": "The tumor's location in the uterine fundus/cornua, invasion from the serosal surface into the myometrium, and immunohistochemical stains showing diffuse positivity for CD99, KIT, and cyclin D1 are consistent with Endometri

## Backbone v0 (compact)
- S1 key_facts: 54-year-old woman; History of stage III invasive ductal breast carcinoma; Treated with mastectomy and chemoradiation 4 years earlier; Presenting with urinary frequency; Worsening right-sided pelvic pain; Weight loss; MRI of the pelvis showed multiple fibroids; Mass involved the right uterine fundus/cornua
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['Uterine leiomyosarcoma', 'Uterine carcinosarcoma', 'High-grade endometrial stromal sarcoma', 'Low-grade endometrial st
- S3 shortlist n=5 gold=True: High-grade endometrial stromal sarcoma, Uterine leiomyosarcoma, Ewing sarcoma, Desmoplastic small round cell tumor, Metastatic breast carcinoma
- S4 champion: **High-grade endometrial stromal sarcoma** gold=False
- S4 raw (trunc): {"champion": "High-grade endometrial stromal sarcoma", "rationale": "The tumor's location in the uterine fundus/cornua, involvement of the myometrium, and diffuse positivity for CD99 are consistent with high-grade endometrial stromal sarcoma. The presence of pseudo-rosette format

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation and histopathological findings, including small, round, hyperchromatic cells with high nuclear-to-cytoplasmic ratios and diffuse posi
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and histopathological findings, including the tumor's aggressive nature and specific immunohistochemical stains, align with 
  - turn2 gold_mention=True diag=
    The patient's clinical presentation, histopathological findings, and immunohistochemical stains are consistent with the prior discussions, strongly supporting E
- supervisor votes=3 top2=["Ewing's Sarcoma", 'High-grade Endometrial Stromal Sarcoma'] gold=False

## Baseline B07
- draft=['Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET)', 'Desmoplastic Small Round Cell Tumor (DSRCT)'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['Ewing sarcoma vs other small round cell tumors', 'CD99 positive tumors', 'KIT and cyclin D1 positive uterine tumors']
- diagnose=['Ewing Sarcoma/Primitive Neuroectodermal Tumor (PNET)', 'Desmoplastic Small Round Cell Tumor (DSRCT)'] gold=True

## Baseline B01
- queries=['small round cell tumors in adults', 'CD99 positive uterine tumors', 'high grade sarcomas with pseudo-rosette formation', 'KIT and cyclin D1 positive pelvic masses']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Desmoplastic small round cell tumor', 'Endometrial stromal sarcoma'] gold=False

