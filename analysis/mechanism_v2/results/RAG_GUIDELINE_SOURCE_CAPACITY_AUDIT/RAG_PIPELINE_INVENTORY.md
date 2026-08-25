# RAG pipeline inventory: source → index → chunks → model payload

Audit target: `cursor4@291e98002d8da619ded8e0ad833cbd1b7a0021b8`  
Scope: repository state on 2026-08-25; implementation/log audit. This checkout intentionally does not hydrate most Git-LFS objects.

## Executive findings

1. **The four methods currently under study have no diagnosis-time RAG.** `collapse3c` and `multistance` use `run_aphhm_c.py` → `AphhmCPipeline`; `forest` and `IMPC` use `run_mosaic.py` → `MosaicPipeline`. Their constructors have no retriever and their online payloads have no `knowledge_chunks`. DA may later use an answer-option RAG mapper, but that is evaluation-time binding, not diagnostic evidence. MCR uses the official LLM judge.
2. **There are two MSD/Merck assets.** The 32 online MSD Professional manifest rows are categorically skipped by the chunker. The purchased Merck Manual 19e has 9,629 chunks; 3,311 survive the current CPG index filter. Merck is reachable through `cpg_index`, not the persisted general `rag_index`.
3. **B01/B07 use simple two-index RRF, not a clinical reranker.** For every query they take top 3 from `rag_index` and top 3 from `cpg_index`, exact-id deduplicate, add `1/(60+rank)`, keep 12, and truncate text to 1,600 characters. There is no chunk cross-encoder, source quota, evidence admission gate, article closure, or adjacent-chunk join.
4. **Actual adjacency is unavailable.** Merck and manifest CPG builders greedily pack paragraphs to 320 whitespace tokens with zero overlap. Metadata has no page, offset, ordinal, `prev_id`, or `next_id`. `expand_ddx_siblings()` is whole-`source_id` closure, not adjacency; Merck `source_id` is an entire chapter.
5. **This checkout cannot replay live RAG.** Both index metadata files and most index bodies are Git-LFS pointer stubs. `RAGRetriever._load()` parses metadata before guarded backend loading, so construction raises `JSONDecodeError` rather than returning `is_ready=False`. Merged PMC/CPG and StatPearls/textbook source chunks are also absent.
6. **A high-severity score-direction defect exists in the legacy guideline branch.** `RAGRetriever` scores are higher-is-better, but `GuidelineBranchSource._recall_legacy`, `_mmr_select`, and `_recall_v2` use `1/(1+score)`, favoring lower-scored and zero-score closure hits. The four current methods and generic B01/B07 RRF do not call this path.
7. **E11 is not an estimate of ideal or current production RAG.** It is a Merck-only local TF-IDF 4×2 development experiment with historical B07 queries, six chunks capped at 1,400 characters, and forced bundle assignment. Only 129/1,950 (6.62%) screened “relevant” chunks were case-specific; 1,397/1,950 (71.64%) had no case fit, and hard negatives contained gold support.

## 1. End-to-end lineage

### 1.1 Generic B01/B07 diagnosis-time RAG

```text
MCR/DA cases.parquet
  → baseline_common.load_runtime_cases()
      → vignette_body(): strips option block
      → runtime_payload(): case_id + vignette + generic question
          → B01 planner: 1–4 queries
          → B07 orchestrator: gate + ≤4 queries; 3-query fallback
              → retrieve_live_bundle()
                  → rag_index top 3/query
                  → cpg_index top 3/query
                  → exact (index,id) dedup
                  → RRF k=60
                  → top 12, text[:1600]
                      → B01 answer
                      → B07 diagnose + same-context refine
```

| Stage | File/function | Actual contract |
|---|---|---|
| Clean cases | `scripts/paper/baseline_common.py:211-277`, `load_runtime_cases`, `runtime_payload` | vignette-only diagnosis input; DA options retained only in case object |
| B01 planner | `scripts/paper/baseline_arms.py:590-632`, `run_b01`; `prompts/naive_cot_live_rag_planner.txt` | planner sees vignette; 1–4 queries; paper runner does not invoke the older repair helper |
| B07 query/gate | `baseline_arms.py:1842-1913`, `run_b07`; `_fixed_manifestation_queries` at 474-523 | orchestrator sees clean payload; `need_retrieval`; ≤4 queries; three fixed queries if empty |
| Retrieval/fusion | `scripts/eval_naive_cot_rag_ablation.py:120-182`, `retrieve_live_bundle`; wrapper `baseline_arms.py:526-547` | threshold 0; top 3/index/query; RRF top 12; 1,600 chars |
| Index construction | `scripts/paper/run_baseline.py:129-149`, `_build_retrievers` | constructs both `RAGRetriever`s; no explicit `is_ready` assertion |
| B01 model input | `baseline_arms.py:614-627` | runtime payload + `knowledge_chunks` |
| B07 model input | `baseline_arms.py:1876-1893` | diagnose sees chunks + orchestrator; refine sees identical chunks + draft + orchestrator |

