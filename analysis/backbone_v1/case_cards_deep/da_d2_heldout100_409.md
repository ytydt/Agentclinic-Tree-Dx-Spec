# DA / d2_heldout100 / case 409

- **gold**: Bilateral syphilitic panuveitis with neurosyphilis
- **layer**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=317; gold_words=5; eponym=False; subtype=True; e7_s2_rank=31; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexual partners with inconsistent protection were reported. Review of systems was positive for a pruritic back rash of crusting erythematous plaques.  Presenting uncorrected visual acuity was hand motions in both eyes. Intraocular pressures were 14 and 9 mm Hg in the right and left eye, respectively. Ri...

## Options
  - A: Bilateral syphilitic panuveitis with neurosyphilis
  - B: Syphilitic uveitis
  - C: Cytomegalovirus (CMV) retinitis
  - D: Ocular syphilis with neurosyphilis

## Backbone e7
- S1 key_facts: Patient has HIV and is not receiving antiretroviral therapy; CD4 count is 24 cells/mm3; HIV RNA level is 175,000 copies/mL; Patient has multiple sexual partners with inconsistent protection; Patient presents with bilateral photophobia and decreased vision; Uncorrected visual acuity is hand motions in both eyes; Intraocular pressures are 14 and 9 mm Hg in the right and left eye, respectively; Aqueous fluid from both eyes is negative for herpetic viral DNA by PCR
- S2 mode=complement k=3 pool_n=52 gold_in_s2=True
  - call1: ['Cytomegalovirus retinitis', 'Toxoplasmic retinochoroiditis', 'Syphilitic retinitis', 'Herpes simplex virus retinitis',
  - call2: ['Pneumocystis jirovecii pneumonia with extrapulmonary involvement', 'Mycobacterium avium complex infection', "Kaposi's 
  - call3: ["Whipple's disease", 'Cat-scratch disease', 'Bartonella henselae neuroretinitis', 'Ehrlichiosis', 'Anaplasmosis', 'Babe
- S3 shortlist n=5 gold=False: Syphilitic retinitis, Cytomegalovirus retinitis, Toxoplasmic retinochoroiditis, Progressive outer retinal necrosis, Syphilitic uveitis
- S4 champion: **Syphilitic retinitis** gold=False
- S4 raw (trunc): {"champion": "Syphilitic retinitis", "rationale": "The patient's positive cerebrospinal fluid T pallidum particle agglutination assay and rapid plasma reagin testing with a 1:64 titer, along with the clinical presentation of bilateral photophobia and decreased vision, support the

## Backbone v0 (compact)
- S1 key_facts: Patient has HIV and is not receiving antiretroviral therapy; CD4 count is 24 cells/mm3; HIV RNA level is 175,000 copies/mL; Patient has multiple sexual partners with inconsistent protection; Patient presents with bilateral photophobia and decreased vision; Uncorrected visual acuity is hand motions in both eyes; Intraocular pressures are 14 and 9 mm Hg in the right and left eye, respectively; Aqueous fluid from both eyes is negative for herpetic viral DNA by PCR
- S2 mode=single k=1 pool_n=15 gold_in_s2=False
  - call1: ['Cytomegalovirus retinitis', 'Toxoplasmosis', 'Syphilitic uveitis', 'Herpes simplex virus retinitis', 'Varicella-zoster
- S3 shortlist n=5 gold=False: Syphilitic uveitis, Cytomegalovirus retinitis, Toxoplasmosis, Syphilitic retinitis, Acute retinal necrosis
- S4 champion: **Syphilitic uveitis** gold=False
- S4 raw (trunc): {"champion": "Syphilitic uveitis", "rationale": "The patient's positive rapid plasma reagin testing (1:64 titer) and positive cerebrospinal fluid T pallidum particle agglutination assay, along with the presence of a pruritic back rash and bilateral ocular symptoms, support the di

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's symptoms, laboratory results, and imaging studies suggest an infectious etiology, with syphilitic uveitis being the most likely diagnosis given th
  - turn1 gold_mention=False diag=
    The patient's low CD4 count, high HIV RNA level, and presence of spirochetes in skin lesion histopathology, along with positive cerebrospinal fluid T pallidum p
  - turn2 gold_mention=False diag=
    The patient's clinical presentation, laboratory results, and imaging studies are consistent with the opinions of Doctor A and Doctor B, supporting syphilitic uv
- supervisor votes=3 top2=['Syphilitic uveitis', 'Toxoplasmic retinochoroiditis'] gold=False

## Baseline B07
- draft=['Ocular Syphilis', 'HIV-related Retinitis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexu', 'differential diagnosis A young adult with HIV not receiving antiretroviral therapy presented with bilateral photophobia and decreased vision. CD4 count was 24 cells/mm3 and HIV RNA level was 175,000 copies/mL. Multiple sexu', 'clinical manifestations diagnosis nd superonasal peripheral retinal whitening. Left eye showed corneal haze, 1-mm hypopyon, posterior synechiae, vitreous cell and haze obscuring retinal vascular']
- diagnose=['Ocular Syphilis', 'HIV-related Retinitis'] gold=False

## APHHM
- tree_n=27 tree_recall=False
- gold_leaf=None
- final_n=1 final_recall=False ranking=['Syphilitic Uveitis']
- human_at1=False fail_mode=tree_miss

