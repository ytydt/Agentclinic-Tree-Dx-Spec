# MCR / mcr_200b / case 469

- **gold**: mantle cell lymphoma
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=301; gold_words=3; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 63-year-old white man presented with a 3-week history of redness of the left eye and extensive bilateral lymphadenopathy. He reported blurred vision and loss of vision in the left lower quadrant, with supraorbital pain in both eyes, all worsening over 3 weeks. His lymph nodes (preauricular, submandibular, cervical, supraclavicular, and axillary) had progressively enlarged. He denied fever, chills, weight loss, rash, or joint pains, but noted several weeks of malaise.  Initial treatment for pre...

## Backbone e7
- S1 key_facts: 63-year-old white man; 3-week history of redness of the left eye; Extensive bilateral lymphadenopathy; Blurred vision and loss of vision in the left lower quadrant; Supraorbital pain in both eyes; No fever, chills, weight loss, rash, or joint pains; Several weeks of malaise; Visual acuity 20/20 in the right eye and 20/125 in the left
- S2 mode=complement k=3 pool_n=53 gold_in_s2=True
  - call1: ['Lymphoma', 'Intraocular lymphoma', 'Primary central nervous system lymphoma', 'Vogt-Koyanagi-Harada disease', 'Sarcoid
  - call2: ['Kimura disease', 'Angioimmunoblastic T-cell lymphoma', 'Natural killer/T-cell lymphoma', 'Extranodal marginal zone lym
  - call3: ['Whipple disease', 'Relapsing polychondritis', 'Giant cell arteritis', 'Polyarteritis nodosa', 'Wegener granulomatosis'
- S3 shortlist n=5 gold=True: Intraocular lymphoma, Vogt-Koyanagi-Harada disease, Primary central nervous system lymphoma, Sarcoidosis, Lymphoma
- S4 champion: **Intraocular lymphoma** gold=False
- S4 raw (trunc): {"champion": "Intraocular lymphoma", "rationale": "The patient's presentation with panuveitis, extensive bilateral lymphadenopathy, and a gelatinous layered hypopyon with red-blood-cell layering in both eyes, along with the absence of systemic symptoms such as fever, chills, and 

## Backbone v0 (compact)
- S1 key_facts: 63-year-old white man; 3-week history of redness of the left eye; Extensive bilateral lymphadenopathy; Blurred vision and loss of vision in the left lower quadrant; Supraorbital pain in both eyes; No fever, chills, weight loss, rash, or joint pains; Several weeks of malaise; Initial treatment with erythromycin ointment, topical prednisolone, tobramycin/d
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Lymphoma', 'Leukemia', 'Sarcoidosis', 'Tuberculosis', 'Syphilis', 'Toxoplasmosis', 'Cytomegalovirus retinitis', 'Herpe
- S3 shortlist n=5 gold=True: Lymphoma, Intraocular lymphoma, Vogt-Koyanagi-Harada disease, Sarcoidosis, Sympathetic ophthalmia
- S4 champion: **Intraocular lymphoma** gold=False
- S4 raw (trunc): {"champion": "Intraocular lymphoma", "rationale": "The patient's presentation with panuveitis, extensive bilateral lymphadenopathy, and a gelatinous layered hypopyon with red-blood-cell layering in both eyes, along with the presence of acellular, dense, proteinaceous material on 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of bilateral lymphadenopathy, panuveitis, and a hemorrhagic hypopyon is highly suggestive of an underlying malignancy or systemic dis
  - turn1 gold_mention=True diag=
    The patient's presentation of bilateral lymphadenopathy, panuveitis, and a hemorrhagic hypopyon, along with the lack of response to initial treatment, supports 
  - turn2 gold_mention=True diag=
    The patient's presentation of bilateral lymphadenopathy, panuveitis, and a hemorrhagic hypopyon, along with the lack of response to initial treatment and the pr
- supervisor votes=3 top2=['Intraocular lymphoma', 'Lymphoma'] gold=True

## Baseline B07
- draft=['Lymphoma', 'Vogt-Koyanagi-Harada disease'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['panuveitis causes', 'lymphadenopathy and uveitis', 'hemorrhagic hypopyon differential diagnosis']
- diagnose=['Lymphoma', 'Vogt-Koyanagi-Harada disease'] gold=True

## Baseline B01
- queries=['panuveitis with lymphadenopathy', 'hemorrhagic hypopyon causes', 'anterior chamber paracentesis acellular proteinaceous material', 'vitreous haze and optic-nerve pallor differential diagnosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Lymphoma', 'Tuberculosis'] gold=True

