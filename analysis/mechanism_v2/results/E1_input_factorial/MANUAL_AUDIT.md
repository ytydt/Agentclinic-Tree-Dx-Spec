# E1 manual trajectory audit

## Responsibility and reviewed set

The judgments below were made manually from the clean vignette, frozen source
options, both condition outputs, candidate lists, rationales and benchmark
label. No external LLM performed the adjudication. Model rationales are
fallible traces used to locate a mechanism; they are not accepted as evidence
that the selected diagnosis is clinically correct.

I reviewed all 4/4 fixed-format strict harms and a purposive mechanism sample
of 18 additional fixed-format transitions: ten strict gains spanning surface,
specificity and substantive diagnostic changes, plus eight cases where the
model copied an option but still missed the registered target. This sample is
explanatory rather than prevalence-estimating. The complete 385-case flip
queue is preserved in the joined artifact for follow-up; E2 supplies the
separate blinded completeness endpoint.

Abbreviations: **H** = one-call hierarchical micro-pipeline; **F** = one-call
flat micro-pipeline; **C** = clean fixed; **O** = options fixed.

## Complete audit of fixed-format strict harms

| Architecture / case | C → O champion | Mechanism | Manual judgment |
|---|---|---|---|
| H, MCR_v1_seq100/125; gold *Cohen syndrome* | *Cohen syndrome* → `Cohen综合征` | Visible options induce a Chinese surface form that the frozen bridge does not equate. Both rationales identify the same neutropenia–microcephaly–retinal-dystrophy syndrome. | Endpoint/translation artifact, not clinical harm. |
| H, MCR_v2_seq100/220; gold *Kawasaki disease* | *Kawasaki disease* → MIS-C | The option-conditioned trace upweights pandemic exposure, age and gastrointestinal symptoms and downweights complete Kawasaki mucocutaneous criteria and absent shock. | Real, clinically plausible distractor harm and diagnostic-scope ambiguity. |
| F, DA_d2_heldout200b/555; gold *Euglycemic Diabetic Ketoacidosis* | euglycemic DKA → starvation ketoacidosis | The option-conditioned trace anchors on 48 hours without feeding and absence of SGLT2 use, overriding diabetes, ketonaemia and anion-gap acidosis. | Real/plausible competing-mechanism harm; the source case itself is diagnostically contestable. |
| F, MCR_v1_seq100/21; gold *Fibrous dysplasia* | fibrous dysplasia → *Fibrous dysplasia (monostotic)* | Visible options add a subtype modifier without changing the disease process. | Granularity/bridge artifact, not clinical harm. |

Thus the fixed-format strict comparison contains two credible clinical harms
and two pure endpoint artifacts. The low harm count does not prove safety:
option visibility changes the champion in 156/178 comparable H cases and
178/199 comparable F cases, including many all-wrong transitions.

## Ten strict gains: what the metric is counting

| Architecture / case | C → O champion | Manual decomposition |
|---|---|---|
| H, DA_d2_heldout200b/608; gold *Isolated cardiac sarcoidosis* | cardiac sarcoidosis → exact gold | Mostly specificity/target-string completion; the clean answer already has the core diagnosis. |
| H, DA_d2_heldout100/399; gold expanded AVNRT label | abbreviated AVNRT → exact expanded label | Pure surface normalization; no new clinical inference. |
| H, DA_d2_seq100/27; gold *Histiocytoid Sweet syndrome* | myeloid sarcoma → exact gold | Substantive rescue: the option triggers correct use of histiocytoid morphology plus MPO/CD68 in the reactive clinical context. |
| H, DA_d2_seq100/95; gold sporadic PAPT | MSA-C → exact gold | Substantive syndrome-level rescue using palatal tremor, non-suppressibility and absent clicking. |
| H, MCR_seq200b/274; gold tricuspid valve aneurysm | papillary fibroelastoma → exact gold | Substantive structural-imaging rescue from a blind-ended, systolic-bulging empty protrusion. |
| H, MCR_v1_seq100/95; gold tuberculosis | disseminated histoplasmosis → tuberculosis | The visible label changes the infectious differential, but the trace offers no decisive organism evidence. Benchmark-concordant, clinically under-confirmed option anchoring. |
| F, DA_d2_heldout100/429; gold secukinumab-induced DM exacerbation | amyopathic DM → exact causal label | Plausible causal-specificity rescue using medication timing; partly target-string completion. |
| F, DA_d2_seq100/219; gold MHIBCC | SUFU-related Gorlin variant → exact gold | Substantive ontology rescue using infundibulocystic histology, SUFU genetics and absent classic Gorlin features. |
| F, DA_d2_heldout200b/553; gold SDH-deficient prostatic paraganglioma with multiplicity/recurrence | metastatic paraganglioma → exact compound label | Evidence-supported compound completion, but the source option supplies nearly the entire requested string. |
| F, DA_d2_seq100/99; gold EBP | pruritic papular epidermolysis bullosa → exact subtype | Predominantly subtype-name/surface repair from COL7A1 and phenotype. |

This sample contains real diagnostic rescues, but only four are cleanly
substantive (Sweet, PAPT, valve aneurysm, MHIBCC). Three are mainly surface or
target-string repairs, two mix legitimate specificity with direct compound
label supply, and one is benchmark-concordant but clinically under-confirmed.
The strict +40pp effect therefore cannot be read as +40pp of independent
clinical reasoning.

