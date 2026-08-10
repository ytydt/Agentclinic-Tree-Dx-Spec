# MCR / mcr_v2 / case 142

- **gold**: angiosarcoma
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=210; gold_words=1; eponym=False; subtype=False; e7_s2_rank=12; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 7-year-old girl presented with a 2-year history of an enlarging, intermittently painful, purplish lump in her left ear canal. Approximately 18 months earlier, she had developed cracking and pus-filled sores at the site and received antibiotics and analgesics before referral. On examination, there was a 3.5 × 2.5 cm purplish-red mass in the left external ear canal, with an irregular, friable surface and bleeding on minimal contact. Contrast-enhanced CT of the mastoids showed a lobulated mass in...

## Backbone e7
- S1 key_facts: 7-year-old girl; 2-year history of enlarging mass; Intermittent pain; Purplish lump in left ear canal; Cracking and pus-filled sores at the site; Received antibiotics and analgesics; 3.5 × 2.5 cm mass in left external ear canal; Irregular, friable surface
- S2 mode=complement k=3 pool_n=45 gold_in_s2=True
  - call1: ['Rhabdomyosarcoma', 'Langerhans cell histiocytosis', 'Merkel cell carcinoma', 'Basal cell carcinoma', 'Squamous cell ca
  - call2: ['Hemangiopericytoma', 'Glomus tumor', 'Plexiform neurofibroma', 'Atypical fibroxanthoma', 'Malignant peripheral nerve s
  - call3: ['Granulomatosis with polyangiitis', 'Erdheim-Chester disease', 'Langerhans cell sarcoma', 'Interdigitating dendritic ce
- S3 shortlist n=5 gold=True: Rhabdomyosarcoma, Langerhans cell histiocytosis, Angiosarcoma, Lymphoma, Ewing's sarcoma
- S4 champion: **Rhabdomyosarcoma** gold=False
- S4 raw (trunc): {"champion": "Rhabdomyosarcoma", "rationale": "The presence of a rapidly enlarging, painful mass with bleeding on minimal contact, along with atypical cells on biopsy, suggests an aggressive malignant tumor. Rhabdomyosarcoma is a common soft tissue sarcoma in children that can pr

## Backbone v0 (compact)
- S1 key_facts: 7-year-old girl; 2-year history of an enlarging mass; Intermittent pain; Purplish lump in the left ear canal; Cracking and pus-filled sores at the site; Received antibiotics and analgesics; Mass size: 3.5 × 2.5 cm; Irregular, friable surface
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Rhabdomyosarcoma', 'Langerhans cell histiocytosis', "Ewing's sarcoma", 'Lymphoma', 'Melanoma', 'Squamous cell carcinom
- S3 shortlist n=5 gold=True: Rhabdomyosarcoma, Langerhans cell histiocytosis, Ewing's sarcoma, Lymphoma, Angiosarcoma
- S4 champion: **Rhabdomyosarcoma** gold=False
- S4 raw (trunc): {"champion": "Rhabdomyosarcoma", "rationale": "The presence of a rapidly enlarging, painful, and bleeding mass in a child, along with atypical cells on biopsy, is most consistent with Rhabdomyosarcoma, a common soft tissue sarcoma in children.", "rejected": [{"label": "Langerhans

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's age, symptoms, and imaging findings, Rhabdomyosarcoma is a strong consideration due to its propensity to occur in the head and neck region o
  - turn1 gold_mention=True diag=
    The patient's age, symptoms, and imaging findings align with Doctor A's considerations, with Rhabdomyosarcoma being a top differential due to its predilection f
  - turn2 gold_mention=True diag=
    The patient's presentation of a rapidly growing, painful, and vascular mass in the ear canal, along with lymph node involvement and atypical cells on biopsy, su
- supervisor votes=3 top2=['Rhabdomyosarcoma', 'Angiosarcoma'] gold=True

## Baseline B07
- draft=['Rhabdomyosarcoma', 'Langerhans Cell Histiocytosis (LCH)'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['auricular malignant tumors in children', 'purplish lump in ear canal', 'atypical cells and granulomatous inflammation in ear mass']
- diagnose=['Rhabdomyosarcoma', 'Langerhans Cell Histiocytosis (LCH)'] gold=False

## Baseline B01
- queries=['pediatric ear canal tumors', 'granulomatous inflammation in ear masses', 'vascular tumors of the ear', 'atypical cells in auricular malignancies']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Embryonal Rhabdomyosarcoma', 'Squamous Cell Carcinoma'] gold=False

