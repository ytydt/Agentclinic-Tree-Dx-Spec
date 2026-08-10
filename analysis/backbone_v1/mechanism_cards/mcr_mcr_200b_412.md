# MCR / mcr_200b / case 412

- **gold**: External cervical resorption
- **layer**: `e7_win_rank` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination was unremarkable. Intraorally, there was generalized bleeding on probing and clinical attachment loss; radiographs showed generalized alveolar bone loss consistent with stage II, grade II periodontitis. Periapical radiographs of the maxillary central incisors revealed cervical areas of rarefaction. On endodontic evaluation, both central incisors were normal in color, responded normally to cold testing, and were asymptomatic to percussion and palpation. A 5 mm probing depth was recorded on the palatal aspects of both teeth. Two additional periapical radiographs with mesial and distal angulation showed that the lesion’s projection remained in the same position relative to the canal and that the canal outline was undisturbed. Cone-beam computed tomography demonstrated radiolucent resorptive lesions cervically on the palatal aspects of teeth #11 and #21, originating from the external palatal surface and perforating into the pulp space. The diagnosis for both central incisors was asymptomat…

## Backbone e7

- S2 n=54 gold_rank=1
  - clusters: gold=1 near=1 other=52
- S3 shortlist (5):
  - [gold] External Cervical Resorption
  - [other] Asymptomatic Irreversible Pulpitis
  - [other] Periodontitis
  - [near] Internal Cervical Resorption
  - [other] Pulpal Necrosis
    - why_kept(External Cervical Resorption): radiographic evidence of cervical areas of rarefaction and cone-beam computed tomography demonstrated radiolucent resorptive lesions
    - why_kept(Asymptomatic Irreversible Pulpitis): endodontic evaluation was normal for both central incisors and presence of radiolucent resorptive lesions
    - why_kept(Periodontitis): generalized bleeding on probing, clinical attachment loss, and stage II, grade II periodontitis
    - why_kept(Internal Cervical Resorption): possibility of resorptive lesions originating from internal tooth structure
    - why_kept(Pulpal Necrosis): potential consequence of asymptomatic irreversible pulpitis and external cervical resorption
- S4 champion: **External Cervical Resorption** cluster=gold jaccard=1.00
- S4 rationale: The cone-beam computed tomography demonstrated radiolucent resorptive lesions cervically on the palatal aspects of teeth, which originated from the external palatal surface and perforated into the pulp space, consistent with external cervical resorption.
- S4 rejected:
  - [other] Asymptomatic Irreversible Pulpitis: Normal response to cold testing and lack of symptoms contradict this diagnosis
  - [other] Periodontitis: While the patient has stage II, grade II periodontitis, it does not explain the cervical areas of rarefaction and radiolucent resorptive lesions
  - [near] Internal Cervical Resorption: The lesions originated from the external palatal surface, not from within the tooth
  - [other] Pulpal Necrosis: The endodontic evaluation was normal for both central incisors, and there were no signs of pulpal necrosis

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption', 'Periodontitis', 'Gingivitis', 'Dental Caries', 'Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption', 'Periodontitis']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Asymptomatic Irreversible Pulpitis with Normal Apical Tissues', 'External Cervical Resorption']
- diagnose: ['Asymptomatic Irreversible Pulpitis with Normal Apical Tissues', 'External Cervical Resorption']
- queries: ['A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination ', 'differential diagnosis A 55-year-old woman presented with generalized gum bleeding and halitosis. Her medical history was noncontributory, and she had undergone orthodontic treatment 18 years earlier. Extraoral examination ', 'clinical manifestations diagnosis  the maxillary central incisors revealed cervical areas of rarefaction. On endodontic evaluation, both central incisors were normal in color, responded normally']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Asymptomatic Irreversible Pulpitis', 'External Cervical Resorption']
- queries: ['external cervical resorption diagnosis', 'asymptomatic irreversible pulpitis treatment', 'periodontitis stage II grade II management', 'cervical resorptive lesions differential diagnosis']
- n_chunks=12

## APHHM
_na_

