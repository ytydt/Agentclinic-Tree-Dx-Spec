# DA / d2_heldout100 / case 317

- **gold**: Pyoderma vegetans
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`draft_miss` B01=`na` APHHM=`tree_miss`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=208; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A teenaged male presented with a 2-week history of vegetating, bleeding plaques and pustules on his face, scalp, trunk, and extremities. Lesions began as pustules and developed into painful, itchy plaques. Prior treatment included prednisolone tablet 5 mg twice daily, clindamycin hydrochloride 300 mg daily, and fluconazole 200 mg daily, but patient continued to develop new lesions. Patient reported difficulty walking due to skin lesions.  Pustules and hemorrhagic-crusted plaques were seen on the...

## Options
  - A: Pyodermatitis-pyostomatitis vegetans
  - B: Pyoderma vegetans
  - C: Blastomycosis-like pyoderma
  - D: Pemphigus vegetans

## Backbone e7
- S1 key_facts: Teenaged male patient; 2-week history of skin lesions; Lesions began as pustules and developed into painful, itchy plaques; Prior treatment with prednisolone, clindamycin hydrochloride, and fluconazole; Continued development of new lesions despite treatment; Difficulty walking due to skin lesions; Pustules and hemorrhagic-crusted plaques on the scalp, legs, arms, and trunk; Keloidal plaques on the face
- S2 mode=complement k=3 pool_n=49 gold_in_s2=False
  - call1: ['Pyoderma gangrenosum', 'Sweet syndrome', 'Erythema elevatum diutinum', 'Leukocytoclastic vasculitis', 'Pyogenic granul
  - call2: ['Halogenoderma', 'Neutrophilic dermatosis of the dorsal hands', 'Rapidly progressive neutrophilic hidradenitis', 'Eosin
  - call3: ['Hyper-IgE syndrome', 'Job syndrome', 'Chronic recurrent multifocal osteomyelitis', 'SAPHO syndrome', 'PASH syndrome', 
- S3 shortlist n=5 gold=False: Pyoderma gangrenosum, Sweet syndrome, Erythema elevatum diutinum, Generalized pustular psoriasis, Acute febrile neutrophilic dermatosis
- S4 champion: **Sweet syndrome** gold=False
- S4 raw (trunc): {"champion": "Sweet syndrome", "rationale": "The patient's symptoms, including painful and itchy plaques, pustules, and histopathology showing epidermal hyperplasia, exocytosis of neutrophils, and dense dermal-mixed inflammatory cell infiltration, are consistent with Sweet syndro

## Backbone v0 (compact)
- S1 key_facts: 2-week history of skin lesions; Lesions began as pustules and developed into painful, itchy plaques; Prior treatment included prednisolone, clindamycin, and fluconazole; Patient continued to develop new lesions despite treatment; Pustules and hemorrhagic-crusted plaques were seen on the scalp, legs, arms, and; Keloidal plaques were seen on the face; Patient reported difficulty walking due to skin lesions; HIV test was negative
- S2 mode=single k=1 pool_n=16 gold_in_s2=False
  - call1: ['Pyoderma gangrenosum', 'Sweet syndrome', 'Erythema elevatum diutinum', 'Leukocytoclastic vasculitis', 'Pyogenic granul
- S3 shortlist n=5 gold=False: Pyoderma gangrenosum, Sweet syndrome, Generalized pustular psoriasis, Subcorneal pustular dermatosis, Acute generalized exanthematous pustulosis
- S4 champion: **Pyoderma gangrenosum** gold=False
- S4 raw (trunc): {"champion": "Pyoderma gangrenosum", "rationale": "The patient's presentation of painful, itchy plaques that began as pustules and developed into vegetative plaques with bleeding and ulceration, along with the histopathological findings of epidermal hyperplasia, dense dermal-mixe

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of vegetating, bleeding plaques and pustules, along with the histopathological findings of epidermal hyperplasia, dense dermal-mixed 
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and histopathological findings are consistent with the top diagnosis, and the lack of response to prior treatment suggests a
  - turn2 gold_mention=True diag=
    The patient's clinical presentation of vegetating, bleeding plaques and pustules, along with histopathological findings, supports the top diagnosis, and the lac
- supervisor votes=3 top2=['Pyoderma gangrenosum', 'Pyoderma vegetans'] gold=True

## Baseline B07
- draft=['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Eosinophilic Dermatitis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['vegetating bleeding plaques and pustules diagnosis', 'pseudoepitheliomatous hyperplasia causes', 'dermal neutrophilia and microabscesses with eosinophilia diagnosis']
- diagnose=['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Eosinophilic Dermatitis'] gold=False

## APHHM
- tree_n=23 tree_recall=False
- gold_leaf=None
- final_n=5 final_recall=False ranking=['Pyoderma gangrenosum', 'Sweet syndrome', 'Sweet syndrome', 'Sweet syndrome', 'Acute generalized exanthematous pustulosis']
- human_at1=False fail_mode=tree_miss

