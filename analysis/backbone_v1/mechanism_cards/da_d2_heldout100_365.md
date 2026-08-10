# DA / d2_heldout100 / case 365

- **gold**: Fibrosis and ulceration caused by meperidine
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A white man in his 30s with a 7-year history of severe, mechanical, low back pain and long-standing mental depression. Current medications include duloxetine hydrochloride, clonazepam, oxcarbazepine, fentanyl, sulpiride, zopiclone, omeprazole magnesium, and baclofen. Patient admitted to self-administering subcutaneous injections of meperidine, 100 mg 4 times per day, for the past 3 years, at different sites, including the deltoid areas and abdomen.

Large and deep, irregularly shaped, cutaneous ulcer on the dorsum of right forearm with necrotic tissue and muscle exposure at the base. Woody induration of skin on both forearms and abdominal region. Bilateral contracture of deltoid, triceps, and biceps muscles. Active and passive range of motion restricted at shoulders and elbows. No signs of joint inflammation.

- Laboratory Tests:
  - Elevated serum creatinine kinase (192 U/L; reference range, 0-174 U/L)
  - Normal complete blood cell count
  - Normal erythrocyte sedimentation rate
  - Normal antinuclear antibody
  - Normal rheumatoid factor
  - Normal aspartate aminotransferase
  - Normal alanine aminotransaminase
  - Normal aldolase levels
  - Normal serum electrophoresis
  - Nega…

## Options
- A: Fibrosis and ulceration caused by meperidine **←gold**
- B: Post-injection granuloma
- C: Factitial panniculitis
- D: Meperidine-induced panniculitis

## Backbone e7

- S2 n=53 gold_rank=None
  - clusters: gold=0 near=1 other=52
- S3 shortlist (5):
  - [other] Factitial panniculitis
  - [near] Meperidine-induced fibrosis
  - [other] Eosinophilic fasciitis
  - [other] Panniculitis
  - [other] Lipodermatosclerosis
    - why_kept(Factitial panniculitis): Patient's history of self-administering subcutaneous injections of meperidine and presence of cutaneous ulcers and lobular panniculitis
    - why_kept(Meperidine-induced fibrosis): Patient's long history of meperidine injections and presence of woody induration of skin and muscle contractures
    - why_kept(Eosinophilic fasciitis): Presence of woody induration of skin, muscle contractures, and elevated serum creatinine kinase
    - why_kept(Panniculitis): Histopathology shows lobular panniculitis and subcutaneous fat lobules with necrotic adipocytes
    - why_kept(Lipodermatosclerosis): Presence of cutaneous ulcers, woody induration of skin, and history of chronic low back pain and mental depression
- S4 champion: **Factitial panniculitis** cluster=other jaccard=0.00
- S4 rationale: The patient's history of self-administering subcutaneous injections of meperidine, the presence of cutaneous ulcers, and the histopathology showing lobular panniculitis with necrotic adipocytes and dense inflammatory infiltrates support this diagnosis
- S4 rejected:
  - [near] Meperidine-induced fibrosis: While meperidine use is a factor, the histopathology and clinical presentation are more consistent with factitial panniculitis
  - [other] Eosinophilic fasciitis: The lack of joint inflammation and the specific histopathological findings do not support this diagnosis
  - [other] Panniculitis: This is a broader category, and factitial panniculitis is a more specific diagnosis that fits the patient's presentation
  - [other] Lipodermatosclerosis: The clinical and histopathological findings do not match this condition, which is typically associated with chronic venous insufficiency

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Scleroderma-like illness due to meperidine injections', 'Chronic fibrosing panniculitis']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Scleroderma-like illness due to meperidine injections', 'Chronic fibrosing paniniculitis', 'Necrotizing fasciitis', 'Scleroderma', 'Fibrosing dermatitis', 'Scleroderma-like illness due to meperidine injections', 'Chronic fibrosing panniculitis', 'Fibrosing dermatitis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Meperidine-induced skin and muscle lesions', 'Lobular panniculitis']
- diagnose: ['Meperidine-induced skin and muscle lesions', 'Lobular panniculitis']
- queries: ['meperidine-induced skin and muscle lesions', 'lobular panniculitis causes', 'subcutaneous injections complications']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=24 final_n=4
- final: ['Necrotizing Fasciitis', 'Factitial Panniculitis', 'Pyoderma gangrenosum', 'Dermatomyositis']
- tree gold_cluster_n=0 final gold=False

