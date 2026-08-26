# Guideline Diagnostic KG v0.1

This directory is a reproducible, citation-bounded **candidate assertion
ledger** built from the repository's auditable Merck Manual 19e, manifest CPG,
and WikEM sources.  It is not a claim that every extracted assertion is
clinically correct, and it is not yet a production ranking graph.

## Release layers

- `source_layer/`: source-work/passages build manifests and aggregate statistics.
  Exact passages remain in the private internal archive.
- `claim_windows/`: source-free pointers, hashes, lineage and rechunking
  statistics.  The internal windows contain source text and remain private.
- `build/graph.public.jsonl`: source-text-free candidate projection.  Exact
  `Passage` and `EvidenceSpan.quote` records exist only in the internal graph.
- `build/residual_queue.jsonl`: source-free residual extraction work list.
- `production_queue/`: bounded extraction-unit pointers and optional,
  source-free lane indexes produced after source-native reassembly and
  claim-closure splitting.
- `safe_views/`: fail-closed, non-ranking projections of the audited template
  candidates and WikEM differential-membership records, plus an explicit
  quarantine ledger. These are still unreviewed authoring views.
- `quality_audit/`: source-free adjudication pointers used to derive the
  fail-closed export rule.
- `hybrid/`: added only when an LLM extraction run passes the stated quality
  gates.  Failed pilots are never merged into the graph.
- `drive_manifest.json`: checksums and private Google Drive locations for large
  internal artifacts.

Public records may carry short normalized labels and source pointers, but not
full passages or exact quotes.  The internal graph is authoritative for audit;
the public graph sets `authoritative=false`.

## Safety semantics

`review_status=unreviewed` means exactly that.  Candidate membership edges,
including WikEM differential enumerations, are marked
`ranking_eligible=false`; a name appearing in a list must not be interpreted as
a diagnostic criterion or likelihood ratio.  Consumers must also preserve
polarity, diagnostic role, necessity, logic, population and temporal scope.
Missing edges use open-world semantics and do not mean that a finding is absent.

## Rebuild outline

The builders read repository-local source files and never invoke Git LFS.
Credentials are read only from process environment variables.

```bash
python scripts/build_guideline_kg_passages.py --help
python scripts/build_guideline_kg_claim_windows.py --help
python scripts/build_guideline_diagnostic_kg.py --help
python scripts/compile_guideline_kg_extraction_queue.py --help
python scripts/extract_guideline_kg_residuals.py --help
python scripts/merge_guideline_kg_records.py --help
python scripts/export_guideline_kg_safe_views.py --help
```

The LLM path refuses silent truncation.  It first reconstructs each source in
native ordinal order, preserves diagnostic/list/table/criteria closure, then
splits into bounded extraction units.  Fixed token overlap is disabled; copied
scope headings are non-citable.  Every cited span must round-trip exactly to an
original Passage through half-open offsets.

For design rationale, token estimates, quality gates and actual build results,
see:

- `analysis/mechanism_v2/GUIDELINE_DIAGNOSTIC_KG_SCHEMA_EXTRACTION_COST.md`
- `analysis/mechanism_v2/GUIDELINE_DIAGNOSTIC_KG_CLAIM_WINDOW_AUDIT.md`
- `analysis/mechanism_v2/GUIDELINE_DIAGNOSTIC_KG_BASE_GRAPH_QUALITY_AUDIT.md`
- `analysis/mechanism_v2/GUIDELINE_DIAGNOSTIC_KG_LLM_PILOT_AUDIT.md`
- `analysis/mechanism_v2/GUIDELINE_DIAGNOSTIC_KG_BUILD_REPORT.md`
