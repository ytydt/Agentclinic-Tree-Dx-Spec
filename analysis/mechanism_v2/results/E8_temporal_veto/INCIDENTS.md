# E8 incidents and protocol enforcement

## Builder contract enforcement

- Gemini returned a transport-valid response for all 220 construction calls, but only 193 passed the scientific contract.
- Fail-closed reasons were 17 overlapping source spans, 6 ungrounded quotes, 3 wrong event counts and 1 invalid sensitivity label. No failed case was silently removed from the 220-case intention-to-analyse table.
- The builder asserted `adequate` sensitivity without vignette support. The frozen prompt explicitly required `unknown` in this situation, so 680 event rows (including rows in eventually failed cases) were deterministically downgraded from their immutable raw responses. No clinical sensitivity was imputed and no API call was repeated.
- The root audit later found six major ledger-A errors in the enriched 30-case sample. The worst was `MCR_v2_seq100/173`: a CT showing a large subdural collection and midline shift was rewritten as “no other abnormalities,” creating a false hard veto against the reference.

## Selector availability and long completion tails

- DeepSeek received `reasoning.max_tokens=64` and `reasoning.exclude=true`, but multiple providers still returned `finish_reason=length` or reached the 180-second cap on a short JSON task.
- Hard-veto served 184/193 construction-valid cases; soft and legal-order each served 192/193; invalid-time served all 125 identifiable interventions. Schema failures remain explicit in case results.
- Hard-veto accumulated 921,083 output tokens and 254 physical attempts for 192 recorded semantic calls. This is a runtime defect/route-control limitation, not a clinical error and not an accuracy denominator adjustment.
- No process-count storm was observed, so non-RAG concurrency remained at the authorized 50. OpenRouter used multiple providers; no Groq provider appeared.

## Heterogeneous proxy audit

- OpenAI GPT-4.1 mini served 25/29 frozen proxy-audit cases. Four outputs used an unregistered meaning-change label and failed closed; they were not retried.
- The proxy repeatedly folded deliberate invalid-time ledger-B changes into builder ledger-A fidelity. It also judged hard vetoes against non-reference candidates when the requested field concerned a reference hard veto. Root review therefore separated the layers and changed at least one coded field in all 29 proxy-sampled cases.
- One additional reference-hard-veto case had a failed soft selector schema and was added to root-only audit, yielding 30 manual cases and complete coverage of all nine hard reference vetoes.

## Environment adaptation

- This environment lacks the `openai`, `httpx` and `requests` packages. The production `RobustLLMClient` therefore selected its dependency-free OpenRouter transport.
- The official OpenAI SDK path remains implemented and is selected by environment/dependency capability when installed; E8 did not replace it with an experiment-specific terminal.
- An offline finalization invocation initially overwrote the transient key-present capability snapshot. `online_execution.json` reconstructs only non-secret run controls from the protected shell and telemetry; manifests now distinguish finalization capabilities from online execution.
