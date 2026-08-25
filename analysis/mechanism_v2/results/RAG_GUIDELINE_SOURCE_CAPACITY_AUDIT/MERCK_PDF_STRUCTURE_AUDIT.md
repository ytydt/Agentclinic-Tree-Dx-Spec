# Merck Manual 19e PDF -> repository corpus: read-only structural audit

## Scope and source identity

- Attached PDF: `/workspace/scratch/83c9adfcac6c/upload/The Merck Manual of Diagnosis and Therapy, Nineteenth Edition (Robert S. Porter, Justin L. Kaplan) (z-library.sk, 1lib.sk, z-lib.sk)(2).pdf`
- SHA-256: `b8933f5e220df34909ed3b7e85807590ffffd8d0a6c7ebc5a3e913e772b8c4a1`
- Repository derivatives:
  - `/workspace/scratch/83c9adfcac6c/repo/data/corpus/merck/merck_manual_19e_extracted.txt`
  - `/workspace/scratch/83c9adfcac6c/repo/data/corpus/merck/merck_manual_19e_toc.json`
  - `/workspace/scratch/83c9adfcac6c/repo/data/corpus/merck/merck_manual_19e_chunks.jsonl`
  - `/workspace/scratch/83c9adfcac6c/repo/data/corpus/merck/manifest.json`
- The manifest points to the same basename without the copy suffix `(2)`. To verify identity rather than rely on the filename, pages 63, 64, 130, 668, 1200, 2000, 3000, 3665, 3674, 3705, and 4114 were freshly extracted from the attachment with the repository's `clean_page_text`; all 11 matched the stored page text exactly, character for character and by SHA-256.

## PDF-native structure

| Item | Evidence |
|---|---|
| Physical pages | 4,114 |
| Page labels | PDF pages 1-10 = `i`-`x`; PDF page 11 = printed page 1; PDF page 63 = printed page 53; PDF page 4114 = printed page 4104 |
| Metadata | Atop CHM to PDF Converter; creation 2012-06-15; modified 2014-04-20; unencrypted; untagged |
| Fonts/text layer | Embedded Unicode CID TrueType fonts (Arial family plus MS UI Gothic); all nonblank sampled pages have machine-readable text |
| Outline | 412 destinations: book/front, part headings, 353 chapter bookmarks, appendixes, index, and index letters |
| Clinical body | PDF pages 63-3673 (printed 53-3663) |
| Chapter 353 | PDF pages 3665-3673 |
| Appendixes | PDF pages 3674-3704 |
| Alphabetical index | PDF pages 3705-4114 |

The PDF outline is only two useful content levels (part -> chapter). It does not bookmark individual disease entries or diagnosis subsections. Disease-level lookup therefore needs text/index search, not bookmarks alone.

Text-layer audit of the clinical body (3,611 physical pages): 8 pages have no body text. Rendering shows that they are intentionally blank except for running header/footer, rather than failed OCR pages (`205, 464, 472, 1922, 2251, 2697, 2747, 3327`). All other clinical pages contain extractable text. The front has two completely blank physical pages (1-2).

## Repository extraction and chunking

The stored extraction contains 4,052 explicit markers, continuously covering PDF pages 63-4114. It is a faithful page-level text extraction of the attached PDF. The loss occurs mainly in the next transformation, not in source identification.

Current chunk corpus:

| Metric | Value |
|---|---:|
| JSONL chunks | 9,629 |
| Distinct chapters | 353 |
| `evaluation` | 3,307 |
| `differential` | 136 |
| `other` | 2,653 |
| `background` | 3,532 |
| `red_flag` | 1 |
| Chunks with any page field | 0 |

### 1. Appendixes and index are incorrectly swallowed by chapter 353

`build_merck_manual_corpus.py` extracts through page 4114. `chunk_extracted` removes all page markers and `split_chapters` makes the final `Chapter 353` segment run to EOF. An in-memory replay at native outline boundaries gives:

| End boundary | Total chunks | Chapter 353 chunks |
|---|---:|---:|
| Before appendixes (through PDF page 3673) | 9,401 | 18 |
| Through appendixes (through 3704) | 9,413 | 30 |
| Current EOF (through 4114) | 9,629 | 246 |

