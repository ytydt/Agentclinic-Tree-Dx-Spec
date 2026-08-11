# E5 manual trajectory and semantic audit

## Responsibility and reviewed universe

The final judgments here were made by the primary Codex analyst after reading
the clean vignette, frozen gold, natural base options, injected label and its
construction rationale, both selector rankings, decisive-for/against traces
and arm-level transition. Model rationales are evidence about model behavior,
not clinical ground truth. No external LLM adjudicator supplied a final label.

The review covers:

1. all 180/180 labels in the outcome-blind frozen semantic sample (20 cases ×
   five typed labels × four width labels);
2. all 66/66 typed injected labels that became champion and all 45/45 unique
   width labels that became champion;
3. a frozen outcome-blind sample of three shared-candidate harms and three
   strict gains per arm, 48 transitions total;
4. every aggregate strict transition, candidate-membership/position trace,
   construction failure and runtime incident.

`manual_adjudications.jsonl` contains all 339 explicit judgments, candidate
text and selector rationale. `e5_manual_adjudications.py` contains compact
decision vectors and fail-closed fingerprints of the reviewed candidate set;
it refuses to reuse these judgments if a label changes.

The review is gold-aware because the task is mechanism dissection. It is not a
replacement blinded confirmation endpoint. The preregistered strict score is
never overwritten.

## Frozen construction fidelity

Manual status definitions:

- **valid**: satisfies the requested relation and, for width, is a plausible,
  complete, non-equivalent, roughly granularity-matched alternative;
- **partial**: useful direction but loses scope, has weak plausibility, or
  rests on a non-clean taxonomy;
- **invalid**: reverses the relation, duplicates/equates the gold or another
  injected item, or is a process rather than a complete diagnosis;
- **uncertain**: the literature available for this rare name does not support
  a confident equivalence decision.

| Claimed role | Valid | Partial | Invalid | Uncertain |
|---|---:|---:|---:|---:|
| Parent | 20 | 0 | 0 | 0 |
| Sibling | 16 | 4 | 0 | 0 |
| Unrelated | 16 | 4 | 0 | 0 |
| Synonym | 13 | 4 | 2 | 1 |
| Component | 13 | 1 | 6 | 0 |
| Width candidate 1 | 17 | 3 | 0 | 0 |
| Width candidate 2 | 15 | 4 | 1 | 0 |
| Width candidate 3 | 12 | 7 | 1 | 0 |
| Width candidate 4 | 12 | 7 | 1 | 0 |
| **Total** | **134** | **34** | **11** | **1** |

### Failures that a schema validator cannot catch

**Semantic duplicate hidden by punctuation.** In DA/477 the typed unrelated
label is “Acute disseminated encephalomyelitis (ADEM)” and width candidate 4 is
“Acute disseminated encephalomyelitis.” Surface normalization leaves the
parenthetical acronym, so both pass uniqueness even though they are the same
disease. This is a concrete failure of string-only deduplication.

**Subtype labeled as component.** Keratinizing squamous cell carcinoma,
trabecular juvenile ossifying fibroma and adrenal nodular hyperplasia are
children/refinements of their reference labels, not incomplete components.
The error matters because a selector correctly preferring a more specific
child is scored as both a strict loss and “component capture.” The supposed
mechanism has the direction backward.

**Composite scope silently dropped.** Four posterior-fossa tumor alternatives
in DA/678 explain the mass but ignore that the reference is *clivus chordoma
associated with TSC*. They are complete tumor names, yet are not matched to a
two-object composite target. The same issue appears when alternatives to TAPS
explain only the anemic fetus and not the paired polycythemia.

**Generic process presented as diagnosis.** “Metastatic calcification” and
“dystrophic calcification” in DA/602 describe processes rather than complete
diagnoses matched to normophosphatemic tumoral calcinosis. They would let the
selector escape the requested diagnostic object.

**False synonym direction.** “Lupus erythematosus panniculitis” is broader
than linear/annular lupus panniculitis of the scalp. “Stage IIIC melanoma with
cutaneous satellite lesions” drops T4aN3. “Tuberculous peritonitis” is one
abdominal-TB form, not a universal synonym. These are not spelling problems;
they lose clinically meaningful qualifiers.

