# CoreLift frozen endpoint evaluation

## Interpretation contract

This is a **development-not-confirmation** analysis of the repeatedly used 800-case development set. Clinical completeness is a blinded three-model panel sensitivity and **not human-root truth**. Official task performance and clinical-complete are different estimands.

DA reports **DA Acc@N / option accuracy** after gold-blind top-1 diagnosis→source-option projection. MCR reports frozen **Prompt-7 Acc**. DA and MCR are never pooled.

## Arm endpoints (ITA)

| Family | Arm | Service | Official task | Clinical complete | C∪P | Complete exposure | C∪P exposure | Conditional conversion | Mean width |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DA | `A0_control` | 97.00% | 22.50% | 3.75% | 58.50% | 4.50% | 71.50% | 83.33% | 2.79 |
| DA | `A1_views` | 99.25% | 28.50% | 5.50% | 65.00% | 6.50% | 85.25% | 84.62% | 5.09 |
| DA | `A2_views_typed` | 97.00% | 25.50% | 5.00% | 63.25% | 5.25% | 79.00% | 95.24% | 3.64 |
| DA | `A3_full` | 99.50% | 25.50% | 5.00% | 63.00% | 5.25% | 81.25% | 95.24% | 3.72 |
| DA | `B1_corelift` | 99.25% | 31.00% | 7.50% | 64.75% | 9.25% | 83.00% | 81.08% | 4.83 |
| MCR | `A0_control` | 97.25% | 31.75% | 25.00% | 41.75% | 30.00% | 54.00% | 83.33% | 2.77 |
| MCR | `A1_views` | 97.50% | 34.75% | 28.00% | 43.75% | 36.00% | 65.00% | 77.78% | 4.71 |
| MCR | `A2_views_typed` | 97.50% | 32.75% | 25.25% | 43.75% | 32.00% | 61.25% | 78.91% | 3.48 |
| MCR | `A3_full` | 97.25% | 32.50% | 24.75% | 44.25% | 31.25% | 61.50% | 79.20% | 3.48 |
| MCR | `B1_corelift` | 97.75% | 30.50% | 25.00% | 43.75% | 33.75% | 63.00% | 74.07% | 4.50 |

## M2/B1 modifier gate

Gate pass: **False**. Literal closure=1.0, raw agreement=0.927122464312547, Gwet AC1=0.9154224472114996, hallucination=0.11119459053343352, service=1.0.

On gate failure, B1 official DA/MCR task results remain reported. B1 clinical-complete is marked `confirmatory_withheld_gate_failure=true`, and B1-vs-A3 clinical confirmatory contrasts are not executed or interpreted.

## Complete transition closure definitions

- `specificity_rescue`: B1 becomes complete through an accepted completion whose parent matches the A3 champion.
- `object_rescue`: B1 becomes complete through a different/new diagnostic object.
- `scope_compression`: A3 complete is lost but B1 remains C∪P.
- `catastrophic_substitution`: A3 complete is lost and B1 is outside C∪P.

The signed closure is specificity rescue + object rescue − scope compression − catastrophic substitution.

Observed A3→B1 discordant counts: specificity rescue=14, object rescue=12, scope compression=3, catastrophic substitution=12; signed complete net=11.

## Paired inference

Primary contrasts use case-level exact McNemar on the full ITA denominator. Holm is applied separately within each benchmark family and endpoint; common-served results are sensitivity analyses only.

Evaluated contrast records: 26; withheld records: 4.
