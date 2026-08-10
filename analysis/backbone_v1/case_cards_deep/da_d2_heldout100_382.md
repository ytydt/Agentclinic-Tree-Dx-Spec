# DA / d2_heldout100 / case 382

- **gold**: Genital porokeratosis (GP)
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=1 B01= APHHM=0
- **loci**: e7=`ok` B06=`agents_miss` B07=`diagnose_ok` B01=`na` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=205; gold_words=3; eponym=False; subtype=False; e7_s2_rank=13; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A man in his 40s presented with a 10-year history of pruritic lesions on the scrotum and buttock. He was previously treated at a local clinic with little improvement. He had no relevant medical history and no family history of similar skin problems.  Scattered, well-defined, annular gray hyperkeratotic plaques with an atrophic center and a slightly elevated edge on the scrotum, buttock, groin, and intergluteal cleft. There was no inguinal adenopathy.  {'Laboratory Tests': 'Routine blood work, in...

## Options
  - A: Porokeratosis of Mibelli
  - B: Porokeratosis Ptychotropica
  - C: Genital porokeratosis (GP)
  - D: Classic Porokeratosis (Mibelli Type)

## Backbone e7
- S1 key_facts: 10-year history of pruritic lesions; Lesions located on scrotum, buttock, groin, and intergluteal cleft; Previous treatment at local clinic with little improvement; No relevant medical history; No family history of similar skin problems; Normal or negative routine blood work, syphilis serologies, and HIV testing; Histopathological examination revealed hyperkeratosis and parakeratotic columns; Perivascular infiltration of lymphocytes in the dermis
- S2 mode=complement k=3 pool_n=43 gold_in_s2=True
  - call1: ["Darier's disease", "Grover's disease", 'Hailey-Hailey disease', "Bowen's disease", 'Erythrasma', 'Seborrheic keratosis
  - call2: ['Necrolytic migratory erythema', 'Glucagonoma syndrome', 'Acrokeratosis paraneoplastica', 'Tylosis', 'Howel-Evans syndr
  - call3: ['Mycosis fungoides', "Paget's disease", 'Intraepithelial carcinoma', 'Lichen planus', 'Pemphigus', 'Parapsoriasis', 'Po
- S3 shortlist n=5 gold=True: Darier's disease, Grover's disease, Porokeratosis, Lichen simplex chronicus, Disseminated superficial porokeratosis
- S4 champion: **Porokeratosis** gold=True
- S4 raw (trunc): {"champion": "Porokeratosis", "rationale": "The presence of hyperkeratosis, irregular papillomatosis, parakeratotic columns (cornoid lamella), and dyskeratotic keratinocytes in the histopathological examination, along with the clinical presentation of well-defined, annular gray h

## Backbone v0 (compact)
- S1 key_facts: 10-year history of pruritic lesions; Lesions located on scrotum, buttock, groin, and intergluteal cleft; Previous treatment at local clinic with little improvement; No relevant medical history; No family history of similar skin problems; Normal or negative routine blood work, syphilis serologies, and HIV testing; Histopathological examination revealed hyperkeratosis and parakeratotic columns; Perivascular infiltration of lymphocytes in the dermis
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['Darier disease', 'Grover disease', 'Hailey-Hailey disease', 'Bowen disease', 'Erythrasma', 'Seborrheic keratosis', 'Li
- S3 shortlist n=5 gold=True: Darier disease, Grover disease, Hailey-Hailey disease, Porokeratosis, Lichen simplex chronicus
- S4 champion: **Porokeratosis** gold=True
- S4 raw (trunc): {"champion": "Porokeratosis", "rationale": "The presence of hyperkeratosis, irregular papillomatosis, parakeratotic columns (cornoid lamella), and dyskeratotic keratinocytes in the histopathological examination are characteristic features of porokeratosis, which is a disorder of 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The clinical presentation and histopathological findings suggest a chronic skin condition with features of hyperkeratosis and dyskeratotic keratinocytes, pointi
  - turn1 gold_mention=False diag=
    The clinical presentation of pruritic, annular, gray hyperkeratotic plaques with atrophic centers, along with histopathological findings of hyperkeratosis, para
  - turn2 gold_mention=False diag=
    The clinical presentation of pruritic, annular, gray hyperkeratotic plaques with atrophic centers, along with histopathological findings, supports Lichen sclero
- supervisor votes=3 top2=['Lichen sclerosus', "Darier's disease"] gold=False

## Baseline B07
- draft=['Porokeratosis', 'Seborrheic Keratosis'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['pruritic lesions on scrotum and buttock', 'annular gray hyperkeratotic plaques', 'hyperkeratosis and parakeratotic columns', 'dyskeratotic keratinocytes and hypogranulosis']
- diagnose=['Porokeratosis', 'Seborrheic Keratosis'] gold=True

## APHHM
- tree_n=25 tree_recall=False
- gold_leaf=None
- final_n=1 final_recall=False ranking=["Darier's disease"]
- human_at1=False fail_mode=tree_miss

