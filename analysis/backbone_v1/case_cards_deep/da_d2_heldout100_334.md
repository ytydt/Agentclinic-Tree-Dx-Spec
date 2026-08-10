# DA / d2_heldout100 / case 334

- **gold**: Phaeohyphomycosis
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **loci**: e7=`s2_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`na` APHHM=`tree_miss`
- **primary_locus**: e7=s2_miss; recalled_but_none_correct
- **covariates**: vig_words=263; gold_words=1; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 至少一臂召回金标但无人 Acc@1——排序/裁决天花板。

## Vignette (trunc)
A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaques within 10 years. There was involvement of the upper respiratory tract, causing palatal perforation and stridor, necessitating a tracheostomy a year ago. History of wheezing and breathlessness. No history of preceding trauma, fever, malaise, joint pain, cough, epistaxis, hemoptysis, or hematuria. ...

## Options
  - A: Granulomatosis with polyangiitis (Wegener’s)
  - B: Chromoblastomycosis
  - C: Phaeohyphomycosis
  - D: Disseminated cutaneous fungal infection

## Backbone e7
- S1 key_facts: Woman in her 30s; Lesions started as an erythematous papule on the face and progressed to larger p; Involvement of the upper respiratory tract; History of wheezing and breathlessness; No history of preceding trauma, fever, malaise, joint pain, cough, epistaxis, he; Multiple well-defined brown erythematous scaly plaques with central scarring; Cervical lymphadenopathy with multiple, nontender, discrete nodes; Anemia with hemoglobin 10.1 g/dL
- S2 mode=complement k=3 pool_n=61 gold_in_s2=False
  - call1: ['Leprosy', 'Sarcoidosis', 'Relapsing polychondritis', 'Granulomatosis with polyangiitis', 'Churg-Strauss syndrome', 'Er
  - call2: ['Histoplasmosis', 'Coccidioidomycosis', 'Blastomycosis', 'Paracoccidioidomycosis', 'Chromoblastomycosis', 'Sporotrichos
  - call3: ['Mycobacterium abscessus infection', 'Mycobacterium chelonae infection', 'Mycobacterium fortuitum infection', 'Buruli u
- S3 shortlist n=5 gold=False: Chromoblastomycosis, Leprosy, Rhinoscleroma, Mycetoma, Exophiala infection
- S4 champion: **Chromoblastomycosis** gold=False
- S4 raw (trunc): {"champion": "Chromoblastomycosis", "rationale": "The presence of well-defined brown erythematous scaly plaques with central scarring, pseudoepitheliomatous hyperplasia, parakeratosis, and dense dermal infiltrate of histiocytes in the histopathology, along with the isolation of a

## Backbone v0 (compact)
- S1 key_facts: Woman in her 30s; Lesions started as an erythematous papule on the face and progressed to larger p; Involvement of the upper respiratory tract; History of wheezing and breathlessness; No history of preceding trauma, fever, malaise, joint pain, cough, epistaxis, he; Multiple well-defined brown erythematous scaly plaques with central scarring; Cervical lymphadenopathy with multiple, nontender, discrete nodes; Anemia with hemoglobin 10.1 g/dL
- S2 mode=single k=1 pool_n=22 gold_in_s2=False
  - call1: ['Leprosy', 'Sarcoidosis', 'Relapsing polychondritis', 'Granulomatosis with polyangiitis', 'Churg-Strauss syndrome', 'Er
- S3 shortlist n=5 gold=False: Leprosy, Relapsing polychondritis, Granulomatosis with polyangiitis, Lupus vulgaris, Chronic cutaneous lupus erythematosus
- S4 champion: **Lupus vulgaris** gold=False
- S4 raw (trunc): {"champion": "Lupus vulgaris", "rationale": "The presence of multiple well-defined brown erythematous scaly plaques with central scarring, pseudoepitheliomatous hyperplasia, and parakeratosis in the histopathology, along with the involvement of the upper respiratory tract and cer

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation of asymptomatic erythematous scaly plaques, palatal perforation, and stridor, along with the histopathological findings of pseudoepit
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and histopathological findings, including the presence of pigmented yeasts and black yeastlike colonies of Exophiala spinife
  - turn2 gold_mention=True diag=
    The patient's clinical presentation of asymptomatic erythematous scaly plaques, palatal perforation, and stridor, along with the histopathological findings of p
- supervisor votes=3 top2=['Chromoblastomycosis', 'Phaeohyphomycosis'] gold=True

## Baseline B07
- draft=['Eumycetoma', 'Chromoblastomycosis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaqu', 'differential diagnosis A woman in her 30s presented with asymptomatic erythematous scaly plaques over the face and proximal extremities. The lesions started as an erythematous papule on the face, progressing to larger plaqu', 'clinical manifestations diagnosis  × 1 to 8 × 7 cm on the face, arm, and thighs. Saddle nose deformity, perforation of the hard palate, and necrotic plaques on the ear with destruction of ear ca']
- diagnose=['Eumycetoma', 'Chromoblastomycosis'] gold=False

## APHHM
- tree_n=19 tree_recall=False
- gold_leaf=None
- final_n=4 final_recall=False ranking=['Chromoblastomycosis', 'Relapsing Polychondritis', 'Chronic Granulomatous Disease', 'Sarcoidosis']
- human_at1=False fail_mode=tree_miss

