# MCR / mcr_200b / case 412

- **gold**: External cervical resorption
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=diagnose_hit_judge_miss
- **covariates**: vig_words=246; gold_words=3; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: layer=e7_win_rank; primary loci above.

## Vignette (trunc)
A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination was unremarkable. Intraorally, there was generalized bleeding on probing and clinical attachment loss; radiographs showed generalized alveolar bone loss consistent with stage II, grade II periodontitis. Periapical radiographs of the maxillary central incisors revealed cervical areas of rarefaction. ...

## Backbone e7
- S1 key_facts: 55-year-old woman; generalized bleeding on probing; clinical attachment loss; stage II, grade II periodontitis; periapical radiographs showed cervical areas of rarefaction; endodontic evaluation was normal for both central incisors; 5 mm probing depth on palatal aspects of both teeth; cone-beam computed tomography demonstrated radiolucent resorptive lesions
- S2 mode=complement k=3 pool_n=54 gold_in_s2=True
  - call1: ['External Cervical Resorption', 'Internal Cervical Resorption', 'Acute Apical Abscess', 'Chronic Apical Abscess', 'Asym
  - call2: ['Periostitis', 'Scleroderma', 'Ehlers-Danlos Syndrome', 'Papillon-Lefevre Syndrome', 'Histiocytosis', 'Langerhans Cell 
  - call3: ['Fibrous Dysplasia', 'Cherubism', 'Pindborg Tumor', 'Adenomatoid Odontogenic Tumor', 'Squamous Odontogenic Tumor', 'Cal
- S3 shortlist n=5 gold=True: External Cervical Resorption, Asymptomatic Irreversible Pulpitis, Periodontitis, Internal Cervical Resorption, Pulpal Necrosis
- S4 champion: **External Cervical Resorption** gold=True
- S4 raw (trunc): {"champion": "External Cervical Resorption", "rationale": "The cone-beam computed tomography demonstrated radiolucent resorptive lesions cervically on the palatal aspects of teeth, which originated from the external palatal surface and perforated into the pulp space, consistent w

## Backbone v0 (compact)
- S1 key_facts: 55-year-old woman; generalized bleeding on probing; clinical attachment loss; stage II, grade II periodontitis; periapical radiographs showed cervical areas of rarefaction; endodontic evaluation was normal for both central incisors; 5 mm probing depth on palatal aspects of both teeth; cone-beam computed tomography demonstrated radiolucent resorptive lesions
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['External Cervical Resorption', 'Internal Cervical Resorption', 'Asymptomatic Irreversible Pulpitis', 'Chronic Periodon
- S3 shortlist n=5 gold=True: External Cervical Resorption, Chronic Periodontitis, Asymptomatic Irreversible Pulpitis, Internal Cervical Resorption, Periodontal Abscess
- S4 champion: **External Cervical Resorption** gold=True
- S4 raw (trunc): {"champion": "External Cervical Resorption", "rationale": "The cone-beam computed tomography demonstrated radiolucent resorptive lesions cervically on the palatal aspects of teeth, which originated from the external palatal surface and perforated into the pulp space, consistent w

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms and radiographic findings are consistent with asymptomatic irreversible pulpitis and external cervical resorption, with periodontitis and
  - turn1 gold_mention=True diag=
    Agree with Doctor A, clinical and radiographic findings support asymptomatic irreversible pulpitis and external cervical resorption, with periodontitis and ging
  - turn2 gold_mention=True diag=
    The patient's presentation of generalized gum bleeding, halitosis, and radiographic findings of generalized alveolar bone loss and cervical areas of rarefaction
- supervisor votes=3 top2=['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption'] gold=True

## Baseline B07
- draft=['Asymptomatic Irreversible Pulpitis with Normal Apical Tissues', 'External Cervical Resorption'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination ', 'differential diagnosis A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination ', 'clinical manifestations diagnosis  the maxillary central incisors revealed cervical areas of rarefaction. On endodontic evaluation, both central incisors were normal in color, responded normally']
- diagnose=['Asymptomatic Irreversible Pulpitis with Normal Apical Tissues', 'External Cervical Resorption'] gold=True

## Baseline B01
- queries=['external cervical resorption diagnosis', 'asymptomatic irreversible pulpitis treatment', 'periodontitis stage II grade II management', 'cervical resorptive lesions differential diagnosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption'] gold=True

