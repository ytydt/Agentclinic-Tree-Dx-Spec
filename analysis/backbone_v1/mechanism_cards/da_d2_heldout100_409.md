# DA / d2_heldout100 / case 409

- **gold**: Bilateral syphilitic panuveitis with neurosyphilis
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexual partners with inconsistent protection were reported. Review of systems was positive for a pruritic back rash of crusting erythematous plaques.

Presenting uncorrected visual acuity was hand motions in both eyes. Intraocular pressures were 14 and 9 mm Hg in the right and left eye, respectively. Right eye showed corneal stromal haze, 3+ anterior chamber cell (26-50 cells/1 × 1 mm slitlamp field), posterior synechiae, vitreous cell and haze obscuring retinal vascular details, blurred disc margins, and superonasal peripheral retinal whitening. Left eye showed corneal haze, 1-mm hypopyon, posterior synechiae, vitreous cell and haze obscuring retinal vascular details, blurred disc margins, and superotemporal peripheral retinal whitening.

- Laboratory Tests:
  * CD4 count: 24 cells/mm3
  * HIV RNA level: 175,000 copies/mL
  * Aqueous fluid from both eyes negative for herpetic viral DNA by PCR
  * Blood cultures: grew polymicrobial bacteria of uncertain significance
  * Vitreous cultures: …

## Options
- A: Bilateral syphilitic panuveitis with neurosyphilis **←gold**
- B: Syphilitic uveitis
- C: Cytomegalovirus (CMV) retinitis
- D: Ocular syphilis with neurosyphilis

## Backbone e7

- S2 n=52 gold_rank=31
  - clusters: gold=1 near=3 other=48
- S3 shortlist (5):
  - [near] Syphilitic retinitis
  - [other] Cytomegalovirus retinitis
  - [other] Toxoplasmic retinochoroiditis
  - [other] Progressive outer retinal necrosis
  - [near] Syphilitic uveitis
    - why_kept(Syphilitic retinitis): Positive cerebrospinal fluid T pallidum particle agglutination assay and rapid plasma reagin testing shows a 1:64 titer
    - why_kept(Cytomegalovirus retinitis): Patient has HIV and is not receiving antiretroviral therapy, with a low CD4 count and high HIV RNA level
    - why_kept(Toxoplasmic retinochoroiditis): Patient has HIV and is not receiving antiretroviral therapy, with a low CD4 count and high HIV RNA level
    - why_kept(Progressive outer retinal necrosis): Patient has HIV and is not receiving antiretroviral therapy, with a low CD4 count and high HIV RNA level, and presents with bilateral photophobia and decreased vision
    - why_kept(Syphilitic uveitis): Positive cerebrospinal fluid T pallidum particle agglutination assay and rapid plasma reagin testing shows a 1:64 titer, and patient presents with uveitis
- S4 champion: **Syphilitic retinitis** cluster=near jaccard=0.17
- S4 rationale: The patient's positive cerebrospinal fluid T pallidum particle agglutination assay and rapid plasma reagin testing with a 1:64 titer, along with the clinical presentation of bilateral photophobia and decreased vision, support the diagnosis of syphilitic retinitis, especially given the patient's history of multiple sexual partners with inconsistent protection.
- S4 rejected:
  - [other] Cytomegalovirus retinitis: Although the patient has a low CD4 count, the absence of herpetic viral DNA by PCR in the aqueous fluid and the specific serological evidence of syphilis point away from CMV retinitis.
  - [other] Toxoplasmic retinochoroiditis: There is no specific evidence provided in the vignette that would point towards toxoplasmosis, such as characteristic retinochoroidal scars or a positive toxoplasma serology.
  - [other] Progressive outer retinal necrosis: While the patient has HIV and a low CD4 count, which could predispose to progressive outer retinal necrosis, the clinical and laboratory findings more strongly support syphilitic retinitis.
  - [near] Syphilitic uveitis: Although the patient has syphilis, the specific involvement of the retina as indicated by the clinical findings and imaging studies makes syphilitic retinitis a more precise diagnosis than syphilitic uveitis alone.

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Syphilitic uveitis', 'Toxoplasmic retinochoroiditis']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Syphilitic uveitis', 'HIV retinopathy', 'Toxoplasmic retinochoroiditis', 'Cytomegalovirus retinitis', 'Acute retinal necrosis', 'Syphilitic uveitis', 'Toxoplasmic retinochoroiditis', 'Cytomegalovirus retinitis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Ocular Syphilis', 'HIV-related Retinitis']
- diagnose: ['Ocular Syphilis', 'HIV-related Retinitis']
- queries: ['A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexu', 'differential diagnosis A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexu', 'clinical manifestations diagnosis nd superonasal peripheral retinal whitening. Left eye showed corneal haze, 1-mm hypopyon, posterior synechiae, vitreous cell and haze obscuring retinal vascular']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=27 final_n=1
- final: ['Syphilitic Uveitis']
- tree gold_cluster_n=0 final gold=False

