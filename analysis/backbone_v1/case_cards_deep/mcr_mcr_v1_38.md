# MCR / mcr_v1 / case 38

- **gold**: trigeminal schwannoma
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`gen_hit_judge_miss` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=draft_miss
- **covariates**: vig_words=277; gold_words=2; eponym=False; subtype=False; e7_s2_rank=10; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A 33-year-old man with no significant past medical history presented with a 3-month history of progressively worsening occipital headache, exacerbated by Valsalva maneuvers. On neurologic examination, he had bilateral past-pointing and an intention tremor. Brain MRI revealed a 6.9 × 5.5 × 6.1 cm lobulated mass centered at the left cerebellopontine angle, extending craniocaudally from the left ambient cistern to the premedullary space. The lesion involved and expanded Meckel’s cave, with a small ...

## Backbone e7
- S1 key_facts: 3-month history of worsening symptoms; Headache exacerbated by Valsalva maneuvers; Bilateral past-pointing on neurologic examination; Intention tremor on neurologic examination; 6.9 × 5.5 × 6.1 cm mass centered at the left cerebellopontine angle; Mass extends craniocaudally from the left ambient cistern to the premedullary sp; Involvement and expansion of Meckel’s cave; Small extension into the left infratemporal fossa via the foramen ovale
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Vestibular schwannoma', 'Meningioma', 'Epidermoid cyst', 'Arachnoid cyst', 'Chordoma', 'Chondrosarcoma', 'Hemangioma',
  - call2: ['Pilocytic astrocytoma', 'Ganglioglioma', 'Hemangioblastoma', 'Papillary craniopharyngioma', 'Rhabdoid tumor', 'Atypica
  - call3: ['Pleomorphic xanthoastrocytoma', 'Anaplastic pleomorphic xanthoastrocytoma', 'Gliosarcoma', 'Primitive neuroectodermal 
- S3 shortlist n=5 gold=True: Vestibular schwannoma, Meningioma, Trigeminal schwannoma, Chordoma, Epidermoid cyst
- S4 champion: **Trigeminal schwannoma** gold=True
- S4 raw (trunc): {"champion": "Trigeminal schwannoma", "rationale": "The tumor's location centered at the left cerebellopontine angle, involvement and expansion of Meckel's cave, and extension into the left infratemporal fossa via the foramen ovale are consistent with a trigeminal schwannoma, whi

## Backbone v0 (compact)
- S1 key_facts: 3-month history of worsening symptoms; Headache exacerbated by Valsalva maneuvers; Bilateral past-pointing on neurologic examination; Intention tremor on neurologic examination; 6.9 × 5.5 × 6.1 cm mass centered at the left cerebellopontine angle; Mass extends craniocaudally from the left ambient cistern to the premedullary sp; Involvement and expansion of Meckel’s cave; Small extension into the left infratemporal fossa via the foramen ovale
- S2 mode=None k=None pool_n=18 gold_in_s2=True
  - pool gold matches: ['Trigeminal schwannoma']
  - pool head: Vestibular schwannoma, Meningioma, Epidermoid cyst, Arachnoid cyst, Chordoma, Chondrosarcoma, Hemangioma, Lipoma
- S3 shortlist n=5 gold=True: Vestibular schwannoma, Meningioma, Trigeminal schwannoma, Cystic meningioma, Epidermoid cyst
- S4 champion: **Trigeminal schwannoma** gold=True
- S4 raw (trunc): {"champion": "Trigeminal schwannoma", "rationale": "The tumor's location centered at the left cerebellopontine angle, involvement and expansion of Meckel's cave, and extension into the left infratemporal fossa via the foramen ovale are consistent with a trigeminal schwannoma, whi

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with a cerebellopontine angle mass and associated neurological symptoms, along with the imaging characteristics, suggests a schwannom
  - turn1 gold_mention=True diag=
    The patient's presentation and imaging characteristics align with Doctor A's assessment, with schwannoma being the most likely diagnosis due to the lobulated ma
  - turn2 gold_mention=True diag=
    The patient's presentation with a cerebellopontine angle mass, associated neurological symptoms, and imaging characteristics showing a lobulated mass with cysti
- supervisor votes=3 top2=['Schwannoma', 'Meningioma'] gold=True

## Baseline B07
- draft=['Chordoma', 'Chondrosarcoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['cerebellopontine angle tumor', "Meckel's cave involvement", 'lobulated mass with cystic and solid components', 'hemorrhagic foci in brain tumor']
- diagnose=['Chordoma', 'Chondrosarcoma'] gold=False

## Baseline B01
- queries=['cerebellopontine angle mass with cystic and solid components', "Meckel's cave involvement with multiloculated cystic areas", 'cranial nerve compression with intention tremor and past-pointing', 'petrous apex erosion with calcifications and hemorrhagic foci']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Chordoma', 'Schwannoma'] gold=True

## APHHM
- tree_n=34 tree_recall=True
- gold_leaf=B3.3:Schwannoma parent=B3
- final_n=5 final_recall=False ranking=['Meningioma', 'Meningioma', 'Chordoma', 'Meningioma', 'Meningioma']
- human_at1=False fail_mode=prune_loss

