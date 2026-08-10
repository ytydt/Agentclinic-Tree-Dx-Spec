# DA / d2_heldout200b / case 477

- **gold**: Multisystem Inflammatory Syndrome in Children (MIS-C) with COVID-19 associated acute ischemic stroke
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01= APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_miss_but_scored_ok` B01=`na` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=310; gold_words=14; eponym=False; subtype=True; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 9-year-old girl presented with:- High-grade fever for 14 days- Throbbing frontal headache- Vomiting - Progressive weakness on the right side of body for 5 daysPast medical history: No significant history mentionedCurrent status: SARS-CoV-2 RNA was detected on nasopharyngeal swab by RT-PCR on presentation  On admission:- Bilateral non-purulent conjunctivitis- Axillary temperature: 39.4°C- Blood oxygen saturation: 98%- Heart rate: 64 bpm- Tachypnoea- Blood pressure: 132/102 mm Hg- Glasgow Coma S...

## Options
  - A: COVID-19 associated multisystem inflammatory syndrome in children (MIS-C) with neurological involvement
  - B: Kawasaki disease
  - C: Multisystem Inflammatory Syndrome in Children (MIS-C) with COVID-19 associated acute ischemic stroke
  - D: COVID-19–associated cerebral vasculitis (ischemic stroke)

## Backbone e7
- S1 key_facts: 9-year-old girl; High-grade fever for 14 days; Throbbing frontal headache; Vomiting; Progressive weakness on the right side of body for 5 days; Bilateral non-purulent conjunctivitis; Axillary temperature: 39.4°C; Blood oxygen saturation: 98%
- S2 mode=complement k=3 pool_n=56 gold_in_s2=False
  - call1: ['Acute Disseminated Encephalomyelitis', 'Subacute Sclerosing Panencephalitis', 'Rasmussen Encephalitis', 'Cerebral Vasc
  - call2: ['Bickerstaff Brainstem Encephalitis', 'Acute Necrotizing Encephalopathy', 'Posterior Reversible Encephalopathy Syndrome
  - call3: ['X-linked Adrenoleukodystrophy', 'Alexander Disease', 'Canavan Disease', 'Krabbe Disease', 'Metachromatic Leukodystroph
- S3 shortlist n=5 gold=False: Acute Disseminated Encephalomyelitis, Cerebral Vasculitis, Rasmussen Encephalitis, Herpes Simplex Encephalitis, Acute Hemorrhagic Leukoencephalitis
- S4 champion: **Acute Disseminated Encephalomyelitis** gold=False
- S4 raw (trunc): {"champion": "Acute Disseminated Encephalomyelitis", "rationale": "The patient's symptoms, including high-grade fever, throbbing headache, vomiting, progressive weakness on one side of the body, and the presence of pleocytosis with slightly increased protein in the CSF, along wit

## Backbone v0 (compact)
- S1 key_facts: 9-year-old girl; High-grade fever for 14 days; Throbbing frontal headache; Vomiting; Progressive weakness on the right side of body for 5 days; Bilateral non-purulent conjunctivitis; Axillary temperature: 39.4°C; Blood oxygen saturation: 98%
- S2 mode=single k=1 pool_n=19 gold_in_s2=False
  - call1: ['Acute Disseminated Encephalomyelitis', 'Subacute Sclerosing Panencephalitis', 'Rasmussen Encephalitis', 'Cerebral Vasc
- S3 shortlist n=5 gold=False: Acute Disseminated Encephalomyelitis, Cerebral Vasculitis, Rasmussen Encephalitis, Moyamoya Disease, Herpes Simplex Encephalitis
- S4 champion: **Acute Disseminated Encephalomyelitis** gold=False
- S4 raw (trunc): {"champion": "Acute Disseminated Encephalomyelitis", "rationale": "The patient's symptoms, including high-grade fever, throbbing headache, vomiting, progressive weakness, and upper motor neuron type right-sided seventh cranial-nerve palsy, along with the presence of multifocal di

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with high-grade fever, headache, vomiting, and progressive weakness on one side of the body, along with the detection of SARS-CoV-2 R
  - turn1 gold_mention=True diag=
    The patient's complex presentation with fever, headache, vomiting, and progressive hemiplegia, combined with the detection of SARS-CoV-2 RNA and specific imagin
  - turn2 gold_mention=True diag=
    The patient's clinical presentation and diagnostic findings align with the previous discussions, emphasizing the likelihood of MIS-C and cerebral vasculitis due
- supervisor votes=3 top2=['Multisystem Inflammatory Syndrome in Children (MIS-C)', 'Cerebral Vasculitis'] gold=True

## Baseline B07
- draft=['COVID-19 associated cerebral vasculitis', 'Moyamoya syndrome'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['Moyamoya disease in children', 'COVID-19 associated vasculitis', 'Pediatric cerebral vasculitis', 'Multifocal cerebral vasculopathy']
- diagnose=['COVID-19 associated cerebral vasculitis', 'Moyamoya syndrome'] gold=False

