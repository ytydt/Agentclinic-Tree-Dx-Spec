# MCR / mcr_v2 / case 197

- **gold**: Pseudoseptic arthritis
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=203; gold_words=2; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 61-year-old African American woman with bilateral knee osteoarthritis presented three days after her third weekly Synvisc viscosupplementation injections in each knee with acute bilateral knee swelling and pain, left greater than right. She reported onset of pain 12 hours after the injections and denied fever, chills, or malaise. On examination, her right knee had a suprapatellar effusion, range of motion 0–70°, no erythema, and no pain with micromotion. Her left knee had a moderate suprapatel...

## Backbone e7
- S1 key_facts: 61-year-old African American woman; Bilateral knee osteoarthritis; Third weekly Synvisc viscosupplementation injections in each knee; Onset of pain 12 hours after injections; No fever, chills, or malaise; Right knee had a suprapatellar effusion and range of motion 0–70°; Left knee had a moderate suprapatellar effusion and range of motion 0–30°; Pain with micromotion in the left knee
- S2 mode=complement k=3 pool_n=50 gold_in_s2=True
  - call1: ['Septic arthritis', 'Crystal-induced arthritis', 'Rheumatoid arthritis', 'Psoriatic arthritis', 'Gout', 'Pseudogout', '
  - call2: ['Eosinophilic synovitis', 'Foreign body-induced synovitis', 'Milwaukee shoulder syndrome', 'Hyaluronic acid-induced inf
  - call3: ['Relapsing seronegative symmetrical synovitis with pitting edema', 'Sjögren syndrome', 'Mixed connective tissue disease
- S3 shortlist n=5 gold=True: Septic arthritis, Viscosupplementation-related inflammatory reaction, Crystal-induced arthritis, Pseudogout, Hypersensitivity reaction to Synvisc
- S4 champion: **Viscosupplementation-related inflammatory reaction** gold=False
- S4 raw (trunc): {"champion": "Viscosupplementation-related inflammatory reaction", "rationale": "The patient presented with acute bilateral knee swelling and pain after receiving Synvisc viscosupplementation injections, with elevated synovial fluid WBC counts but negative gram stains and culture

## Backbone v0 (compact)
- S1 key_facts: 61-year-old African American woman; Bilateral knee osteoarthritis; Third weekly Synvisc viscosupplementation injections; Onset of pain 12 hours after injections; No fever, chills, or malaise; Peripheral white blood cell count of 12.8×10^3/mm³; C-reactive protein level of 159 mg/L; Erythrocyte sedimentation rate of 79 mm/hr
- S2 mode=single k=1 pool_n=16 gold_in_s2=True
  - call1: ['Septic arthritis', 'Crystal-induced arthritis', 'Rheumatoid arthritis', 'Psoriatic arthritis', 'Gout', 'Pseudogout', '
- S3 shortlist n=5 gold=True: Septic arthritis, Viscosupplementation-related inflammatory reaction, Crystal-induced arthritis, Gonococcal arthritis, Pseudogout
- S4 champion: **Viscosupplementation-related inflammatory reaction** gold=False
- S4 raw (trunc): {"champion": "Viscosupplementation-related inflammatory reaction", "rationale": "The patient's symptoms of acute bilateral knee swelling and pain started 12 hours after the Synvisc viscosupplementation injections, and the laboratory results show elevated inflammatory markers with

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's recent history of Synvisc viscosupplementation injections and the presence of acute bilateral knee swelling and pain, the most likely diagno
  - turn1 gold_mention=True diag=
    The patient's presentation with acute bilateral knee swelling and pain following Synvisc injections, along with the laboratory and synovial fluid results, suppo
  - turn2 gold_mention=True diag=
    The patient's symptoms and laboratory results, including the high WBC count in the synovial fluid, are consistent with Pseudoseptic Arthritis, which is a known 
- supervisor votes=3 top2=['Pseudoseptic Arthritis', 'Septic Arthritis'] gold=True

## Baseline B07
- draft=['Aseptic inflammatory reaction to Synvisc injections', 'Septic arthritis'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['Synvisc viscosupplementation injection complications', 'septic arthritis vs aseptic inflammatory reaction', 'knee osteoarthritis treatment side effects']
- diagnose=['Aseptic inflammatory reaction to Synvisc injections', 'Septic arthritis'] gold=True

## Baseline B01
- queries=['septic arthritis vs aseptic inflammatory reaction after viscosupplementation injections', 'causes of acute knee swelling and pain after intra-articular injections', 'diagnostic criteria for septic arthritis in the setting of recent joint injection', 'differential diagnosis of knee effusion with elevated white blood cell count and negative cultures']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Septic Arthritis', 'Aseptic Inflammatory Reaction'] gold=True

