# Relation-slot annotation codebook

One row = one extracted assertion.  Question: **does the cited guideline text
license this relation slot for this (disease, finding) pair?**

Write `1` (licensed) or `0` (not licensed) in the `licensed` column.  Use `?`
if the quote is too truncated to judge; `?` rows are dropped, not guessed.

Slot meanings (the closed schema the engine consumes):

| relation | reading |
|---|---|
| `required_for` | the finding must be present to make the diagnosis |
| `pathognomonic_for` | the finding on its own establishes the diagnosis |
| `sufficient_for` | the finding is enough to diagnose, others may also be |
| `excludes` | the finding being **present** rules the disease out |

Conventions fixed by earlier rounds (keep them, they define the target):

1. A workup statement is not a necessity.  "Evaluation includes echocardiography",
   "an ECG is required", "Holter monitoring" -> `0` for `required_for`.
2. A test may be required only when the text is exclusive about it: "the
   diagnosis can only be made after angiography", "cannot be diagnosed without",
   or when the requirement is the test's *result*.
3. Screening and risk stratification are not index diagnosis: "essential to
   identify at-risk relatives" -> `0`.
4. Treatment or administrative thresholds are not diagnostic criteria:
   "gradient of 50 mmHg or more" (treatment), "grounded for seven days" -> `0`.
5. Counting criteria are necessities: "at least 2 of the three precordial
   leads", "3 or more metabolic abnormalities" -> `1` for `required_for`.
6. A disease-name tautology is not pathognomonic: "a condition termed long QT
   syndrome" for predicate `prolonged QT` -> `0`.
7. Judge the *relation slot as written*, not whether some other slot would have
   been better.  A true necessity written as `pathognomonic_for` is `0` here.
