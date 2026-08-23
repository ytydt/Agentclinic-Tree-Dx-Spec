# Manual OpenRouter-bypass resume for C0 reviewers B and C

Date: 2026-08-15

Frozen protocol forbade model substitution. This directory records an explicit
operator override: finish the 402-interrupted panel without OpenRouter.

| Role | Frozen cache identity | Actual executor |
|---|---|---|
| Reviewer B | `anthropic/claude-sonnet-4.6` | local Cursor Grok 4.6 (parent + inherit subagents) |
| Reviewer C | `openai/gpt-5.6-sol` | `gpt-5.6-sol-high` subagents |

Cache keys still hash the frozen model IDs so `OnlineJSONCaller` identities
remain resume-compatible. Each new cache record includes `manual_resume`.

Scope: missing-cache cards only (B 922, C 301). Reviewer A validator-invalid
cards are not in this round. Successful immutable caches from the original
run are retained.
