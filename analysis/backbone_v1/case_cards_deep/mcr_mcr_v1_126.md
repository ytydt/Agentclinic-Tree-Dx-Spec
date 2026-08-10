# MCR / mcr_v1 / case 126

- **gold**: Extranodal natural killer/T-cell lymphoma nasal type
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`supervisor_hit_judge_miss` B07=`diagnose_ok` B01=`gen_hit_judge_miss` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=s2_hit_s3_drop; B07=diagnose_ok
- **covariates**: vig_words=231; gold_words=8; eponym=False; subtype=False; e7_s2_rank=7; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 53-year-old Hispanic man presented with painful left lower-extremity swelling and erythema. Six months earlier, incidentally noted bilateral adrenal and periaortic retroperitoneal masses were not further evaluated. He reported intermittent fevers, episodic night sweats, decreased appetite, and palpitations. He denied trauma or injury to the leg. On examination, the left calf had ill-defined, warm, confluent erythema, edema, and tender induration. Laboratory studies showed mild lymphocytopenia,...

## Backbone e7
- S1 key_facts: 53-year-old Hispanic man; Painful left lower-extremity swelling and erythema; Incidentally noted bilateral adrenal and periaortic retroperitoneal masses six m; Intermittent fevers, episodic night sweats, decreased appetite, and palpitations; Denies trauma or injury to the leg; Mild lymphocytopenia, moderate anemia, elevated creatine kinase, elevated aldola; Peripheral-blood flow cytometry was unremarkable; CT and MRI of the leg revealed gastrocnemius myositis, extensive subcutaneous an
- S2 mode=complement k=3 pool_n=51 gold_in_s2=True
  - call1: ['Cellulitis', 'Erythema nodosum', 'Pyomyositis', 'Necrotizing fasciitis', 'Subcutaneous panniculitis-like T-cell lympho
  - call2: ['Kikuchi-Fujimoto disease', 'Kimura disease', 'Erdheim-Chester disease', 'Langerhans cell histiocytosis', 'Rosai-Dorfma
  - call3: ['Kawasaki disease', 'Sweet syndrome', 'Erythema multiforme', 'Acute hemorrhagic edema of infancy', 'Annular erythema of
- S3 shortlist n=5 gold=False: Subcutaneous panniculitis-like T-cell lymphoma, Wegener's granulomatosis, Polyarteritis nodosa, Takayasu arteritis, Erdheim-Chester disease
- S4 champion: **Subcutaneous panniculitis-like T-cell lymphoma** gold=False
- S4 raw (trunc): {"champion": "Subcutaneous panniculitis-like T-cell lymphoma", "rationale": "The presence of a sparse perivascular and interstitial infiltrate of enlarged atypical mononuclear cells in the punch biopsy, along with systemic symptoms such as intermittent fevers, night sweats, and w

## Backbone v0 (compact)
- S1 key_facts: 53-year-old Hispanic man; Incidentally noted bilateral adrenal and periaortic retroperitoneal masses six m; Denies trauma or injury to the leg; Mild lymphocytopenia, moderate anemia, elevated creatine kinase, elevated aldola; Peripheral-blood flow cytometry was unremarkable; CT and MRI of the leg revealed gastrocnemius myositis, extensive subcutaneous an; No improvement with intravenous ceftriaxone for presumed cellulitis and pyomyosi; Punch biopsy of skin from the lower leg showed a sparse perivascular and interst
- S2 mode=None k=None pool_n=19 gold_in_s2=True
  - pool gold matches: ['Lymphoma']
  - pool head: Cellulitis, Erythema nodosum, Deep vein thrombosis, Necrotizing fasciitis, Pyomyositis, Lymphoma, Leukemia cutis, Panniculitis
- S3 shortlist n=5 gold=True: Lymphoma, Leukemia cutis, Granulomatosis with polyangiitis, Panniculitis, Lymphomatoid granulomatosis
- S4 champion: **Lymphoma** gold=True
- S4 raw (trunc): {"champion": "Lymphoma", "rationale": "The presence of bilateral adrenal and periaortic retroperitoneal masses, systemic symptoms such as fevers, night sweats, and weight loss, along with laboratory findings of mild lymphocytopenia, moderate anemia, and elevated lactate dehydroge

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    Given the patient's symptoms, laboratory results, and imaging studies, a diagnosis of lymphoma is considered due to the presence of atypical mononuclear cells a
  - turn1 gold_mention=False diag=
    The patient's presentation of painful lower-extremity swelling, systemic symptoms, and biopsy findings of atypical mononuclear cells, along with the lack of res
  - turn2 gold_mention=False diag=
    The patient's symptoms, laboratory results, imaging studies, and biopsy findings, along with the lack of response to antibiotics, support a diagnosis of lymphom
- supervisor votes=3 top2=['Lymphoma', 'Sarcoma'] gold=True

## Baseline B07
- draft=['Lymphoma', 'Mantle Cell Lymphoma'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['lymphoma with skin and muscle involvement', 'periaortic retroperitoneal masses and lymphadenopathy', 'atypical mononuclear cells in skin biopsy']
- diagnose=['Lymphoma', 'Mantle Cell Lymphoma'] gold=True

## Baseline B01
- queries=['atypical mononuclear cell infiltrate in skin biopsy', 'periaortic retroperitoneal masses with systemic symptoms', 'myositis and lymphadenopathy without infection', 'elevated lactate dehydrogenase and aldolase with anemia']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Lymphoma', 'Dermatomyositis'] gold=True

## APHHM
- tree_n=48 tree_recall=True
- gold_leaf=B1.5:Lymphoma parent=B1
- final_n=4 final_recall=True ranking=['Lymphoma', 'Castleman disease', 'Immune-Mediated Necrotizing Myopathy', 'Rosai-Dorfman disease']
- human_at1=True fail_mode=final_ok

