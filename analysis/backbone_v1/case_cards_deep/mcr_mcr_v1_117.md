# MCR / mcr_v1 / case 117

- **gold**: Antiphospholipid syndrome
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`gen_ok` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=367; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A 43-year-old man with no significant medical history presented in December with a 4-day history of fever to 38.8 °C, shaking chills, hemoptysis, and worsening dyspnea. He reported several months of intermittent night sweats, arthralgias of the wrists and ankles, and a 10-kg weight loss. One day before admission, he noted a painful ecchymotic lesion on his left calf; over the next 24 hours, similar lesions appeared on his abdomen, back, right upper arm, and right calf. His 3-year-old son had rec...

## Backbone e7
- S1 key_facts: 4-day history of fever to 38.8 °C; Shaking chills; Intermittent night sweats for several months; Arthralgias of the wrists and ankles; 10-kg weight loss; Recent respiratory illness in 3-year-old son; Bilateral wheezes on examination; Multiple painful ecchymoses with hemorrhagic bullae
- S2 mode=complement k=3 pool_n=53 gold_in_s2=False
  - call1: ["Wegener's granulomatosis", 'Churg-Strauss syndrome', 'Microscopic polyangiitis', 'Goodpasture syndrome', 'Henoch-Schön
  - call2: ['Granulomatosis with polyangiitis', 'Eosinophilic pneumonia', 'Acute interstitial pneumonia', 'Cryptogenic organizing p
  - call3: ['Rocky Mountain spotted fever', 'Ehrlichiosis', 'Anaplasmosis', 'Meningococcemia', 'Staphylococcal toxic shock syndrome
- S3 shortlist n=5 gold=True: Antiphospholipid syndrome, Leukocytoclastic vasculitis, Granulomatosis with polyangiitis, Eosinophilic granuloma with polyangiitis, Henoch-Schönlein purpura
- S4 champion: **Antiphospholipid syndrome** gold=True
- S4 raw (trunc): {"champion": "Antiphospholipid syndrome", "rationale": "The patient's presentation with fever, weight loss, and multiple painful ecchymoses with hemorrhagic bullae, along with laboratory findings of thrombotic paucicellular vasculopathy and positive tests for lupus anticoagulant,

## Backbone v0 (compact)
- S1 key_facts: 4-day history of fever to 38.8 °C; Shaking chills; Intermittent night sweats for several months; Arthralgias of the wrists and ankles; 10-kg weight loss; Recent respiratory illness in 3-year-old son; Bilateral wheezes on examination; Multiple painful ecchymoses with hemorrhagic bullae
- S2 mode=None k=None pool_n=19 gold_in_s2=False
  - pool gold matches: []
  - pool head: Wegener's granulomatosis, Churg-Strauss syndrome, Microscopic polyangiitis, Goodpasture syndrome, Henoch-Schönlein purpura, Thrombotic thrombocytopenic purpura, Hemophagocytic lymphohistiocytosis, Infectious vasculitis
- S3 shortlist n=5 gold=False: Infectious vasculitis, Henoch-Schönlein purpura, Microscopic polyangiitis, Wegener's granulomatosis, Churg-Strauss syndrome
- S4 champion: **Infectious vasculitis** gold=False
- S4 raw (trunc): {"champion": "Infectious vasculitis", "rationale": "The patient's symptoms, including fever, shaking chills, and recent respiratory illness in a family member, along with the presence of a recent respiratory illness in the 3-year-old son and positive FilmArray respiratory panel f

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with fever, hemoptysis, dyspnea, and painful ecchymotic lesions, along with laboratory findings of thrombotic paucicellular vasculopa
  - turn1 gold_mention=True diag=
    The patient's symptoms and laboratory results, including positive antiphospholipid antibodies and thrombotic paucicellular vasculopathy, support antiphospholipi
  - turn2 gold_mention=True diag=
    The patient's clinical presentation and laboratory findings, including positive antiphospholipid antibodies and thrombotic paucicellular vasculopathy, align wit
- supervisor votes=3 top2=['Antiphospholipid syndrome', 'Infectious mononucleosis due to Epstein-Barr virus'] gold=True

## Baseline B07
- draft=['Antiphospholipid Syndrome', 'Respiratory Syncytial Virus Infection'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['antiphospholipid syndrome diagnosis', 'respiratory syncytial virus in adults', 'thrombotic paucicellular vasculopathy', 'lupus anticoagulant positive diagnosis']
- diagnose=['Antiphospholipid Syndrome', 'Respiratory Syncytial Virus Infection'] gold=True

## Baseline B01
- queries=['fever and hemoptysis with skin lesions and thrombotic vasculopathy', 'community-acquired pneumonia with negative bacterial tests and positive respiratory syncytial virus', 'systemic symptoms with positive lupus anticoagulant and anticardiolipin IgM', 'respiratory illness with multifocal alveolar infiltrates and negative CT angiography for pulmonary embolism']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Antiphospholipid syndrome', 'Respiratory syncytial virus pneumonia'] gold=True

## APHHM
- tree_n=83 tree_recall=False
- gold_leaf=None
- final_n=3 final_recall=False ranking=['Cryoglobulinemic vasculitis', 'Systemic Lupus Erythematosus', 'Hemophagocytic lymphohistiocytosis']
- human_at1=False fail_mode=tree_miss

