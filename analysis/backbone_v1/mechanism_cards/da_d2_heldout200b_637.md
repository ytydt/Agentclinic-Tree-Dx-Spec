# DA / d2_heldout200b / case 637

- **gold**: Chronic Spontaneous Urticaria (CSU)
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 35-year-old woman with a medical history of Hashimoto disease, mild persistent asthma, allergic rhinitis, and Ehlers-Danlos syndrome. Approximately 7 hours after receiving her first dose of vaccination, she developed generalized pruritus and urticaria. The patient had no history of urticaria, angioedema, or COVID-19 infection. Her symptoms were not associated with recent viral illness, new medications, nonsteroidal anti-inflammatory drugs, opioids, alcohol, food, or physical stimuli including pressure or temperature changes.

The patient presented with:- Generalized urticaria- Angioedema of lower lip without airway compromise- Urticarial lesions visible on right knee and popliteal fossa

Laboratory evaluation results:- Complete blood count with differential: normal- Erythrocyte sedimentation rate: normal- C-reactive protein: normal- Complement component 4: normal- Thyroid-stimulating hormone: normalImages:- Image 1 Title: Right knee urticaria- Image 2 Title: Popliteal fossa urticaria

What is the most likely diagnosis?

Options:
A. Acute urticaria (idiopathic)
B. Chronic Spontaneous Urticaria (CSU)
C. Acute spontaneous urticaria
D. Autoimmune urticaria


## Options
- A: Acute urticaria (idiopathic)
- B: Chronic Spontaneous Urticaria (CSU) **←gold**
- C: Acute spontaneous urticaria
- D: Autoimmune urticaria

## Backbone e7

- S2 n=50 gold_rank=None
  - clusters: gold=0 near=9 other=41
- S3 shortlist (5):
  - [other] Anaphylaxis
  - [other] Vaccine-induced anaphylaxis
  - [near] Autoimmune urticaria
  - [other] Angioedema due to C1 esterase inhibitor deficiency
  - [other] Ehlers-Danlos syndrome-associated angioedema
    - why_kept(Anaphylaxis): Acute onset of generalized skin reaction with urticaria and angioedema following vaccination
    - why_kept(Vaccine-induced anaphylaxis): Symptoms developed approximately 7 hours after vaccination
    - why_kept(Autoimmune urticaria): Medical history of Hashimoto disease and presence of urticaria
    - why_kept(Angioedema due to C1 esterase inhibitor deficiency): Angioedema of lower lip without airway compromise
    - why_kept(Ehlers-Danlos syndrome-associated angioedema): Medical history of Ehlers-Danlos syndrome and presence of angioedema
- S4 champion: **Vaccine-induced anaphylaxis** cluster=other jaccard=0.00
- S4 rationale: The patient developed generalized pruritus and urticaria approximately 7 hours after receiving her first dose of vaccination, which is a typical timeline for an allergic reaction to a vaccine.
- S4 rejected:
  - [other] Anaphylaxis: Too broad, as it doesn't specify the cause of the anaphylaxis
  - [near] Autoimmune urticaria: The patient's symptoms are more likely related to the vaccine than an autoimmune cause
  - [other] Angioedema due to C1 esterase inhibitor deficiency: The patient's complement component 4 level is normal, which makes this diagnosis less likely
  - [other] Ehlers-Danlos syndrome-associated angioedema: While the patient has Ehlers-Danlos syndrome, the timing of the symptoms in relation to the vaccination suggests a vaccine-induced reaction rather than a syndrome-associated one

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Allergic reaction to vaccination', 'Urticaria']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Allergic reaction to vaccination', 'Urticaria', 'Angioedema', 'Anaphylaxis', 'Mastocytosis', 'Allergic reaction to vaccination', 'Urticaria', 'Angioedema']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Allergic reaction to vaccine (urticaria and angioedema)', 'Anaphylaxis']
- diagnose: ['Allergic reaction to vaccine (urticaria and angioedema)', 'Anaphylaxis']
- queries: ['urticaria after vaccination', 'allergic reactions to vaccines', 'anaphylaxis vs urticaria']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

