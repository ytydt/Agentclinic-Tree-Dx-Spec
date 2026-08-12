# E7 registry identity replay

## Result in one sentence

Across 800 existing development trajectories, the legacy substring registry made at least one non-synonym fold in 299 cases (37.4%); replacing it with exact frozen-synonym identity restored a mean of 0.550 separately addressable concepts per case.

These are mechanism/development estimates, not a new confirmation result. The offline replay isolates identity and exposure mechanics; it does not count the old selector's answer as if the selector had seen the changed pool.

## Endpoint and audit boundary

`legacy substring` names the **registry-construction treatment** in this
offline replay. It is not the historical `legacy-chain` scoring endpoint.
Likewise, exact frozen-synonym identity is used here to test node separation
and contamination; this report does not present safe-exact diagnosis accuracy,
clinical-complete accuracy, partial credit or task/mapper accuracy. Those
endpoints require an actual arm output under their own frozen contracts.

The 800-case counts below are deterministic structural replay results. Human
clinical review in `MANUAL_AUDIT.md` covers ten purposively selected
high-leverage trajectories and is exhaustive only for those ten mechanism
traces. The other cases did not receive complete/partial/no root adjudication,
so the review cannot be converted into a clinical rate. No E2 full-800 replay
number is inserted into this E7a cohort.

## Primary structural endpoints

| Group | n | Cases with unsafe fold | Unsafe pairs | Evidence-transfer targets | Mean nodes restored | Legacy-registry gold identity contamination | Exact-synonym contamination |
|---|---:|---:|---:|---:|---:|---:|---:|
| ALL | 800 | 299 (37.4%) | 1199 | 1040 | 0.550 | 2.8% | 0.0% |
| DA | 400 | 167 (41.8%) | 725 | 588 | 0.645 | 0.5% | 0.0% |
| MCR | 400 | 132 (33.0%) | 474 | 452 | 0.455 | 5.0% | 0.0% |

The identity-contamination endpoint asks whether the node containing an exact/frozen-synonym gold or selected label also contains a label that is not a confirmed synonym. It is therefore a more conservative structural condition than simple post-registry recall: a swallowed gold string can remain textually present while losing its own node.

## Reconstruction check

The replay reproduced the logged production concept count in 100.0% of cases, the logged preferred-name/alias partition in 100.0%, and logged scores in 100.0%.

Any non-100% reconstruction is retained at case level and is a scope warning, not silently discarded.

## Highest-leverage trajectories for manual audit

| Slice / case | Gold | Logged champion | Unsafe pairs | Foreign support spans | Legacy top score | Exact top score |
|---|---|---|---:|---:|---|---|
| DA_d2_heldout200b/638 | Laryngeal histoplasmosis | Histoplasmosis | 17 | 36 | Histoplasmosis | Histoplasmosis |
| MCR_v2_seq100/197 | Pseudoseptic arthritis | viscosupplementation-related inflammatory reaction | 12 | 47 | viscosupplementation-related inflammatory reaction | viscosupplementation-related inflammatory reaction |
| MCR_seq200b/407 | Adrenal myelolipoma | Myelolipoma | 11 | 9 | Myelolipoma | Myelolipoma |
| MCR_seq200b/283 | dermoid cyst | Dermoid cyst | 9 | 23 | Dermoid cyst | Dermoid cyst |
| MCR_v2_seq100/173 | Chronic subdural hematoma | Subdural Hematoma | 9 | 22 | Subdural Hematoma | Chronic Subdural Hematoma |
| MCR_v2_seq100/205 | Cysticercosis | Cysticercosis | 7 | 16 | Cysticercosis | Cysticercosis |
| MCR_seq200b/383 | Idiopathic granulomatous mastitis | Idiopathic granulomatous mastitis | 5 | 15 | Idiopathic granulomatous mastitis | Granulomatous mastitis |
| MCR_v1_seq100/54 | Trigeminal neuralgia | Trigeminal Neuralgia | 3 | 12 | Trigeminal Neuralgia | Trigeminal Neuralgia |
| MCR_seq200b/464 | ruptured popliteal artery aneurysm | Popliteal artery aneurysm | 3 | 10 | Popliteal artery aneurysm | Popliteal artery aneurysm |
| MCR_v1_seq100/12 | Tumor-induced osteomalacia | Osteomalacia | 3 | 8 | Osteomalacia | Osteomalacia |
| MCR_v2_seq100/169 | rheumatoid arthritis | Rheumatoid Arthritis | 3 | 8 | Rheumatoid Arthritis | Rheumatoid Arthritis |
| MCR_v1_seq100/13 | Compound odontoma | Odontoma | 3 | 7 | Odontoma | Odontoma |
| MCR_v2_seq100/154 | Decompression sickness | Decompression Sickness | 3 | 6 | Decompression Sickness | Decompression Sickness |
| MCR_seq200b/386 | chondrosarcoma | Laryngeal Chondrosarcoma | 3 | 4 | Laryngeal Chondrosarcoma | Laryngeal Chondrosarcoma |
| DA_d2_heldout100/261 | Cutaneous malakoplakia | Malakoplakia | 2 | 7 | Malakoplakia | Malakoplakia |
| MCR_seq200b/322 | Factitious disorder | Factitious disorder imposed on self | 2 | 6 | Factitious disorder imposed on self | Somatoform disorder |
| MCR_v2_seq100/159 | endometrioid adenocarcinoma | Iatrogenic tumor dissemination | 2 | 3 | Disseminated peritoneal leiomyomatosis | Disseminated peritoneal leiomyomatosis |
| MCR_v1_seq100/69 | Gastric lipoma | Gastric Lipoma | 2 | 2 | Gastrointestinal Stromal Tumor (GIST) | Gastrointestinal Stromal Tumor (GIST) |
| MCR_seq200b/418 | Sarcoidosis | Sarcoidosis | 2 | 2 | Sarcoidosis | Arrhythmogenic Right Ventricular Cardiomyopathy |
| MCR_v2_seq100/236 | Eosinophilic mastitis | Eosinophilic mastitis | 2 | 0 | Eosinophilic mastitis | Eosinophilic mastitis |

## Mechanism interpretation and falsifier

The production rule is not merely cosmetic deduplication. When a broad label is encountered first, a later specific label can be converted into an alias; support spans, generator agreement and axis bonuses are then pooled into the broad node. Reversing insertion order tests the complementary failure: the same evidence may be attached to a different preferred surface, and non-transitive substring chains can change the partition itself. The typed arm keeps those nodes distinct and records `non_equivalent_lexical_relation` edges. Their clinical direction is deliberately unresolved: for example, pseudoseptic arthritis is not a subtype of septic arthritis merely because one string contains the other.

This mechanism would be weakened if (a) unsafe folds were rare with tight case-level intervals, (b) they caused no evidence or exposure change, and (c) fresh blinded selector calls were invariant. E7a tests (a) and the registry portion of (b). E7b is the preregistered fresh-selector test for (c).

## Deliberate limits

- The disease bridge is used only by exact normalized key lookup; its fuzzy and substring resolver tiers are disabled.
- Lexical relation edges assert non-identity and surface containment only; they are not a clinical ontology gold standard.
- Logged selector outputs are mapped for identity contamination only; no clinical win/loss is credited without a fresh selector call.
- No task result is inferred from the pre-mapper registry, and no
  `legacy-chain` or safe-exact result is inferred from node containment.
- Full unsafe-pair ledger contains 1199 rows; case-level JSONL retains all arm payloads.