There is **no retrieved-chunk reranker** in B01/B07. B02's listwise LLM reranks diagnosis candidates, not chunks.

### 1.2 Current four methods: exact payload boundary

| Method | Runner/mode | Model-visible data | Diagnosis RAG |
|---|---|---|---|
| APHHM-C `collapse3c` | `scripts/paper/run_aphhm_c.py`; archived `c4_selector_candev_nomatrix` | fact call: vignette + max facts; concept call: vignette + fact ledger + obligations/budget; selector: vignette + candidates/notes/groups | No |
| APHHM-C `multistance` | same runner; `multistance` | isolated stance calls receive same vignette/facts; tournament receives candidate groups/evidence | No |
| MOSAIC `forest` | `scripts/paper/run_mosaic.py`; `MosaicPipeline._run_forest` | each of three axis generators sees `vignette[:6000]`; selector sees vignette + shortlist + notes | No |
| MOSAIC `IMPC` | same runner; `_run_impc` | each doctor sees `vignette[:6000]` + doctor/perspective; selector sees registry/frontier | No |

File-level proof:

- `run_aphhm_c.py:136-214` constructs `AphhmCPipeline` without retriever and calls `pipe.run(case_id, vignette)`.
- All APHHM-C online calls in `src/agentclinic_tree_dx/aphhm_c.py` occur near 1085, 1130, 1267/1281, 1355, 1422, 1580, 1942, 2030, 2054, 2082, 2093; none has a knowledge/retrieval field.
- `run_mosaic.py:80-128` constructs `MosaicPipeline` without retriever and calls `pipe.run(case_id, vignette)`.
- All MOSAIC calls in `src/agentclinic_tree_dx/mosaic.py` occur near 538-678, 763 and 832 and use only vignette/internal state.
- Representative manifests: `logs/backbone_v1/diagnosisarena/{aphhm_c_collapse3c_v1,aphhm_c_multistance_v1,mosaic_forest_v1,mosaic_impc_v1}/manifest.json`.

Therefore the mere presence of a gold diagnosis in MSD/CPG cannot affect these four diagnostic executions unless a new adapter explicitly injects retrieval.

### 1.3 DA evaluation-time RAG mapper

`scripts/paper/baseline_mapper_score.py:123-211` creates `RelationAwareAnswerMapper` in `typed_llm_disagreement_rag` mode. `src/agentclinic_tree_dx/answer_projection_mapper.py:856-1026` passes vignette, question, all MCQ options and predicted leaves. For unmatched/low-confidence/schema-failed/deterministic-disagreement options, `_retrieve` at 715-755 uses:

```text
<question_target> relation between option '<option>' and diagnosis '<up to 4 leaves>'
```

It takes top 3 per index, truncates each to 1,200 chars, sorts sparse and dense raw scores together, and retains top 8 per dispute. The critic sees options/leaves/disputes/snippets. This can change DA scoring, but is not diagnosis-time RAG. MCR has no such mapper.

## 2. Sources and observed counts

### 2.1 Open CPG/MSD manifest

`data/cpg/manifest_latest.jsonl` contains 9,489 rows: 9,485 `ok`, 4 error, and 9,485 with `text_path`. There are 9,483 files under `data/cpg/text` and 14 API files.

Major manifest sources: PMC-OA 5,869; NICE 1,549; ACOG 339; ACR 300; ACC/AHA 248; SSC/SCCM 196; WikEM 163; ASH 156; ESC 153; IDSA 105; AAN 90; RCOG 72; Endocrine Society 69; EULAR 43; **Merck/MSD Manual 32**.

