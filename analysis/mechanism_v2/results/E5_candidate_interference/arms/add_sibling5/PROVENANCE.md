# E5 add-sibling arm recovery provenance

The first execution of this frozen arm completed 200 ITA rows and reported
165 served rows, but its local scratch workspace was reclaimed before the arm
could be analysed, archived or committed. No prediction from that execution is
available and none enters an endpoint, variance estimate or model-selection
decision.

Recovery proceeded from remote `cursor4` at `0ca125486f88`, which contains the
frozen E5 preregistration, perturbations and all earlier arm commits. An initial
full checkout was stopped during unrelated Git-LFS smudging and quarantined; it
did not run an experiment. The first sparse recovery attempt produced 200
local failure rows with `ModuleNotFoundError` before any API request because
only `llm_client.py`, not its package imports, was checked out. That invalid
directory was quarantined and is not included here.

The committed result is the sole analysed reconstruction. It uses the same
frozen cases, perturbations, payload construction, prompt hash, model and
runtime controls as preregistered. It served 165/200 rows: 34 retained
construction failures and one selector schema failure. This recovery run is
not treated as a scientific replicate; the unavailable first execution is not
used for stability or variance claims.
