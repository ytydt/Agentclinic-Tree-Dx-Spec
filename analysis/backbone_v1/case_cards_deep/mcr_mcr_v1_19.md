# MCR / mcr_v1 / case 19

- **gold**: Leiomyosarcoma
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=1
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`final_ok`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=218; gold_words=1; eponym=False; subtype=False; e7_s2_rank=11; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass behind the ear over one month. She had no neurological deficits or systemic symptoms. Laboratory studies, including complete blood counts, metabolic panel, and viral serology for HIV and Epstein-Barr virus, were all normal or negative. Noncontrast CT of the head revealed a 5-cm hyperdense meningeal mass with parietal bone invasion. Gadol...

## Backbone e7
- S1 key_facts: 76-year-old woman; History of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma; Mass located behind the ear; No neurological deficits or systemic symptoms; Normal or negative laboratory studies, including complete blood counts, metaboli; Noncontrast CT showed a 5-cm hyperdense meningeal mass; Gadolinium-enhanced MRI showed a heterogeneously enhancing lesion; Cerebral angiography demonstrated a vascular tumor supplied by the middle mening
- S2 mode=complement k=3 pool_n=44 gold_in_s2=True
  - call1: ['Meningioma', 'Hemangiopericytoma', 'Solitary fibrous tumor', 'Osteosarcoma', 'Chondrosarcoma', "Ewing's sarcoma", 'Lym
  - call2: ['Desmoplastic fibroblastoma', 'Intraosseous hemangioma', 'Pseudosarcomatous fibro-osseous lesion', 'Myopericytoma', 'An
  - call3: ['Malignant solitary fibrous tumor', 'Hemangiopericytoma variant with malignant transformation', 'Sarcomatoid meningioma
- S3 shortlist n=5 gold=True: Meningioma, Hemangiopericytoma, Solitary fibrous tumor, Leiomyosarcoma, Sarcomatoid meningioma
- S4 champion: **Sarcomatoid meningioma** gold=False
- S4 raw (trunc): {"champion": "Sarcomatoid meningioma", "rationale": "The tumor's extradural location, skull destruction, and lack of intradural involvement, combined with its malignant spindle cell histology and positive immunostaining for α-smooth muscle actin, vimentin, and desmin, are most co

## Backbone v0 (compact)
- S1 key_facts: 76-year-old woman; History of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma; Mass enlarged over one month; No neurological deficits or systemic symptoms; Normal or negative laboratory studies, including complete blood counts, metaboli; Noncontrast CT showed a 5-cm hyperdense meningeal mass; Gadolinium-enhanced MRI showed a heterogeneously enhancing lesion; Cerebral angiography demonstrated a vascular tumor supplied by the middle mening
- S2 mode=None k=None pool_n=18 gold_in_s2=True
  - pool gold matches: ['Leiomyosarcoma']
  - pool head: Meningioma, Hemangiopericytoma, Solitary fibrous tumor, Osteosarcoma, Chondrosarcoma, Ewing's sarcoma, Lymphoma, Metastatic carcinoma
- S3 shortlist n=5 gold=True: Meningioma, Hemangiopericytoma, Solitary fibrous tumor, Leiomyosarcoma, Lymphoma
- S4 champion: **Hemangiopericytoma** gold=False
- S4 raw (trunc): {"champion": "Hemangiopericytoma", "rationale": "The tumor's extradural location, vascular nature as demonstrated by cerebral angiography, and histological features of a malignant spindle cell neoplasm with positive immunostaining for α-smooth muscle actin, vimentin, and desmin a

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    Given the patient's presentation with a rapidly enlarging right parietal mass, normal laboratory studies, and imaging findings of a hyperdense meningeal mass wi
  - turn1 gold_mention=False diag=
    The patient's clinical presentation and imaging findings are consistent with a meningioma, but the histological features of a malignant spindle cell neoplasm wi
  - turn2 gold_mention=False diag=
    The patient's clinical presentation, imaging findings, and histological features, including positive immunostaining for α-smooth muscle actin, vimentin, and des
- supervisor votes=3 top2=['Sarcoma', 'Hemangiopericytoma'] gold=True

## Baseline B07
- draft=['Solitary Fibrous Tumor/Hemangiopericytoma', 'Meningeal Sarcoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass behind the ear over one month. She had no neurological deficits or systemic symptoms. Laboratory studies, including com', 'differential diagnosis A 76-year-old woman with a history of appendicitis, torsion of an ovarian cyst pedicle, and uterine myoma presented with a rapidly enlarging right parietal mass', 'clinical manifestations diagnosis plete blood counts, metabolic panel, and viral serology for HIV and Epstein-Barr virus, were all normal or negative. Noncontrast CT of the head revealed a 5-cm ']
- diagnose=['Solitary Fibrous Tumor/Hemangiopericytoma', 'Meningeal Sarcoma'] gold=False

## Baseline B01
- queries=['malignant spindle cell neoplasm of the meninges', 'differential diagnosis of extradural skull tumors', 'immunohistochemical markers for meningioma vs sarcoma', 'vascular tumors of the skull with parietal bone invasion']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Meningeal Sarcoma', 'Osteosarcoma'] gold=False

## APHHM
- tree_n=32 tree_recall=True
- gold_leaf=B1.6:Sarcoma parent=B1
- final_n=3 final_recall=True ranking=['Leiomyosarcoma', 'Hemangiopericytoma', 'Meningioma']
- human_at1=True fail_mode=final_ok

