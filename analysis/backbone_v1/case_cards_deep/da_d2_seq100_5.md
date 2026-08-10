# DA / d2_seq100 / case 5

- **gold**: Left maxillary giant cell reparative granuloma (GCRG)
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01=0 APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_miss_but_scored_ok` B01=`rag_miss` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=193; gold_words=7; eponym=False; subtype=False; e7_s2_rank=35; mapper_rescue=True
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A teenage girl presented with several months of sinus pressure and facial swelling, and several weeks of external deviation of her nasal septum. No significant past medical history was mentioned.  On examination, a left nasal mass was noted. Mild left-sided proptosis was present.  - Imaging Studies:    CT scan (without and with contrast):    - Image Title: Computed tomographic scans of a heterogeneous mass in the left maxillary sinus    - Image Description: Shows a heterogeneous mass with solid ...

## Options
  - A: Ossifying Fibroma
  - B: Giant cell tumor of bone
  - C: Central Giant Cell Granuloma
  - D: Left maxillary giant cell reparative granuloma (GCRG)

## Backbone e7
- S1 key_facts: Several months of sinus pressure and facial swelling; Several weeks of external deviation of her nasal septum; No significant past medical history; Left nasal mass noted on examination; Mild left-sided proptosis present; CT scan showed a heterogeneous mass in the left maxillary sinus; Mass eroded the orbital floor, medial and posterior maxillary walls, and anterio; Displacement of inferior rectus without muscle invasion
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Juvenile nasopharyngeal angiofibroma', 'Rhabdomyosarcoma', "Ewing's sarcoma", 'Osteosarcoma', 'Chondrosarcoma', 'Sinon
  - call2: ['Chordoma', 'Sinonasal teratocarcinosarcoma', 'NUT carcinoma', 'Sinonasal adenocarcinoma', 'Mycetoma', 'Actinomycosis',
  - call3: ['Plexiform fibrohistiocytic tumor', 'Giant cell reparative granuloma', 'Chordoid glioma', 'Sinonasal hemangioma', "Kapo
- S3 shortlist n=5 gold=False: Giant cell tumor, Juvenile nasopharyngeal angiofibroma, Esthesioneuroblastoma, Sinonasal undifferentiated carcinoma, Fibrous dysplasia
- S4 champion: **Giant cell tumor** gold=False
- S4 raw (trunc): {"champion": "Giant cell tumor", "rationale": "The biopsy results showing a spindle cell process with significant multinucleated giant cells, rare mitotic activity, and no cytologic atypia are consistent with a giant cell tumor. The clinical presentation and imaging findings of a

## Backbone v0 (compact)
- S1 key_facts: Several months of sinus pressure and facial swelling; Several weeks of external deviation of the nasal septum; No significant past medical history; Left nasal mass on examination; Mild left-sided proptosis; CT scan showed a heterogeneous mass in the left maxillary sinus; Mass eroded the orbital floor, medial and posterior maxillary walls, and anterio; Displacement of inferior rectus without muscle invasion
- S2 mode=None k=None pool_n=19 gold_in_s2=False
  - pool gold matches: []
  - pool head: Juvenile nasopharyngeal angiofibroma, Rhabdomyosarcoma, Ewing's sarcoma, Osteosarcoma, Chondrosarcoma, Fibrosarcoma, Malignant fibrous histiocytoma, Giant cell tumor
- S3 shortlist n=5 gold=False: Juvenile nasopharyngeal angiofibroma, Giant cell tumor, Fibrous dysplasia, Aneurysmal bone cyst, Ossifying fibroma
- S4 champion: **Giant cell tumor** gold=False
- S4 raw (trunc): {"champion": "Giant cell tumor", "rationale": "The biopsy results showing a spindle cell process with significant multinucleated giant cells, rare mitotic activity, and no cytologic atypia are consistent with a giant cell tumor. The clinical presentation and imaging findings of a

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation of a left nasal mass with proptosis and erosion of surrounding bone, combined with imaging and biopsy results showing a heterogeneous
  - turn1 gold_mention=False diag=
    The biopsy results showing a spindle cell process with significant multinucleated giant cells and rare mitotic activity, along with the imaging findings of a he
  - turn2 gold_mention=False diag=
    The patient's presentation and biopsy results align with a Giant Cell Tumor, considering the spindle cell process and significant multinucleated giant cells, wh
- supervisor votes=3 top2=['Giant Cell Tumor', 'Juvenile Nasopharyngeal Angiofibroma'] gold=False

## Baseline B07
- draft=['Giant Cell Tumor', 'Fibrous Dysplasia'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['sinus mass with spindle cell process and multinucleated giant cells', 'maxillary sinus tumor with erosion of orbital floor and displacement of inferior rectus', 'differential diagnosis of heterogeneous mass in maxillary sinus']
- diagnose=['Giant Cell Tumor', 'Fibrous Dysplasia'] gold=False

## Baseline B01
- queries=['sinus mass with spindle cell process and multinucleated giant cells', 'maxillary sinus tumor with orbital floor erosion and proptosis', 'nasal septum deviation with heterogeneous mass in maxillary sinus', 'spindle cell neoplasm of the head and neck in adolescents']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Juvenile Nasopharyngeal Angiofibroma', 'Antrochoanal Polyp'] gold=False

## APHHM
- tree_n=27 tree_recall=False
- gold_leaf=None
- final_n=3 final_recall=False ranking=['Juvenile Nasopharyngeal Angiofibroma', "Ewing's Sarcoma of the Sinonasal Tract", 'Rhabdomyosarcoma']
- human_at1=False fail_mode=tree_miss

