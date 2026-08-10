# DA / d2_heldout100 / case 382

- **gold**: Genital porokeratosis (GP)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=1 B01= APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A man in his 40s presented with a 10-year history of pruritic lesions on the scrotum and buttock. He was previously treated at a local clinic with little improvement. He had no relevant medical history and no family history of similar skin problems.

Scattered, well-defined, annular gray hyperkeratotic plaques with an atrophic center and a slightly elevated edge on the scrotum, buttock, groin, and intergluteal cleft. There was no inguinal adenopathy.

{'Laboratory Tests': 'Routine blood work, including blood biochemistry, syphilis serologies, and HIV testing, were normal or negative.', 'Histopathological Examination': {'Specimens': 'Two specimens taken from the scrotum and buttock', 'Findings': 'Revealed hyperkeratosis, irregular papillomatosis, parakeratotic columns (cornoid lamella) overlying dyskeratotic keratinocytes, and hypogranulosis with a perivascular infiltration of lymphocytes in the dermis', 'Images': {'Figure 1A': 'Clinical photograph showing scattered, well-defined, annular gray hyperkeratotic plaques with an atrophic center with a slightly elevated edge on the scrotum, buttock, groin, and intergluteal cleft', 'Figure 1B': 'Biopsy findings showing hyperkeratosis, irre…

## Options
- A: Porokeratosis of Mibelli
- B: Porokeratosis Ptychotropica
- C: Genital porokeratosis (GP) **←gold**
- D: Classic Porokeratosis (Mibelli Type)

## Backbone e7

- S2 n=43 gold_rank=13
  - clusters: gold=1 near=2 other=40
- S3 shortlist (5):
  - [other] Darier's disease
  - [other] Grover's disease
  - [gold] Porokeratosis
  - [other] Lichen simplex chronicus
  - [near] Disseminated superficial porokeratosis
    - why_kept(Darier's disease): Hyperkeratotic plaques and dyskeratotic keratinocytes match this rare genetic disorder
    - why_kept(Grover's disease): Pruritic lesions and hyperkeratosis are consistent with this condition
    - why_kept(Porokeratosis): Presence of parakeratotic columns and hyperkeratosis aligns with this disease
    - why_kept(Lichen simplex chronicus): Chronic pruritic lesions and hyperkeratotic plaques are characteristic of this condition
    - why_kept(Disseminated superficial porokeratosis): Clinical presentation and histopathological findings are consistent with this rare skin disorder
- S4 champion: **Porokeratosis** cluster=gold jaccard=0.50
- S4 rationale: The presence of hyperkeratosis, irregular papillomatosis, parakeratotic columns (cornoid lamella), and dyskeratotic keratinocytes in the histopathological examination, along with the clinical presentation of well-defined, annular gray hyperkeratotic plaques, are characteristic features of porokeratosis.
- S4 rejected:
  - [other] Darier's disease: Darier's disease typically presents with greasy, crusted papules in seborrheic areas, which does not match the clinical description provided.
  - [other] Grover's disease: Grover's disease is characterized by sudden onset of pruritic papules, often with a distinctive 'nutmeg grater' appearance under the microscope, which is not described in this case.
  - [other] Lichen simplex chronicus: Lichen simplex chronicus typically presents with thickened, hyperpigmented plaques due to chronic scratching, but the histopathological findings do not match those described in this case.
  - [near] Disseminated superficial porokeratosis: While this condition shares some similarities with the case presentation, the specific details provided, such as the location and appearance of the lesions, along with the histopathological findings, more closely align with the diagnosis of porokeratosis rather than its disseminated superficial form.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Lichen sclerosus', "Darier's disease"]
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ["Darier's disease", "Grover's disease", 'Seborrheic keratosis', 'Lichen sclerosus', 'Psoriasis', 'Lichen sclerosus', "Darier's disease", "Grover's disease"]
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Porokeratosis', 'Seborrheic Keratosis']
- diagnose: ['Porokeratosis', 'Seborrheic Keratosis']
- queries: ['pruritic lesions on scrotum and buttock', 'annular gray hyperkeratotic plaques', 'hyperkeratosis and parakeratotic columns', 'dyskeratotic keratinocytes and hypogranulosis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=25 final_n=1
- final: ["Darier's disease"]
- tree gold_cluster_n=0 final gold=False

