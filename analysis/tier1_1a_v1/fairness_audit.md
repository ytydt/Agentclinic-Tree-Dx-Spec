# T1-04 Fairness / budget audit

Created: 2026-07-31T03:39:45.493594+00:00

**Disclaimer:** Token columns are POST-HOC estimates, not an official ledger (PAPER I05 deferred). M00 input tokens are not recoverable from response-only caches; use schedule proxies + any prior gap file.

Tokenizer: `tiktoken_cl100k_base`

| system | kind | n | calls | retr_snips | out_tok_est | in_tok_est | knobs |
|---|---|---:|---:|---:|---:|---:|---:|
| mcr_m00 | APHHM | 100 | 37.0 | 17.0 | 13744.2 | — | 4 |
| ox_m00_hot | APHHM | 100 | 81.2 | 13.4 | 32563.7 | — | 4 |
| ra_m00 | APHHM | 100 | 36.5 | — | 13999.5 | — | 4 |
| mcr:B00-direct-cot | baseline | 100 | 1.0 | 0.0 | 0.0 | 0.0 | 0 |
| mcr:B01-cot-rag | baseline | 100 | 2.0 | 12.0 | 0.0 | 0.0 | 0 |
| mcr:B04-dual-inf | baseline | 100 | 5.1 | 0.0 | 0.0 | 0.0 | 0 |
| mcr:B05-mdagents | baseline | 100 | 6.5 | 0.0 | 0.0 | 0.0 | 0 |
| mcr:B06-mac-single-vendor | baseline | 100 | 4.0 | 0.0 | 0.0 | 0.0 | 0 |
| mcr:B07-meddxagent-complete | baseline | 100 | 3.0 | 10.3 | 0.0 | 0.0 | 0 |
| mcr:B12-sc-cot-5 | baseline | 100 | 5.0 | 0.0 | 0.0 | 0.0 | 0 |
| ra:B00-direct-cot | baseline | 100 | 1.0 | 0.0 | 0.0 | 0.0 | 0 |
| ra:B01-cot-rag | baseline | 100 | 2.0 | 12.0 | 0.0 | 0.0 | 0 |
| ra:B04-dual-inf | baseline | 100 | 5.1 | 0.0 | 0.0 | 0.0 | 0 |
| ra:B05-mdagents | baseline | 100 | 6.6 | 0.0 | 0.0 | 0.0 | 0 |
| ra:B06-mac-single-vendor | baseline | 100 | 4.0 | 0.0 | 0.0 | 0.0 | 0 |
| ra:B07-meddxagent-complete | baseline | 100 | 3.0 | 9.2 | 0.0 | 0.0 | 0 |
| ra:B12-sc-cot-5 | baseline | 100 | 5.0 | 0.0 | 0.0 | 0.0 | 0 |
