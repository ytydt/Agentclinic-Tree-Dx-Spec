# MCR / mcr_200b / case 268

- **gold**: pustular psoriasis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s3_why_ignored_gold`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 70‐year‐old woman with an undifferentiated connective tissue disorder and rheumatoid arthritis was treated with hydroxychloroquine in 2010, after which she developed a severe generalized bullous and pustular rash that resolved over three months following drug discontinuation and corticosteroid therapy. In 2022, hydroxychloroquine was restarted for her rheumatoid arthritis. Three days after restarting the drug, she was admitted with widespread erythema, desquamation, and pustulation. She denied any history of psoriasis. Laboratory studies revealed marked leukocytosis, hyperglycemia, hypoproteinemia, transaminitis, and an elevated C‐reactive protein level. Skin biopsies from the back demonstrated separation of the stratum corneum with multifocal subcorneal collections of neutrophils, underlying spongiotic epidermis with neutrophilic exocytosis, papillary dermal edema, and a superficial perivascular and interstitial infiltrate composed of lymphocytes, histiocytes, neutrophils, and rare eosinophils.

What is the most likely diagnosis?

Options:
A. pustular psoriasis
B. AGEP was initially favored based on presentation and histology
C. Pustular psoriasis was ultimately diagnosed given …

## Backbone e7

- S2 n=49 gold_rank=3
  - clusters: gold=1 near=2 other=46
- S3 shortlist (5):
  - [other] Toxic Epidermal Necrolysis
  - [other] Stevens-Johnson Syndrome
  - [other] Acute Generalized Exanthematous Pustulosis
  - [other] Drug Rash with Eosinophilia and Systemic Symptoms
  - [other] Severe Cutaneous Adverse Reaction
    - why_kept(Toxic Epidermal Necrolysis): Severe generalized bullous and pustular rash after hydroxychloroquine restart
    - why_kept(Stevens-Johnson Syndrome): Widespread erythema, desquamation, and pustulation with systemic inflammation
    - why_kept(Acute Generalized Exanthematous Pustulosis): Skin biopsies showing subcorneal collections of neutrophils and spongiotic epidermis
    - why_kept(Drug Rash with Eosinophilia and Systemic Symptoms): Marked leukocytosis, hyperglycemia, and elevated C-reactive protein level after hydroxychloroquine restart
    - why_kept(Severe Cutaneous Adverse Reaction): History of severe skin reaction to hydroxychloroquine in 2010
- S4 champion: **Acute Generalized Exanthematous Pustulosis** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms, including widespread erythema, desquamation, and pustulation, along with laboratory findings of marked leukocytosis and skin biopsies showing subcorneal collections of neutrophils, are consistent with Acute Generalized Exanthematous Pustulosis, a condition often triggered by medications such as hydroxychloroquine.
- S4 rejected:
  - [other] Toxic Epidermal Necrolysis: While the patient had a severe skin reaction, the presence of pustulation and the specific histological findings are more characteristic of Acute Generalized Exanthematous Pustulosis than Toxic Epidermal Necrolysis.
  - [other] Stevens-Johnson Syndrome: Stevens-Johnson Syndrome typically involves mucous membranes and has a different set of histological findings, which do not match the patient's presentation.
  - [other] Drug Rash with Eosinophilia and Systemic Symptoms: Although the patient had a drug reaction, the lack of significant eosinophilia in the laboratory findings and the specific skin biopsy results make this diagnosis less likely.
  - [other] Severe Cutaneous Adverse Reaction: This is a broader category that encompasses several conditions, including the champion diagnosis; the specific details provided point more precisely to Acute Generalized Exanthematous Pustulosis.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Acute Generalized Exanthematous Pustulosis', 'Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)', 'Stevens-Johnson Syndrome', 'Toxic Epidermal Necrolysis', 'Generalized Pustular Psoriasis', 'Acute Generalized Exanthematous Pustulosis', 'Acute Generalized Exanthematous Pustulosis', 'Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)', 'Generalized Pustular Psoriasis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS) syndrome', 'Acute Generalized Exanthematous Pustulosis (AGEP)']
- diagnose: ['Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS) syndrome', 'Acute Generalized Exanthematous Pustulosis (AGEP)']
- queries: ['drug reaction with eosinophilia and systemic symptoms (DRESS) syndrome', 'hydroxychloroquine adverse effects', 'bullous and pustular rash differential diagnosis']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Acute Generalized Exanthematous Pustulosis (AGEP)', 'Drug Reaction with Eosinophilia and Systemic Symptoms (DRESS)']
- queries: ['drug reaction with eosinophilia and systemic symptoms (DRESS) syndrome', 'Stevens-Johnson syndrome vs toxic epidermal necrolysis', 'acute generalized exanthematous pustulosis (AGEP) diagnosis', 'hydroxychloroquine-induced severe cutaneous adverse reactions']
- n_chunks=12

## APHHM
_na_

