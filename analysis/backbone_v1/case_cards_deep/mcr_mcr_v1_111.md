# MCR / mcr_v1 / case 111

- **gold**: Giant cell tumor of bone
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **loci**: e7=`ok` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_hit_gen_miss` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=ok; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=225; gold_words=5; eponym=False; subtype=False; e7_s2_rank=4; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A 29-year-old man presented with a 6-month history of progressive neck pain radiating to his left hand. The pain was described as electrical in nature and was associated with numbness in the C8–T1 dermatomes. Over the preceding week, he noted weakness in fine movements and a weak grip of the left hand. His medical and surgical history was unremarkable.  On examination, there was marked atrophy of the hypothenar and interosseous muscles of the left hand. Motor testing of the left hand revealed mu...

## Backbone e7
- S1 key_facts: 6-month history of progressive neck pain; Pain radiates to the left hand; Numbness in the C8–T1 dermatomes; Weakness in fine movements of the left hand; Weak grip of the left hand; Atrophy of the hypothenar and interosseous muscles of the left hand; Motor testing of the left hand revealed muscle strength of 3/5; Marked osteolysis and collapse of the T1 vertebra on CT
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Osteolytic metastasis', 'Multiple myeloma', 'Chordoma', 'Giant cell tumor', 'Aneurysmal bone cyst', 'Osteoblastoma', '
  - call2: ['Brown tumor', 'Gorham-Stout disease', 'Langerhans cell histiocytosis', 'Rosai-Dorfman disease', 'Erdheim-Chester disea
  - call3: ['Chordoid glioma', 'Notochordal tumor', 'Adamantinoma', 'Sclerotic metastasis from prostate cancer', 'Intraosseous lipo
- S3 shortlist n=5 gold=True: Chordoma, Osteolytic metastasis, Giant cell tumor, Plasmacytoma, Multiple myeloma
- S4 champion: **Giant cell tumor** gold=True
- S4 raw (trunc): {"champion": "Giant cell tumor", "rationale": "The presence of marked osteolysis and collapse of the T1 vertebra, along with the involvement of the anterior and posterior longitudinal ligaments, is consistent with a giant cell tumor. The tumor's location in the spine and its effe

## Backbone v0 (compact)
- S1 key_facts: 6-month history of progressive neck pain; Pain radiates to the left hand; Numbness in the C8–T1 dermatomes; Weakness in fine movements of the left hand; Weak grip of the left hand; Atrophy of the hypothenar and interosseous muscles of the left hand; Motor testing of the left hand revealed muscle strength of 3/5; Marked osteolysis and collapse of the T1 vertebra on CT
- S2 mode=None k=None pool_n=18 gold_in_s2=True
  - pool gold matches: ['Giant cell tumor']
  - pool head: Osteolytic metastasis, Multiple myeloma, Chordoma, Giant cell tumor, Aneurysmal bone cyst, Osteoblastoma, Hemangioma, Eosinophilic granuloma
- S3 shortlist n=5 gold=True: Osteolytic metastasis, Chordoma, Giant cell tumor, Plasmacytoma, Spinal tuberculosis
- S4 champion: **Osteolytic metastasis** gold=False
- S4 raw (trunc): {"champion": "Osteolytic metastasis", "rationale": "The patient's presentation of progressive neck pain radiating to the left hand, numbness in the C8–T1 dermatomes, and marked osteolysis and collapse of the T1 vertebra on CT are consistent with osteolytic metastasis. The lesion'

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of progressive neck pain radiating to the left hand with associated numbness and weakness, along with marked atrophy of specific musc
  - turn1 gold_mention=True diag=
    The patient's symptoms and imaging findings are consistent with an aggressive spinal lesion, with metastatic disease and primary bone tumor being top considerat
  - turn2 gold_mention=True diag=
    The patient's presentation and imaging findings suggest an aggressive spinal lesion, with metastatic disease and primary bone tumor being top considerations, wh
- supervisor votes=3 top2=['Metastatic disease', 'Primary bone tumor'] gold=False

## Baseline B07
- draft=['Vertebral Osteomyelitis', 'Vertebral Tumor'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['cervical spine osteolysis causes', 'T1 vertebra collapse differential diagnosis', 'paravertebral soft tissue mass with osteolysis']
- diagnose=['Vertebral Osteomyelitis', 'Vertebral Tumor'] gold=False

## Baseline B01
- queries=['causes of progressive neck pain with radiating pain to the arm', 'differential diagnosis of osteolysis and collapse of the vertebra', 'neoplastic versus infectious causes of vertebral destruction', 'diagnostic criteria for spinal tumors with neurological deficits']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Metastatic spinal tumor', 'Vertebral osteomyelitis'] gold=False

## APHHM
- tree_n=24 tree_recall=True
- gold_leaf=B3.4:Giant cell tumor parent=B3
- final_n=3 final_recall=False ranking=['Chordoma', 'Pancoast tumor', 'Tuberculous spondylitis']
- human_at1=False fail_mode=prune_loss

