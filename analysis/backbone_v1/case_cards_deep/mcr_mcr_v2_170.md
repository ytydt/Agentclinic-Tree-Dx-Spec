# MCR / mcr_v2 / case 170

- **gold**: T-cell lymphoblastic lymphoma
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=diagnose_hit_judge_miss
- **covariates**: vig_words=229; gold_words=4; eponym=False; subtype=False; e7_s2_rank=33; mapper_rescue=False
- **causal**: layer=e7_win_rank; primary loci above.

## Vignette (trunc)
A 6-year-old girl presented with a 1-week history of dyspnea and pleuritic chest pain that was worse when supine, associated with orthopnea, mild agitation, and fever. Her parents also reported intermittent fever over the preceding 3 months. There was no significant past medical history and no known contact with COVID-19 patients. On examination, she was febrile, alert, and in mild respiratory distress. Lung auscultation was clear except for decreased breath sounds at the right lower zone. Cardi...

## Backbone e7
- S1 key_facts: 1-week history of dyspnea and pleuritic chest pain; Worse symptoms when supine; Associated with orthopnea, mild agitation, and fever; Intermittent fever over the preceding 3 months; No significant past medical history; No known contact with COVID-19 patients; Febrile, alert, and in mild respiratory distress on examination; Decreased breath sounds at the right lower zone on lung auscultation
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Hodgkin lymphoma', 'Non-Hodgkin lymphoma', 'Thymoma', 'Teratoma', 'Germ cell tumor', 'Mediastinal neuroblastoma', 'Pan
  - call2: ['Rosai-Dorfman disease', 'Langerhans cell histiocytosis', 'Desmoid tumor', 'Solitary fibrous tumor of the mediastinum',
  - call3: ['Lymphoblastic lymphoma', 'Anaplastic large cell lymphoma', 'Mediastinal gray zone lymphoma', 'Primary mediastinal larg
- S3 shortlist n=5 gold=True: Hodgkin lymphoma, Non-Hodgkin lymphoma, Thymoma, Castleman disease, Lymphoblastic lymphoma
- S4 champion: **Lymphoblastic lymphoma** gold=True
- S4 raw (trunc): {"champion": "Lymphoblastic lymphoma", "rationale": "The presence of an anterior mediastinal mass, large pericardial effusion, and pleural effusions, along with systemic symptoms such as fever and hepatomegaly, are highly suggestive of lymphoblastic lymphoma, which is a type of n

## Backbone v0 (compact)
- S1 key_facts: 1-week history of dyspnea and pleuritic chest pain; Worse symptoms when supine; Associated with orthopnea, mild agitation, and fever; Intermittent fever over the preceding 3 months; No significant past medical history; No known contact with COVID-19 patients; Fever, alert, and in mild respiratory distress on examination; Decreased breath sounds at the right lower zone on lung auscultation
- S2 mode=single k=1 pool_n=18 gold_in_s2=False
  - call1: ['Hodgkin lymphoma', 'Non-Hodgkin lymphoma', 'Thymoma', 'Teratoma', 'Germ cell tumor', 'Mediastinal neuroblastoma', 'Pan
- S3 shortlist n=5 gold=False: Hodgkin lymphoma, Non-Hodgkin lymphoma, Tuberculous pericarditis, Castleman disease, Lymphomatoid granulomatosis
- S4 champion: **Hodgkin lymphoma** gold=False
- S4 raw (trunc): {"champion": "Hodgkin lymphoma", "rationale": "The presence of an anterior mediastinal mass, large pericardial effusion, and systemic symptoms such as fever and weight loss (implied by hepatomegaly and elevated inflammatory markers) are consistent with Hodgkin lymphoma, particula

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with dyspnea, pleuritic chest pain, and orthopnea, along with the findings of a large pericardial effusion and an anterior mediastina
  - turn1 gold_mention=True diag=
    The patient's symptoms and imaging findings are consistent with a mediastinal malignancy, and the laboratory results support this diagnosis, with lymphoma being
  - turn2 gold_mention=True diag=
    The patient's presentation and imaging findings are consistent with a mediastinal malignancy, with lymphoma being the most likely diagnosis given the age and ma
- supervisor votes=3 top2=['Lymphoma', 'Mediastinal germ cell tumor'] gold=True

## Baseline B07
- draft=['Lymphoma', 'Germ Cell Tumor'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['pediatric anterior mediastinal mass', 'pericardial effusion and mediastinal mass in children', 'causes of intermittent fever and dyspnea in a 6-year-old']
- diagnose=['Lymphoma', 'Germ Cell Tumor'] gold=True

## Baseline B01
- queries=['pediatric pericardial effusion with mediastinal mass', 'causes of orthopnea and pleuritic chest pain in children', 'differential diagnosis of anterior mediastinal mass in pediatric patients', 'pericardial effusion with electrical alternans in pediatric patients']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Lymphoma', 'Germ Cell Tumor'] gold=True

