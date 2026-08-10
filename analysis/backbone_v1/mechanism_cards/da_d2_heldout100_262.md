# DA / d2_heldout100 / case 262

- **gold**: IBD-associated neutrophilic dermatosis with ulcerative colitis
- **layer**: `e7_win_recall` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `option_echo_da`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A 55-year-old white woman with a history of diverticulosis and colonic polyps presented with new-onset flulike symptoms followed by low-grade fever, facial crusted plaques, and 4 weeks of bloody and watery diarrhea. Her facial lesions initially presented as ill-defined pink patches over her cheeks and red papules on her forehead. Over the next 4 days, the lesions spread to her chest, abdomen, back, and left buttock, and a single papule appeared on the right lower extremity. Her low-grade fevers and diarrhea persisted throughout this 4-day period.

In the emergency department, she was febrile and tachycardic. Physical findings included:- 6 × 7-cm well-demarcated vegetative crusted plaques on the bilateral cheeks- Several discrete, round, 1- to 2-cm crusted plaques on the temple- Discrete pustules, vesicles, and umbilicated papules on cheeks and temple- Lesions on chest, abdomen, back, and left buttock- Painful subcutaneous nodules over lower extremities- Polyarthralgia

Laboratory Tests:- Mild leukocytosis with normal differential- Mildly elevated transaminase and alkaline phosphatase levels- Negative wound culture- Blood cultures showed no growth- Negative PCR for herpes simplex vi…

## Options
- A: Ulcerative colitis **←gold**
- B: Sweet’s syndrome (acute febrile neutrophilic dermatosis)
- C: Crohn disease
- D: IBD-associated neutrophilic dermatosis with ulcerative colitis **←gold**

## Backbone e7

- S2 n=51 gold_rank=13
  - clusters: gold=1 near=5 other=45
- S3 shortlist (5):
  - [other] Sweet syndrome
  - [other] Pyoderma gangrenosum
  - [gold] Neutrophilic dermatosis
  - [other] Inflammatory bowel disease
  - [near] Bowel-associated dermatosis-arthritis syndrome
    - why_kept(Sweet syndrome): Acute onset of fever, diarrhea, and skin lesions with intradermal neutrophilic inflammation on biopsy
    - why_kept(Pyoderma gangrenosum): Presence of painful subcutaneous nodules and ulcerative skin lesions
    - why_kept(Neutrophilic dermatosis): Histopathological findings of intradermal neutrophilic inflammation with ulceration
    - why_kept(Inflammatory bowel disease): History of diverticulosis and colonic polyps, and moderate inflammation on colonoscopy
    - why_kept(Bowel-associated dermatosis-arthritis syndrome): Combination of gastrointestinal symptoms and skin lesions
- S4 champion: **Sweet syndrome** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of new-onset flulike symptoms, low-grade fever, facial crusted plaques, and bloody and watery diarrhea, along with laboratory findings of mild leukocytosis and intradermal neutrophilic inflammation with ulceration on biopsy, are consistent with Sweet syndrome, a condition characterized by neutrophilic dermatosis and often associated with underlying inflammatory bowel disease or other systemic conditions.
- S4 rejected:
  - [other] Pyoderma gangrenosum: While pyoderma gangrenosum can present with similar skin lesions, the patient's biopsy findings and lack of typical ulcerative lesions are not as consistent with this diagnosis.
  - [gold] Neutrophilic dermatosis: This is a broader term that encompasses Sweet syndrome, but Sweet syndrome is a more specific diagnosis that better explains the patient's presentation.
  - [other] Inflammatory bowel disease: While the patient has a history of diverticulosis and colonic polyps, and colonoscopy showed moderate inflammation, the primary presentation is dermatologic, making Sweet syndrome a more direct explanation for the current symptoms.
  - [near] Bowel-associated dermatosis-arthritis syndrome: This condition is less well-defined and does not specifically account for the patient's dermatologic findings as well as Sweet syndrome does.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Sweet syndrome', 'Inflammatory bowel disease']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Sweet syndrome', 'Pyoderma gangrenosum', 'Inflammatory bowel disease', 'Erythema nodosum', 'Neutrophilic dermatosis', 'Sweet syndrome', 'Pyoderma gangrenosum', 'Inflammatory bowel disease']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Sweet Syndrome', 'Inflammatory Bowel Disease (IBD)']
- diagnose: ['Sweet Syndrome', 'Inflammatory Bowel Disease (IBD)']
- queries: ['neutrophilic dermatosis', 'diverticulosis and colonic polyps and skin lesions', 'septal panniculitis with Miescher radial granulomas']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=26 final_n=3
- final: ['Sweet syndrome', 'Neutrophilic dermatosis', 'Pyoderma Gangrenosum']
- tree gold_cluster_n=2 final gold=True

