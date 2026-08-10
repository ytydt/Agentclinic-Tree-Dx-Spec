# MCR / mcr_v1 / case 33

- **gold**: Dyke-Davidoff-Masson syndrome
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=1
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`final_ok` code=`aphhm_ok` prune_e7_ok=0

## Vignette
An 8-year-old girl was evaluated for recurrent seizures, left-sided weakness, and developmental delays. Seizures began at age 3 months, initially infrequent but progressively more frequent despite antiepileptic therapy. The parents also noted delayed motor and cognitive milestones and gradual behavioral changes, including disturbed sleep, irritability, and episodes of aimless talking. There was no family history of neurological disorders and no reported perinatal complications or trauma. 

On neurologic examination, she had significant cognitive impairment and marked left hemiparesis with brisk reflexes, consistent with an upper motor neuron pattern. Sensory examination and cranial nerves were unremarkable. Routine laboratory studies, including metabolic and infectious panels, were normal. Electroencephalography showed focal abnormal brain activity concordant with her seizure semiology. 

Brain magnetic resonance imaging demonstrated marked asymmetry of the cerebral hemispheres, with significant atrophy of the right cerebral hemisphere and ex vacuo dilatation of the right lateral ventricle. Ipsilateral calvarial thickening and compensatory hyperpneumatization of the right sphenoid …

## Backbone e7

- S2 n=52 gold_rank=17
  - clusters: gold=1 near=5 other=46
- S3 shortlist (5):
  - [other] Rasmussen's encephalitis
  - [other] Hemimegalencephaly
  - [gold] Dyke-Davidoff-Masson syndrome
  - [near] Sturge-Weber syndrome
  - [other] Porencephaly
    - why_kept(Rasmussen's encephalitis): Focal seizures, hemiparesis, and progressive neurological decline
    - why_kept(Hemimegalencephaly): Cerebral hemisphere atrophy and ex vacuo dilatation of the lateral ventricle
    - why_kept(Dyke-Davidoff-Masson syndrome): Cerebral hemiatrophy and compensatory hyperpneumatization of the sphenoid bone and bilateral mastoid air cells
    - why_kept(Sturge-Weber syndrome): Seizures, hemiparesis, and possible calvarial thickening
    - why_kept(Porencephaly): Cystic encephalomalacia and gliosis in the right fronto-parieto-temporal region
- S4 champion: **Dyke-Davidoff-Masson syndrome** cluster=gold jaccard=1.00
- S4 rationale: The combination of cerebral hemisphere atrophy, ex vacuo dilatation of the lateral ventricle, ipsilateral calvarial thickening, and compensatory hyperpneumatization of the sphenoid bone and bilateral mastoid air cells are characteristic findings of Dyke-Davidoff-Masson syndrome, which is consistent with the patient's presentation of seizures, hemiparesis, and developmental delays.
- S4 rejected:
  - [other] Rasmussen's encephalitis: Rasmussen's encephalitis typically presents with progressive unilateral cerebral inflammation and atrophy, but it is not typically associated with the degree of calvarial thickening and hyperpneumatization seen in this patient.
  - [other] Hemimegalencephaly: Hemimegalencephaly is characterized by an overgrowth of one cerebral hemisphere, which is not consistent with the atrophy seen in this patient.
  - [near] Sturge-Weber syndrome: Sturge-Weber syndrome typically presents with a port-wine stain, which is not mentioned in the vignette, and is associated with leptomeningeal angiomatosis, which is not described in the imaging findings.
  - [other] Porencephaly: Porencephaly refers to a cystic cavity within the brain, which is not the primary finding in this patient, who has more extensive cerebral atrophy and calvarial changes.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ["Rasmussen's Encephalitis", 'Hemispheric Epilepsy Surgery Candidate']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Hemispheric Epilepsy Surgery Candidate', "Rasmussen's Encephalitis", 'Sturge-Weber Syndrome', 'Hemimegalencephaly', 'Porencephaly', "Rasmussen's Encephalitis", 'Hemispheric Epilepsy Surgery Candidate', 'Porencephaly']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ["Rasmussen's Encephalitis", 'Sturge-Weber Syndrome']
- diagnose: ["Rasmussen's Encephalitis", 'Sturge-Weber Syndrome']
- queries: ['Hemispheric brain atrophy in children', 'Cystic encephalomalacia causes', 'Upper motor neuron pattern weakness in pediatric patients']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ["Rasmussen's encephalitis", 'Hemiconvulsive-hemiplegic epilepsy']
- queries: ['causes of hemispheric atrophy in children', 'remote focal brain injury and seizures', 'cystic encephalomalacia and developmental delays', 'upper motor neuron signs and cerebral hemisphere asymmetry']
- n_chunks=12

## APHHM
- tree_n=33 final_n=5
- final: ['Dyke-Davidoff-Masson syndrome', 'Rasmussen encephalitis', 'Hemimegalencephaly', 'Cerebral hemiatrophy-hemiplegia-epilepsy syndrome', "Rasmussen's encephalitis"]
- tree gold_cluster_n=1 final gold=True

