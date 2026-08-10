# DA / d2_heldout100 / case 262

- **gold**: IBD-associated neutrophilic dermatosis with ulcerative colitis
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`na` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=s3_hit_s4_miss; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=303; gold_words=7; eponym=False; subtype=True; e7_s2_rank=13; mapper_rescue=True
- **causal**: DA mapper_rescue: e7 S4 未命中金标但 option@1 仍对——不可记入口/终裁优势。

## Vignette (trunc)
A 55-year-old white woman with a history of diverticulosis and colonic polyps presented with new-onset flulike symptoms followed by low-grade fever, facial crusted plaques, and 4 weeks of bloody and watery diarrhea. Her facial lesions initially presented as ill-defined pink patches over her cheeks and red papules on her forehead. Over the next 4 days, the lesions spread to her chest, abdomen, back, and left buttock, and a single papule appeared on the right lower extremity. Her low-grade fevers ...

## Options
  - A: Ulcerative colitis
  - B: Sweet’s syndrome (acute febrile neutrophilic dermatosis)
  - C: Crohn disease
  - D: IBD-associated neutrophilic dermatosis with ulcerative colitis

## Backbone e7
- S1 key_facts: 55-year-old woman; History of diverticulosis and colonic polyps; Low-grade fever; Facial lesions initially presented as ill-defined pink patches; Lesions spread to chest, abdomen, back, and left buttock; Mild leukocytosis with normal differential; Mildly elevated transaminase and alkaline phosphatase levels; Negative wound culture
- S2 mode=complement k=3 pool_n=51 gold_in_s2=True
  - call1: ['Sweet syndrome', 'Pyoderma gangrenosum', 'Erythema multiforme', 'Stevens-Johnson syndrome', 'Toxic epidermal necrolysi
  - call2: ['Granulomatosis with polyangiitis', 'Microscopic polyangiitis', 'Eosinophilic granulomatosis with polyangiitis', 'IgA v
  - call3: ['Granulomatous rosacea', 'Perioral dermatitis', 'SAPHO syndrome', 'Pustular psoriasis', 'Acute febrile neutrophilic der
- S3 shortlist n=5 gold=True: Sweet syndrome, Pyoderma gangrenosum, Neutrophilic dermatosis, Inflammatory bowel disease, Bowel-associated dermatosis-arthritis syndrome
- S4 champion: **Sweet syndrome** gold=False
- S4 raw (trunc): {"champion": "Sweet syndrome", "rationale": "The patient's presentation of new-onset flulike symptoms, low-grade fever, facial crusted plaques, and bloody and watery diarrhea, along with laboratory findings of mild leukocytosis and intradermal neutrophilic inflammation with ulcer

## Backbone v0 (compact)
- S1 key_facts: 55-year-old woman; History of diverticulosis and colonic polyps; Low-grade fever; Facial lesions initially presented as ill-defined pink patches; Lesions spread to chest, abdomen, back, and left buttock; Mild leukocytosis with normal differential; Mildly elevated transaminase and alkaline phosphatase levels; Negative wound culture
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Sweet syndrome', 'Pyoderma gangrenosum', 'Erythema multiforme', 'Stevens-Johnson syndrome', 'Toxic epidermal necrolysi
- S3 shortlist n=5 gold=True: Sweet syndrome, Pyoderma gangrenosum, Inflammatory bowel disease, Neutrophilic dermatosis, Behçet's disease
- S4 champion: **Sweet syndrome** gold=False
- S4 raw (trunc): {"champion": "Sweet syndrome", "rationale": "The patient's presentation of new-onset flulike symptoms, low-grade fever, and facial crusted plaques, along with the biopsy findings of intradermal neutrophilic inflammation and the presence of systemic symptoms such as polyarthralgia

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of new-onset flulike symptoms, low-grade fever, facial crusted plaques, and bloody and watery diarrhea, along with the histopathologi
  - turn1 gold_mention=True diag=
    The patient's symptoms and histopathological findings are consistent with Sweet syndrome, which is often associated with inflammatory bowel disease, and the pre
  - turn2 gold_mention=True diag=
    The patient's presentation of new-onset flulike symptoms, low-grade fever, facial crusted plaques, and bloody and watery diarrhea, along with the histopathologi
- supervisor votes=3 top2=['Sweet syndrome', 'Inflammatory bowel disease'] gold=False

## Baseline B07
- draft=['Sweet Syndrome', 'Inflammatory Bowel Disease (IBD)'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['neutrophilic dermatosis', 'diverticulosis and colonic polyps and skin lesions', 'septal panniculitis with Miescher radial granulomas']
- diagnose=['Sweet Syndrome', 'Inflammatory Bowel Disease (IBD)'] gold=False

## APHHM
- tree_n=26 tree_recall=True
- gold_leaf=B1.1:Ulcerative Colitis parent=B1
- final_n=3 final_recall=True ranking=['Sweet syndrome', 'Neutrophilic dermatosis', 'Pyoderma Gangrenosum']
- human_at1=False fail_mode=final_ok

