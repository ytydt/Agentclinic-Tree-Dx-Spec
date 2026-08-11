# E7c manual trajectory audit

## Audit responsibility and coverage

This audit was performed after the frozen online run. External model responses
are treated as evidence to inspect, not as adjudication. The final clinical and
causal judgements below are the experimenter's responsibility.

Coverage:

- all 84 cases with any champion or correctness discordance were reviewed at
  the label/transition level;
- all seven cases with a strict correctness transition were reviewed using the
  full vignette, fixed candidates, support/contradiction spans, all four
  selector rationales and every typed edge;
- all seven terminal selector failures and all nine failed relation chunks were
  reviewed;
- repeated-pair contradictions were enumerated for the full run, followed by
  manual clinical inspection of correctness-transition edges and representative
  high-confidence structural failures.

The frozen endpoint is exact/frozen-synonym top-1. The clinical comments below
do not silently replace that endpoint; they identify whether an observed score
transition is a credible mechanism effect.

## Every strict correctness transition

| Case | Observed transition | Manual mechanism judgement |
|---|---|---|
| `DA_d2_heldout200b/638` | exact/generic correctly select laryngeal histoplasmosis; directional/bounded select disseminated histoplasmosis | Credible typed-graph harm. The graph simultaneously says generic histoplasmosis is a subtype of laryngeal disease, laryngeal disease is a parent of generic disease, and laryngeal disease is an anatomic refinement of generic disease. The first two directions are wrong, while a `component_of` edge and severe ICL make disseminated disease salient despite absent systemic symptoms. This is both direction corruption and over-broad scope projection. |
| `MCR_seq200b/326` | bounded changes correct brucellosis to spinal epidural abscess; other three arms remain correct | Credible policy harm, not a typing error on the active edge. Spinal epidural abscess is correctly related to epidural abscess, but bounded-inheritance prose rewards the anatomically specific manifestation. It overrides the vignette's etiologic cue (unpasteurised sheep exposure) and the question's expected underlying disease. Relation specificity cannot substitute for task-object projection. |
| `MCR_seq200b/345` | bounded changes HHRH to generic hypophosphatemic rickets | Mixed/unclean harm. The graph reverses the hierarchy (`Hypophosphatemic rickets subtype_of HHRH`). The policy then makes the reversed direction operational. The vignette also reports normal urine calcium despite the gold label's hypercalciuria, creating a genuine identifiability tension. This case supports a direction validator but should not be used as clean evidence about ideal inheritance. |
| `MCR_seq200b/348` | directional changes complex odontoma to calcifying epithelial odontogenic tumour; bounded restores the gold | Salience/selector instability. The one edge, CEOT `subtype_of` odontogenic tumour, is clinically reasonable but does not involve complex odontoma. The directional rationale overweights the graph-linked CEOT despite age and dense amorphous morphology favouring odontoma. Bounded prose reverses the choice without adding clinical evidence. This is not evidence that inheritance works. |
| `MCR_seq200b/412` | exact selects pulpitis; all three nonempty-graph arms select external cervical resorption | Endpoint gain but not a relation-semantic gain. The graph only connects `Periodontitis` and `Stage II, Grade II Periodontitis`; it contains no edge involving ECR or pulpitis. Generic, directional and bounded all rescue the case, so the plausible cause is context/salience or selector sampling, not typed relations. |
| `MCR_v1_seq100/21` | directional changes fibrous dysplasia to orbital meningioma; bounded restores fibrous dysplasia | Salience harm followed by an unidentifiable rescue. `Orbital meningioma subtype_of Meningioma` is correct but irrelevant to the gold candidate. The edge focuses the selector on the meningioma cluster and it rationalises away the lytic bone finding; policy prose changes it back. Neither transition estimates the intended evidence-inheritance mechanism cleanly. |
| `MCR_v2_seq100/205` | generic changes cysticercosis to NF1; exact/directional/bounded select cysticercosis | The generic arm is a placebo-context harm. Typed cysticercosis `parent_of` neurocysticercosis is reasonable, but the same run calls NF1/fibromatosis `parent_of`, `subtype_of` and `unrelated`. Directional returning to the exact winner is not a gain over control and its graph is internally contradictory. |

The seven-case audit explains why counting one directional gain and three harms
alone is inadequate. Only the histoplasmosis harm cleanly demonstrates the
intended relation channel causing a wrong decision. The ECR gain is caused by a
graph that is irrelevant to the decisive comparison; two apparent bounded
rescues reverse salience harms rather than adding valid inherited evidence.