The 32 online MSD texts live in `data/cpg/text/merck-msd-manual/`, but `scripts/build_manifest_cpg_chunks.py:1-11` documents their exclusion and `scripts/cpg_manifest_common.py:21-22,90-96` enforces it through `SKIP_SOURCES` and id prefixes. They contribute zero downstream chunks.

### 2.2 Purchased Merck Manual 19e

| Artifact/statistic | Observed |
|---|---:|
| `data/corpus/merck/manifest.json` | pages 63-end; internal RAG; redistribution prohibited |
| `merck_manual_19e_extracted.txt` | 12.37 MB |
| `merck_manual_19e_chunks.jsonl` | 9,629 chunks |
| chapter-level `source_id`s | 353 |
| unique `(chapter, entry_title)` | 2,529 |
| entry type | disease 8,345; syndrome 1,284 |
| chunk type | background 3,532; evaluation 3,307; other 2,653; differential 136; red flag 1 |
| token length | mean 173.87; median 154; max 320 |
| rows surviving current CPG filter | 3,311 |

Build lineage:

- `scripts/build_merck_manual_corpus.py:50-87`: PDF extraction and chapter split.
- `scripts/merck_manual_common.py:101-126`: page cleanup.
- `merck_manual_common.py:154-176`: heuristic entry-title recognition.
- `merck_manual_common.py:179-206`: heuristic type classification.
- `merck_manual_common.py:213-232`: paragraph packing, zero overlap.
- `merck_manual_common.py:235-315`: emitted schema.

Structural risks: page markers are dropped before chunking and not restored; table/figure/bullet/bracket-only lines can be skipped; normal disease headings are mostly recognized only when followed by a standard subsection; “Approach” chapters use a broad Title-Case fallback; `source_id` is a chapter, not an entry; there is no within-paragraph split or true tokenizer accounting.

### 2.3 Processed guideline chunks present

| File | Chunks | Source IDs | Distribution |
|---|---:|---:|---|
| `data/cpg/processed/manifest_cpg_chunks.jsonl` | 39,091 | 2,270 | NICE 29,391; ACR 1,876; IDSA 1,222; ACOG 1,082; ESC 834; SSC/SCCM 749; ASH 747; ACC/AHA 693; rest 2,497 |
| same, chunk types | 39,091 | — | recommendation 31,260; evaluation 7,268; background 384; red flag 99; differential 80 |
| `data/cpg/processed/wikem_ddx_chunks.jsonl` | 1,055 | 149 | differential 379; evaluation 344; other 271; red flag 61 |
| Merck 19e | 9,629 | 353 chapters | as above |

The manifest parser also greedily packs to 320 whitespace tokens with zero overlap (`cpg_manifest_common.py:_chunk_paragraphs`, 284-299). `_emit_chunk` at 302-340 stores article/source id and section path but no page/offset/neighbors.

Missing current files:

- `data/cpg/processed/pmc_oa_ddx_chunks.jsonl`;
- merged `data/cpg/processed/cpg_chunks.jsonl`;
- StatPearls and textbook chunk JSONL files.

`scripts/build_cpg_chunks.py:33-40,93-164` is the merge step, but absent inputs mean a local rebuild would silently omit PMC. Historical documentation reports 360,234 merged rows; that cannot be reproduced from this checkout alone.

## 3. Persisted index inventory

| Index | Config | Verifiable composition | Current materialization |
|---|---|---|---|
| `data/corpus/rag_index` | MiniLM-L6-v2, 384-d, `IndexIVFPQ`, 493,646 | persisted config/history: 367,799 StatPearls + about 125,847 textbooks; no Merck/CPG | real 37-MB FAISS; metadata/TF-IDF are LFS stubs |
| `data/corpus/cpg_index` | TF-IDF, ≤80k features, 205,115, useful-only | aligned `cpg_medcpt_index/ids.json`: PMC 198,996 (97.01%); Merck 3,311 (1.61%); society/other 1,091; NICE 1,058; WikEM 659 | metadata/matrix/vectorizer are LFS stubs |
| `cpg_medcpt_index` | MedCPT, 768-d `IndexFlatIP`, 205,115 | exact aligned IDs present | embeddings/index are LFS stubs |
| `cpg_diff_index` | five TF-IDF buckets, 295,041 | society 1,091; Merck 2,240; NICE 1,072; PMC 289,741; WikEM 897 | manifest real; runtime assets LFS stubs |
| `case_report_index` | TF-IDF 40k, 77,849 | config only | runtime assets LFS stubs |

