# MCR / mcr_200b / case 250

- **gold**: Toxocariasis
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_miss_but_scored_ok` B07=`diagnose_hit_judge_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_miss_but_scored_ok
- **covariates**: vig_words=382; gold_words=1; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 9-year-old girl with a small muscular ventricular septal defect presented with chest pain and dyspnea one week after recovering from an upper respiratory infection and after minor anterior chest trauma in a fall. She was afebrile. Heart rate was 104 beats/min, respiratory rate 28 breaths/min, blood pressure 113/66 mm Hg, and oxygen saturation normal. Physical examination revealed mild tenderness over the sternum and normal cardiac auscultation.   Chest radiography showed mild cardiomediastinal...

## Backbone e7
- S1 key_facts: 9-year-old girl with a small muscular ventricular septal defect; Recent upper respiratory infection; Minor anterior chest trauma in a fall; Afebrile; Heart rate 104 beats/min; Respiratory rate 28 breaths/min; Blood pressure 113/66 mm Hg; Oxygen saturation normal
- S2 mode=complement k=3 pool_n=51 gold_in_s2=False
  - call1: ['Viral myopericarditis', 'Bacterial pericarditis', 'Tuberculous pericarditis', 'Uremic pericarditis', 'Autoimmune peric
  - call2: ['Eosinophilic granulomatosis with polyangiitis', "Loeffler's endocarditis", 'Acute eosinophilic pneumonia', 'Chronic eo
  - call3: ['Eosinophilic fasciitis', 'Necrotizing eosinophilic myocarditis', "Loeffler's cardiomyopathy", 'Eosinophilic coronary a
- S3 shortlist n=5 gold=False: Eosinophilic pericarditis, Hypereosinophilic syndrome, Viral myopericarditis, Churg-Strauss syndrome, Eosinophilic granulomatosis with polyangiitis
- S4 champion: **Eosinophilic pericarditis** gold=False
- S4 raw (trunc): {"champion": "Eosinophilic pericarditis", "rationale": "The patient's presentation with pericardial effusion, elevated eosinophil count, and resolution of symptoms with ibuprofen and colchicine treatment supports this diagnosis, and the absence of other systemic symptoms or findi

## Backbone v0 (compact)
- S1 key_facts: 9-year-old girl with a small muscular ventricular septal defect; Presented with chest pain and dyspnea; Afebrile; Heart rate was 104 beats/min; Respiratory rate 28 breaths/min; Blood pressure 113/66 mm Hg; Oxygen saturation normal; Mild tenderness over the sternum
- S2 mode=single k=1 pool_n=16 gold_in_s2=False
  - call1: ['Viral myopericarditis', 'Bacterial pericarditis', 'Tuberculous pericarditis', 'Uremic pericarditis', 'Traumatic perica
- S3 shortlist n=5 gold=False: Viral myopericarditis, Eosinophilic pericarditis, Hypereosinophilic syndrome, Churg-Strauss syndrome, Postcardiac injury syndrome
- S4 champion: **Eosinophilic pericarditis** gold=False
- S4 raw (trunc): {"champion": "Eosinophilic pericarditis", "rationale": "The patient's significantly elevated absolute eosinophil count and the presence of a moderate pericardial effusion, along with the resolution of symptoms and reduction of the pericardial effusion after treatment, but with a 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation with chest pain, dyspnea, and pericardial effusion after a recent upper respiratory infection suggests viral myopericarditis as the p
  - turn1 gold_mention=False diag=
    The patient's elevated absolute eosinophil count, pica, and exposure to dogs and a cat, along with the presence of pulmonary nodules and ground-glass opacities 
  - turn2 gold_mention=False diag=
    The patient's elevated absolute eosinophil count, pica, and exposure to dogs and a cat, along with the presence of pulmonary nodules and ground-glass opacities 
- supervisor votes=3 top2=['Toxocara infection', 'Eosinophilic pneumonia'] gold=False

## Baseline B07
- draft=['Loeffler syndrome', 'Toxocariasis'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['viral myopericarditis diagnosis', 'eosinophilia causes in children', 'Toxocara serology interpretation', 'myopericarditis vs. loeffler syndrome']
- diagnose=['Loeffler syndrome', 'Toxocariasis'] gold=True

## Baseline B01
- queries=['eosinophilia with pericardial effusion and pulmonary nodules', 'viral myopericarditis with elevated eosinophil count', 'differential diagnosis of hypereosinophilia with cardiac involvement', 'Toxocara infection presenting with cardiac and pulmonary symptoms']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Hypereosinophilic syndrome', 'Toxocara infection'] gold=False

