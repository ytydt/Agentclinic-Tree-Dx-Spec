# MCR / mcr_v2 / case 237

- **gold**: Peripheral odontoma
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=172; gold_words=2; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 30-year-old man was referred for evaluation of an asymptomatic, calcified mass on the right anterior maxilla that had been present for 18 months. On intraoral examination, there was a mucosal fenestration through which a hard, mineralized structure approximately 1 cm in diameter was visible. A periapical radiograph of the upper right premolar area demonstrated a discrete radiopaque lesion. The initial diagnostic hypothesis was maxillary exostosis. An incisional biopsy was performed to remove a...

## Backbone e7
- S1 key_facts: 30-year-old man; asymptomatic mass; mass present for 18 months; location on right anterior maxilla; mucosal fenestration; hard, mineralized structure approximately 1 cm in diameter; discrete radiopaque lesion on periapical radiograph; incisional biopsy performed
- S2 mode=complement k=3 pool_n=43 gold_in_s2=True
  - call1: ['Odontoma', 'Maxillary exostosis', 'Mandibular torus', 'Compound odontoma', 'Complex odontoma', 'Dentigerous cyst', 'Pe
  - call2: ['Adenomatoid odontogenic tumor', 'Calcifying odontogenic cyst', 'Gorlin syndrome', 'Hyperparathyroidism-jaw tumor syndr
  - call3: ['Monostotic fibrous dysplasia', 'Ossifying fibroma of the jaw', 'Cemento-osseous dysplasia', 'Familial adenomatous poly
- S3 shortlist n=5 gold=True: Odontoma, Maxillary exostosis, Osteoma, Cemento-ossifying fibroma, Focal cemento-osseous dysplasia
- S4 champion: **Maxillary exostosis** gold=False
- S4 raw (trunc): {"champion": "Maxillary exostosis", "rationale": "The presence of a hard, mineralized structure and a discrete radiopaque lesion on the periapical radiograph, along with the location on the right anterior maxilla, supports the diagnosis of maxillary exostosis, which is a benign b

## Backbone v0 (compact)
- S1 key_facts: The patient is a 30-year-old man; The mass has been present for 18 months; The mass is located on the right anterior maxilla; The mass is asymptomatic; There is a mucosal fenestration; A hard, mineralized structure is visible through the fenestration; The structure is approximately 1 cm in diameter; A periapical radiograph shows a discrete radiopaque lesion
- S2 mode=single k=1 pool_n=16 gold_in_s2=False
  - call1: ['Maxillary exostosis', 'Compound odontoma', 'Complex odontoma', 'Periapical cemental dysplasia', 'Benign fibro-osseous 
- S3 shortlist n=5 gold=False: Maxillary exostosis, Compound odontoma, Complex odontoma, Periapical cemental dysplasia, Osteoma
- S4 champion: **Maxillary exostosis** gold=False
- S4 raw (trunc): {"champion": "Maxillary exostosis", "rationale": "The presence of a calcified, asymptomatic mass on the right anterior maxilla with a mucosal fenestration and a hard, mineralized structure visible through it, along with a discrete radiopaque lesion on the periapical radiograph, i

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Based on the presence of a calcified mass on the right anterior maxilla and the radiographic findings, the top diagnosis is maxillary exostosis, but other possi
  - turn1 gold_mention=True diag=
    The presence of a calcified, mineralized structure and radiopaque lesion supports the initial hypothesis of maxillary exostosis, with odontoma and osteoma as cl
  - turn2 gold_mention=True diag=
    The clinical presentation and radiographic findings align with the initial hypothesis of maxillary exostosis, while odontoma and osteoma remain as strong differ
- supervisor votes=3 top2=['Maxillary Exostosis', 'Odontoma'] gold=True

## Baseline B07
- draft=['Maxillary Exostosis', 'Dens Evaginatus'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['maxillary exostosis symptoms', 'maxillary exostosis diagnosis', 'calcified mass on maxilla', 'mucosal fenestration with mineralized structure']
- diagnose=['Maxillary Exostosis', 'Dens Evaginatus'] gold=False

## Baseline B01
- queries=['calcified mass on maxilla', 'mucosal fenestration with mineralized structure', 'radiopaque lesion in maxillary bone', 'differential diagnosis for maxillary exostosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Maxillary exostosis', 'Odontogenic keratocyst'] gold=False

