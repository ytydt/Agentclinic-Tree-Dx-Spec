# Frozen public source subset for phenotype-overlay experiments

These files support the offline, provenance-first source audit in
`analysis/mechanism_v2/phenotype_overlay_source_audit.py`. They are not an
activated clinical knowledge graph and do not authorize clinical inference by
co-occurrence alone.

## MedlinePlus

- File: `medlineplus/mplus_topics_compressed_2026-08-25.zip`
- Source: <https://medlineplus.gov/xml.html>
- Frozen download: <https://medlineplus.gov/xml/mplus_topics_compressed_2026-08-25.zip>
- SHA-256: `c7cf8c0c450ebf602249959152d0f07a942c7857913fcafbde231aeac8ab372d`
- Boundary: only NLM health-topic metadata and `full-summary` content is
  processed. Third-party `<site>` content is excluded. NLM attribution is
  retained.
- Attribution: Source: MedlinePlus, National Library of Medicine.

## Orphadata phenotype annotations

- File: `orphadata/en_product4_2026-07.xml.gz` (deterministic gzip of the
  downloaded XML; the XML content SHA-256 is recorded in the audit report)
- Source: <https://sciences.orphadata.com/phenotypes/>
- Frozen download endpoint: <https://www.orphadata.com/data/xml/en_product4.xml>
- Header date: `2026-06-23 07:57:18`
- SHA-256: `4f44e8a61201399911aa1ba44a293c0ccaa5ce11272c47d40862255cb72f6b32`
- Stored gzip SHA-256: `c1f0d44866f751d2d7bb58e04278f1d92d445a106fc4d0dd6427566f79ea65f7`
- License: CC BY 4.0. Copyright Orphanet 2026.
- Boundary: disorder--HPO associations are downstream retrieval postings, not
  phenotype definitions or logical entailment edges.

## DisMech source-discovery subset

- Upstream: <https://github.com/monarch-initiative/dismech>
- Commit: `93a6b51f5821868fd364b51010424e41045f2b5e`
- Included files: three YAML modules relevant to the six seed prototypes.
- Content license: CC BY 4.0; code license: BSD-3-Clause.
- Boundary: DisMech is AI-curated. Exact-snippet/citation checks support source
  discovery and provenance auditing, but do not establish clinical evidence
  strength or activate an edge.

## HOOM

- File: `hoom/hoom_orphanet_2.6.zip`
- Source: <https://sciences.orphadata.com/hoom/>
- Frozen download: <https://www.orphadata.com/data/ontologies/hoom/hoom_orphanet_2.6.zip>
- Version/date: 2.6, 2026-06-23/2026-07 release
- SHA-256: `5e33a3edaf97c6b1d008d601aaa90bd4d5460af073e54fc7df36e9638a49c395`
- License: CC BY 4.0.
- Boundary: frequency, diagnostic-criterion and pathognomonic qualifiers make
  HOOM a stronger rare-disease posting source than a flat association file, but
  still do not define how an arbitrary set of observations entails a phenotype.

No Git LFS object is used by this frozen source subset. The builder makes zero
network calls and zero LLM calls. Its only non-standard-library dependency is
`PyYAML>=6.0`, declared by the `phenotype-overlay` optional extra in
`pyproject.toml`.
