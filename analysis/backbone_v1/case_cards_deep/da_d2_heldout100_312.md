# DA / d2_heldout100 / case 312

- **gold**: Pseudo-α-galactosidase deficiency (PAGD) syndrome with mild neurocognitive disorder
- **layer**: `aphhm_lose`
- **correct**: e7=0 v0=1 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`s2_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: APHHM=tree_hit_final_drop
- **covariates**: vig_words=175; gold_words=10; eponym=False; subtype=True; e7_s2_rank=None; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A woman in her 40s presented with a 3-year history of a complex progressive disorder characterized by:- Emotional lability- Cognitive decline - Generalized ataxia- Autonomic dysfunctionPatient denied paresthesias, dysesthesias, or loss of sensation.  Autonomic testing revealed:- Abnormal cardiac parasympathetic function (without orthostatic hypotension)- Patchy decrease in sweat output on quantitative sudomotor axon reflex test- Markedly abnormal thermoregulatory sweat test with near complete gl...

## Options
  - A: Multiple system atrophy (cerebellar subtype)
  - B: Fabry disease
  - C: Wilson’s disease
  - D: Pseudo-α-galactosidase deficiency (PAGD) syndrome with mild neurocognitive disorder

## Backbone e7
- S1 key_facts: 3-year history of progressive disorder; Denies paresthesias, dysesthesias, or loss of sensation; Abnormal cardiac parasympathetic function without orthostatic hypotension; Patchy decrease in sweat output on quantitative sudomotor axon reflex test; Near complete global anhidrosis on thermoregulatory sweat test; Low α-galactosidase activity (0.056 U/L); Elevated protein levels in cerebrospinal fluid (95 mg/dL); No pleocytosis in cerebrospinal fluid
- S2 mode=complement k=3 pool_n=43 gold_in_s2=False
  - call1: ['Multiple System Atrophy', 'Familial Dysautonomia', 'Autonomic Dysfunction with Orthostatic Hypotension', 'Pure Autonom
  - call2: ['Adult Polyglucosan Body Disease', 'Neuronal Intranuclear Inclusion Disease', 'Chronic Intestinal Pseudo-obstruction wi
  - call3: ['Adult Polyglucosan Body Disease due to Glycogen Branching Enzyme Deficiency', 'Neuropathic Gaucher Disease Type 3', 'L
- S3 shortlist n=5 gold=False: Multiple System Atrophy, Fabry Disease, Frontotemporal Dementia, Late-Onset Tay-Sachs Disease, Adult Polyglucosan Body Disease
- S4 champion: **Multiple System Atrophy** gold=False
- S4 raw (trunc): {"champion": "Multiple System Atrophy", "rationale": "The combination of progressive disorder, autonomic dysfunction (abnormal cardiac parasympathetic function, patchy decrease in sweat output, and near complete global anhidrosis), generalized ataxia, and cognitive decline withou

## Backbone v0 (compact)
- S1 key_facts: 3-year history of progressive disorder; Denies paresthesias, dysesthesias, or loss of sensation; Abnormal cardiac parasympathetic function without orthostatic hypotension; Patchy decrease in sweat output on quantitative sudomotor axon reflex test; Near complete global anhidrosis on thermoregulatory sweat test; Low α-galactosidase activity (0.056 U/L); Elevated cerebrospinal fluid protein levels (95 mg/dL); No pleocytosis in cerebrospinal fluid
- S2 mode=single k=1 pool_n=16 gold_in_s2=False
  - call1: ['Multiple System Atrophy', 'Autonomic Dysfunction with Orthostatic Hypotension', 'Familial Dysautonomia', 'Fabry Diseas
- S3 shortlist n=5 gold=False: Multiple System Atrophy, Fabry Disease, Alpha-Galactosidase A Deficiency, Frontotemporal Dementia with Parkinsonism, Lewy Body Dementia
- S4 champion: **Alpha-Galactosidase A Deficiency** gold=False
- S4 raw (trunc): {"champion": "Alpha-Galactosidase A Deficiency", "rationale": "The patient's low α-galactosidase activity (0.056 U/L) and positive pseudo-α-galactosidase allele, along with symptoms such as generalized ataxia, autonomic dysfunction, and cognitive decline, are consistent with Alph

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's complex progressive disorder with emotional lability, cognitive decline, generalized ataxia, and autonomic dysfunction, along with abnormal autono
  - turn1 gold_mention=False diag=
    The patient's presentation and diagnostic findings align closely with the discussion by Doctor A, emphasizing the complexity of the case and the need to conside
  - turn2 gold_mention=True diag=
    The patient's complex presentation with emotional lability, cognitive decline, ataxia, and autonomic dysfunction, combined with abnormal autonomic testing, low 
- supervisor votes=3 top2=['Multiple System Atrophy', 'Fabry Disease'] gold=False

## Baseline B07
- draft=['Fabry Disease', 'Multiple System Atrophy (MSA)'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['α-galactosidase deficiency and neurological symptoms', 'ataxia and autonomic dysfunction diagnosis', 'cognitive decline and generalized ataxia']
- diagnose=['Fabry Disease', 'Multiple System Atrophy (MSA)'] gold=False

## APHHM
- tree_n=63 tree_recall=True
- gold_leaf=B4.22:Disorder parent=B4
- final_n=3 final_recall=False ranking=['Fabry disease', 'Multiple System Atrophy', 'Autonomic Failure']
- human_at1=False fail_mode=prune_loss