Build details:

- `scripts/build_cpg_tfidf_index.py:48-82` keeps differential/red-flag/evaluation/recommendation, requires ≥120 characters, removes gate/noise, and SHA-deduplicates only if a SHA exists.
- Lines 96-122 index `section_path + content + wiki_links` using bigram TF-IDF; no field weighting.
- `build_medcpt_cpg_index.py:60-70` aligns to sparse metadata; content is cut at 4,000 chars before a 512-token model limit.
- `build_rag_index.py:36-54` and `build_tfidf_index.py:29-46` now list Merck, while persisted `rag_index/config.json` lists only StatPearls/textbooks. Script and artifact generations have drifted.
- Both general builders write `data/corpus/rag_index`; one may leave stale incompatible sidecars from the other. Dense builder config still hard-codes only two sources although its loader now lists Merck.

Minimal current-state check:

```bash
PYTHONPATH=src python - <<'PY'
from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever
for path in ('data/corpus/rag_index', 'data/corpus/cpg_index'):
    try:
        print(path, RAGRetriever(path, device='cpu').is_ready)
    except Exception as exc:
        print(path, type(exc).__name__, exc)
PY
```

Both constructors currently raise `JSONDecodeError` on the LFS pointer header.

## 4. Retriever, closure and truncation behavior

### `RAGRetriever`

- `_load` (`src/.../knowledge/rag_retriever.py:55-100`) parses all metadata before guarded backend loads; no LFS detection or row-alignment assertion.
- `search` (277-333) emits higher-is-better normalized-IP or TF-IDF cosine scores.
- If metadata is shorter than the index, a vector can map to `{}` instead of failing (314/331).
- `expand_ddx_siblings` (243-275) appends WikEM link chunks and **all useful chunks with the same `source_id`**, score 0, with no internal cap. Source IDs are iterated from a set, so group order can vary by hash seed.
- No function retrieves actual previous/next chunks.

### `GuidelineBranchSource` (legacy/original APHHM path)

`src/.../knowledge/guideline_branch_source.py` defaults to top-k 30 and max 40 candidates. It supports multi-query fanout, pool/grounding/off closure, MMR/source diversity, deterministic name spotting and optional LLM extraction. Grounding returns ≤24 excerpts, each `content[:400]` (`_retrieve_snippets`, 928-972).

Implementation defect: `_recall_legacy` 565-568, `_mmr_select` 674-676 and `_recall_v2` 719-720 compute `1/(1+score)` despite higher-is-better scores. A 0.8 direct hit gets 0.556 while a zero-score closure sibling gets 1.0. `_recall_from_findings` 483-490 correctly uses raw score plus a 0.05 closure floor, confirming internal inconsistency.

### Generic B01/B07 limitations

- Repeated similar queries give repeated RRF credit to generic chunks.
- No source quota protects scarce Merck/NICE/WikEM against a 97%-PMC CPG index.
- No entity, scope, relation, temporality, contradiction or case-fit admission precedes prompt injection.
- Only the first 1,600 characters are served; late decisive criteria disappear.
- Paper traces record queries/request counts/served IDs/hash, but not served text. Once metadata is unavailable or changes, the exact historical prompt cannot be reconstructed.

## 5. Observed usage and failures

### 5.1 Older 17-case × 3 ablation

Artifacts: `logs/naive_cot_rag_ablation_v1/{summary.json,records.csv,traces/*.json}` and `TALP_STATUS_EXPLAINER.md:1825-1848`.

- 51 paired records; 42 gold-present records (14 cases ×3).
- Gold-present live RAG vs no RAG: Top-1 21.4% vs 26.2%; Top-2 59.5% vs 57.1%; MRR@2 40.5% vs 41.7%.
- Differences −4.8/+2.4/−1.2pp; intervals wide and cross zero.
- 612 served chunks, 271 unique IDs: general 236, PMC 260, Merck 54, WikEM 46, NICE 16.
- These traces preserve exact `input.knowledge_chunks`, unlike main paper traces.
- Known failures: Pancoast query anchoring on brachial plexopathy; glucagonoma anchoring on generic hyperglycemic crisis; pediatric obstruction text promoting intussusception over malrotation.

This older wrapper uses `case["case_text"]` directly at `eval_naive_cot_rag_ablation.py:195`; its fixtures can include options, so it is not byte-equivalent to the current paper clean-vignette path.

