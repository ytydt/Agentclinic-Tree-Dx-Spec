# E7c aborted preflights

These were engineering preflights, not completed scientific arms. They are
listed so the successful formal run does not erase failed implementation
attempts.

| Local directory | Attempt | Why stopped | Scientific consequence |
|---|---|---|---|
| `/tmp/E7c_directional_registry_aborted_v1_20260811` | Per-case DeepSeek relation typing | Relation objects repeatedly exhausted the output budget before completing valid JSON. | No endpoint was analysed; design changed from per-case relation output to bounded chunks. |
| `/tmp/E7c_directional_registry_preflight_v2_20260811` | Preregistration-only dry setup | Used to verify the frozen selection and payload contract before calls. | No model result and no arm estimate. |
| `/tmp/e7c_v2_extreme_smoke` | DeepSeek relation chunks on extreme cases | Only four of six worst-case chunks validated; output-length failures remained. | DeepSeek was rejected as the relation annotator for the formal run. |
| `/tmp/e7c_gemini_extreme_smoke` | Gemini relation chunks on the same extremes | Six of six chunks validated. | Supported choosing Gemini for relation typing; not included in the outcome data. |

The formal run started from a newly written preregistration, used all 299 frozen
cases, and did not mix any preflight response into its cache or endpoint table.
