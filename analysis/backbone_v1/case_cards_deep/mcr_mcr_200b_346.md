# MCR / mcr_200b / case 346

- **gold**: myxoinflammatory fibroblastic sarcoma
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=195; gold_words=3; eponym=False; subtype=False; e7_s2_rank=17; mapper_rescue=False
- **causal**: layer=e7_win_recall; primary loci above.

## Vignette (trunc)
A 25-year-old man with a history of Hodgkin lymphoma presented with a 2-month history of a gradually enlarging mass over the dorsum of his left hand. Six years earlier, he had been diagnosed with Hodgkin lymphoma on the basis of mediastinal lymphadenopathy and systemic symptoms, and he received 13 courses of chemotherapy. Physical examination at this visit revealed a soft-tissue mass over the second metacarpal dorsum, approximately 4 cm in greatest dimension, with mild tenderness and no limitati...

## Backbone e7
- S1 key_facts: 25-year-old man; History of Hodgkin lymphoma; Diagnosed with Hodgkin lymphoma 6 years earlier; Received 13 courses of chemotherapy; Mass located over the dorsum of the left hand; Mass measures approximately 4 cm in greatest dimension; Mild tenderness but no limitation of movement; Microscopic examination shows a mixture of inflammatory cells and myxoid stroma
- S2 mode=complement k=3 pool_n=44 gold_in_s2=True
  - call1: ['Liposarcoma', 'Myxoid liposarcoma', 'Dedifferentiated liposarcoma', 'Pleomorphic liposarcoma', 'Myxofibrosarcoma', 'Un
  - call2: ['Inflammatory myofibroblastic tumor', 'Myxoinflammatory fibroblastic sarcoma', 'Acral myxoinflammatory fibroblastic sar
  - call3: ['Superficial acral fibromyxoma', 'Atypical fibroxanthoma', 'Malignant granular cell tumor', 'Alveolar soft part sarcoma
- S3 shortlist n=5 gold=True: Myxoinflammatory fibroblastic sarcoma, Acral myxoinflammatory fibroblastic sarcoma, Myxoid liposarcoma, Inflammatory myofibroblastic tumor, Hodgkin lymphoma
- S4 champion: **Acral myxoinflammatory fibroblastic sarcoma** gold=True
- S4 raw (trunc): {"champion": "Acral myxoinflammatory fibroblastic sarcoma", "rationale": "The mass is located over the dorsum of the hand, which is a characteristic location for acral myxoinflammatory fibroblastic sarcoma, and the microscopic examination shows a mixture of inflammatory cells, my

## Backbone v0 (compact)
- S1 key_facts: 25-year-old man; History of Hodgkin lymphoma; Diagnosed with Hodgkin lymphoma 6 years earlier; Received 13 courses of chemotherapy; Mass located over the dorsum of the left hand; Mass measures approximately 4 cm in greatest dimension; Mild tenderness with no limitation of movement; Microscopic examination shows a mixture of inflammatory cells and myxoid stroma
- S2 mode=single k=1 pool_n=15 gold_in_s2=True
  - call1: ['Liposarcoma', 'Myxoid liposarcoma', 'Dedifferentiated liposarcoma', 'Pleomorphic liposarcoma', 'Myxofibrosarcoma', 'Un
- S3 shortlist n=5 gold=True: Myxoinflammatory fibroblastic sarcoma, Myxoid liposarcoma, Inflammatory myofibroblastic tumor, Liposarcoma, Myxofibrosarcoma
- S4 champion: **Myxoinflammatory fibroblastic sarcoma** gold=True
- S4 raw (trunc): {"champion": "Myxoinflammatory fibroblastic sarcoma", "rationale": "The presence of a mixture of inflammatory cells, myxoid stroma, epithelioid and spindle-shaped cells, lipoblast-like cells, and occasional Reed–Sternberg–like cells is most consistent with Myxoinflammatory fibrob

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The presence of Reed-Sternberg-like cells and a history of Hodgkin lymphoma suggests a possible diagnosis of Hodgkin lymphoma, but the myxoid stroma and lipobla
  - turn1 gold_mention=True diag=
    The presence of myxoid stroma, lipoblast-like cells, and Reed-Sternberg-like cells, along with the patient's history of Hodgkin lymphoma, suggests a complex dif
  - turn2 gold_mention=True diag=
    The presence of Reed-Sternberg-like cells and myxoid stroma suggests a complex differential diagnosis, with myxoid liposarcoma and lipoblastoma being top consid
- supervisor votes=3 top2=['Myxoid liposarcoma', 'Lipoblastoma'] gold=False

## Baseline B07
- draft=['Hodgkin lymphoma', 'Myxoid liposarcoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['Reed-Sternberg-like cells diagnosis', 'myxoid stroma and lipoblast-like cells', 'Hodgkin lymphoma and soft tissue mass', 'inflammatory background and epithelioid cells']
- diagnose=['Hodgkin lymphoma', 'Myxoid liposarcoma'] gold=False

## Baseline B01
- queries=['Reed-Sternberg-like cells in soft tissue tumors', 'Inflammatory myxoid tumors of the hand', 'Immunohistochemical staining for Hodgkin lymphoma vs other lymphomas', 'Differential diagnosis of soft tissue masses with Reed-Sternberg-like cells']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Hodgkin lymphoma', 'Myxoid tumor'] gold=False

