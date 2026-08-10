# MCR / mcr_200b / case 345

- **gold**: Hereditary hypophosphatemic rickets with hypercalciuria
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; recalled_but_none_correct
- **covariates**: vig_words=254; gold_words=5; eponym=False; subtype=True; e7_s2_rank=4; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 32-year-old Caucasian woman presents with severe left knee pain and bilateral genu valgum deformity. She recalls being told she “may have had rickets” at age 9 but was lost to follow-up. At 22, she had trochanteric bursitis and an X-ray showed a Q-angle of 17°; no metabolic evaluation was done. She takes OTC vitamin D3 without calcium. She is 155 cm tall, weighs 58.5 kg (BMI 23.8), with no personal or family history of fractures or metabolic bone disease.  On exam, there is marked bilateral va...

## Backbone e7
- S1 key_facts: Patient is a 32-year-old Caucasian woman; Patient has severe left knee pain; Patient has bilateral genu valgum deformity; Patient had trochanteric bursitis at age 22; Patient takes OTC vitamin D3 without calcium; Patient's height is 155 cm and weight is 58.5 kg; Patient's BMI is 23.8; Patient has no personal or family history of fractures or metabolic bone disease
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['X-linked hypophosphatemia', 'Autosomal dominant hypophosphatemic rickets', 'Autosomal recessive hypophosphatemic ricke
  - call2: ['Epidermal nevus syndrome', 'Linear nevus sebaceous syndrome', 'Osteoglophonic dysplasia', 'Raine syndrome', 'Gorham-St
  - call3: ['Fibrodysplasia ossificans progressiva', 'Progressive osseous heteroplasia', 'Ehlers-Danlos syndrome', 'Marfan syndrome
- S3 shortlist n=5 gold=True: Hypophosphatemic rickets with nephrocalcinosis, X-linked hypophosphatemia, Hereditary hypophosphatemic rickets with hypercalciuria, Autosomal dominant hypophosphatemic rickets, Dent disease
- S4 champion: **Hypophosphatemic rickets with nephrocalcinosis** gold=False
- S4 raw (trunc): {"champion": "Hypophosphatemic rickets with nephrocalcinosis", "rationale": "The patient's presentation of severe knee pain, bilateral genu valgum deformity, low serum phosphate, elevated vitamin D levels, and bilateral medullary nephrocalcinosis without stones is most consistent

## Backbone v0 (compact)
- S1 key_facts: Patient is a 32-year-old woman; Patient has severe left knee pain; Patient has bilateral genu valgum deformity; Patient had trochanteric bursitis at age 22; Patient takes OTC vitamin D3 without calcium; Patient's Q-angle was 17° at age 22 and 23° currently; Patient has osteopenia of the left femoral head; Patient has normal lumbar spine density
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['X-linked hypophosphatemia', 'Autosomal dominant hypophosphatemic rickets', 'Autosomal recessive hypophosphatemic ricke
- S3 shortlist n=5 gold=True: X-linked hypophosphatemia, Hereditary hypophosphatemic rickets with hypercalciuria, Autosomal dominant hypophosphatemic rickets, Dent disease, Vitamin D-dependent rickets type 1
- S4 champion: **X-linked hypophosphatemia** gold=False
- S4 raw (trunc): {"champion": "X-linked hypophosphatemia", "rationale": "The patient's presentation of bilateral genu valgum deformity, low serum phosphate, and history suggestive of rickets, along with the laboratory findings of low serum phosphate, elevated vitamin D levels, and low parathyroid

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of possible rickets, bilateral genu valgum deformity, and laboratory findings of hypophosphatemia, elevated vitamin D levels, and low para
  - turn1 gold_mention=True diag=
    The patient's presentation of severe left knee pain, bilateral genu valgum deformity, and laboratory findings of hypophosphatemia, elevated vitamin D levels, an
  - turn2 gold_mention=True diag=
    The patient's history and laboratory findings are consistent with hypophosphatemic rickets, and the undetectable FGF23 levels may suggest a specific subtype suc
- supervisor votes=3 top2=['Hypophosphatemic rickets', 'Hereditary hypophosphatemic rickets with hypercalciuria'] gold=True

## Baseline B07
- draft=['Hereditary Hypophosphatemic Rickets', 'Familial Hypomagnesemia with Hypercalciuria and Nephrocalcinosis (FHHNC)'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['hypophosphatemic rickets', 'vitamin D metabolism disorders', 'FGF23-related disorders', 'medullary nephrocalcinosis']
- diagnose=['Hereditary Hypophosphatemic Rickets', 'Familial Hypomagnesemia with Hypercalciuria and Nephrocalcinosis (FHHNC)'] gold=True

## Baseline B01
- queries=['hypophosphatemia with elevated vitamin D levels', 'bilateral genu valgum deformity and osteopenia', 'inappropriately normal phosphate excretion with hypophosphatemia', 'medullary nephrocalcinosis with normal urine calcium']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Hypophosphatemic Rickets', 'Familial Hypomagnesemia with Hypercalciuria and Nephrocalcinosis (FHHNC)'] gold=True

