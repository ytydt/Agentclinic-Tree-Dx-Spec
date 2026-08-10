# DA / d2_heldout100 / case 349

- **gold**: Cutaneous histoplasmosis
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **loci**: e7=`s3_hit_s4_miss` B06=`agents_miss` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=223; gold_words=2; eponym=False; subtype=False; e7_s2_rank=7; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A man in his 70s presented with 2 progressively enlarging, painless nodular lesions on the forehead and right cheek, initially observed as erythematous nodules 3 months prior. The lesions gradually increased in size with subsequent central ulceration and blackish crusting. No fever, pain, or discharge from the lesions was noted. Patient had history of kidney transplant in 2004 causing immunocompromised status.  Two distinct lesions measuring 2 × 2 cm each were identified over the glabella and ri...

## Options
  - A: Cutaneous histoplasmosis
  - B: Cutaneous cryptococcosis
  - C: Histoplasmosis
  - D: Cutaneous blastomycosis

## Backbone e7
- S1 key_facts: Patient is a man in his 70s; Lesions were initially observed as erythematous nodules 3 months prior; Lesions gradually increased in size; No fever, pain, or discharge from the lesions; Patient has a history of kidney transplant in 2004; Patient is immunocompromised; Lesions are firm with central ulceration and hemorrhagic crusting; Dermoscopy showed arborizing telangiectasias, central ulceration with crusting, 
- S2 mode=complement k=3 pool_n=57 gold_in_s2=True
  - call1: ['Basal cell carcinoma', 'Squamous cell carcinoma', 'Merkel cell carcinoma', 'Cutaneous lymphoma', "Kaposi's sarcoma", '
  - call2: ['Lobomycosis', 'Sporotrichosis', 'Penicilliosis', 'Emmonsiosis', 'Entomophthoromycosis', 'Pythiosis', 'Lacazia loboi in
  - call3: ['Lobular capillary hemangioma', 'Pyogenic granuloma', 'Microcystic adnexal carcinoma', 'Trichoepithelioma', 'Pilomatrix
- S3 shortlist n=5 gold=True: Cryptococcosis, Blastomycosis, Histoplasmosis, Kaposi's sarcoma, Cutaneous lymphoma
- S4 champion: **Cryptococcosis** gold=False
- S4 raw (trunc): {"champion": "Cryptococcosis", "rationale": "The presence of intracellular yeasts with surrounding halos on histopathological examination is characteristic of Cryptococcosis, particularly in an immunocompromised patient.", "rejected": [{"label": "Blastomycosis", "why": "While Bla

## Backbone v0 (compact)
- S1 key_facts: Patient is a man in his 70s; Lesions were initially observed as erythematous nodules 3 months prior; Lesions gradually increased in size; No fever, pain, or discharge from the lesions; Patient has a history of kidney transplant in 2004; Patient is immunocompromised; Lesions are firm with central ulceration and hemorrhagic crusting; Dermoscopy showed arborizing telangiectasias, central ulceration with crusting, 
- S2 mode=single k=1 pool_n=21 gold_in_s2=True
  - call1: ['Basal cell carcinoma', 'Squamous cell carcinoma', 'Merkel cell carcinoma', 'Cutaneous lymphoma', "Kaposi's sarcoma", '
- S3 shortlist n=5 gold=True: Cryptococcosis, Blastomycosis, Histoplasmosis, Basal cell carcinoma, Squamous cell carcinoma
- S4 champion: **Cryptococcosis** gold=False
- S4 raw (trunc): {"champion": "Cryptococcosis", "rationale": "The presence of intracellular yeasts with surrounding halos on histopathological examination is a key feature of Cryptococcosis, especially in an immunocompromised patient.", "rejected": [{"label": "Blastomycosis", "why": "While Blasto

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's immunocompromised status and histopathological findings of intracellular yeasts with surrounding halos are highly suggestive of Cryptococcosis, wh
  - turn1 gold_mention=False diag=
    The patient's immunocompromised status, histopathological findings of intracellular yeasts, and dermoscopic features support Cryptococcosis as the top diagnosis
  - turn2 gold_mention=False diag=
    The patient's immunocompromised status, histopathological findings of intracellular yeasts with surrounding halos, and dermoscopic features of arborizing telang
- supervisor votes=3 top2=['Cryptococcosis', 'Basal cell carcinoma'] gold=False

## Baseline B07
- draft=['Cutaneous Leishmaniasis', 'Cryptococcosis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['cutaneous leishmaniasis in immunocompromised patients', 'skin lesions with intracellular yeasts and halos', 'differential diagnosis for umbilicated skin lesions with central ulceration']
- diagnose=['Cutaneous Leishmaniasis', 'Cryptococcosis'] gold=False

## APHHM
- tree_n=32 tree_recall=True
- gold_leaf=B1.3:Histoplasmosis parent=B1
- final_n=2 final_recall=False ranking=['Cryptococcosis', "Kaposi's sarcoma"]
- human_at1=False fail_mode=prune_loss

