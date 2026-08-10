# DA / d2_heldout100 / case 312

- **gold**: Pseudo-α-galactosidase deficiency (PAGD) syndrome with mild neurocognitive disorder
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A woman in her 40s presented with a 3-year history of a complex progressive disorder characterized by:- Emotional lability- Cognitive decline - Generalized ataxia- Autonomic dysfunctionPatient denied paresthesias, dysesthesias, or loss of sensation.

Autonomic testing revealed:- Abnormal cardiac parasympathetic function (without orthostatic hypotension)- Patchy decrease in sweat output on quantitative sudomotor axon reflex test- Markedly abnormal thermoregulatory sweat test with near complete global anhidrosis

- Laboratory tests:  - α-galactosidase activity: 0.056 U/L (normal range: 0.074-0.457 U/L)  - Cerebrospinal fluid analysis:    - Elevated protein levels (95 mg/dL)    - No pleocytosis (WBC: 0/μL)    - Polymorphonucleocytes: 7%    - Lymphocytes: 83%    - Monocytes: 9%  - Imaging studies:  - MRI Brain:    Image Description: Bilateral hyperintensity in the pulvinar region of thalami and global diffuse brain volume loss  - MRI Spine: No spinal cord lesions  - Genetic Testing:  - Positive for pseudo-α-galactosidase allele  - Neuropsychological Testing:  - Showed mild neurocognitive and memory deficits

What is the most likely diagnosis?

Options:
A. Multiple system atrophy (cereb…

## Options
- A: Multiple system atrophy (cerebellar subtype)
- B: Fabry disease
- C: Wilson’s disease
- D: Pseudo-α-galactosidase deficiency (PAGD) syndrome with mild neurocognitive disorder **←gold**

## Backbone e7

- S2 n=43 gold_rank=None
  - clusters: gold=0 near=7 other=36
- S3 shortlist (5):
  - [other] Multiple System Atrophy
  - [other] Fabry Disease
  - [other] Frontotemporal Dementia
  - [other] Late-Onset Tay-Sachs Disease
  - [other] Adult Polyglucosan Body Disease
    - why_kept(Multiple System Atrophy): Progressive neurological disorder with autonomic dysfunction and cognitive decline
    - why_kept(Fabry Disease): Low α-galactosidase activity and progressive neurological disorder
    - why_kept(Frontotemporal Dementia): Cognitive decline and global diffuse brain volume loss
    - why_kept(Late-Onset Tay-Sachs Disease): Progressive neurological disorder and positive for pseudo-α-galactosidase allele
    - why_kept(Adult Polyglucosan Body Disease): Progressive neurological disorder with autonomic dysfunction and cognitive decline
- S4 champion: **Multiple System Atrophy** cluster=other jaccard=0.00
- S4 rationale: The combination of progressive disorder, autonomic dysfunction (abnormal cardiac parasympathetic function, patchy decrease in sweat output, and near complete global anhidrosis), generalized ataxia, and cognitive decline without significant sensory symptoms aligns closely with Multiple System Atrophy. Additionally, the imaging findings of bilateral hyperintensity in the pulvinar region of thalami and global diffuse brain volume loss support this diagnosis.
- S4 rejected:
  - [other] Fabry Disease: Low α-galactosidase activity is consistent with Fabry Disease, but the absence of paresthesias, dysesthesias, or loss of sensation and the specific pattern of autonomic dysfunction and imaging findings make it less likely.
  - [other] Frontotemporal Dementia: While cognitive decline is present, the prominent autonomic dysfunction and ataxia are not typical of Frontotemporal Dementia.
  - [other] Late-Onset Tay-Sachs Disease: This condition typically presents with motor symptoms and cognitive decline, but the autonomic dysfunction and specific imaging findings in this case do not align with Late-Onset Tay-Sachs Disease.
  - [other] Adult Polyglucosan Body Disease: This condition involves progressive upper and lower motor neuron impairment and dementia, which does not fully match the combination of symptoms and findings in this case, particularly the prominent autonomic features.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Multiple System Atrophy', 'Fabry Disease']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Multiple System Atrophy', 'Fabry Disease', 'Autonomic Dysfunction Syndrome', 'Multisystem Proteinopathy', 'Frontotemporal Dementia', 'Multiple System Atrophy', 'Fabry Disease', 'Multisystem Proteinopathy']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Fabry Disease', 'Multiple System Atrophy (MSA)']
- diagnose: ['Fabry Disease', 'Multiple System Atrophy (MSA)']
- queries: ['α-galactosidase deficiency and neurological symptoms', 'ataxia and autonomic dysfunction diagnosis', 'cognitive decline and generalized ataxia']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=63 final_n=3
- final: ['Fabry disease', 'Multiple System Atrophy', 'Autonomic Failure']
- tree gold_cluster_n=2 final gold=False

