# MCR / mcr_200b / case 257

- **gold**: collar button abscess
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=163; gold_words=3; eponym=False; subtype=False; e7_s2_rank=5; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 66-year-old man with type 2 diabetes (HbA1c 11.2%) presented with a one-week history of worsening right hand pain, swelling, and erythema, most prominent in the distal palm. Two weeks earlier, a concrete bench had fallen on the dorsal base of his right fourth digit without skin break; over the following week, he noted a bruise at that site. On examination, there was a 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, with focal tenderness ...

## Backbone e7
- S1 key_facts: 66-year-old man with type 2 diabetes; HbA1c 11.2%; One-week history of worsening right hand pain, swelling, and erythema; Trauma to the dorsal base of the right fourth digit two weeks prior; Bruise at the site of trauma; 1.5-cm painful, fluctuant mass on examination; Focal tenderness over the flexor sheath; Limited active digit motion
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Pyogenic flexor tenosynovitis', 'Septic arthritis', 'Osteomyelitis', 'Cellulitis', 'Abscess', 'Ganglion cyst infection
  - call2: ['Sporotrichosis', 'Mycobacterium marinum infection', 'Nocardiosis', 'Actinomycosis', 'Eumycotic mycetoma', 'Chronic gra
  - call3: ['Tuberculous tenosynovitis', 'Brucellar tenosynovitis', 'Fungal tenosynovitis', 'Sporotrichoid lymphocutaneous infectio
- S3 shortlist n=5 gold=True: Pyogenic flexor tenosynovitis, Abscess, Cellulitis, Septic arthritis, Necrotizing fasciitis
- S4 champion: **Pyogenic flexor tenosynovitis** gold=False
- S4 raw (trunc): {"champion": "Pyogenic flexor tenosynovitis", "rationale": "The patient's presentation of a painful, fluctuant mass extending from the palmar web space to the A2 pulley of the fourth digit, with focal tenderness over the flexor sheath and limited active digit motion, is highly su

## Backbone v0 (compact)
- S1 key_facts: 66-year-old man with type 2 diabetes; HbA1c 11.2%; One-week history of worsening right hand pain, swelling, and erythema; Trauma to the dorsal base of the right fourth digit two weeks prior; Bruise at the site of trauma; 1.5-cm painful, fluctuant mass extending from the palmar web space to the A2 pul; Focal tenderness over the flexor sheath; Limited active digit motion
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Pyogenic flexor tenosynovitis', 'Septic arthritis', 'Osteomyelitis', 'Cellulitis', 'Abscess', 'Ganglion cyst infection
- S3 shortlist n=5 gold=True: Pyogenic flexor tenosynovitis, Septic arthritis, Abscess, Cellulitis, Deep space infection of the hand
- S4 champion: **Pyogenic flexor tenosynovitis** gold=False
- S4 raw (trunc): {"champion": "Pyogenic flexor tenosynovitis", "rationale": "The presence of a painful, fluctuant mass extending from the palmar web space to the A2 pulley, focal tenderness over the flexor sheath, and limited active digit motion are highly suggestive of pyogenic flexor tenosynovi

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of a painful, fluctuant mass with focal tenderness over the flexor sheath, limited active digit motion, and elevated WBC count sugges
  - turn1 gold_mention=True diag=
    The patient's symptoms and examination findings, including the painful, fluctuant mass and elevated WBC count, are consistent with an infectious process, and th
  - turn2 gold_mention=True diag=
    The patient's presentation and history of trauma, along with the physical examination findings and laboratory results, support Pyogenic Flexor Tenosynovitis as 
- supervisor votes=3 top2=['Pyogenic Flexor Tenosynovitis', 'Abscess'] gold=True

## Baseline B07
- draft=['Pyogenic Flexor Tenosynovitis', 'Hand Deep Space Infection'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['infections of the hand in diabetic patients', 'flexor tenosynovitis diagnosis', 'diagnosis of pyogenic flexor tenosynovitis']
- diagnose=['Pyogenic Flexor Tenosynovitis', 'Hand Deep Space Infection'] gold=False

## Baseline B01
- queries=['diagnosis of hand pain and swelling after trauma in diabetic patients', 'infections of the flexor tendon sheath', 'diagnostic criteria for pyogenic flexor tenosynovitis', 'differential diagnosis of fluctuant mass in the hand']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Pyogenic Flexor Tenosynovitis', 'Infectious Tenosynovitis'] gold=False

