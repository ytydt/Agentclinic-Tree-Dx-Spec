# Batch B blind root-audit review

## Scope and blinding

- Adjudicated only blind cards `U0135` through `U0267` (source lines 135–267) under `ROOT_PROTOCOL.md`.
- No arm, leaderboard, endpoint, mapping, index, dual-review, or historical evaluation material was consulted.
- Candidate relations follow the supplied card order. A candidate received `C` only when it was a clinically complete equivalent of the reference object; compatible parents, components, or answers missing a material qualifier received `P`.

## Low-confidence identity decisions

- **U0141 — M:** post-arrest hypoxic-ischemic encephalopathy and contrast encephalopathy are both plausible complete etiologies. Imaging timing/distribution details needed for separation are absent.
- **U0168 — M:** the available mass localization and aspiration evidence do not securely distinguish anaplastic thyroid carcinoma from a hypopharyngeal primary.
- **U0194 — F:** p63 favors sarcomatoid squamous carcinoma, while pan-cytokeratin negativity and prior radiation leave a true post-radiation sarcoma unresolved.
- **U0208 — M:** onset after combined pemetrexed/pembrolizumab does not uniquely assign the sclerotic reaction to either agent.
- **U0214 — M:** high IgG supports seronegative autoimmune hepatitis, but recent HAV with persistent IgM leaves relapsing hepatitis A plausible without biopsy or treatment-response evidence.
- **U0267 — I:** variability and negative targeted workup suggest functional neurologic disorder, but positive balance/cerebellar findings make the diagnosis of exclusion incomplete.

## Identity evidence limitations requiring attention

- **Reference specificity unsupported (`S`):** U0140 (neurosyphilitic etiology), U0145 (HSV trigger), U0159 (full multisystem/etiologic composite), U0175 (exact melanoma stage), U0179 (M. chelonae species), U0185 (histoplasmosis), U0187 (secukinumab causality), U0192 (reference contradicted by GIST markers), U0197 (chronic necrotizing pancreatitis object), U0212 (secondary/unknown-primary status), U0215 (cryoglobulinemic etiology), U0240 (fungal invasion contradicted by tests), U0242 (heroin causality), U0255 (Fanconi component).
- **Family supported but full subtype not compelled (`F`):** U0147, U0149, U0154, U0160, U0174, U0188, U0194, U0220, U0229, U0243, U0259.
- **Missing decisive pathology/microbiology/imaging (`I`):** U0135, U0144, U0150, U0151, U0153, U0161, U0164, U0169, U0172, U0173, U0178, U0181, U0184, U0186, U0198, U0199, U0204, U0207, U0209, U0210, U0216, U0219, U0221, U0227, U0228, U0235, U0241, U0251, U0262, U0264, U0266, U0267.

## Complete–partial and task-object boundaries

- **U0142:** HLH and SPTCL each capture only one half of the supported composite; both remain `P`, not `C`.
- **U0146:** myocarditis, Kawasaki disease, and generic vaccine vasculitis capture components/parents of the full vaccine-associated Kawasaki-like multisystem syndrome; `P`.
- **U0147:** “extranodal marginal-zone lymphoma of the iris” is a complete clinical synonym for iris MALT lymphoma (`C`); generic iris lymphoma is `P`.
- **U0157:** Kummell disease is the complete eponymous equivalent (`C`); vertebral osteonecrosis/compression fracture are less complete (`P`).
- **U0159:** DAH, myocarditis, and vaccine myocarditis are components of the composite and therefore `P`.
- **U0163:** prostatic stromal sarcoma is relation-`C` to the reference even though case identity is `M`, because the biopsy also leaves STUMP as a second complete case-level answer.
- **U0165:** “aquatic dysautonomia or water-induced epilepsy” contains the target in a disjunction and is therefore `P`; committed epilepsy with aquatic triggers is `C`.
- **U0197:** pancreaticopleural fistula is a complication/alternate requested object, not a complete equivalent of chronic necrotizing pancreatitis; relation `M`.
- **U0202:** aortic thrombosis and embolic stroke each omit material portions of the retained-device causal chain; `P`.
- **U0211:** peritonitis is the source syndrome (`M`), while organism-specific bacteremia is the reference object.
- **U0220:** pancreaticopleural fistula is `P` to the full “complete pancreatic divisum with fistula” composite; acute pancreatitis is `M`.
- **U0222:** sarcoid cardiomyopathy and cardiac sarcoidosis are complete equivalents (`C`); generic sarcoidosis is `P`; heart-failure phenotypes are `M`.
- **U0226:** several candidates use nonstandard “vascular/VTC” wording. They were treated as broad descriptions of metastatic thyroid-origin cancer (`P`) rather than assumed to be exact vesicular thyroid carcinoma.
- **U0238:** all RBD candidates are `M` relative to the explicit advanced-Parkinson reference, despite RBD being the narrative's apparent requested object.
- **U0245:** ACS from left-ostial obstruction is a consequence (`M`) of the organized native-valve thrombus, not a complete equivalent.
- **U0247:** florid papillomatosis/generic paraneoplastic syndrome are manifestations (`M`) of the biopsy-proven renal urothelial carcinoma; specific alternative paraneoplastic syndromes are `X`.
- **U0252:** ELANE-SCN and liver abscess candidates are `P` because the reference is the genotype–abscess–organism composite.
- **U0257:** neutrophilic panniculitis is a tissue manifestation (`M`), while Sweet syndrome is a distinct neutrophilic dermatosis (`X`).
- **U0261:** generic cholesterol embolization/atheroembolism is `P` because it omits the cutaneous localization.

## Review cautions

- `U0193` and `U0158` have no candidates; their empty relation arrays are intentional.
- `U0238` is a likely source-question/reference-object mismatch and should not be silently “corrected” by candidate string similarity.
- Relation codes are reference-relative even when identity is `I`, `S`, or `M`; thus a reference-equivalent candidate can still be `C` in an identity-ambiguous case (for example U0163 and U0184).
