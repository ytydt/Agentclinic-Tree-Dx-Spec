# E5 perturbation construction checkpoint

The frozen 200-case sample contains 100 DA and 100 MCR cases, each with a
natural four-candidate source pool that contains one exact-or-frozen-synonym
gold option. Before any selector arm ran, one target-aware construction call
per case attempted to create five typed single-candidate interventions
(parent, sibling, unrelated, synonym and component) plus four separately
matched complete-diagnosis distractors for the nested width control.

## Construction result

| Family | Valid complete construction | Retained construction failure |
|---|---:|---:|
| DA | 90/100 | 10/100 |
| MCR | 76/100 | 24/100 |
| Total | **166/200** | **34/200** |

Thirty-three failures returned a width-control label that duplicated a typed
or base candidate; one failed to return exactly five typed relations. The
strict validator rejected the whole construction. Although some typed rows in
those responses may be individually usable, they are not salvaged: all five
typed additions and both width additions fail closed on the same 34 cases.
Base-4 and remove-one arms remain valid for all 200 cases. This preserves the
pre-run all-or-nothing contract and prevents post-outcome selective recovery,
at the cost of power and unequal DA/MCR missingness.

The construction phase recorded 200 semantic calls, 427 physical attempts,
285,089 input tokens and 2,026,073 output tokens. Aggregate provider latency
was 32,080.8 seconds. Fourteen provider names appear in telemetry; no Groq-only
route was used. The environment lacked the official `openai` package, so the
environment-selected standard-library transport was used while the official
SDK path remains available in code.

Many physical retries followed output truncation or timeout before the final
semantic contract result. This is an implementation weakness of asking a
reasoning model/provider mix for nine ontology objects in one strict response,
not a credential failure. The OpenRouter key remained usable.

A stable SHA sample of 10 valid DA and 10 valid MCR constructions was frozen
in `perturbation_audit_sample.jsonl` before selector outcomes. Final manual
analysis will judge semantic relation fidelity in that sample and all
effect-discordant injected-candidate cases; self-reported `valid=true` is not
treated as ontology ground truth.
