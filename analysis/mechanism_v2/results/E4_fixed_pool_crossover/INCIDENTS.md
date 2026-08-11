# E4 runtime incidents

## e7 contrast arm

Attempt 01 failed 400/400 locally with `ModuleNotFoundError` before any API
call.  Attempt 02 completed at least 375 future results, then a 2048-token cap
and two long provider calls left the runner waiting in its tail; the PTY ended
before result assembly.  The final resume raised the cap to 8192, reused the
immutable per-payload cache, and served 400/400 without schema failure.

These attempts are provenance incidents, not repeat-run experimental arms.
Their raw files are stored in `E4_e7_contrast_RAW.tar.gz` and are excluded from
accuracy comparisons.
