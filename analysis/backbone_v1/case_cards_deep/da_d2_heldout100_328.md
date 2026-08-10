# DA / d2_heldout100 / case 328

- **gold**: Chronic idiopathic urticaria (CIU) due to methylisothiazolinone contact sensitization
- **layer**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`final_hit_judge_miss`
- **primary_locus**: APHHM=final_hit_judge_miss
- **covariates**: vig_words=152; gold_words=9; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A woman in her 50s presented with a 2.5-year history of severe urticaria. The primary symptom was chronic pruritus, which was worsening and refractory to treatment. Previous medication trials of doxepin, monteleukast, hydroxizine, famotidine, fexofenadine, and ranitidine provided only minimal benefit. She initially responded well to omalizumab but became refractory after 1 week of treatment.  Examination revealed edematous, superficial wheals and plaques on the arms, back, and thighs, along with...

## Options
  - A: Chronic Inducible Urticaria (Dermatographism)
  - B: Chronic idiopathic urticaria (CIU) due to methylisothiazolinone contact sensitization
  - C: Contact Urticaria (Methylisothiazolinones)
  - D: Chronic Spontaneous Urticaria

## Backbone e7
- S1 key_facts: 2.5-year history of severe urticaria; Chronic pruritus as the primary symptom; Previous medication trials provided only minimal benefit; Initial response to omalizumab, but became refractory after 1 week; Edematous, superficial wheals and plaques on the arms, back, and thighs; Dermatographism present; Skin biopsies showed dermal edema with sparse chronic inflammation; Skin-prick allergy testing was negative
- S2 mode=complement k=3 pool_n=48 gold_in_s2=False
  - call1: ['Chronic autoimmune urticaria', 'Urticarial vasculitis', 'Mastocytosis', 'Mast cell activation syndrome', 'Allergic con
  - call2: ['Eosinophilic cellulitis', "Well's syndrome", "Gleich's syndrome", 'Hyperimmunoglobulinemia E syndrome', 'Nodular regen
  - call3: ['Eosinophilic granulomatosis with polyangiitis', 'Relapsing polychondritis', 'Granulomatosis with polyangiitis', 'Eosin
- S3 shortlist n=5 gold=False: Chronic autoimmune urticaria, Dermatographic urticaria, Allergic contact dermatitis, Mastocytosis, Urticarial vasculitis
- S4 champion: **Chronic autoimmune urticaria** gold=False
- S4 raw (trunc): {"champion": "Chronic autoimmune urticaria", "rationale": "The patient's long history of severe urticaria, chronic pruritus, and initial response to omalizumab (which is often used to treat autoimmune urticaria) support this diagnosis. The lack of response to antihistamines and o

## Backbone v0 (compact)
- S1 key_facts: Female patient in her 50s; 2.5-year history of severe urticaria; Chronic pruritus; Previous medication trials provided minimal benefit; Initial response to omalizumab, but became refractory after 1 week; Edematous, superficial wheals and plaques on the arms, back, and thighs; Dermatographism present; Skin biopsies showed dermal edema with sparse chronic inflammation
- S2 mode=single k=1 pool_n=19 gold_in_s2=True
  - call1: ['Chronic autoimmune urticaria', 'Chronic idiopathic urticaria', 'Urticarial vasculitis', 'Mastocytosis', 'Mast cell act
- S3 shortlist n=5 gold=True: Chronic autoimmune urticaria, Dermatographic urticaria, Allergic contact dermatitis, Chronic idiopathic urticaria, Urticarial vasculitis
- S4 champion: **Chronic autoimmune urticaria** gold=False
- S4 raw (trunc): {"champion": "Chronic autoimmune urticaria", "rationale": "The patient's severe urticaria, chronic pruritus, and initial response to omalizumab (which is often used to treat autoimmune urticaria) suggest an autoimmune component, and the lack of response to other treatments and pr

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms of severe urticaria, chronic pruritus, and dermatographism, along with the skin biopsy results and positive skin patch testing for methyl
  - turn1 gold_mention=True diag=
    The patient's refractory response to treatment and positive skin patch testing for methylisothiazolinones supports a diagnosis of contact dermatitis, while chro
  - turn2 gold_mention=True diag=
    Engaging with prior opinions, the patient's chronic pruritus, dermatographism, and positive skin patch testing for methylisothiazolinones support a multifactori
- supervisor votes=3 top2=['Chronic Urticaria', 'Contact Dermatitis'] gold=False

## Baseline B07
- draft=['Chronic Autoimmune Urticaria', 'Contact Dermatitis due to Methylisothiazolinones Sensitivity'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['chronic urticaria causes', 'dermal hypersensitivity diagnosis', 'methylisothiazolinones allergy']
- diagnose=['Chronic Autoimmune Urticaria', 'Contact Dermatitis due to Methylisothiazolinones Sensitivity'] gold=False

## APHHM
- tree_n=44 tree_recall=True
- gold_leaf=B2.1:Chronic Idiopathic Urticaria parent=B2
- final_n=2 final_recall=True ranking=['Dermatographic Urticaria', 'Chronic Idiopathic Urticaria']
- human_at1=False fail_mode=final_ok

