# OpenRouter reasoning-control runtime check

Purpose: prevent the selector reasoning/output storm observed in E7c while
retaining both supported transports.

Implemented controls:

- `TREE_DX_REASONING_EFFORT` or `TREE_DX_REASONING_MAX_TOKENS` (mutually
  exclusive);
- `TREE_DX_REASONING_EXCLUDE` for returned reasoning text;
- official OpenAI SDK requests use `extra_body={"reasoning": ...}`;
- requests/stdlib OpenRouter requests carry the same top-level `reasoning`
  object;
- no environment variable means byte-for-byte legacy request semantics.

Verification on 2026-08-11:

- six dependency-free tests passed, including fake official-SDK and stdlib
  transport captures;
- a first online smoke inherited a stale dynamic proxy port from a long-lived
  shell and failed with connection refused; it was stopped and was not entered
  into an experiment cache;
- a fresh-shell online call to `deepseek/deepseek-v4-flash-0731` with
  `max_tokens=64`, `exclude=true` and output cap 512 returned the requested
  compact JSON successfully;
- the environment still lacks the official `openai` package, so the live smoke
  used the stdlib path. The SDK path is exercised by the captured-request unit
  test and remains preferred automatically when that dependency is installed.

Subsequent scientific runners should snapshot these variables into their
manifest and use `TREE_DX_LLAMA_PROVIDER_POLICY=balanced` whenever a Llama model
is selected, preventing Groq-only routing.