## Eight option-copy failures

| Architecture / case | Gold | O champion | Failure mechanism |
|---|---|---|---|
| F, DA_d2_heldout200b/579 | gas-containing brain abscess | organism-specific bacterial brain abscess | Chooses microbiologic cause and drops the image-defining gas phenotype requested by the target. |
| H, DA_d2_heldout200b/698 | concurrent pulmonary and cerebral mucormycosis | fungal brain abscess secondary to pulmonary infection | Copies a generic relation but loses organism and the required two-site compound diagnosis. |
| F, DA_d2_heldout200b/747 | severe MPP with coronary dilation and necrotizing pneumonia | MPP with Kawasaki disease | Reifies coronary dilation as a new Kawasaki diagnosis and drops necrotizing pneumonia. |
| F, DA_d2_seq100/237 | intergluteal and sacral hyperhidrosis | primary focal hyperhidrosis, gluteal region | Parent/region label is clinically related but incomplete for the registered anatomic object. |
| F, DA_d2_seq100/151 | large MCA-territory embolic stroke | cardioembolic stroke due to atrial fibrillation | Answers etiology while dropping the requested territory/extent. |
| H, DA_d2_heldout100/301 | paroxysmal AV block | phase-4 His–Purkinje block | Answers a proposed mechanism rather than the syndrome-level target. |
| F, DA_d2_heldout100/349 | cutaneous histoplasmosis | cutaneous cryptococcosis | The trace explicitly disputes the gold using halo morphology; this is evidence disagreement, not a recall or string problem. |
| H, DA_d2_heldout200b/579 | gas-containing brain abscess | organism-specific bacterial brain abscess | “More specific” is used in the wrong dimension: pathogen specificity replaces rather than preserves the imaging-defined diagnostic object. |

Copying is therefore neither sufficient for exact success nor a benign
mechanism. It can repair spelling, import a compound answer, substitute a
parent/component, or redirect the model to a plausible but benchmark-opposed
disease. The typed object-and-obligation work in E6/RCR3 must distinguish these
transitions rather than rewarding any source-label overlap.

## Cross-case mechanism conclusions

### 1. Candidate visibility acts before and at selection

With fixed format, raw gold recall rises by 106 versus 4 discordant H cases and
107 versus 2 discordant F cases. Champion option copying also rises from
28/189 to 119/187 for H and from 23/200 to 124/199 for F. This is not merely a
ranker choosing among an unchanged internally generated set: visible labels
enter candidate generation itself.

### 2. The effect is strongly presentation-dependent

The fixed visibility effect is +41.0pp H and +40.2pp F, but after clinical
blocks and option labels are deterministically rearranged it falls to +23.2pp
and +31.8pp. Shuffling visible-option format itself causes net harms of 26/167
for H and 20/198 for F. Conventional `Options:` formatting is therefore part
of the causal leakage channel.

The intervention is not a pure position control: it also reorders clinical
paragraphs, which can disturb chronology and discourse. The interaction is a
test of input organization, not an isolated estimate of answer-option order.

### 3. Candidate generation is highly path-dependent even without options

Clean fixed versus clean shuffled changes the champion in 133/180 comparable
H cases and 165/199 F cases, with mean candidate-set Jaccard only 0.180 and
0.132. Yet strict accuracy changes by only +0.6pp H and -1.0pp F. At a low
strict baseline, similar endpoint rates conceal radically different case
trajectories; aggregate accuracy alone is therefore an inadequate stability
diagnostic.

### 4. Hierarchy adds output and schema risk here, not demonstrated accuracy

The H prompt emits more candidates but has 11–24 invalid cases per arm and
roughly 0.62–1.26M output tokens. F has 0–1 invalid cases and 0.30–0.57M output
tokens. Clean strict top-1 is similar. This comparison only identifies the
behavior of these frozen one-call prompts; it is not evidence against the full
multi-call APHHM architecture.

## Threats to inference

- The 200 cases are development/mechanism data, not a new confirmation set.
- Exact-or-frozen-synonym top-1 under-credits translation, modifier and
  parent/child equivalence while sometimes rewarding benchmark string supply.
- Paired estimates use only cases served in both conditions; ITA arm counts
  retain failures, and the hierarchical missingness is condition-dependent.
- Clinical-block reordering may change temporal interpretation, so the
  visibility-by-format interaction does not isolate option position.
- One deterministic run per payload was used, as requested; model/provider
  stochasticity is not averaged away.
- Manual review is single-reviewer and gold-aware because its purpose is
  mechanism dissection. It does not replace E2's blinded adjudication.

## Audit conclusion

E1 falsifies the claim that source options are a harmless formatting detail.
They causally enter candidate generation, often repair benchmark labels, and
occasionally cause real distractor harm. It also falsifies any inference from
similar aggregate accuracy to similar trajectories: clean formatting changes
most champions while leaving the low strict rate nearly unchanged. What E1
does not show is a production APHHM advantage or a +40pp clinical improvement.
The defensible conclusion is narrower: answer visibility and presentation are
major, interacting determinants of both candidate identity and endpoint
alignment in these input-sensitive stages.
