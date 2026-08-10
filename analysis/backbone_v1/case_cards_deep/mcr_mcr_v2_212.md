# MCR / mcr_v2 / case 212

- **gold**: Neurofibromatosis type 2
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_hit_judge_miss` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=308; gold_words=3; eponym=False; subtype=True; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
An 18-year-old Chinese woman noted a grey dot in the central vision of her left eye 4 days before presentation. She had a known plexiform neurofibroma of the arm confirmed by biopsy 1 year earlier; otherwise, she denied medical history, trauma, family history, smoking, coffee, tea, illicit drugs, or oral contraceptive use. Blood pressure was 110/70 mmHg. Visual acuity was 20/20 in the right eye and 20/25 in the left eye, with no relative afferent pupillary defect. Slit-lamp examination showed mi...

## Backbone e7
- S1 key_facts: 18-year-old Chinese woman; Known plexiform neurofibroma of the arm; No medical history, trauma, family history, smoking, coffee, tea, illicit drugs,; Blood pressure 110/70 mmHg; Visual acuity 20/20 in right eye and 20/25 in left eye; No relative afferent pupillary defect; Mild subcapsular cataracts bilaterally; Bilateral vestibular schwannomas on brain MRI
- S2 mode=complement k=3 pool_n=49 gold_in_s2=False
  - call1: ['Neurofibromatosis type 1', 'Optic neuritis', 'Papilledema', 'Central retinal artery occlusion', 'Branch retinal artery
  - call2: ['Eale disease', 'Purtscher retinopathy', 'Compressive optic neuropathy', 'Neurofibroma-related optic glioma', 'Choroida
  - call3: ['Pseudoxanthoma elasticum', 'Ehlers-Danlos syndrome', 'Marfan syndrome', 'Sturge-Weber syndrome', 'Klippel-Trenaunay-We
- S3 shortlist n=5 gold=False: Neurofibromatosis type 1, Paracentral acute middle maculopathy, Optic neuritis, Neurofibroma-related optic glioma, Multiple sclerosis
- S4 champion: **Neurofibromatosis type 1** gold=False
- S4 raw (trunc): {"champion": "Neurofibromatosis type 1", "rationale": "The patient has a known plexiform neurofibroma of the arm, bilateral vestibular schwannomas, and a parasellar mass consistent with a meningioma, which are all characteristic features of Neurofibromatosis type 1.", "rejected":

## Backbone v0 (compact)
- S1 key_facts: 18-year-old Chinese woman; Known plexiform neurofibroma of the arm; No medical history, trauma, family history, smoking, or illicit drug use; Visual acuity 20/20 in right eye and 20/25 in left eye; No relative afferent pupillary defect; Mild subcapsular cataracts bilaterally; Blood pressure 110/70 mmHg; Normal carotid Doppler ultrasound and transthoracic echocardiography
- S2 mode=single k=1 pool_n=18 gold_in_s2=False
  - call1: ['Neurofibromatosis type 1', 'Optic neuritis', 'Papilledema', 'Central retinal artery occlusion', 'Branch retinal artery
- S3 shortlist n=5 gold=False: Neurofibromatosis type 1, Paracentral acute middle maculopathy, Optic neuritis, Acute posterior multifocal placoid pigment epitheliopathy, Neuromyelitis optica
- S4 champion: **Neurofibromatosis type 1** gold=False
- S4 raw (trunc): {"champion": "Neurofibromatosis type 1", "rationale": "The patient has a known plexiform neurofibroma of the arm and bilateral vestibular schwannomas, a parasellar mass, and a cervical extramedullary lesion, which are characteristic features of Neurofibromatosis type 1.", "reject

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's known plexiform neurofibroma, bilateral vestibular schwannomas, and parasellar mass consistent with a meningioma are highly suggestive of a neurof
  - turn1 gold_mention=True diag=
    The patient's complex presentation with bilateral vestibular schwannomas, a parasellar mass, and a history of plexiform neurofibroma strongly supports a diagnos
  - turn2 gold_mention=True diag=
    The patient's known plexiform neurofibroma, bilateral vestibular schwannomas, and parasellar mass are highly suggestive of neurofibromatosis type 2, with ocular
- supervisor votes=3 top2=['Neurofibromatosis type 2', 'Paracentral acute middle maculopathy'] gold=True

## Baseline B07
- draft=['Neurofibromatosis Type 2', 'Neurofibromatosis Type 1'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['Neurofibromatosis type 1 and vision loss', 'Plexiform neurofibroma and eye symptoms', 'Bilateral vestibular schwannomas and meningioma diagnosis']
- diagnose=['Neurofibromatosis Type 2', 'Neurofibromatosis Type 1'] gold=True

## Baseline B01
- queries=['neurofibromatosis type 1 and vision loss', 'paracentral acute middle maculopathy causes', 'optic disc swelling and grey-white retinal lesions', 'plexiform neurofibroma and associated ocular findings']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Neurofibromatosis type 1', 'Paracentral acute middle maculopathy'] gold=False

