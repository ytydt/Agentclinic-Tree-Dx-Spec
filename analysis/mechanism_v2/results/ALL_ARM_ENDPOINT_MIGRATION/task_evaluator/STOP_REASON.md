# Fresh task replay stop record

The fresh `unified-task-endpoint-v1` run used
`google/gemini-2.5-flash` at temperature 0 in a new, unseeded cache namespace.
The external API subsequently returned HTTP 402 with an explicit
`Insufficient credits` response. Online retries were stopped.

A cache-only closure pass then enumerated the full frozen registry:

- registered unique payloads: 5,832;
- successful fresh payloads: 3,337;
- cache-missing/not-evaluable payloads: 2,495;
- historical task outcomes reused: 0;
- missing task outcomes imputed: 0;
- task contrasts inferred from the partial cache: 0.

Clinical relation migration is independent of this stop and is complete for
all 23,035 served Top-1 rows. The task endpoint remains explicitly partial
until the same frozen namespace can be completed.
