# DA / d2_heldout200b / case 488

- **gold**: Myelodysplastic syndrome (MDS) with refractory anaemia with excess blasts-1 presenting with leukaemic vasculitis
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 75-year-old black woman with insulin-dependent diabetes and obesity presented with a 10-day history of pruritic lesions on her arms and legs, 2–3 months of night sweats, and 3 weeks of right-sided headache, sinus pain, and congestion. The skin lesions had developed while she was taking prednisone. She had no associated fever, abdominal pain, diarrhoea, myalgia, or arthralgia.

Patient looked well. On the extensor elbows extending down her forearms bilaterally and on her knees and shins were dozens of 1–2 cm oedematous pink-red papules with a darker red-violet central zone, resembling atypical papular target lesions. Along Wallace's lines on the medial aspect of her feet and the tips of her fingers and toes were about 20 red macules, 5–15 mm in diameter. She had one 2 mm erosion on the soft palate of her mouth; her face was otherwise spared.

Laboratory Tests:
- White blood cell count 2.7 × 10⁹/L (43% neutrophils, 37% lymphocytes, 8% monocytes, 1% eosinophils, 1% atypical lymphocytes, 10% bands)
- Haemoglobin: 100 g/L
- Platelet count: 129 × 10⁹/L
- Absolute neutrophil count 1.4 × 10⁹/L
- Normal liver function tests
- Urinalysis: 2+ protein, no blood
- Negative PCR for herpes simp…

## Options
- A: Myelodysplastic syndrome (MDS) with refractory anaemia with excess blasts-1 presenting with leukaemic vasculitis **←gold**
- B: High-risk myelodysplastic syndrome (MDS) with cutaneous involvement
- C: Myelodysplastic syndrome (MDS) with leukemia cutis
- D: Erythema multiforme or paraneoplastic vasculitis-like process

## Backbone e7

- S2 n=56 gold_rank=None
  - clusters: gold=0 near=13 other=43
- S3 shortlist (5):
  - [near] Leukocytoclastic vasculitis
  - [other] Erythema multiforme
  - [near] Sweet syndrome
  - [near] IgA vasculitis
  - [near] Cutaneous small-vessel vasculitis
    - why_kept(Leukocytoclastic vasculitis): pruritic skin lesions with vascular damage and leucocytoclasia
    - why_kept(Erythema multiforme): atypical papular target lesions and mucosal involvement
    - why_kept(Sweet syndrome): fever, night sweats, and pruritic skin lesions with neutrophilic infiltrate
    - why_kept(IgA vasculitis): elevated IgA levels and skin lesions with vascular damage
    - why_kept(Cutaneous small-vessel vasculitis): pruritic skin lesions with vascular damage and small-vessel involvement
- S4 champion: **Sweet syndrome** cluster=near jaccard=0.08
- S4 rationale: The patient's presentation of pruritic lesions, night sweats, and headache, along with the skin biopsy findings of atypical mononuclear cells and vascular damage, are consistent with Sweet syndrome. The elevated IgA levels and the presence of myeloperoxidase-positive cells also support this diagnosis.
- S4 rejected:
  - [near] Leukocytoclastic vasculitis: While the patient has vasculitis, the clinical presentation and laboratory findings are more consistent with Sweet syndrome.
  - [other] Erythema multiforme: The patient's lesions do not have the typical targetoid appearance of erythema multiforme, and the presence of atypical mononuclear cells is not typical of this condition.
  - [near] IgA vasculitis: The patient's age and clinical presentation are not typical of IgA vasculitis, which is more commonly seen in children.
  - [near] Cutaneous small-vessel vasculitis: While the patient has small-vessel vasculitis, the clinical presentation and laboratory findings are more consistent with Sweet syndrome.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Myelodysplastic syndrome', 'Sweet syndrome']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Sweet syndrome', 'Leukemia cutis', 'Vasculitis', 'Myelodysplastic syndrome', 'Erythema multiforme', 'Myelodysplastic syndrome', 'Leukemia cutis', 'Sweet syndrome']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Myelodysplastic Syndrome (MDS) with cutaneous involvement', 'Acute Myeloid Leukemia (AML) with cutaneous involvement']
- diagnose: ['Myelodysplastic Syndrome (MDS) with cutaneous involvement', 'Acute Myeloid Leukemia (AML) with cutaneous involvement']
- queries: ['myeloperoxidase positive skin lesions', 'elevated IgA and skin lesions', 'atypical mononuclear cells and vascular damage', 'myeloblasts in bone marrow and skin lesions']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

