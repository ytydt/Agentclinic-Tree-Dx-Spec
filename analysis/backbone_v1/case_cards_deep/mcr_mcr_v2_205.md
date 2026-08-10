# MCR / mcr_v2 / case 205

- **gold**: Cysticercosis
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=223; gold_words=1; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 55-year-old man presented with multiple asymptomatic, skin-colored nodules over his neck, trunk, and upper limbs for 1 year. The lesions had slowly increased in size and number. He reported no systemic complaints, including no fever, weight loss, or neurologic symptoms. He ate beef but denied consumption of pork and had never noted passage of tape-like worms in his stool.  On examination, vital signs were normal. General and systemic examinations were unremarkable, with no lymphadenopathy. Cut...

## Backbone e7
- S1 key_facts: 55-year-old man; Asymptomatic skin nodules for 1 year; No systemic complaints, including no fever, weight loss, or neurologic symptoms; Eats beef, denies consumption of pork; No passage of tape-like worms in stool; Normal vital signs; Unremarkable general and systemic examinations; No lymphadenopathy
- S2 mode=complement k=3 pool_n=52 gold_in_s2=False
  - call1: ['Neurofibromatosis type 1', 'Tuberous sclerosis', 'Multiple lipomas', 'Familial cylindromatosis', 'Basal cell nevus syn
  - call2: ['Erdheim-Chester disease', 'Langerhans cell histiocytosis', 'Rosai-Dorfman disease', 'Histiocytosis X', 'Multicentric r
  - call3: ['Scleredema adultorum', 'Nephrogenic systemic fibrosis', 'Eosinophilic fasciitis', 'Panniculitis', 'Subcutaneous fat ne
- S3 shortlist n=5 gold=False: Neurofibromatosis type 1, Lipoid proteinosis, Multiple lipomas, Dermatofibromas, Fibromatosis
- S4 champion: **Lipoid proteinosis** gold=False
- S4 raw (trunc): {"champion": "Lipoid proteinosis", "rationale": "The presence of asymptomatic, skin-colored nodules and a firm nodule on the lateral tongue is consistent with lipoid proteinosis, a rare condition characterized by the deposition of hyaline material in the skin and mucous membranes

## Backbone v0 (compact)
- S1 key_facts: 55-year-old man; Asymptomatic skin nodules for 1 year; No systemic complaints, including no fever, weight loss, or neurologic symptoms; Eats beef, denies consumption of pork; No passage of tape-like worms in stool; Normal vital signs; Unremarkable general and systemic examinations; No lymphadenopathy
- S2 mode=single k=1 pool_n=19 gold_in_s2=False
  - call1: ['Neurofibromatosis type 1', 'Tuberous sclerosis', 'Multiple lipomas', 'Familial cystic hygroma', 'Cystic lymphangioma',
- S3 shortlist n=5 gold=False: Neurofibromatosis type 1, Multiple lipomas, Dermatofibrosarcoma protuberans, Cylindroma, Tuberous sclerosis
- S4 champion: **Multiple lipomas** gold=False
- S4 raw (trunc): {"champion": "Multiple lipomas", "rationale": "The patient presents with multiple asymptomatic, skin-colored nodules that are discrete, firm, and freely mobile, which is consistent with the characteristics of lipomas. The absence of systemic complaints, normal laboratory investig

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of multiple asymptomatic, skin-colored nodules is suggestive of a few possible diagnoses, with Cysticercosis being a strong considera
  - turn1 gold_mention=True diag=
    The patient's presentation and lack of systemic symptoms align with Doctor A's considerations, with Cysticercosis remaining a top differential due to the subcut
  - turn2 gold_mention=True diag=
    The patient's presentation of multiple asymptomatic, skin-colored nodules, along with a nodule on the lateral tongue, supports the prior opinions, with Cysticer
- supervisor votes=3 top2=['Cysticercosis', 'Neurofibromatosis'] gold=True

## Baseline B07
- draft=['Cysticercosis', 'Lipoma'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['skin-colored nodules on neck trunk and upper limbs', 'asymptomatic skin nodules', 'firm freely mobile nodules', 'subcutaneous nodules differential diagnosis']
- diagnose=['Cysticercosis', 'Lipoma'] gold=True

## Baseline B01
- queries=['skin-colored nodules on neck, trunk, and upper limbs', 'asymptomatic skin nodules with slow growth', 'firm, freely mobile cutaneous nodules without systemic symptoms', 'subcutaneous nodules with normal laboratory investigations']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Dermatofibroma', 'Nevus Anemicus'] gold=False