### 5.2 Main B01 census: DA100 + MCR400

Trace roots: `runs/paper_v1/diagnosisarena_rag_smoke_live/B01-cot-rag/...` and the three MCR B01 subsets (`seq100_v1`, `seq100_v2`, `seq200b_v1`). All 500 cases used four queries, eight index requests and 12 chunks.

| Source | Chunks | Share |
|---|---:|---:|
| general `rag_index` | 2,280 | 38.00% |
| PMC-OA | 3,099 | 51.65% |
| Merck | 311 | 5.18% |
| WikEM | 263 | 4.38% |
| NICE | 38 | 0.63% |
| other CPG | 9 | 0.15% |

### 5.3 Main B07 census: DA400 + MCR400

| Family | retrieval-on | chunks | general | PMC | Merck | WikEM | NICE | other |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DA | 334/400 | 4,008 | 1,759 | 1,914 | 166 | 131 | 33 | 5 |
| MCR | 356/400 | 4,260 | 1,908 | 1,992 | 152 | 175 | 25 | 8 |
| Combined | 690/800 | 8,268 | 3,667 | 3,906 | 318 | 306 | 58 | 13 |

Merck is 318/8,268 (3.85%) of served B07 contexts. B07 has no paired pre-retrieval diagnosis, so these observational traces cannot identify retrieval's causal effect.

### 5.4 E11 boundary

Files: `analysis/mechanism_v2/e11_b07_factorial.py` and `results/E11_b07_factorial/{preregistration.json,retrieval_manifest.json,retrieval_plan.jsonl,REPORT.md}`.

Contract:

- E11 records source commit `bb0fbd81d38bf0ab25ec492b771f81c7ea5db6e4`, not current HEAD.
- 400 development cases, DA200 + MCR200, selected from earlier E4.
- Merck-only `MerckLexicalIndex`: TF-IDF over title + content, 9,629 rows.
- Frozen historical B07 queries: 339 orchestrator, 61 runtime fallback.
- Six article-diverse query-top chunks; hard negative starts after top six and excludes their article IDs; random is stable/disjoint.
- Six chunks × ≤1,400 chars; non-off bundles are character-length matched.
- Retrieval condition is forced regardless of historical gate. Gold/options/scores/condition label are withheld.

Limits:

1. It is not `rag_index + cpg_index` RRF, MedCPT, differentiated retrieval, closure, adjacency or typed retrieval.
2. It inherits generic B07 queries rather than declaring a top-pair information need.
3. Treatment fidelity is weak: only 6.62% relevant chunks case-specific; 71.64% no-fit; 160/325 valid bundles had no reference support.
4. Hard negatives are contaminated: 84/325 valid bundles directly/partially support the reference.
5. Provider was not frozen; repeat runs/new confirmation/provider standardization were explicitly excluded.
6. The defensible result is: **forcing this weak lexical Merck bundle did not improve complete diagnosis**. It does not reject gold-supporting, vignette-matched, typed/adjacent RAG.

## 6. Ranked implementation risks

| Severity | Risk | Locus/consequence |
|---|---|---|
| Critical | LFS metadata pointer crash | `rag_retriever.py:55-62`; live constructor fails |
| Critical | four target methods lack diagnosis RAG | `run_aphhm_c.py`, `run_mosaic.py`; source capacity cannot affect their diagnosis |
| High | inverted guideline relevance score | `guideline_branch_source.py:565-568,674-676,719-720` |
| High | no true adjacency; Merck chapter-wide closure | chunk emitters + `expand_ddx_siblings` |
| High | 97% PMC in CPG index | scarce authoritative source passages compete in one pool |
| High | no chunk reranker/admission | `retrieve_live_bundle` forces topic-near noise |
| High | paper traces omit served text | exact historical payload not reconstructible from IDs alone |
| Medium-high | mapper merges uncalibrated raw sparse/dense scores | `answer_projection_mapper.py:752-755` |
| Medium-high | no metadata/index row assertion | stale metadata can silently bind empty/wrong hits |
| Medium-high | script/artifact source drift | general builder now lists Merck; persisted index does not |
| Medium | dense/sparse builders share output directory | stale incompatible sidecars can coexist |
| Medium | first-character truncation | decision criteria later in chunks are dropped |
| Medium | exact-ID-only dedup | semantic duplicates occupy slots and gain repeated-query credit |
| Medium | heuristic heading/type classification | diagnostic text can be filtered as background/other |
| Medium | online MSD categorically skipped | 32 stored rows have zero index capacity |

