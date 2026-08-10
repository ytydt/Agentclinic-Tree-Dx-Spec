# MCR / mcr_v2 / case 192

- **gold**: Neurosyphilis
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s2_hit_s3_drop; recalled_but_none_correct
- **covariates**: vig_words=363; gold_words=1; eponym=False; subtype=False; e7_s2_rank=11; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 36‐year‐old man of Indian origin presented at 2:30 a.m. with acute right‐sided weakness and three episodes of vomiting. He awoke around midnight with headache and vomiting, then noted right‐sided numbness and weakness; there was no visual change or speech disturbance. He had experienced odd sensations and occasional tremors in his right arm and leg over the prior two weeks but had not sought care. His medical history was unremarkable. He was a nonsmoker, denied alcohol or drug use, and worked ...

## Backbone e7
- S1 key_facts: 36-year-old man of Indian origin; Presented at 2:30 a.m. with acute symptoms; Awoke around midnight with headache and vomiting; No visual change or speech disturbance; History of odd sensations and occasional tremors in right arm and leg; No medical history; Nonsmoker, denied alcohol or drug use; Normal vital signs
- S2 mode=complement k=3 pool_n=47 gold_in_s2=True
  - call1: ['Ischemic stroke', 'Hemorrhagic stroke', 'Cerebral vasculitis', 'Reversible cerebral vasoconstriction syndrome', 'Caver
  - call2: ['Susac syndrome', 'Sneddon syndrome', 'Ehlers-Danlos syndrome type IV', 'Pseudoxanthoma elasticum', 'Neurofibromatosis 
  - call3: ['Rendu-Osler-Weber disease', 'Wyburn-Mason syndrome', 'Hereditary hemorrhagic telangiectasia', 'Capillary telangiectasi
- S3 shortlist n=5 gold=False: Ischemic stroke, Cerebral vasculitis, Reversible cerebral vasoconstriction syndrome, Cavernous malformation, Central nervous system vasculitis
- S4 champion: **Ischemic stroke** gold=False
- S4 raw (trunc): {"champion": "Ischemic stroke", "rationale": "The patient presented with acute right-sided weakness and vomiting, and brain MRI showed a recent ischemic infarction in the left paramedian medulla, which explains the key facts without contradiction.", "rejected": [{"label": "Cerebr

## Backbone v0 (compact)
- S1 key_facts: 36-year-old man of Indian origin; Presented at 2:30 a.m. with acute symptoms; Awoke around midnight with headache and vomiting; Noted right-sided numbness and weakness; No visual change or speech disturbance; Experienced odd sensations and occasional tremors in right arm and leg over prio; Pulse was 88 bpm; Blood pressure 124/87 mmHg
- S2 mode=single k=1 pool_n=17 gold_in_s2=False
  - call1: ['Lateral Medullary Syndrome', 'Medial Medullary Syndrome', 'Wallenberg Syndrome', 'Cavernous Malformation', 'Arterioven
- S3 shortlist n=5 gold=False: Wallenberg Syndrome, Lateral Medullary Syndrome, Cavernous Malformation, Medial Medullary Syndrome, Central Nervous System Vasculitis
- S4 champion: **Lateral Medullary Syndrome** gold=False
- S4 raw (trunc): {"champion": "Lateral Medullary Syndrome", "rationale": "The patient's symptoms, including acute right-sided weakness, numbness, partial left ptosis, bilateral torsional nystagmus, and right ankle clonus, are consistent with a lesion in the lateral medulla, which is a characteris

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation with acute right-sided weakness and vomiting, along with the findings of a recent ischemic infarction in the left paramedian medulla 
  - turn1 gold_mention=False diag=
    Agreeing with Doctor A, the clinical presentation and imaging findings strongly support ischemic stroke, with the need for further investigation into the etiolo
  - turn2 gold_mention=False diag=
    The patient's clinical presentation and imaging findings are consistent with ischemic stroke, and the presence of a cavernoma may be an incidental finding or a 
- supervisor votes=3 top2=['Ischemic Stroke', 'Cavernous Malformation'] gold=False

## Baseline B07
- draft=['Ischemic Stroke', 'Cavernoma-related Stroke'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['stroke in young adults', 'medullary infarction causes', 'cavernoma and stroke', 'stroke with no apparent risk factors']
- diagnose=['Ischemic Stroke', 'Cavernoma-related Stroke'] gold=False

## Baseline B01
- queries=['young adult ischemic stroke causes', 'medullary infarction symptoms and diagnosis', 'stroke in patients with no traditional risk factors', 'cavernoma and stroke association']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Ischemic stroke', 'Medullary infarction'] gold=False