## Representative relation adjudication

| Case / pair | Model relation | Manual judgement |
|---|---|---|
| `DA_d2_heldout200b/638`: Histoplasmosis / Laryngeal histoplasmosis | generic `subtype_of` laryngeal; laryngeal `parent_of` generic; laryngeal `anatomic_refinement_of` generic | First two are directionally wrong; the anatomic refinement is correct. The same pair is internally contradictory. |
| `MCR_seq200b/345`: Hypophosphatemic rickets / HHRH | generic `subtype_of` HHRH | Wrong direction; HHRH is the specific hereditary subtype. |
| `MCR_seq200b/388`: Meningioma / Clear-cell meningioma | both directions appear as `subtype_of`, plus correct `parent_of` instances | Repeated high-confidence contradiction. Clear-cell meningioma is the subtype. |
| `DA_d2_seq100/241`: Endophthalmitis / Streptococcal endophthalmitis | most instances put generic disease as `subtype_of`; later instances reverse it | Repeated direction failure; streptococcal endophthalmitis is the etiologic subtype/refinement. |
| `DA_d2_heldout200b/500`: Lipodermatosclerosis / acute lipodermatosclerosis | generic disease `subtype_of` acute disease | Wrong direction; “acute” refines the base entity. |
| `MCR_seq200b/264`: Ovarian cystadenocarcinoma / ovarian cyst | carcinoma `parent_of` cyst and cyst `subtype_of` carcinoma | Clinically false hierarchy, not just reversed wording. A cystadenocarcinoma is not the parent class of ovarian cyst. |
| `MCR_seq200b/283`: Dermoid cyst / epidermoid cyst | `cooccurs_with` in six instances and `same_as` in three | Unsupported equivalence/co-occurrence. They are distinct lesion types and may be differentials; neither relation is entailed by the labels or case. |
| `MCR_v2_seq100/205`: NF1 / fibromatosis | `parent_of`, `subtype_of`, and `unrelated` | Only the non-equivalence direction is defensible; NF1 and fibromatosis are distinct entities, and the three predictions expose repeat instability. |
| `MCR_seq200b/348`: CEOT / odontogenic tumour | CEOT `subtype_of` odontogenic tumour | Correct, but irrelevant to the gold-versus-CEOT comparison; demonstrates graph salience rather than graph error. |
| `MCR_v1_seq100/21`: Orbital meningioma / meningioma | orbital `subtype_of` generic | Correct, but the edge pulls selection away from an unrelated correct candidate. |

## Discordance anatomy beyond the seven scored transitions

The 84-case census contains large numbers of all-wrong label movements. These
are still mechanistically informative because the endpoint is often not exposed
in this unsafe-fold subset.

- Directional vs exact: 48 label flips; 36 touch at least one graph node, 15
  directly connect the two champions, and 12 involve neither champion.
- Bounded vs directional: 45 label flips from policy prose alone; eight involve
  neither champion as a graph node.
- Generic vs exact: 47 flips from non-semantic edges; 15 involve neither
  champion. Examples include myocarditis to TTP when the edge concerns another
  pair, and MIS-C to cerebral vasculitis when the graph only asserts an
  unrelated `same_as` pair.

Thus “the graph changed the answer” is not sufficient evidence that the model
used the graph relation correctly. Direct graph contact, task-object relevance,
relation validity and counterfactual specificity must all be checked.

## Failures retained in ITA

Seven selector conditions are invalid. Three are empty parsed objects; four
contain useful-looking prose but violate the required schema, commonly emitting
`champion` instead of `champion_id`. None is repaired post hoc. Nine relation
chunks fail because of more than one qualifier span or reversed endpoint order
for a symmetric predicate. Their cases remain marked incomplete and their
typed edges are absent.

This failure policy prevents selective deletion, but the extraordinary selector
output volume and retry burden show that subsequent arms need an explicit
reasoning-token cap before scientific execution.

## Final audit finding

E7c is a negative implementation result with a useful mechanism diagnosis:

- exact identity repair from E7a/E7b remains necessary;
- unconstrained LLM relation typing is too directionally unstable to operationalise
  evidence inheritance;
- even a correct edge can harm through graph salience when task projection is
  absent;
- bounded policy text does not enforce bounded computation;
- deterministic graph validation and relevance filtering must precede the RCR
  selector, and any alarm must be visible in the trajectory artifact.
