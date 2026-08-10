# MCR / mcr_v1 / case 33

- **gold**: Dyke-Davidoff-Masson syndrome
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=1
- **loci**: e7=`ok` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_miss` APHHM=`final_ok`
- **primary_locus**: e7=ok; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=229; gold_words=4; eponym=True; subtype=False; e7_s2_rank=17; mapper_rescue=False
- **causal**: layer=e7_win_recall; primary loci above.

## Vignette (trunc)
An 8-year-old girl was evaluated for recurrent seizures, left-sided weakness, and developmental delays. Seizures began at age 3 months, initially infrequent but progressively more frequent despite antiepileptic therapy. The parents also noted delayed motor and cognitive milestones and gradual behavioral changes, including disturbed sleep, irritability, and episodes of aimless talking. There was no family history of neurological disorders and no reported perinatal complications or trauma.   On ne...

## Backbone e7
- S1 key_facts: Age of seizure onset: 3 months; Seizures have increased in frequency despite antiepileptic therapy; Delayed motor and cognitive milestones; Gradual behavioral changes, including disturbed sleep and irritability; No family history of neurological disorders; No reported perinatal complications or trauma; Normal routine laboratory studies, including metabolic and infectious panels; EEG shows focal abnormal brain activity
- S2 mode=complement k=3 pool_n=52 gold_in_s2=True
  - call1: ["Rasmussen's encephalitis", 'Sturge-Weber syndrome', 'Tuberous sclerosis complex', 'Hemimegalencephaly', 'Focal cortica
  - call2: ["Alpers' disease", 'Leigh syndrome', 'Mitochondrial encephalomyopathy, lactic acidosis, and stroke-like episodes', 'MEL
  - call3: ['Dentatorubral-pallidoluysian atrophy', 'Pantothenate kinase-associated neurodegeneration', 'Beta-propeller protein-ass
- S3 shortlist n=5 gold=True: Rasmussen's encephalitis, Hemimegalencephaly, Dyke-Davidoff-Masson syndrome, Sturge-Weber syndrome, Porencephaly
- S4 champion: **Dyke-Davidoff-Masson syndrome** gold=True
- S4 raw (trunc): {"champion": "Dyke-Davidoff-Masson syndrome", "rationale": "The combination of cerebral hemisphere atrophy, ex vacuo dilatation of the lateral ventricle, ipsilateral calvarial thickening, and compensatory hyperpneumatization of the sphenoid bone and bilateral mastoid air cells ar

## Backbone v0 (compact)
- S1 key_facts: Age of seizure onset: 3 months; Seizures have increased in frequency despite antiepileptic therapy; Delayed motor and cognitive milestones; Behavioral changes, including disturbed sleep and irritability; No family history of neurological disorders; No perinatal complications or trauma; Normal routine laboratory studies, including metabolic and infectious panels; EEG shows focal abnormal brain activity
- S2 mode=None k=None pool_n=18 gold_in_s2=True
  - pool gold matches: ['Dyke-Davidoff-Masson syndrome']
  - pool head: Rasmussen's encephalitis, Sturge-Weber syndrome, Tuberous sclerosis complex, Hemimegalencephaly, Focal cortical dysplasia, Perinatal stroke, Cerebral vasculitis, Moyamoya disease
- S3 shortlist n=5 gold=True: Rasmussen's encephalitis, Hemimegalencephaly, Dyke-Davidoff-Masson syndrome, Sturge-Weber syndrome, Porencephaly
- S4 champion: **Dyke-Davidoff-Masson syndrome** gold=True
- S4 raw (trunc): {"champion": "Dyke-Davidoff-Masson syndrome", "rationale": "The combination of cerebral hemisphere atrophy, ex vacuo dilatation of the lateral ventricle, ipsilateral calvarial thickening, and compensatory hyperpneumatization of the sphenoid bone and bilateral mastoid air cells, a

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of recurrent seizures, left-sided weakness, developmental delays, and marked asymmetry of the cerebral hemispheres with atrophy of th
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and imaging findings, including significant atrophy of the right cerebral hemisphere and areas of cystic encephalomalacia, a
  - turn2 gold_mention=True diag=
    The patient's clinical presentation of recurrent seizures, left-sided weakness, developmental delays, and imaging findings of significant atrophy of the right c
- supervisor votes=3 top2=["Rasmussen's Encephalitis", 'Hemispheric Epilepsy Surgery Candidate'] gold=False

## Baseline B07
- draft=["Rasmussen's Encephalitis", 'Sturge-Weber Syndrome'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['Hemispheric brain atrophy in children', 'Cystic encephalomalacia causes', 'Upper motor neuron pattern weakness in pediatric patients']
- diagnose=["Rasmussen's Encephalitis", 'Sturge-Weber Syndrome'] gold=False

## Baseline B01
- queries=['causes of hemispheric atrophy in children', 'remote focal brain injury and seizures', 'cystic encephalomalacia and developmental delays', 'upper motor neuron signs and cerebral hemisphere asymmetry']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=["Rasmussen's encephalitis", 'Hemiconvulsive-hemiplegic epilepsy'] gold=False

## APHHM
- tree_n=33 tree_recall=True
- gold_leaf=B4.2:Dyke-Davidoff-Masson syndrome parent=B4
- final_n=5 final_recall=True ranking=['Dyke-Davidoff-Masson syndrome', 'Rasmussen encephalitis', 'Hemimegalencephaly', 'Cerebral hemiatrophy-hemiplegia-epilepsy syndrome', "Rasmussen's encephalitis"]
- human_at1=True fail_mode=final_ok

