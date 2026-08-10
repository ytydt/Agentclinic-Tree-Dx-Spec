# DA / d2_heldout100 / case 314

- **gold**: Peeling skin disease (PSD)
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=1
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_ok` B01=`na` APHHM=`tree_miss`
- **primary_locus**: e7=s2_hit_s3_drop; B06=supervisor_miss_but_scored_ok
- **covariates**: vig_words=246; gold_words=4; eponym=False; subtype=False; e7_s2_rank=9; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 2-year-old girl presented with skin fragility since early infancy. She had 2 older brothers, and the family had no medical history of note. Symptoms improved in winter and worsened in summer. Physical and mental developments were normal. The mother reported finding the child peeling off skin with marked facility.  Physical examination revealed:- Mild xerosis with superficial skin erosions- Erythematous residual macules from previous erosions- Some lesions had unusual linear geographic contour-...

## Options
  - A: Acral Peeling Skin Syndrome
  - B: Peeling skin disease (PSD)
  - C: Peeling skin syndrome
  - D: Peeling Skin Syndrome Type B (Acral)

## Backbone e7
- S1 key_facts: 2-year-old girl presented with skin fragility; Symptoms improved in winter and worsened in summer; Physical and mental developments were normal; Mild xerosis with superficial skin erosions; Erythematous residual macules from previous erosions; Lesions had unusual linear geographic contour; Lesions predominantly located at areas of friction; Hair, nails, and mucous membranes were normal
- S2 mode=complement k=3 pool_n=58 gold_in_s2=True
  - call1: ['Peeling skin syndrome', 'Keratolysis exfoliativa', 'Focal acral hyperkeratosis', 'Erythrokeratodermia variabilis', 'Ic
  - call2: ['Incontinentia pigmenti', 'Galli-Galli disease', 'Darier disease', 'Hailey-Hailey disease', 'Dowling-Degos disease', 'G
  - call3: ['Peeling skin disease type C', 'Acral peeling skin syndrome type 2', 'CDSN-related peeling skin syndrome', 'Autosomal r
- S3 shortlist n=5 gold=False: Peeling skin syndrome, Acral peeling skin syndrome, CDSN-related peeling skin syndrome, Samira type peeling skin syndrome, Generalized peeling skin syndrome
- S4 champion: **CDSN-related peeling skin syndrome** gold=False
- S4 raw (trunc): {"champion": "CDSN-related peeling skin syndrome", "rationale": "The genetic study revealed 2 heterozygous mutations in exon 2 of the CDSN gene, which is a strong evidence for CDSN-related peeling skin syndrome", "rejected": [{"label": "Peeling skin syndrome", "why": "Too general

## Backbone v0 (compact)
- S1 key_facts: 2-year-old girl presented with skin fragility; Symptoms improved in winter and worsened in summer; Physical and mental developments were normal; Mild xerosis with superficial skin erosions; Erythematous residual macules from previous erosions; Lesions had unusual linear geographic contour; Lesions predominantly located at areas of friction; Hair, nails, and mucous membranes were normal
- S2 mode=single k=1 pool_n=21 gold_in_s2=True
  - call1: ['Peeling skin syndrome', 'Keratolysis exfoliativa', 'Erythrokeratodermia variabilis', 'Ichthyosis bullosa of Siemens', 
- S3 shortlist n=5 gold=False: Peeling skin syndrome, Acral peeling skin syndrome, Samira type peeling skin syndrome, Keratolysis exfoliativa, Generalized peeling skin syndrome
- S4 champion: **Peeling skin syndrome** gold=False
- S4 raw (trunc): {"champion": "Peeling skin syndrome", "rationale": "The patient's symptoms of skin fragility, superficial skin erosions, and erythematous residual macules, along with the genetic study revealing 2 heterozygous mutations in exon 2 of the CDSN gene, are consistent with peeling skin

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms of skin fragility, superficial skin erosions, and peeling, particularly worsening in summer, along with the specific findings on skin bio
  - turn1 gold_mention=True diag=
    The patient's presentation of skin fragility, superficial erosions, and peeling, combined with the genetic study showing mutations in the CDSN gene and specific
  - turn2 gold_mention=True diag=
    The patient's symptoms and genetic study revealing mutations in the CDSN gene strongly support Peeling Skin Syndrome as the primary diagnosis, consistent with p
- supervisor votes=3 top2=['Peeling Skin Syndrome', 'Keratosis Pilaris'] gold=False

## Baseline B07
- draft=['Peeling Skin Disease', 'Dermatitis Artefacta'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['peeling skin disease', 'CDSN gene mutations', 'skin fragility in children']
- diagnose=['Peeling Skin Disease', 'Dermatitis Artefacta'] gold=True

## APHHM
- tree_n=23 tree_recall=False
- gold_leaf=None
- final_n=1 final_recall=False ranking=['Acral Peeling Skin Syndrome']
- human_at1=False fail_mode=tree_miss

