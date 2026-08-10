# MCR / mcr_v2 / case 139

- **gold**: type 2 autoimmune pancreatitis
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=266; gold_words=4; eponym=False; subtype=True; e7_s2_rank=5; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 67‐year‐old man with a 3‐year history of type 2 diabetes mellitus managed with metformin, glimepiride, and a prior percutaneous coronary intervention for acute myocardial infarction 2 months earlier was referred for treatment of newly diagnosed extensive ulcerative colitis. He had a 40‐year smoking history but had quit after his myocardial infarction. He reported four episodes of bloody diarrhea daily but denied abdominal pain or fever. On admission for a 2‐week educational trial of a plant‐ba...

## Backbone e7
- S1 key_facts: 67-year-old man with a 3-year history of type 2 diabetes mellitus; Managed with metformin and glimepiride; Prior percutaneous coronary intervention for acute myocardial infarction 2 month; 40-year smoking history, quit after myocardial infarction; Four episodes of bloody diarrhea daily; No abdominal pain or fever; Normal white-cell count, bilirubin, and liver function tests; Microalbuminuria of 50.7 mg/day
- S2 mode=complement k=3 pool_n=52 gold_in_s2=True
  - call1: ['Acute pancreatitis', 'Chronic pancreatitis', 'Pancreatic cancer', 'Intraductal papillary mucinous neoplasm', 'Autoimmu
  - call2: ['Pancreatic lymphoma', 'Primary pancreatic lymphoma', 'Secondary pancreatic lymphoma', 'Intrapancreatic accessory splee
  - call3: ['Idiopathic duct-centric pancreatitis', 'Focal chronic pancreatitis', 'Groove carcinoma', 'Intraductal tubulopapillary 
- S3 shortlist n=5 gold=True: Autoimmune pancreatitis, IgG4-related pancreatitis, Acute pancreatitis, Chronic pancreatitis, Pancreatic involvement in IgG4-related disease with inflammatory bowel disease
- S4 champion: **IgG4-related pancreatitis** gold=False
- S4 raw (trunc): {"champion": "IgG4-related pancreatitis", "rationale": "Elevated serum IgG4, pancreatic swelling, and duct narrowing on imaging studies are consistent with IgG4-related pancreatitis, and the presence of extensive ulcerative colitis suggests a possible association with IgG4-relate

## Backbone v0 (compact)
- S1 key_facts: 67-year-old man with a 3-year history of type 2 diabetes mellitus; Managed with metformin and glimepiride; Prior percutaneous coronary intervention for acute myocardial infarction 2 month; 40-year smoking history, quit after myocardial infarction; Four episodes of bloody diarrhea daily; No abdominal pain or fever; Normal white-cell count, bilirubin, and liver function tests; Plasma glucose rose from 258 mg/dL to 449 mg/dL
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Acute pancreatitis', 'Chronic pancreatitis', 'Autoimmune pancreatitis', 'IgG4-related pancreatitis', 'Pancreatic cance
- S3 shortlist n=5 gold=True: Autoimmune pancreatitis, Acute pancreatitis, IgG4-related pancreatitis, Chronic pancreatitis, Ulcerative colitis-associated pancreatitis
- S4 champion: **IgG4-related pancreatitis** gold=False
- S4 raw (trunc): {"champion": "IgG4-related pancreatitis", "rationale": "Elevated serum amylase and lipase, swelling of the pancreas with a peripheral rim on imaging, and the patient's recent onset of extensive ulcerative colitis are consistent with IgG4-related pancreatitis, although the serum I

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with elevated serum amylase and lipase, swelling of the pancreas, and narrowing of the main pancreatic duct, along with a history of 
  - turn1 gold_mention=True diag=
    The patient's elevated serum amylase and lipase, pancreatic swelling, and main pancreatic duct narrowing support an inflammatory process, with autoimmune pancre
  - turn2 gold_mention=True diag=
    Engaging with prior opinions, the combination of pancreatic swelling, elevated serum amylase and lipase, and the patient's complex medical history including ulc
- supervisor votes=3 top2=['Autoimmune Pancreatitis', 'Chronic Pancreatitis'] gold=True

## Baseline B07
- draft=['Autoimmune Pancreatitis', 'IgG4-related Disease'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['autoimmune pancreatitis', 'IgG4-related disease', 'ulcerative colitis and pancreatitis association']
- diagnose=['Autoimmune Pancreatitis', 'IgG4-related Disease'] gold=True

## Baseline B01
- queries=['diabetes mellitus and pancreatitis', 'ulcerative colitis and pancreatic swelling', 'elevated serum amylase and lipase in diabetes', 'IgG4-related disease and pancreas']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['IgG4-related pancreatitis', 'Chronic pancreatitis'] gold=False

