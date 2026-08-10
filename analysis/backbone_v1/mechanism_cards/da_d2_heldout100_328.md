# DA / d2_heldout100 / case 328

- **gold**: Chronic idiopathic urticaria (CIU) due to methylisothiazolinone contact sensitization
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A woman in her 50s presented with a 2.5-year history of severe urticaria. The primary symptom was chronic pruritus, which was worsening and refractory to treatment. Previous medication trials of doxepin, monteleukast, hydroxizine, famotidine, fexofenadine, and ranitidine provided only minimal benefit. She initially responded well to omalizumab but became refractory after 1 week of treatment.

Examination revealed edematous, superficial wheals and plaques on the arms, back, and thighs, along with dermatographism.

- Skin biopsies: Two 0.4-mm punch biopsies revealed dermal edema with sparse chronic inflammation and dilated blood vessels within the superficial dermis, consistent with dermal hypersensitivity.    - Allergy testing:    - Skin-prick allergy testing was negative    - Food elimination diet results were negative    - Skin patch testing showed positive results for methylisothiazolinones

What is the most likely diagnosis?

Options:
A. Chronic Inducible Urticaria (Dermatographism)
B. Chronic idiopathic urticaria (CIU) due to methylisothiazolinone contact sensitization
C. Contact Urticaria (Methylisothiazolinones)
D. Chronic Spontaneous Urticaria


## Options
- A: Chronic Inducible Urticaria (Dermatographism)
- B: Chronic idiopathic urticaria (CIU) due to methylisothiazolinone contact sensitization **←gold**
- C: Contact Urticaria (Methylisothiazolinones)
- D: Chronic Spontaneous Urticaria

## Backbone e7

- S2 n=48 gold_rank=None
  - clusters: gold=0 near=14 other=34
- S3 shortlist (5):
  - [near] Chronic autoimmune urticaria
  - [near] Dermatographic urticaria
  - [near] Allergic contact dermatitis
  - [other] Mastocytosis
  - [other] Urticarial vasculitis
    - why_kept(Chronic autoimmune urticaria): 2.5-year history of severe urticaria and refractory to treatment
    - why_kept(Dermatographic urticaria): Dermatographism present and skin biopsies showed dermal edema with sparse chronic inflammation
    - why_kept(Allergic contact dermatitis): Positive skin patch testing results for methylisothiazolinones
    - why_kept(Mastocytosis): Edematous, superficial wheals and plaques on the arms, back, and thighs, and initial response to omalizumab
    - why_kept(Urticarial vasculitis): Chronic pruritus and refractory to treatment, with skin biopsies showing dermal edema and sparse chronic inflammation
- S4 champion: **Chronic autoimmune urticaria** cluster=near jaccard=0.22
- S4 rationale: The patient's long history of severe urticaria, chronic pruritus, and initial response to omalizumab (which is often used to treat autoimmune urticaria) support this diagnosis. The lack of response to antihistamines and other treatments also points towards an autoimmune cause.
- S4 rejected:
  - [near] Dermatographic urticaria: While dermatographism is present, it does not fully explain the patient's chronic and severe urticaria.
  - [near] Allergic contact dermatitis: The positive skin patch testing for methylisothiazolinones could suggest contact dermatitis, but the patient's widespread and chronic urticaria is not typical for this condition.
  - [other] Mastocytosis: There is no mention of mast cell degranulation symptoms or elevated tryptase levels, making this diagnosis less likely.
  - [other] Urticarial vasculitis: The skin biopsies did not show vasculitis, which is a hallmark of this condition.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Chronic Urticaria', 'Contact Dermatitis']
  clusters: {'gold': 0, 'near': 2, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Chronic Urticaria', 'Dermal Hypersensitivity Reaction', 'Contact Dermatitis', 'Autoimmune Urticaria', 'Mastocytosis', 'Chronic Urticaria', 'Contact Dermatitis', 'Autoimmune Urticaria']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Chronic Autoimmune Urticaria', 'Contact Dermatitis due to Methylisothiazolinones Sensitivity']
- diagnose: ['Chronic Autoimmune Urticaria', 'Contact Dermatitis due to Methylisothiazolinones Sensitivity']
- queries: ['chronic urticaria causes', 'dermal hypersensitivity diagnosis', 'methylisothiazolinones allergy']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=44 final_n=2
- final: ['Dermatographic Urticaria', 'Chronic Idiopathic Urticaria']
- tree gold_cluster_n=3 final gold=True