Therefore 228/9,629 chunks are structurally polluted: 12 appendix chunks and 216 alphabetical-index chunks. All are mislabeled as `Chapter 353. The Dying Patient`. Examples include entry titles `Appendix II: Normal Laboratory Values`, `Dermatitis; Skin;`, and `Phylloquinone` inside Chapter 353.

The index is potentially valuable, but should be parsed separately as a lexical alias/back-reference resource. It should not be embedded as diagnostic prose.

### 2. Page provenance is destroyed

`PAGE_MARKER_RE.sub("\n", text)` removes every page marker before chunk creation. None of the 9,629 JSONL rows has `page`, `page_start`, `page_end`, or printed-page-label metadata. A retrieved chunk therefore cannot be audited against the source page without a second full-text search, and page-neighbor expansion cannot be implemented from chunk metadata.

### 3. Disease heading recognition is systematically unreliable

The parser accepts a line as an entry title primarily when the next line is a recognized subsection. Merck entries often instead have: disease title -> parenthetical synonym -> bold summary paragraph -> `Etiology`/`Symptoms and Signs`. These titles are missed, while a preceding summary sentence immediately before a subsection is promoted to the entry title.

Deterministic warning indicators before Chapter 353:

- 2,446 unique `entry_title` values.
- 586 unique titles end in a period and label 2,577 chunks.
- 1,055 unique titles end in punctuation and label 4,371 chunks.
- A conservative sentence-like heuristic flags 936 unique titles covering 3,863 chunks. This is a warning count rather than a validated false-positive rate.

Directly verified examples:

| True entry | Source pages | Actual chunk metadata |
|---|---|---|
| Appendicitis | PDF 174-175, printed 164-165 | symptoms and diagnosis are under `In all types of perforation, nausea, vomiting, and anorexia are common. Bowel sounds are quiet to absent.` |
| Wilson disease | PDF 111-113, printed 101-103 | diagnostic chunks are under `Wilson's disease should be suspected in people < 40 with any of the following:`; symptoms remain under the previous disease's summary sentence |
| Pheochromocytoma | PDF 942-944, printed 932-934 | symptoms/diagnosis are under `Patients with Cushing's disease usually have a small adenoma of the pituitary gland.` |
| Epiglottitis | PDF 585-587, printed 575-577 | entry begins inside a `GABHS.` treatment chunk; symptoms remain under `GABHS.`; diagnosis is under `However, severe throat pain with a normal-appearing pharynx raises suspicion of epiglottitis.` |

This means the prose often contains the right diagnosis, but metadata-based title boosting, entry filters, source closure, and disease-name matching can point to the wrong entity.

### 4. Fixed-token chunks often sever sentences and criteria, without overlap

In the 9,383 pre-Chapter-353 chunks:

- 2,193 (23.4%) begin with a lowercase letter.
- 96 begin with punctuation.
- 2,688 (28.6%) end without terminal sentence punctuation.
- 2,537 (27.0%) are at least 300 words/tokens; maximum is 320; there is no overlap.

Across 3,594 nonempty adjacent clinical-page boundaries, 1,393 (38.8%) have both a nonterminal preceding page ending and a lowercase next-page start, strongly indicating a continued sentence. Removing page markers retains rough order but eliminates the ability to restore boundary context or distinguish a page-spanning criterion from a new section.

For epiglottitis, the title/summary is in chunk 33, manifestations (drooling, toxicity, tripod position) in chunk 34, diagnostic contrast (`severe sore throat and no pharyngitis`) in chunk 35, and treatment in chunk 36. A direct hit on only one chunk does not contain the complete diagnostic pattern. Adjacent `chunk_id +/- 1` expansion is therefore evidence-backed, whereas chapter-wide `source_id` closure would pull all 36 unrelated Chapter 52 chunks.

### 5. CHM popup tables/figures are absent, and their labels leak into prose

The clinical extraction contains 872 lines beginning `[Table` and 213 beginning `[Fig.`. Visual inspection of PDF page 586 shows `[Table 52-1. Differentiating Epiglottitis from Croup]` as a blue, underlined CHM link-style label only; the table body is not embedded in the PDF (and the converted PDF page has no link annotation). The current parser drops the first placeholder line but often leaves continuation text such as `Glycemic Index of Some Foods]` inside the surrounding chunk.

