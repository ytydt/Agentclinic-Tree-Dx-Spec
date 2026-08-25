# LOINC2HPO annotation snapshot

This directory contains a pinned copy of the public LOINC2HPO annotation table
used by the offline phenotype-lift feasibility probe.

- Upstream: <https://github.com/TheJacksonLaboratory/loinc2hpoAnnotation>
- Commit: `c1068d6d6b80ce757ff7a26e4c38a5ac8e7c830c`
- Commit date: 2021-11-07
- Imported: 2026-08-25
- Table SHA-256: `bb112ccf9359719bdf2c18a45d3a3e6116059a19d917cdc4473ad0642e4141e0`
- Census: 7,415 rows, 3,118 unique LOINC identifiers, 827 unique HPO identifiers

The table maps an already identified LOINC observation plus a categorical
result interpretation to one HPO term. It does not parse free text, choose a
reference range, or define multi-finding syndromes.

Redistribution and use remain subject to the upstream `License.md`, including
its LOINC notice. The snapshot is deliberately pinned because it is old and
should not be presented as current LOINC coverage.
