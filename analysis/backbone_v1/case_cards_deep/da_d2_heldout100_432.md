# DA / d2_heldout100 / case 432

- **gold**: Bullous lichen planus of the nails
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=274; gold_words=6; eponym=False; subtype=False; e7_s2_rank=2; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A man in his 60s presented with painful swelling of the proximal nail folds, dripping of blood from his fingernails and toenails for the last year, and occasional pus discharge. There was no history of preceding trauma or drug intake. Oral mucosa showed lichenoid plaques on the right angle of mouth, bilateral buccal mucosa, and erosions covered with hemorrhagic crusts on the upper and lower lips.  The proximal nail folds were found to be swollen and showed violaceous discoloration of 7 fingernai...

## Options
  - A: Erosive lichen planus
  - B: Hepatitis C-associated nail lichen planus
  - C: Lichen planus
  - D: Bullous lichen planus of the nails

## Backbone e7
- S1 key_facts: Male patient in his 60s; Symptoms present for the last year; No history of preceding trauma or drug intake; Proximal nail folds are swollen and show violaceous discoloration; Nails show longitudinal ridging, thinning, and focal fragmentation; Partial to complete loss of nail plate with oozing of blood and hemorrhagic crus; Oral mucosa shows lichenoid plaques and erosions; Raised liver enzyme levels
- S2 mode=complement k=3 pool_n=53 gold_in_s2=True
  - call1: ['Hepatitis C-associated porphyria cutanea tarda', 'Lichen planus', 'Psoriatic nail dystrophy', 'Dermatomyositis', 'Lupu
  - call2: ['Mixed cryoglobulinemia', 'Hepatitis C-associated lichen planus', 'Necrolytic migratory erythema', 'Acantholytic autoim
  - call3: ['Multicentric reticulohistiocytosis', 'Sjögren-Larsson syndrome', 'Keratoderma blennorrhagicum', 'Pityriasis rubra pila
- S3 shortlist n=5 gold=True: Lichen planus, Hepatitis C-associated porphyria cutanea tarda, Hepatitis C-associated lichen planus, Necrolytic acral erythema, Mixed cryoglobulinemia
- S4 champion: **Hepatitis C-associated lichen planus** gold=False
- S4 raw (trunc): {"champion": "Hepatitis C-associated lichen planus", "rationale": "The patient's symptoms, including painful swelling of the proximal nail folds, lichenoid plaques on the oral mucosa, and histopathology showing hyperkeratosis, hypergranulosis, acanthosis, and basal cell degenerat

## Backbone v0 (compact)
- S1 key_facts: Male patient in his 60s; Symptoms present for the last year; No history of preceding trauma or drug intake; Proximal nail folds are swollen and show violaceous discoloration; Nails demonstrate longitudinal ridging, thinning, and focal fragmentation; Partial to complete loss of nail plate with oozing of blood and hemorrhagic crus; Oral mucosa shows lichenoid plaques and erosions; Raised liver enzyme levels
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Lichen planus', 'Psoriatic nail disease', 'Dermatomyositis', 'Lupus erythematosus', "Sjögren's syndrome", 'Scleroderma
- S3 shortlist n=5 gold=True: Lichen planus, Hepatitis C-associated lichen planus, Psoriatic nail disease, Dermatomyositis, Necrolytic acral erythema
- S4 champion: **Hepatitis C-associated lichen planus** gold=False
- S4 raw (trunc): {"champion": "Hepatitis C-associated lichen planus", "rationale": "The patient's symptoms, including painful swelling of the proximal nail folds, lichenoid plaques on the oral mucosa, and histopathological findings of hyperkeratosis, hypergranulosis, and basal cell degeneration, 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of painful swelling of the proximal nail folds, dripping of blood from fingernails and toenails, and occasional pus discharge, along 
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and histopathology results are consistent with lichen planus, which is further supported by the presence of lichenoid plaque
  - turn2 gold_mention=True diag=
    The patient's clinical presentation and histopathology results are consistent with lichen planus, which is further supported by the presence of lichenoid plaque
- supervisor votes=3 top2=['Lichen Planus', 'Hepatitis C Virus Associated Skin Disorder'] gold=True

## Baseline B07
- draft=['Lichen Planus', 'Hepatitis C Virus Infection'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['nail disorders with liver enzyme abnormalities', 'hepatitis C virus and nail manifestations', 'lichen planus and nail involvement', 'nail fold biopsy and bandlike lymphohistiocytic infiltrate']
- diagnose=['Lichen Planus', 'Hepatitis C Virus Infection'] gold=True

## APHHM
- tree_n=44 tree_recall=True
- gold_leaf=B3.1:Lichen planus parent=B3
- final_n=2 final_recall=False ranking=['Hepatitis C-associated Lichen Planus', 'psoriasis']
- human_at1=False fail_mode=prune_loss