This is partly a source limitation, not merely a splitter bug. The modern online MSD epiglottitis file in the repository contains the missing comparison table (onset, age, barking cough, epiglottis appearance, thumb/steeple x-ray signs), whereas the 19e PDF and its chunks do not. A vignette keyed to `thumb sign` therefore cannot be bridged from the 19e epiglottitis entry even with perfect chunk retrieval; the only `thumb sign` occurrence in the 19e extraction is unrelated.

### 6. Subscript and cross-reference cleanup destroys clinically important symbols

`clean_page_text` deletes any line consisting only of digits before trying to repair split references. In the raw PDF text on physical page 2004, `O2 saturation` is represented as `O\n2\n saturation`; cleaning removes `2`, yielding `O saturation`. There are 54 chunks containing this degraded `O ... saturation` pattern. Exact-line remnants also include `PaO`, `PaCO`, `FIO`, and `HCO` with their subscripts lost or detached.

The same order-of-operations removes numeric page targets from `see p.\n2879`, and table placeholders are removed separately. Epiglottitis chunk 35 consequently contains `bronchitis-see ... and p. ... )` rather than `see Table 52-1 and p. 2879`.

## Separate online MSD text directory

`/workspace/scratch/83c9adfcac6c/repo/data/cpg/text/merck-msd-manual/` is not the PDF derivative. It contains 32 files totaling 574,416 bytes, dated/reviewed as modern online MSD content. Thirty are specialty/site navigation or index dumps: they contain disease/subsection names but generally no article prose. Two are article-style pages: epiglottitis and laboratory reference ranges.

This directory should not be treated as a second full MSD corpus. It is useful as a hierarchy vocabulary and, for the two full pages, as an updated supplement. The epiglottitis comparison also proves that online content can contain diagnostic tables and newer terminology absent from the 19e CHM export.

## Read-only disease/synonym -> source page workflow

Helper script:

`/workspace/scratch/83c9adfcac6c/tmp_agent_pdf/merck_page_search.py`

Example:

```bash
python /workspace/scratch/83c9adfcac6c/tmp_agent_pdf/merck_page_search.py \
  "Epiglottitis" "Supraglottitis" --neighbors 1 --max-hits 20
```

The script:

1. reads the faithful page-marked extraction for fast search;
2. normalizes Unicode, whitespace, dash variants, ampersands, and possessives;
3. searches an OR-list of disease names/synonyms;
4. obtains printed page labels and clinical/appendix/index bounds from the PDF outline;
5. returns PDF physical page, printed label, matched synonym, excerpt, and adjacent physical/printed pages;
6. excludes appendixes and index by default, with explicit flags to include them.

Example output for epiglottitis locates the main entry at PDF pages 585-587 (printed 575-577) and the symptom-oriented sore-throat approach at PDF pages 571-574 (printed 561-564). Searching old/new nomenclature with `"Granulomatosis with polyangiitis" "Wegener granulomatosis"` finds only the older-name hits, which makes an edition-vocabulary gap explicit rather than silently reporting no source coverage.

For visual or layout verification of a returned hit, render the hit and neighbors without touching the source:

```bash
pdftoppm -f 584 -l 586 -png -r 170 "<PDF>" /tmp/merck_hit
```

## Immediate implications for a diagnosis-capability audit

- Assess source capability at three distinct levels: exact PDF page, faithful page text, and runtime chunk. A gold diagnosis can be present at page level yet absent from chunk title metadata or split across neighbors.
- Search old and current aliases separately. The 19e uses older disease names such as Wegener granulomatosis; exact matching current terminology alone yields false source-absence conclusions.
- Treat table-dependent cases as source-limited. The CHM export may name a table without containing its body.
- Separate lexical/index coverage from diagnostic-prose coverage. Index hits demonstrate that a term existed in the book, not that the retrieved index chunk explains the diagnosis.
- For manual audit sampling, record both physical PDF page and printed page label. All in-text cross-references use the printed label (physical page minus 10 after the front matter).
