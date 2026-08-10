# MCR / mcr_v1 / case 78

- **gold**: schwannoma
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_miss_but_scored_ok` B01=`rag_miss` APHHM=`final_hit_judge_miss`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=218; gold_words=1; eponym=False; subtype=False; e7_s2_rank=2; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 35-year-old woman presented with an 8-month history of radicular pain radiating from her lower back down the left leg, with occasional tingling. The pain progressively worsened and was particularly severe by August. She denied any weakness, autonomic symptoms, history of trauma, or injury. On examination, she had mild hypesthesia in the left L5–S1 dermatome but normal muscle strength, normal abduction and adduction, and negative Lasègue, Kernig, Bragard, and Sicard signs. Electromyography show...

## Backbone e7
- S1 key_facts: 8-month history of radicular pain; Pain radiates from lower back down the left leg; Occasional tingling; No weakness or autonomic symptoms; No history of trauma or injury; Mild hypesthesia in the left L5–S1 dermatome; Normal muscle strength; Negative Lasègue, Kernig, Bragard, and Sicard signs
- S2 mode=complement k=3 pool_n=44 gold_in_s2=True
  - call1: ['Neurofibroma', 'Schwannoma', 'Malignant peripheral nerve sheath tumor', 'Plexiform neurofibroma', 'Perineurioma', 'Lip
  - call2: ['Ancient schwannoma', 'Cellular schwannoma', 'Melanotic schwannoma', 'Plexiform schwannoma', 'Hybrid neurofibroma/schwa
  - call3: ['Neurothekeoma', 'Granular cell tumor', 'Desmoid tumor', 'Aggressive fibromatosis', 'Nerve sheath fibrosarcoma', 'Intra
- S3 shortlist n=5 gold=True: Schwannoma, Neurofibroma, Tarlov cyst, Ganglion cyst, Plexiform neurofibroma
- S4 champion: **Tarlov cyst** gold=False
- S4 raw (trunc): {"champion": "Tarlov cyst", "rationale": "The patient's presentation of radicular pain and the imaging findings of a solitary, completely cystic mass in the left L5–S1 foraminal zone that is hypointense on T1-weighted images and hyperintense on T2-weighted images, with peripheral

## Backbone v0 (compact)
- S1 key_facts: 8-month history of radicular pain; Pain radiates from lower back down the left leg; Occasional tingling; No weakness or autonomic symptoms; No history of trauma or injury; Mild hypesthesia in the left L5–S1 dermatome; Normal muscle strength; Negative Lasègue, Kernig, Bragard, and Sicard signs
- S2 mode=None k=None pool_n=16 gold_in_s2=True
  - pool gold matches: ['Schwannoma']
  - pool head: Neurofibroma, Schwannoma, Malignant peripheral nerve sheath tumor, Plexiform neurofibroma, Perineurioma, Lipomatosis of nerve, Neurilemmoma, Ganglioneuroma
- S3 shortlist n=5 gold=True: Schwannoma, Neurofibroma, Tarlov cyst, Plexiform neurofibroma, Intraneural ganglion cyst
- S4 champion: **Intraneural ganglion cyst** gold=False
- S4 raw (trunc): {"champion": "Intraneural ganglion cyst", "rationale": "The patient's presentation of radicular pain and tingling, along with the MRI findings of a solitary, completely cystic mass in the left L5–S1 foraminal zone that is hypointense on T1-weighted images and hyperintense on T2-w

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of radicular pain and the imaging findings of a cystic mass along the course of the sciatic nerve are most consistent with a nerve sh
  - turn1 gold_mention=True diag=
    The patient's symptoms and imaging findings, including the cystic nature of the mass and its association with the sciatic nerve, align with the characteristics 
  - turn2 gold_mention=True diag=
    The patient's presentation and imaging findings are consistent with a nerve sheath tumor, with schwannoma and neurofibroma being top considerations due to their
- supervisor votes=3 top2=['Schwannoma', 'Neurofibroma'] gold=True

## Baseline B07
- draft=['Peripheral Nerve Sheath Tumor (PNST)', 'Neurofibroma'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['solitary cystic mass in foraminal zone', 'sciatic nerve tumor', 'peripheral nerve sheath tumor', 'neuropathic irritation of nerve roots']
- diagnose=['Peripheral Nerve Sheath Tumor (PNST)', 'Neurofibroma'] gold=False

## Baseline B01
- queries=['cystic masses in the lumbar spine', 'sciatic nerve tumors', 'peripheral nerve sheath tumors', 'foraminal cystic lesions causing radiculopathy']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Peroneal nerve sheath tumor', 'Neurofibroma'] gold=False

## APHHM
- tree_n=25 tree_recall=True
- gold_leaf=B1.1:Schwannoma parent=B1
- final_n=2 final_recall=True ranking=['intraneural ganglion cyst', 'sciatic schwannoma']
- human_at1=False fail_mode=final_ok