For rare relationships, the audit was cross-checked against primary or
specialist sources. Pretibial DEB and DEB pruriginosa have documented clinical
overlap rather than clean sibling separation ([PubMed 19061625](https://pubmed.ncbi.nlm.nih.gov/19061625/)).
IPEH/Masson's lesion is a distinct reactive vascular lesion
([PubMed 29308369](https://pubmed.ncbi.nlm.nih.gov/29308369/)), while papillary
hemangioma is a recently described separate vascular tumor
([DOI 10.1111/cup.14554](https://doi.org/10.1111/cup.14554)); therefore IPEH is
not accepted as a mere papillary-hemangioma component. LALPS is explicitly a
linear/annular scalp form ([PubMed 39050080](https://pubmed.ncbi.nlm.nih.gov/39050080/)).
Fibrolipomatous hamartoma can coexist with macrodystrophia lipomatosa as an
associated lesion ([PubMed 20875626](https://pubmed.ncbi.nlm.nih.gov/20875626/)),
not an obligatory component.

## Every injected champion: relation fidelity and endpoint meaning

| Arm / unique winning labels | Valid | Partial | Invalid | Strict direct harms | Mechanistic interpretation |
|---|---:|---:|---:|---:|---|
| Parent / 13 | 12 | 1 | 0 | 8 | Mostly genuine retreat to a broader object; five other parent wins occur when base is already wrong. |
| Sibling / 18 | 13 | 5 | 0 | 13 | Mostly direct alternative capture; overlap in satellite/in-transit melanoma, pretibial EBP and TB axes weakens five labels. |
| Unrelated / 8 | 5 | 1 | 2 | 6 | Two “unrelated” labels are actually sibling opportunistic infection/bone-sarcoma alternatives. |
| Synonym / 12 | 9 | 3 | 0 | 11 | Eleven nominal harms are overwhelmingly bridge misses, not reasoning errors. |
| Component / 15 | 6 | 1 | 8 | 10 | The majority of winners reverse the intended direction or name another lesion; aggregate null is uninterpretable. |
| Width union / 45 | 41 | 1 | 3 | 31 unique labels harm at least one width arm | Width capture is mostly real; three wins are compatible refinements and one is a broad description. |

### Synonym arm: frozen endpoint versus semantic answer

The 12 injected synonym winners are:

- nine clear equivalents: nonbullous neutrophilic dermatosis of lupus, DEB
  pruriginosa, biliary/hepatic cystadenoma, invasive fungal sinusitis,
  ectopic lingual thyroid, foreign-body-induced granuloma, Aspergillus
  infection, Panayiotopoulos syndrome and stomach/gastric lipoma;
- three partial equivalents: post-COVID abdominal epilepsy, acute pancreatitis
  with AKI versus “renal failure,” and tuberculous peritonitis versus abdominal
  tuberculosis.

The frozen bridge credits none. On 165 successful base/synonym pairs, strict
scoring is 20 harms/19 gains (−0.61pp). Crediting only the nine clear manual
equivalents gives 11/19 (+4.85pp, p=.2005); including partial equivalents gives
9/20 (+6.67pp, p=.0614). The sensitivity analysis is not a new primary score,
but it falsifies the interpretation that the synonym intervention itself had
no useful effect.

### Component arm: why zero net is not reassuring

Six winning labels are genuine manifestations/components: leukemic
vasculitis, nonbacterial thrombotic endocarditis as a proposed embolic lesion,
acute ischemic stroke, rhabdomyolysis, Aspergillus brain abscess and
Coccidioides pneumonia. Left renal vein compression is a partial mechanistic
restatement of posterior nutcracker syndrome.

Eight are invalid in the claimed direction:

- EBV-positive plasmablastic lymphoma, monophasic synovial sarcoma,
  trabecular JOF and adrenal nodular hyperplasia are child subtypes;
- orbital dermoid is the location-completed form of dermoid cyst;
- keratinizing SCC is a subtype of SCC;
- gastric glandular hyperplasia is a different competing lesion;
- hemangioma is the parent of spindle-cell hemangioma.

The strict arm has 15 harms and 15 gains, but ten harms occur when an injected
label wins and eight of the 15 winning labels do not implement “component.” A
zero coefficient averages different interventions and cannot establish a
safe component mechanism.

## Frozen context-transition sample

The sample includes three context harms and three gains per arm (48 total).
It is selected by a frozen hash after transition classes are defined, not by
how persuasive a case looks.

All 24 gains return the exact frozen target. The 24 harms decompose as:

| Manual harm class | n | Meaning |
|---|---:|---|
| Compatible incomplete composite | 7 | Same underlying disease but a cause, stage, complication or co-diagnosis is dropped. |
| Compatible underspecification | 4 | A broader parent wins after the set changes. |
| Compatible near-equivalent | 2 | Surface or modifier distinction, not a new disease. |
| Compatible reframing | 1 | Different disease-object phrasing of the same process. |
| Non-diagnostic surface artifact | 4 | A sentence/evidence statement containing the disease wins as if it were a diagnosis. |
| Missing-target/non-diagnostic choice | 1 | The model selects `None` because its preferred unlisted diagnosis is absent. |
| Time-scope ambiguity | 2 | Current lesion versus complete trajectory changes the answer. |
| Real competing diagnosis | **3** | Clear switch to a different diagnosis. |

This asymmetry explains why strict context harms should not be read as 24
clinical errors. It also identifies a separate source-option sanitation bug:
some natural options are explanatory sentences or “None,” so list mutation
can select an answer-shaped evidence statement rather than a diagnosis.

## Six trajectory dissections

### 1. MCR/330 — one case traverses parent, sibling, child and unrelated axes

Frozen target/base champion is *squamous cell carcinoma*. Adding the parent
selects *non-small-cell lung carcinoma*; adding the sibling selects
*adenocarcinoma*; the “component” arm selects *keratinizing SCC*; width 8
selects *malignant pleural mesothelioma*. Removal, unrelated, synonym and
width 6 retain the gold.

These are not equivalent errors. Parent selection is under-specification,
adenocarcinoma and mesothelioma are genuine alternative capture, while
keratinizing SCC is a clinically compatible refinement that the builder
mislabels as component and strict scoring rejects. A single 1→0 endpoint
cannot identify the mechanism without relation and direction audit.

### 2. MCR/40 — the benchmark punishes clinically richer HCC answers

Base chooses *hepatocellular carcinoma*. Removal and parent arms choose the
natural option “Confirmation of metastatic HCC by IHC,” a non-diagnostic
instruction/evidence sentence. Width 6 chooses *extrahepatic metastasis of HCC
to the rib* and width 8 chooses *metastatic HCC to the chest wall*. Both width
labels are more specific compatible descriptions of the vignette, not
non-equivalent distractors.

This case simultaneously reveals source-option pollution, width-builder
contract failure and modifier-direction endpoint bias. Treating its three
strict harms as distractor susceptibility would be wrong.

### 3. DA/775 — composite stripping without injected-candidate capture

Base returns the complete target: mixed *Rhizopus microsporus* plus *Mucor
racemosus* disseminated mucormycosis. Removal, sibling, unrelated, component,
width 6 and width 8 all shift to an already-present base label naming
rhino-orbital-cerebral mucormycosis; none of the added labels is champion.

The new candidate changes the contrast set, and the selector retreats from a
species-plus-dissemination trajectory to the most salient anatomical
syndrome. This is pure shared-candidate context harm and a concrete DA
composite-stripping mechanism.

### 4. MCR/151 — plausible alternatives expose time/target ambiguity

Base and parent/synonym arms choose *coccidioidomycosis*. Sibling chooses
histoplasmosis; “unrelated” chooses PJP (actually a sibling opportunistic
infection); component chooses *Coccidioides pneumonia*; width 6 chooses
cryptococcal pneumonia and width 8 pulmonary tuberculosis.

The vignette contains advanced HIV and a new pulmonary syndrome after an
earlier diagnostic trajectory. Several alternatives may be more plausible for
the current episode even if the frozen target names the reported case
diagnosis. This is genuine alternative capture entangled with time-scope
identifiability, not random label noise.

### 5. MCR/302 — a width “distractor” is nested inside the gold

Base chooses *septic arthritis*. Parent chooses generic *arthritis*; sibling
chooses reactive arthritis; width 6 selects a natural `None`; width 8 selects
*gonococcal arthritis*. Gonococcal arthritis is a septic-arthritis subtype, so
the width-8 label violates the required non-equivalence and is a compatible
refinement. The selector's rationale uses age, bilateral knees and recent
ectopic pregnancy to support disseminated gonococcal infection.

The strict loss is real target mismatch but not evidence that an unrelated
plausible decoy beat the diagnosis. Semantic containment must be checked in
both directions before a width experiment.

### 6. DA/257 — width destabilizes exact versus equivalent HTRA1 labels

The pool contains the exact target *heterozygous HTRA1-related CSVD* plus
*HTRA1-related autosomal dominant CSVD* and another hereditary HTRA1 label.
Every arm through component chooses the exact label. Width 6 and width 8 both
choose the autosomal-dominant formulation and rank the exact option second.
The added width labels do not win.

Clinically, heterozygous HTRA1 disease and autosomal-dominant HTRA1 CSVD are
strongly aligned here; the vignette gives a heterozygous variant and dominant
family history. The trajectory is a shared-candidate reordering and bridge
coverage failure, not loss of the underlying diagnosis. It exemplifies why
DA's harms are context-heavy while MCR's are direct-capture-heavy.

## Position and payload audit

Every shared candidate keeps its ID, label and relative order in all 1,358
successful base-to-arm comparisons. Every successful width-6 pool is an exact
subset of width 8 with two additional labels. No hidden candidate text change
explains a flip.

Hash insertion changes absolute positions. Across the five single-injection
arms, 66 injected candidates win among 828 exposures. Winners appear at mean
position 2.55; non-winners at 3.05. A post-hoc permutation that preserves each
arm's number of injected winners gives p=.00564. Position 1/2 accounts for
38/66 injected winners, versus 17/66 at positions 4/5. This is not a randomized
position arm and is not promoted to a causal primary result, but it is
inconsistent with confidently treating the ranker as permutation invariant.

## Mechanism conclusion

Candidate-set interference has at least four layers:

1. **direct semantic competition**, strongest for MCR sibling and width
   candidates;
2. **shared-candidate contrast reordering**, strongest for DA composites and
   near-duplicate labels;
3. **serial-position sensitivity**, suggested by outcome-blind hash order;
4. **measurement/construction error**, especially missing synonyms,
   child-versus-component reversal and option sentences masquerading as
   diagnoses.

The evidence supports typed comparison and safe entity aggregation, but only
if relation direction and target scope are audited. A larger untyped list is
not a harmless recall buffer; a smaller list is not uniformly safer; and a
strict lexical endpoint cannot by itself tell clinical capture from ontology
or granularity mismatch.
