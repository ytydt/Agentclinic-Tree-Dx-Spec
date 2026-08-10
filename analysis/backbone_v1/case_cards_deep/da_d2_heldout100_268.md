# DA / d2_heldout100 / case 268

- **gold**: Ipsilateral hemisphere hemorrhagic stroke with peripheral-type facial paralysis
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=s2_miss; recalled_but_none_correct
- **covariates**: vig_words=224; gold_words=9; eponym=False; subtype=True; e7_s2_rank=None; mapper_rescue=False
- **causal**: 至少一臂召回金标但无人 Acc@1——排序/裁决天花板。

## Vignette (trunc)
A 66-year-old man presented with a 24-hour history of incomplete closure of the right eye, flattening of the right nasolabial fold, and right-sided hemiplegia rendering him unable to sit up or stand. The patient had a 3-year history of hypertension but no history of neurological disorders. The patient was alert and oriented.  - Effacement of the right frontal wrinkle- Incomplete closure of the right eyelid- Flattening of the right nasolabial fold- Muscle strength in the right upper and lower ext...

## Options
  - A: Left thalamic intracerebral hemorrhage with intraventricular extension
  - B: Ipsilateral hemisphere hemorrhagic stroke with peripheral-type facial paralysis
  - C: Hypertensive intracerebral hemorrhage
  - D: Left hypertensive intracerebral hemorrhage (thalamus–corona radiata region)

## Backbone e7
- S1 key_facts: 66-year-old man; 24-hour history of symptoms; 3-year history of hypertension; No history of neurological disorders; Alert and oriented; Effacement of the right frontal wrinkle; Incomplete closure of the right eyelid; Muscle strength in the right upper and lower extremities: grade 0/5
- S2 mode=complement k=3 pool_n=47 gold_in_s2=False
  - call1: ['Ischemic stroke', 'Intracerebral hemorrhage', 'Cerebral vasculitis', 'Moyamoya disease', 'Arteriovenous malformation',
  - call2: ['Amyloid angiopathy-related hemorrhage', 'Cerebral autosomal dominant arteriopathy with subcortical infarcts and leukoe
  - call3: ['CADASIL syndrome', 'MELAS syndrome', 'Homocystinuria', 'Ehlers-Danlos syndrome', 'Pseudoxanthoma elasticum', 'Menkes d
- S3 shortlist n=5 gold=False: Intracerebral hemorrhage, Ischemic stroke, Thalamic hemorrhage, Cerebral amyloid angiopathy, Hypertensive encephalopathy
- S4 champion: **Intracerebral hemorrhage** gold=False
- S4 raw (trunc): {"champion": "Intracerebral hemorrhage", "rationale": "The patient's symptoms, including incomplete closure of the right eye, flattening of the right nasolabial fold, and right-sided hemiplegia, are consistent with a left-sided intracerebral hemorrhage, which is confirmed by the 

## Backbone v0 (compact)
- S1 key_facts: 66-year-old man; 24-hour history of symptoms; History of hypertension; No history of neurological disorders; Alert and oriented; Effacement of the right frontal wrinkle; Incomplete closure of the right eyelid; Muscle strength in the right upper and lower extremities: grade 0/5
- S2 mode=single k=1 pool_n=17 gold_in_s2=False
  - call1: ['Ischemic stroke', 'Intracerebral hemorrhage', 'Cerebral vasculitis', 'Moyamoya disease', 'Arteriovenous malformation',
- S3 shortlist n=5 gold=False: Ischemic stroke, Intracerebral hemorrhage, Cerebral vasculitis, Arteriovenous malformation, Cavernous angioma
- S4 champion: **Intracerebral hemorrhage** gold=False
- S4 raw (trunc): {"champion": "Intracerebral hemorrhage", "rationale": "The emergency CT scan of the head showed hemorrhage in the left thalamus-radiation crown region and in the lateral ventricle, which directly supports the diagnosis of intracerebral hemorrhage.", "rejected": [{"label": "Ischem

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's symptoms, including incomplete closure of the right eye, flattening of the right nasolabial fold, and right-sided hemiplegia, along with the imagi
  - turn1 gold_mention=False diag=
    The patient's presentation of incomplete eye closure, facial weakness, and hemiplegia, combined with imaging evidence of hemorrhage in the left thalamus and lat
  - turn2 gold_mention=False diag=
    The patient's symptoms and imaging studies align with a vascular event, supporting the prior opinions that a stroke, likely due to intracerebral hemorrhage, is 
- supervisor votes=3 top2=['Stroke', 'Intracerebral Hemorrhage'] gold=True

## Baseline B07
- draft=['Stroke', 'Thalamic Hemorrhage'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['stroke symptoms', 'thalamus hemorrhage', 'corticobulbar tract damage']
- diagnose=['Stroke', 'Thalamic Hemorrhage'] gold=True

## APHHM
- tree_n=17 tree_recall=True
- gold_leaf=B5.1:Stroke parent=B5
- final_n=2 final_recall=False ranking=['Intracerebral Hemorrhage', 'Thalamic hemorrhage']
- human_at1=False fail_mode=prune_loss