## 7. Safe replay commands

### Merck PDF extraction/chunking

```bash
PYTHONPATH=src:scripts python scripts/build_merck_manual_corpus.py \
  --pdf "<path-to-merck-19e.pdf>" \
  --start-page 63 --toc-end-page 52 --max-tokens 320

PYTHONPATH=src:scripts python scripts/build_merck_manual_corpus.py \
  --chunk-only \
  --pdf "<path-to-merck-19e.pdf>" \
  --max-tokens 320
```

These write canonical Merck outputs; run in an isolated copy when preserving existing artifacts.

### CPG rebuild after restoring missing PMC/source files

```bash
PYTHONPATH=src:scripts python scripts/build_manifest_cpg_chunks.py --useful-only --max-tokens 320
PYTHONPATH=src:scripts python scripts/build_cpg_chunks.py --useful-only
PYTHONPATH=src python scripts/build_cpg_tfidf_index.py
PYTHONPATH=src python scripts/build_medcpt_cpg_index.py
PYTHONPATH=src python scripts/build_differentiated_cpg_index.py
```

Without `pmc_oa_ddx_chunks.jsonl`, this silently builds a different corpus.

### General index after restoring StatPearls/textbook chunks

```bash
PYTHONPATH=src python scripts/build_rag_index.py \
  --model /data2/wanghongyi/models/all-MiniLM-L6-v2 --batch-size 64
```

This overwrites `data/corpus/rag_index`; do not mix dense and TF-IDF outputs in the same audit directory.

### Paper B01/B07 after hydrating indexes

```bash
PYTHONPATH=src:scripts:scripts/paper python scripts/paper/run_baseline.py \
  --dataset diagnosisarena \
  --subset-dir data/benchmarks/diagnosisarena/subsets/d2_seq100_v1 \
  --arms B01-cot-rag --case-ids 5 --workers 1 \
  --rag-index data/corpus/rag_index --cpg-index data/corpus/cpg_index

PYTHONPATH=src:scripts:scripts/paper python scripts/paper/run_baseline.py \
  --dataset diagnosisarena \
  --subset-dir data/benchmarks/diagnosisarena/subsets/d2_seq100_v1 \
  --arms B07-meddxagent-complete --case-ids 5 --workers 1 \
  --rag-index data/corpus/rag_index --cpg-index data/corpus/cpg_index
```

For MCR, change dataset/subset accordingly.

### Legacy 17-case ablation

```bash
PYTHONPATH=src:scripts python scripts/eval_naive_cot_rag_ablation.py \
  --rag-index data/corpus/rag_index --cpg-index data/corpus/cpg_index \
  --replicates 3 --workers 3 --output-dir /tmp/naive_cot_rag_replay
```

Defaults resolve historical fixtures; use `--cases`, `--gold`, `--tree-dir` and `--manual-adjudication` to freeze explicit inputs.

### E11 frozen Merck treatment

```bash
PYTHONPATH=src python analysis/mechanism_v2/e11_b07_factorial.py freeze \
  --retriever merck --workers 25 --out /tmp/E11_replay
```

Then run `diagnose` and `refine` once for each `--retrieval off|relevant|random|hard_negative`. This replays E11's treatment, not production B01/B07 retrieval.

## 8. Instrumentation required for the next capacity audit

Persist per case/call:

1. source/index build IDs, file hashes, counts and row-alignment assertions;
2. clean vignette hash and exact generated query;
3. all pre-fusion hits with source, raw score, rank and document/chunk ordinal;
4. fusion, rerank and admission decisions with rejection reasons;
5. true local neighbors by stable `(document_id, ordinal)` and broader article closure separately;
6. exact untruncated/served text hashes, truncation boundaries and model-visible order;
7. per-chunk gold mention/relation, vignette fit, decisive criterion, misleading content and neighbor-only decisive evidence;
8. frozen no-RAG, direct-only, direct+adjacent and direct+article-closure counterfactuals under identical model/provider;
9. diagnosis output separately from DA answer-mapper output.

“The manual contains the answer,” “retrieval hit a related article,” and “the model saw the decisive criterion” are three distinct claims and require separate endpoints.
