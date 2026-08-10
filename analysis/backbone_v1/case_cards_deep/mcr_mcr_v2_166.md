# MCR / mcr_v2 / case 166

- **gold**: Contrast-induced encephalopathy
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`gen_ok` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=255; gold_words=3; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 2-month-old full-term female with known complex congenital heart disease (single ventricle defect, double-outlet right ventricle with D-transposition of the great arteries, and an ostium secundum atrial septal defect with left superior vena cava) was admitted for evaluation of occasional cyanosis. She was in good general condition, weighed 5 kg, had an oxygen saturation of 80%, and showed no signs of respiratory distress. Her medications included furosemide and spironolactone. The team planned...

## Backbone e7
- S1 key_facts: 2-month-old full-term female; Complex congenital heart disease; Single ventricle defect; Double-outlet right ventricle with D-transposition of the great arteries; Ostium secundum atrial septal defect with left superior vena cava; Weight 5 kg; Oxygen saturation 80%; No signs of respiratory distress
- S2 mode=complement k=3 pool_n=50 gold_in_s2=False
  - call1: ['Hypoxic-Ischemic Encephalopathy', 'Cerebral Vasculitis', 'Intracranial Hemorrhage', 'Cerebral Edema', 'Seizure Disorde
  - call2: ['Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS)', 'Leigh Syndrome', 'Kearns-Sayre Synd
  - call3: ['Acute Disseminated Encephalomyelitis', 'Rasmussen Encephalitis', 'Subacute Sclerosing Panencephalitis', 'Hashimoto Enc
- S3 shortlist n=5 gold=False: Hypoxic-Ischemic Encephalopathy, Cerebral Edema, Seizure Disorder, Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS), Neonatal Encephalopathy with Seizures in Term Newborns
- S4 champion: **Hypoxic-Ischemic Encephalopathy** gold=False
- S4 raw (trunc): {"champion": "Hypoxic-Ischemic Encephalopathy", "rationale": "The patient experienced cardiorespiratory arrest during the procedure, which likely led to a period of hypoxia-ischemia, and subsequently developed seizures and changes in cortical density on the head CT, consistent wi

## Backbone v0 (compact)
- S1 key_facts: 2-month-old full-term female; Complex congenital heart disease; Single ventricle defect; Double-outlet right ventricle with D-transposition of the great arteries; Ostium secundum atrial septal defect with left superior vena cava; Oxygen saturation of 80%; No signs of respiratory distress; Medications included furosemide and spironolactone
- S2 mode=single k=1 pool_n=19 gold_in_s2=False
  - call1: ['Hypoxic-Ischemic Encephalopathy', 'Cerebral Vasculitis', 'Intracranial Hemorrhage', 'Cerebral Edema', 'Seizure Disorde
- S3 shortlist n=5 gold=False: Hypoxic-Ischemic Encephalopathy, Cerebral Edema, Seizure Disorder, Arterial Ischemic Stroke, Reversible Posterior Leukoencephalopathy Syndrome
- S4 champion: **Hypoxic-Ischemic Encephalopathy** gold=False
- S4 raw (trunc): {"champion": "Hypoxic-Ischemic Encephalopathy", "rationale": "The patient's complex congenital heart disease, low oxygen saturation, and cardiorespiratory arrest during surgery increase the risk of hypoxic-ischemic brain injury, which is consistent with the seizure-like activity 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms and imaging findings are consistent with cerebral edema, which may be related to the recent cardiac catheterization procedure, cardioresp
  - turn1 gold_mention=True diag=
    The patient's seizure and imaging findings after cardiac catheterization with contrast are highly suggestive of contrast-induced encephalopathy, considering the
  - turn2 gold_mention=True diag=
    The patient's clinical presentation and imaging findings, particularly the temporal relationship with the cardiac catheterization procedure using contrast, supp
- supervisor votes=3 top2=['Contrast-Induced Encephalopathy', 'Cerebral Edema'] gold=True

## Baseline B07
- draft=['Contrast-induced encephalopathy', 'Cerebral complication related to complex congenital heart disease'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['contrast-induced encephalopathy in pediatric patients', 'Iopromide side effects', 'single ventricle defect and cerebral complications', 'cardiac catheterization complications in infants']
- diagnose=['Contrast-induced encephalopathy', 'Cerebral complication related to complex congenital heart disease'] gold=True

## Baseline B01
- queries=['contrast-induced encephalopathy in pediatric patients', 'seizures after cardiac catheterization with iodinated contrast', 'cerebral injury following cardiac procedures in infants', 'neurological complications of nonionic iodinated contrast agents in children']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Contrast-induced encephalopathy', 'Hypoxic-ischemic encephalopathy'] gold=True

