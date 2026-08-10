# DA / d2_heldout100 / case 306

- **gold**: Candida tropicalis meningoencephalitis
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A 66-year-old woman with hypertension presented with 2 months of progressive right earache and headache without fever, 2 weeks of mild left-sided weakness, and 1 week of intermittent hallucinations and nonsensical speech. The patient was later found to have type 2 diabetes.

The patient had a left pronator drift with the remainder of examination results being unremarkable. There was no obvious manifestation of external ear canal infection during endoscopy of the right ear.

{'Laboratory Tests': ['- Erythrocyte sedimentation rate: 42 mm/h (normal, <20 mm/h)', '- C-reactive protein level: 25 mg/L (normal, <10 mg/L)', '- Glycosylated hemoglobin A1C level: 6.8% (normal, 4.3%-6.1%)', '- Serological tests unremarkable for IgG4, HIV, syphilis, tuberculosis, Toxoplasma gondii, rubella virus, cytomegalovirus, and herpes simplex virus', '- CSF examination revealed no suggestive abnormalities', '- Autoimmune antibody testing: positive for anti-NMDAR antibodies (CSF titer 1:320, serum titer 1:100), CSF anti-AMPAR1 antibody positive at 1:1', '- CSF next-generation sequencing: positive for Candida tropicalis'], 'Imaging Studies': ['- CT scan of temporal bone showed otitis media, mastoiditis, and…

## Options
- A: Candida tropicalis meningitis
- B: Candida tropicalis meningoencephalitis **←gold**
- C: Skull base osteomyelitis (fungal)
- D: Fungal meningoencephalitis (Candida tropicalis)

## Backbone e7

- S2 n=54 gold_rank=None
  - clusters: gold=0 near=1 other=53
- S3 shortlist (5):
  - [other] NMDAR antibody encephalitis
  - [other] AMPAR antibody encephalitis
  - [near] Candida meningitis
  - [other] Mastoiditis with intracranial extension
  - [other] Autoimmune encephalitis
    - why_kept(NMDAR antibody encephalitis): Positive for anti-NMDAR antibodies
    - why_kept(AMPAR antibody encephalitis): Positive for CSF anti-AMPAR1 antibody
    - why_kept(Candida meningitis): CSF next-generation sequencing positive for Candida tropicalis
    - why_kept(Mastoiditis with intracranial extension): CT scan of temporal bone showed otitis media, mastoiditis, and local bone destruction in the right ear
    - why_kept(Autoimmune encephalitis): Elevated erythrocyte sedimentation rate and C-reactive protein level, and positive autoimmune antibody testing
- S4 champion: **NMDAR antibody encephalitis** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms of hallucinations, nonsensical speech, and positive test for anti-NMDAR antibodies in both CSF and serum are highly suggestive of NMDAR antibody encephalitis, which is known to cause psychiatric and neurological symptoms.
- S4 rejected:
  - [other] AMPAR antibody encephalitis: Although the patient is positive for CSF anti-AMPAR1 antibody, the clinical presentation and high titers of anti-NMDAR antibodies are more indicative of NMDAR antibody encephalitis
  - [near] Candida meningitis: The presence of Candida tropicalis in CSF next-generation sequencing does not directly correlate with the patient's symptoms, and other findings are more suggestive of an autoimmune encephalitis
  - [other] Mastoiditis with intracranial extension: While the patient has mastoiditis, the neurological symptoms and presence of anti-NMDAR antibodies suggest a more complex condition like NMDAR antibody encephalitis
  - [other] Autoimmune encephalitis: This is a broad category that includes NMDAR antibody encephalitis; the specific diagnosis of NMDAR antibody encephalitis is more precise given the patient's test results and symptoms

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Anti-NMDAR encephalitis', 'Candida meningitis']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Candida meningitis', 'Otitis media and mastoiditis', 'Anti-NMDAR encephalitis', 'Autoimmune encephalitis', 'Chronic meningitis', 'Anti-NMDAR encephalitis', 'Candida meningitis', 'Otitis media and mastoiditis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Chronic otitis media with secondary CNS involvement (fungal meningitis or brain abscess)', 'Autoimmune encephalitis (anti-NMDAR or anti-AMPAR antibody-associated)']
- diagnose: ['Chronic otitis media with secondary CNS involvement (fungal meningitis or brain abscess)', 'Autoimmune encephalitis (anti-NMDAR or anti-AMPAR antibody-associated)']
- queries: ['A 66-year-old woman with hypertension presented with 2 months of progressive right earache and headache without fever, 2 weeks of mild left-sided weakness, and 1 week of intermittent hallucinations an', 'differential diagnosis A 66-year-old woman with hypertension presented with 2 months of progressive right earache and headache without fever, 2 weeks of mild left-sided weakness, and 1 week of intermittent hallucinations an', "clinical manifestations diagnosis ein level: 25 mg/L (normal, <10 mg/L)', '- Glycosylated hemoglobin A1C level: 6.8% (normal, 4.3%-6.1%)', '- Serological tests unremarkable for IgG4, HIV, syphil"]

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=35 final_n=2
- final: ['Anti-NMDAR Encephalitis', 'Inflammatory Pseudotumor']
- tree gold_cluster_n=2 final gold=False

