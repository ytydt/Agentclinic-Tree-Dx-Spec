# MCR / mcr_200b / case 268

- **gold**: pustular psoriasis
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s2_hit_s3_drop; recalled_but_none_correct
- **covariates**: vig_words=171; gold_words=2; eponym=False; subtype=False; e7_s2_rank=3; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 70‐year‐old woman with an undifferentiated connective tissue disorder and rheumatoid arthritis was treated with hydroxychloroquine in 2010, after which she developed a severe generalized bullous and pustular rash that resolved over three months following drug discontinuation and corticosteroid therapy. In 2022, hydroxychloroquine was restarted for her rheumatoid arthritis. Three days after restarting the drug, she was admitted with widespread erythema, desquamation, and pustulation. She denied...

## Backbone e7
- S1 key_facts: 70-year-old woman with undifferentiated connective tissue disorder and rheumatoi; Treated with hydroxychloroquine in 2010; Developed severe generalized bullous and pustular rash after starting hydroxychl; Rash resolved after drug discontinuation and corticosteroid therapy; Hydroxychloroquine was restarted in 2022; Admitted with widespread erythema, desquamation, and pustulation three days afte; Denied any history of psoriasis; Laboratory studies revealed marked leukocytosis, hyperglycemia, hypoproteinemia,
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Toxic Epidermal Necrolysis', 'Stevens-Johnson Syndrome', 'Generalized Pustular Psoriasis', 'Acute Generalized Exanthem
  - call2: ['Generalized Exfoliative Dermatitis', 'Pityriasis Rubra Pilaris', 'Subcorneal Pustular Dermatosis', 'IgA Pemphigus', 'E
  - call3: ['Acute Interstitial Granulomatous Dermatitis', 'Churg-Strauss Syndrome', 'Eosinophilic Cellulitis', 'Granulomatous Rosa
- S3 shortlist n=5 gold=False: Toxic Epidermal Necrolysis, Stevens-Johnson Syndrome, Acute Generalized Exanthematous Pustulosis, Drug Rash with Eosinophilia and Systemic Symptoms, Severe Cutaneous Adverse Reaction
- S4 champion: **Acute Generalized Exanthematous Pustulosis** gold=False
- S4 raw (trunc): {"champion": "Acute Generalized Exanthematous Pustulosis", "rationale": "The patient's symptoms, including widespread erythema, desquamation, and pustulation, along with laboratory findings of marked leukocytosis and skin biopsies showing subcorneal collections of neutrophils, ar

## Backbone v0 (compact)
- S1 key_facts: 70-year-old woman with undifferentiated connective tissue disorder and rheumatoi; Treated with hydroxychloroquine in 2010; Developed severe generalized bullous and pustular rash after starting hydroxychl; Rash resolved after drug discontinuation and corticosteroid therapy; Hydroxychloroquine was restarted in 2022; Admitted with widespread erythema, desquamation, and pustulation three days afte; Denied any history of psoriasis; Laboratory studies revealed marked leukocytosis, hyperglycemia, hypoproteinemia,
- S2 mode=single k=1 pool_n=16 gold_in_s2=True
  - call1: ['Toxic Epidermal Necrolysis', 'Stevens-Johnson Syndrome', 'Generalized Pustular Psoriasis', 'Acute Generalized Exanthem
- S3 shortlist n=5 gold=False: Toxic Epidermal Necrolysis, Stevens-Johnson Syndrome, Acute Generalized Exanthematous Pustulosis, Drug Rash with Eosinophilia and Systemic Symptoms, Hydroxychloroquine-Induced Hypersensitivity Reaction
- S4 champion: **Acute Generalized Exanthematous Pustulosis** gold=False
- S4 raw (trunc): {"champion": "Acute Generalized Exanthematous Pustulosis", "rationale": "The patient's symptoms, including widespread erythema, desquamation, and pustulation, along with laboratory findings of marked leukocytosis and skin biopsies showing subcorneal collections of neutrophils, ar

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of a severe reaction to hydroxychloroquine in the past and the current presentation with widespread erythema, desquamation, and pustulatio
  - turn1 gold_mention=True diag=
    The patient's history of a severe reaction to hydroxychloroquine and the current presentation with widespread erythema, desquamation, and pustulation, along wit
  - turn2 gold_mention=True diag=
    The patient's history of a severe reaction to hydroxychloroquine and the current presentation with widespread erythema, desquamation, and pustulation, along wit
- supervisor votes=3 top2=['Acute Generalized Exanthematous Pustulosis', 'Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)'] gold=False

## Baseline B07
- draft=['Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS) syndrome', 'Acute Generalized Exanthematous Pustulosis (AGEP)'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['drug reaction with eosinophilia and systemic symptoms (DRESS) syndrome', 'hydroxychloroquine adverse effects', 'bullous and pustular rash differential diagnosis']
- diagnose=['Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS) syndrome', 'Acute Generalized Exanthematous Pustulosis (AGEP)'] gold=False

## Baseline B01
- queries=['drug reaction with eosinophilia and systemic symptoms (DRESS) syndrome', 'Stevens-Johnson syndrome vs toxic epidermal necrolysis', 'acute generalized exanthematous pustulosis (AGEP) diagnosis', 'hydroxychloroquine-induced severe cutaneous adverse reactions']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)'] gold=False

