"""§31.13.11 — Guideline-grounded mandatory-branch recall (StatPearls/textbook RAG).

Determines the candidate disease families for a presenting syndrome by RETRIEVING
the differential-diagnosis / etiology / evaluation sections of the local
StatPearls + textbook RAG corpus (``data/corpus/rag_index``) and spotting the
disorder entities that appear VERBATIM in those snippets. This is the
"guideline/textbook as the mandatory-branch source" path of §31.13.11 — it
recovers the *presenting-syndrome → differential* framing that the disease-
intrinsic ontologies (SNOMED ``is_a``/``finding_site``) cannot reconstruct
(§31.13.10).

Design (deterministic, no LLM — the GARMLE-G generation-augmented query and LLM
grounded extraction are kept as a *reference backup* per §31.13.12, to be added
only if this deterministic recall underperforms):

  1. query    : "differential diagnosis of {syndrome}" + "causes / etiology of
                {syndrome}" against the dense RAG index.
  2. filter   : keep snippets whose title section is Differential Diagnosis /
                Etiology / Evaluation / Causes (StatPearls titles are already
                "{Article}. > {Section}"), or whose article title matches the
                syndrome — so off-topic neighbours are dropped.
  3. spot     : longest-match n-gram lookup of the aggregated snippet text against
                the SNOMED *disorder* vocabulary → disorder entities mentioned in
                the differential.
  4. score    : disease score = Σ retrieval-score over snippets it appears in;
                returned ranked. Feeds KBAxisMap.partition_from_candidates for
                the axis/domain partition (so the branch_knowledge contract and
                all downstream options are unchanged).
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .cpg_chunk_gate import snippet_on_topic

logger = logging.getLogger(__name__)

# generic disorder tokens that must never be returned as a standalone family
_GENERIC = {
    "disease", "disorder", "syndrome", "condition", "infection", "neoplasm",
    "tumor", "tumour", "mass", "lesion", "disease, unspecified", "complication",
    "injury", "pain", "fever", "inflammation", "abnormality", "finding",
}
# §31.13.13 improvement ①: non-discriminative whole names that pollute the
# SNOMED is_a partition (too broad to be a useful mandatory family). Dropped
# from the recalled candidate set (matched on the full spotted phrase).
_GENERIC_NAMES = {
    "disorders", "diseases", "disease", "cancer", "carcinoma", "malignancy",
    "trauma", "ischemia", "hematoma", "fracture", "sepsis", "abscess",
    "hypoxia", "infection", "neoplasm", "tumor", "tumour", "inflammation",
    "secondary infection", "viral illness", "bacterial infection",
    "hematologic malignancy", "solid tumor", "metastasis", "metastatic disease",
}
# §31.13.13 improvement ②: jargon/qualifier tokens stripped from the syndrome
# label to produce a more colloquial retrieval query.
_QUERY_STOP = {
    "deficit", "frame", "framing", "with", "and", "the", "of", "acute",
    "chronic", "unilateral", "bilateral", "focal", "diffuse", "undifferentiated",
    "syndrome", "disorder", "neuro",
}


# Generic HEAD nouns that must never be added as a standalone alias when a
# compound SNOMED name is decomposed (they'd spot on nearly every DDx snippet).
_GENERIC_HEADS = {
    "disorder", "disease", "syndrome", "condition", "infection", "neoplasm",
    "tumor", "tumour", "mass", "lesion", "carcinoma", "cancer", "malignancy",
    "inflammation", "injury", "cyst", "abscess", "ulcer", "fracture", "deficiency",
    "insufficiency", "failure", "hemorrhage", "haemorrhage", "obstruction",
    "stenosis", "hypertrophy", "atrophy", "necrosis", "fibrosis", "edema",
    "oedema", "effusion", "abnormality", "finding", "complication", "defect",
    "dysfunction", "swelling", "pain", "fever", "rupture", "perforation",
}


def _head_alias(name: str) -> str | None:
    """The distinctive HEAD of a compound SNOMED disorder name, so the corpus's
    bare head noun is spottable. "Angiodysplasia of intestine" → "angiodysplasia";
    "Vascular ectasia of colon" → "vascular ectasia". Returns None when the head
    is generic/too short (would over-spot). Sites/qualifiers after the first
    of/due-to/caused-by/in separator are dropped."""
    head = re.split(r"\b(?:of|due to|caused by|in|with|from|secondary to)\b",
                    name, maxsplit=1)[0].strip(" ,")
    if not head or head == name:
        return None
    toks = head.split()
    if not toks or toks[0] in _GENERIC_HEADS or head in _GENERIC_HEADS:
        return None
    # single-token head must be long/distinctive (angiodysplasia, glucagonoma);
    # multi-token head (vascular ectasia) needs a modest length only.
    if len(toks) == 1:
        return head if len(head) >= 9 else None
    return head if len(head) >= 8 else None


def build_disorder_vocab(snomed_concepts: dict, *, min_len: int = 5,
                         max_len: int = 60, head_aliases: bool = False) -> set[str]:
    """SNOMED ``disorder`` preferred names + synonyms (lowercased), length-gated,
    minus over-generic single words. Used as the verbatim-spotting dictionary.

    ``head_aliases`` (default OFF): also add the distinctive HEAD of compound
    names ("Angiodysplasia of intestine" → "angiodysplasia") so the corpus's
    bare head noun is spottable. NOTE: empirically this is net-neutral-to-
    NEGATIVE on the balanced 8/14 + RareArena sets — the ~8.8k added aliases
    introduce spotting noise that displaces some golds (cr common 8→6), while the
    angiodysplasia it rescues is still diluted below @20 by the weak salient in
    fusion (§RESIDUAL_MISS §D-entity). Kept opt-in for experiments; NOT enabled
    by default (legacy vocab preserved)."""
    vocab: set[str] = set()
    aliases: set[str] = set()
    for c in snomed_concepts.values():
        if c.get("tag") != "disorder":
            continue
        for nm in [c.get("preferred", "")] + (c.get("synonyms") or []):
            nm = (nm or "").strip().lower()
            if min_len <= len(nm) <= max_len and nm not in _GENERIC:
                vocab.add(nm)
                if head_aliases:
                    h = _head_alias(nm)
                    if h and min_len <= len(h) <= max_len:
                        aliases.add(h)
    # add aliases that are not already generic-blocked
    for h in aliases:
        if h not in _GENERIC and h not in _GENERIC_NAMES:
            vocab.add(h)
    return vocab


class GuidelineBranchSource:
    def __init__(self, retriever, disorder_vocab: set[str], *,
                 top_k: int = 30, max_candidates: int = 40, resolver=None,
                 retrieve_k: Optional[int] = None, extract_k: Optional[int] = None,
                 mmr_lambda: Optional[float] = None, closure_mode: str = "pool",
                 extractor: str = "spotter", llm_client=None,
                 taxonomy=None, rollup_mode: str = "off",
                 inject_poles: bool = False, cant_miss: Optional[dict] = None,
                 query_mode: str = "legacy", nominate: bool = False,
                 pathognomonic: Optional[list] = None,
                 cant_miss_hard: bool = False,
                 degeneric_rerank: bool = False) -> None:
        self._r = retriever
        self._vocab = disorder_vocab
        self._top_k = top_k
        self._max_candidates = max_candidates
        # De-generic entity re-rank (opt-in): the spot-and-sum-frequency scoring
        # rewards common co-occurring diseases (hypotension, CKD) that appear in
        # many DDx snippets, burying the specific rare gold below the cut
        # (angiodysplasia rank 49; leukemoid rank 21 — §RESIDUAL_MISS §2). When
        # on, each entity's aggregate score is scaled by a SPECIFICITY factor
        # derived from the retriever's TF-IDF idf (rarer term = higher idf =
        # up-weight), applied BEFORE the max_candidates cut. Default OFF
        # (byte-identical legacy ranking).
        self._degeneric = degeneric_rerank
        self._idf_cache = "unset"
        # §31.13.13 improvement ③: optional DiseaseNameResolver — expands recalled
        # broad families ("myeloproliferative disorder") into specific member
        # entities (CML/PV/ET/PMF) and canonicalises mechanism phrasings, so the
        # gold entity itself enters the candidate set for projection.
        self._resolver = resolver
        # token → does any vocab phrase start with it (cheap prefilter for n-grams)
        self._first_tokens = {v.split(" ", 1)[0] for v in disorder_vocab}
        # ----- IMP-63: decoupled retrieval / extraction (CPG §17.7 P0) ----------
        # retrieve_k governs the chunk-retrieval breadth; extract_k caps how many
        # snippets are fed to the spotter AFTER MMR/source-dedup (§17.5.4: a single
        # k must not serve both). Defaults preserve the legacy single-k behaviour.
        self._retrieve_k = retrieve_k
        self._extract_k = extract_k
        self._mmr_lambda = mmr_lambda
        # closure_mode: "pool"=legacy (closure feeds the spotter pool),
        # "grounding"=closure only feeds the LLM grounding snippets (not spotter),
        # "off"=no closure in the spotter pool. §19.5.2: closure crowds the 40-slot
        # candidate pool, so "grounding" tests whether the "closure harmful" verdict
        # is a C4 artefact.
        self._closure_mode = closure_mode
        # extractor: "spotter"=legacy n-gram, "llm"=recall_llm only,
        # "spotter+llm"=union of both (C7: deterministic spotter under-extracts).
        self._extractor = extractor
        self._llm_client = llm_client
        # ----- IMP-64: ontology reverse-rollup (CPG §21.5) ---------------------
        # taxonomy = a KBAxisMap exposing _taxonomy_groups(); rollup_mode controls
        # whether spotted flat entities compete at family level before the cut.
        self._taxonomy = taxonomy
        self._rollup_mode = rollup_mode
        # ----- IMP-60: mandatory axis-pole injection (CPG §19.5) ---------------
        self._inject_poles = inject_poles
        self._cant_miss = cant_miss or {}
        # ----- 表C 待办落地项 (§17.9) ------------------------------------------
        # IMP-52 (B1): multi-facet query fan-out. "legacy"=2-4 DDx/etiology
        # queries; "fanout"=+mechanism/anatomy/urgency/workup/symptom-entry facets
        # so a single lexical framing cannot bottleneck retrieval (§17 B1).
        self._query_mode = query_mode
        # IMP-58 (C1/c1/L4) + pathognomonic 接入 recall (L13/D3/c1/c13): scan the
        # clinical context for mechanism/morphology phrasings, broad-family
        # keywords and pathognomonic markers, and DIRECTLY NOMINATE the implied
        # disease entities into the candidate pool. Closes the mechanism/eponym
        # gap that no amount of retrieval recovers (the entity is absent from the
        # DDx snippets because the option is phrased as a mechanism).
        self._nominate = nominate
        self._pathognomonic = pathognomonic or []
        # IMP-56 (L11) can't-miss HARD layer: guarantee injected can't-miss /
        # nominated entities SURVIVE the max_candidates cut (vs the soft floor of
        # IMP-60, which a crowded pool can still evict).
        self._cant_miss_hard = cant_miss_hard
        # Longest n-gram the spotter tries. Default 5 (legacy, bit-identical).
        # Case-report diagnoses can be longer ("chronic myeloid leukemia in
        # blast crisis" = 6 tokens), so CaseReportBranchSource raises this.
        self._max_ngram = 5

    def _new_path_active(self) -> bool:
        """True when any IMP-63/64/60 or 表C mode departs from legacy behaviour."""
        return (self._extract_k is not None or self._mmr_lambda is not None
                or self._closure_mode != "pool" or self._extractor != "spotter"
                or self._rollup_mode != "off" or self._inject_poles
                or self._query_mode != "legacy" or self._nominate
                or self._cant_miss_hard)

    @staticmethod
    def _colloquial(syndrome: str) -> str:
        """Strip jargon/qualifier tokens → a plainer query phrase (improvement ②)."""
        toks = [t for t in re.findall(r"[a-z0-9]+", (syndrome or "").lower())
                if t not in _QUERY_STOP]
        return " ".join(toks) or syndrome

    # --------------------------------------------------------------- spotting
    def _spot(self, text: str) -> set[str]:
        """Longest-match n-gram lookup of disorder names in ``text``."""
        toks = re.findall(r"[a-z0-9]+", (text or "").lower())
        hits: set[str] = set()
        covered = [False] * len(toks)
        # longest first so "chronic myeloid leukemia" wins over "leukemia"
        for n in range(self._max_ngram, 0, -1):
            for i in range(len(toks) - n + 1):
                if covered[i] or toks[i] not in self._first_tokens:
                    continue
                gram = " ".join(toks[i:i + n])
                if gram in self._vocab:
                    hits.add(gram)
                    for j in range(i, i + n):
                        covered[j] = True
        return hits

    def _spot_weighted(self, title: str, content: str) -> dict[str, float]:
        """Spot disorder names in a hit, returning a per-entity weight multiplier.

        Base implementation is flat (title and content pooled, all weight 1.0) —
        bit-identical to the legacy ``self._spot(title + ". " + content)`` behaviour
        used by the CPG path. ``CaseReportBranchSource`` overrides this to up-weight
        the case's CONFIRMED diagnosis (which sits in the title) over the diseases
        that merely appear in its differential list, so common co-occurring DDx
        entities no longer out-score the rare gold the case is actually about."""
        return {dz: 1.0 for dz in self._spot((title or "") + ". " + (content or ""))}

    # -------------------------------------------------- de-generic specificity
    def _idf_lookup(self):
        """(vocabulary, idf_array, median_idf) from the retriever's fitted TF-IDF
        vectorizer, or None (dense/FAISS index or no vectorizer). Cached."""
        if self._idf_cache != "unset":
            return self._idf_cache
        self._idf_cache = None
        vec = getattr(self._r, "_tfidf_vectorizer", None)
        try:
            import numpy as np
            if vec is not None and hasattr(vec, "idf_") and hasattr(vec, "vocabulary_"):
                self._idf_cache = (vec.vocabulary_, vec.idf_,
                                   float(np.median(vec.idf_)))
        except Exception:  # pragma: no cover - defensive
            self._idf_cache = None
        return self._idf_cache

    def _specificity(self, dz: str) -> float:
        """Specificity multiplier in [0.6, 1.8]: mean TF-IDF idf of the entity's
        unigram tokens / corpus median idf. Rare/discriminating names (idf high)
        are up-weighted; generic co-occurring names (idf low) down-weighted."""
        look = self._idf_lookup()
        if not look:
            return 1.0
        vocab, idf, med = look
        vals = [idf[vocab[t]] for t in re.findall(r"[a-z0-9]+", dz.lower())
                if t in vocab]
        if not vals or med <= 0:
            return 1.0
        ratio = (sum(vals) / len(vals)) / med
        return max(0.6, min(1.8, ratio))

    def _apply_specificity(self, scored: dict[str, float]) -> dict[str, float]:
        if not self._degeneric or not scored:
            return scored
        return {d: s * self._specificity(d) for d, s in scored.items()}

    # ----------------------------------------------------------------- recall
    def recall(self, syndrome: str, *, top_k: Optional[int] = None,
               context: str = "",
               salient_findings: Optional[list[str]] = None,
               finding_entrance_weight: float = 1.0,
               rrf_k: int = 60,
               salient_gate: bool = False) -> dict[str, float]:
        """Recall candidate disorder families for ``syndrome`` from guideline /
        textbook differential sections. Returns {disease: score} ranked.

        ``context`` (optional, §31.13.12 GARMLE-G ① *backup*): a generation-
        augmented enrichment string — the upstream clinical features / chief
        findings. When given, an extra query fuses the syndrome with these
        verbatim clinical terms, so awkward syndrome labels ("focal limb neuro
        deficit") are supplemented by the actual presentation ("apical lung mass,
        arm pain, hand atrophy"). Deterministic; no LLM.

        ``salient_findings`` (optional, DUAL-ENTRANCE): the concrete
        discriminating findings from the RootSelector second entrance. When
        given, an INDEPENDENT retrieval is run keyed on each finding (a plain,
        corpus-searchable term rather than the abstract syndrome frame), and its
        disease ranking is RECIPROCAL-RANK-FUSED with the syndrome-entrance
        ranking. This closes the lexical gap where the abstract frame cannot
        reach the answer disease's snippets but a concrete sign can (c1/Pancoast:
        "apical lung mass" retrieves the DDx that "focal limb deficit" misses).

        Dispatch: legacy single-k spotter (default, bit-identical to pre-IMP-63),
        or the IMP-63/64/60 decoupled path when any new mode is active. The
        syndrome entrance is byte-identical to before when no salient_findings
        are supplied (the fusion is strictly additive)."""
        if self._r is None or not getattr(self._r, "is_ready", False):
            return {}
        base = (self._recall_v2(syndrome, top_k=top_k, context=context)
                if self._new_path_active()
                else self._recall_legacy(syndrome, top_k=top_k, context=context))
        sal = [s for s in (salient_findings or []) if s and str(s).strip()]
        # D-fusion salient quality gate (opt-in): a low-precision finding made
        # only of common/qualifier tokens ("in older adult", "without blasts")
        # runs a broad second entrance whose top entities crowd out the
        # syndrome-strong gold under equal-weight RRF (angiodysplasia 19→37,
        # §RESIDUAL_MISS §D-entity). Keep only findings carrying ≥1 discriminating
        # (high-idf) token; if none survive, fall back to the syndrome entrance.
        if salient_gate and sal:
            sal = [s for s in sal if self._finding_is_discriminative(s)] or []
            if not sal:
                return base
        if not sal:
            return base
        finding_scored = self._recall_from_findings(sal, top_k=top_k)
        if not finding_scored:
            return base
        # Weight the concrete-finding entrance vs the abstract syndrome-frame
        # entrance. Concrete signs ("apical lung mass") are higher-precision for
        # reaching the specific gold than the deliberately broad frame, so the
        # finding entrance is up-weighted by default.
        fused = self._rrf_merge([base, finding_scored], k=rrf_k,
                                weights=[1.0, finding_entrance_weight])
        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
        return dict(ranked[: self._max_candidates])

    def _finding_is_discriminative(self, finding: str) -> bool:
        """A salient finding is kept for the second entrance only if it carries at
        least one discriminating (high-idf) content token. Findings made entirely
        of common/qualifier words are non-specific and dilute the fusion. When no
        idf table is available (dense index), keep everything (fail-open)."""
        look = self._idf_lookup()
        toks = [t for t in re.findall(r"[a-z0-9]+", finding.lower()) if len(t) > 3]
        if not toks:
            return False
        if not look:
            return True
        vocab, idf, med = look
        return any(t in vocab and idf[vocab[t]] >= 1.15 * med for t in toks)

    def recall_for_branches(
        self,
        syndrome: str,
        axis_map,
        entry: dict,
        *,
        split: bool = False,
        salient_findings: Optional[list[str]] = None,
        context: str = "",
        top_k: Optional[int] = None,
        per_domain_cap: int = 6,
        finding_entrance_weight: float = 1.0,
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        """Dual-entrance recall (syndrome ∪ salient findings, RRF-fused) projected
        onto the matched axis ``entry``'s MECE domains.

        Returns ``(scored, entities_by_domain)`` where ``scored`` is the raw
        {disease: fused_score} ranking and ``entities_by_domain`` maps each axis
        domain to the recalled diseases that project into it (score-descending,
        capped per domain). Diseases that do not project onto any domain are
        dropped (they cannot be attached to a mandatory branch). ``recall`` is
        polymorphic, so subclasses (CaseReportBranchSource) reuse this
        projection unchanged over their own corpus-tuned recall."""
        scored = self.recall(
            syndrome, top_k=top_k, context=context,
            salient_findings=salient_findings,
            finding_entrance_weight=finding_entrance_weight,
        )
        by_domain: dict[str, list[str]] = {}
        for dz in sorted(scored, key=lambda d: scored[d], reverse=True):
            try:
                dom = axis_map.project_entity(dz, entry, split=split)
            except Exception:  # pragma: no cover - defensive
                dom = None
            if not dom:
                continue
            lst = by_domain.setdefault(dom, [])
            if len(lst) >= per_domain_cap:
                continue
            if dz.lower() not in [e.lower() for e in lst]:
                lst.append(dz)
        return scored, by_domain

    # ------------------------------------------------ dual-entrance (findings)
    @staticmethod
    def _rrf_merge(rankings: list[dict[str, float]], *, k: int = 60,
                   weights: Optional[list[float]] = None) -> dict[str, float]:
        """Weighted reciprocal-rank fusion of several {item: score} rankings.
        Each ranking contributes ``weight * 1/(k + rank)`` per item (rank is
        0-based within that ranking, score-descending). Robust to disparate
        score scales across entrances — the syndrome spotter weight and the
        finding spotter weight need not be comparable, only their within-entrance
        ORDER matters (the property that makes the two entrances safely
        fusable). ``weights`` (default all-1) lets a higher-precision entrance
        dominate ties."""
        fused: dict[str, float] = defaultdict(float)
        ws = weights or [1.0] * len(rankings)
        for ranking, w in zip(rankings, ws):
            ordered = sorted(ranking.items(), key=lambda kv: kv[1], reverse=True)
            for rank, (item, _score) in enumerate(ordered):
                fused[item] += w * (1.0 / (k + rank))
        return dict(fused)

    def _recall_from_findings(self, findings: list[str], *,
                              top_k: Optional[int] = None) -> dict[str, float]:
        """SECOND ENTRANCE: retrieve DDx snippets keyed on each concrete salient
        finding (not the abstract syndrome frame), spot disorder entities, and
        aggregate. Same spotting/resolver machinery as the syndrome entrance, so
        the two rankings are homogeneous inputs to ``_rrf_merge``. Each finding
        is gated on ITS OWN tokens (not the syndrome's) so an off-topic snippet
        for that finding is dropped."""
        k = top_k or self._retrieve_k or self._top_k
        scored: dict[str, float] = defaultdict(float)
        for finding in findings:
            f = str(finding).strip()
            if not f:
                continue
            f_toks = {t for t in re.findall(r"[a-z0-9]+", f.lower()) if len(t) > 3}
            queries = [
                f"differential diagnosis of {f}",
                f"conditions that cause {f}",
                f,
            ]
            seen: set[str] = set()
            for q in queries:
                try:
                    hits = self._r.search(q, top_k=k, score_threshold=0.0)
                    # Drop zero-similarity hits BEFORE closure: a doc sharing no
                    # query term is never on-topic for the finding, and a small
                    # index would otherwise return the whole corpus at score 0
                    # (spurious spotting). Closure then runs only over genuinely
                    # matched articles.
                    hits = [h for h in hits
                            if float(h.get("score", 0.0) or 0.0) > 0.0]
                    if hasattr(self._r, "expand_ddx_siblings"):
                        hits = self._r.expand_ddx_siblings(hits)
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("finding-entrance query failed (%s): %s", q, e)
                    continue
                for h in hits:
                    title = str(h.get("title", "") or "")
                    content = str(h.get("content", "") or "")
                    # gate on the finding's own tokens (empty → accept useful types)
                    if f_toks and not snippet_on_topic(
                        title=title, content=content, syndrome_tokens=f_toks,
                        chunk_type=h.get("chunk_type"), entry_type=h.get("entry_type"),
                        syndrome_anchor=h.get("syndrome_anchor"),
                        section_path=h.get("section_path") or title,
                    ):
                        continue
                    sig = title[:60] + "|" + content[:40]
                    if sig in seen:
                        continue
                    seen.add(sig)
                    # Weight by ACTUAL similarity (higher = more relevant, for
                    # both TF-IDF cosine and normalised-IP FAISS). A closure
                    # sibling carries score 0.0 → a small floor so an explicitly
                    # linked DDx entity still counts, but far below a directly
                    # matched snippet. (The syndrome entrance keeps its legacy
                    # frequency weighting; RRF only compares WITHIN an entrance.)
                    score = max(0.0, float(h.get("score", 0.0) or 0.0))
                    w = score if score > 0.0 else 0.05
                    # Per-case dedup: a case's diagnosis appears in its entry
                    # chunk AND its wiki_links closure sibling — count it once
                    # per case per finding so a case contributes its gold a
                    # single time (was: summed across siblings, inflating any
                    # disease that co-occurs across many retrieved cases).
                    case_key = str(h.get("source_id") or h.get("article_id") or sig)
                    for dz, mult in self._spot_weighted(title, content).items():
                        if dz in _GENERIC_NAMES:
                            continue
                        dedup = (case_key, dz)
                        if dedup in seen:
                            continue
                        seen.add(dedup)
                        scored[dz] += w * mult
        # resolver expansion (identical shape to the syndrome entrance)
        if self._resolver is not None:
            for dz in list(scored):
                base = scored[dz]
                try:
                    canon = self._resolver.canonicalize_entity(dz)
                    if canon and canon != dz and canon not in _GENERIC_NAMES:
                        scored[canon] = max(scored.get(canon, 0.0), base)
                    for ent in self._resolver.expand_to_entities(dz) or []:
                        if ent not in _GENERIC_NAMES:
                            scored[ent] = max(scored.get(ent, 0.0), 0.9 * base)
                except Exception:  # pragma: no cover - defensive
                    pass
        return self._apply_specificity(dict(scored))

    def _recall_legacy(self, syndrome: str, *, top_k: Optional[int] = None,
                       context: str = "") -> dict[str, float]:
        k = top_k or self._top_k
        syn = (syndrome or "").strip().lower()
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", syn) if len(t) > 3}
        # ② colloquial phrasing as an extra query (handles jargon labels like
        # "focal limb neuro deficit" → "limb").
        colloq = self._colloquial(syndrome)
        queries = [f"differential diagnosis of {syndrome}",
                   f"causes and etiology of {syndrome}"]
        if colloq and colloq != syn:
            queries.append(f"differential diagnosis of {colloq}")
            queries.append(f"approach to {colloq}")
        # GARMLE-G ① generation-augmented query (backup, additive)
        ctx = (context or "").strip()
        if ctx:
            queries.append(f"differential diagnosis of {colloq or syndrome}. "
                           f"clinical features: {ctx[:300]}")
        scored: dict[str, float] = defaultdict(float)
        seen_snippets: set[str] = set()
        for q in queries:
            try:
                hits = self._r.search(q, top_k=k, score_threshold=0.0)
                if hasattr(self._r, "expand_ddx_siblings"):
                    hits = self._r.expand_ddx_siblings(hits)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("guideline recall query failed (%s): %s", q, e)
                continue
            for h in hits:
                title = str(h.get("title", "") or "")
                content = str(h.get("content", "") or "")
                if not snippet_on_topic(
                    title=title,
                    content=content,
                    syndrome_tokens=syn_toks,
                    chunk_type=h.get("chunk_type"),
                    entry_type=h.get("entry_type"),
                    syndrome_anchor=h.get("syndrome_anchor"),
                    section_path=h.get("section_path") or title,
                ):
                    continue
                sig = title[:60] + "|" + content[:40]
                if sig in seen_snippets:
                    continue
                seen_snippets.add(sig)
                score = float(h.get("score", 0.0) or 0.0)
                # higher cosine score in this index = LESS similar (L2)? guard: use
                # a bounded positive weight so frequency dominates ties.
                w = 1.0 / (1.0 + max(0.0, score))
                for dz in self._spot(title + ". " + content):
                    dz_toks = set(re.findall(r"[a-z0-9]+", dz))
                    # drop the syndrome term itself recalled as a "disease"
                    if dz_toks <= syn_toks or dz == syn:
                        continue
                    # ① drop non-discriminative generic names that pollute the
                    # SNOMED is_a partition.
                    if dz in _GENERIC_NAMES:
                        continue
                    scored[dz] += w
        # ③ resolver expansion: inject specific member entities for any recalled
        # broad family + canonicalise mechanism phrasings, so the gold entity
        # itself can become a candidate (e.g. "myeloproliferative disorder" → CML).
        if self._resolver is not None:
            for dz in list(scored):
                base = scored[dz]
                try:
                    canon = self._resolver.canonicalize_entity(dz)
                    if canon and canon != dz and canon not in _GENERIC_NAMES:
                        scored[canon] = max(scored.get(canon, 0.0), base)
                    for ent in self._resolver.expand_to_entities(dz) or []:
                        if ent not in _GENERIC_NAMES:
                            # slightly discount expanded members vs directly cited
                            scored[ent] = max(scored.get(ent, 0.0), 0.9 * base)
                except Exception:  # pragma: no cover - defensive
                    pass
        scored = self._apply_specificity(scored)
        ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
        return dict(ranked[: self._max_candidates])

    # ------------------------------------------------------- IMP-63 recall v2
    def _build_queries(self, syndrome: str, syn: str, context: str) -> list[str]:
        """The retrieval queries shared by the spotter pool and LLM grounding."""
        colloq = self._colloquial(syndrome)
        queries = [f"differential diagnosis of {syndrome}",
                   f"causes and etiology of {syndrome}"]
        if colloq and colloq != syn:
            queries.append(f"differential diagnosis of {colloq}")
            queries.append(f"approach to {colloq}")
        ctx = (context or "").strip()
        if ctx:
            queries.append(f"differential diagnosis of {colloq or syndrome}. "
                           f"clinical features: {ctx[:300]}")
        # IMP-52 (B1): multi-facet query fan-out — a single "differential of X"
        # framing biases retrieval toward one cluster (§17 B1). Add orthogonal
        # facets so mechanism-/anatomy-/urgency-keyed chunks are also surfaced.
        if self._query_mode == "fanout":
            base = colloq or syndrome
            queries.extend([
                f"pathophysiology and mechanism of {base}",          # Qmech
                f"anatomic and organ-system causes of {base}",       # Qanat
                f"life-threatening can't-miss causes of {base}",     # Qurg
                f"diagnostic workup and evaluation of {base}",       # Qwork
                f"{base} clinical presentation and findings",        # Qsymptom
            ])
        return queries

    def _gather_spot_hits(self, queries: list[str], syn_toks: set[str]) -> list[dict]:
        """Retrieve at ``retrieve_k``, on-topic filter, de-duplicate. Closure is
        applied to the spotter pool ONLY in ``closure_mode='pool'`` (legacy);
        in 'grounding'/'off' closure is withheld so it cannot crowd the 40-slot
        candidate pool (§19.5.2)."""
        rk = self._retrieve_k or self._top_k
        out: list[dict] = []
        seen: set[str] = set()
        for q in queries:
            try:
                hits = self._r.search(q, top_k=rk, score_threshold=0.0)
                if self._closure_mode == "pool" and hasattr(self._r, "expand_ddx_siblings"):
                    hits = self._r.expand_ddx_siblings(hits)
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("guideline recall query failed (%s): %s", q, e)
                continue
            for h in hits:
                title = str(h.get("title", "") or "")
                content = str(h.get("content", "") or "")
                if not snippet_on_topic(
                    title=title, content=content, syndrome_tokens=syn_toks,
                    chunk_type=h.get("chunk_type"), entry_type=h.get("entry_type"),
                    syndrome_anchor=h.get("syndrome_anchor"),
                    section_path=h.get("section_path") or title,
                ):
                    continue
                sig = title[:60] + "|" + content[:40]
                if sig in seen:
                    continue
                seen.add(sig)
                out.append(h)
        return out

    def _mmr_select(self, hits: list[dict], k: Optional[int],
                    lam: Optional[float]) -> list[dict]:
        """Greedy MMR over the retrieved snippets (relevance vs diversity), with a
        same-source penalty so PMC's ~90% top-k share (§17.5.6 L5/L9) cannot
        monopolise the snippets the spotter sees. ``lam`` weights relevance vs
        diversity; ``k`` caps the kept snippets (``extract_k``)."""
        n = len(hits)
        if not hits:
            return hits
        if lam is None:
            return hits[:k] if k else hits
        if k is None or k >= n:
            k = n
        items = []
        for h in hits:
            score = float(h.get("score", 0.0) or 0.0)
            rel = 1.0 / (1.0 + max(0.0, score))
            toks = set(re.findall(r"[a-z0-9]+", (str(h.get("content", "") or "")[:400]).lower()))
            src = str(h.get("source_id") or h.get("article_id") or "")
            items.append((h, rel, toks, src))
        chosen: list[int] = []
        remaining = set(range(n))
        while remaining and len(chosen) < k:
            best_i, best_val = None, -1e18
            for i in remaining:
                _, rel, toks, src = items[i]
                div = 0.0
                for cj in chosen:
                    _, _, ctoks, csrc = items[cj]
                    if toks or ctoks:
                        j = len(toks & ctoks) / max(1, len(toks | ctoks))
                    else:
                        j = 0.0
                    if src and src == csrc:
                        j = max(j, 0.6)
                    if j > div:
                        div = j
                val = lam * rel - (1.0 - lam) * div
                if val > best_val:
                    best_val, best_i = val, i
            chosen.append(best_i)
            remaining.discard(best_i)
        return [items[i][0] for i in chosen]

    def _recall_v2(self, syndrome: str, *, top_k: Optional[int] = None,
                   context: str = "") -> dict[str, float]:
        """IMP-63/64/60 path: decoupled retrieve/extract k + MMR/source-dedup,
        closure routed away from the spotter pool, optional LLM extractor union,
        optional ontology rollup + axis-pole injection."""
        syn = (syndrome or "").strip().lower()
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", syn) if len(t) > 3}
        queries = self._build_queries(syndrome, syn, context)
        hits = self._gather_spot_hits(queries, syn_toks)
        # IMP-63: trim to extract_k via MMR/source-dedup BEFORE spotting
        if self._mmr_lambda is not None or self._extract_k is not None:
            hits = self._mmr_select(hits, self._extract_k, self._mmr_lambda)
        scored: dict[str, float] = defaultdict(float)
        for h in hits:
            title = str(h.get("title", "") or "")
            content = str(h.get("content", "") or "")
            score = float(h.get("score", 0.0) or 0.0)
            w = 1.0 / (1.0 + max(0.0, score))
            for dz in self._spot(title + ". " + content):
                dz_toks = set(re.findall(r"[a-z0-9]+", dz))
                if dz_toks <= syn_toks or dz == syn:
                    continue
                if dz in _GENERIC_NAMES:
                    continue
                scored[dz] += w
        # resolver expansion (identical to legacy)
        if self._resolver is not None:
            for dz in list(scored):
                base = scored[dz]
                try:
                    canon = self._resolver.canonicalize_entity(dz)
                    if canon and canon != dz and canon not in _GENERIC_NAMES:
                        scored[canon] = max(scored.get(canon, 0.0), base)
                    for ent in self._resolver.expand_to_entities(dz) or []:
                        if ent not in _GENERIC_NAMES:
                            scored[ent] = max(scored.get(ent, 0.0), 0.9 * base)
                except Exception:  # pragma: no cover - defensive
                    pass
        # C7: merge / replace with LLM grounded extraction
        if self._extractor in ("llm", "spotter+llm") and self._llm_client is not None:
            try:
                llm_out = self.recall_llm(syndrome, self._llm_client, context=context)
            except Exception as e:  # pragma: no cover - network/LLM defensive
                logger.warning("recall_llm merge failed: %s", e)
                llm_out = {}
            if self._extractor == "llm":
                scored = defaultdict(float)
            for d, s in llm_out.items():
                scored[d] = max(scored.get(d, 0.0), float(s))
        # IMP-58 + pathognomonic 接入: context-driven direct nomination. Runs
        # BEFORE rollup/cut so a nominated rare gold competes (and, if hard, is
        # guaranteed to survive). ``forced`` collects the must-keep keys.
        forced: list[str] = []
        if self._nominate:
            scored = self._nominate_from_context(syndrome, syn, context, scored, forced)
        # IMP-64 ontology reverse-rollup (family-level competition)
        if self._rollup_mode != "off" and self._taxonomy is not None and scored:
            scored = self._rollup_candidates(scored)
        # IMP-60 mandatory axis-pole injection
        if self._inject_poles:
            scored = self._inject_axis_poles(syndrome, syn, scored, forced)
        scored = self._apply_specificity(scored)
        ranked = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)
        out = dict(ranked[: self._max_candidates])
        # IMP-56 can't-miss HARD layer: re-insert any forced key the cut dropped,
        # so a mandatory family can never be silently evicted by pool crowding.
        if self._cant_miss_hard and forced:
            for k in forced:
                if k not in out and k in scored:
                    out[k] = scored[k]
        return out

    # ------------------------------------------- IMP-64 ontology reverse-rollup
    def _rollup_candidates(self, scored: dict[str, float]) -> dict[str, float]:
        """§21.5: reverse-cluster the spotted disease entities into is_a
        SUPER-FAMILIES (via ``KBAxisMap._taxonomy_groups``) so the
        ``max_candidates`` cut competes at FAMILY level, not flat-entity level
        (§21.3: a single-mention rare gold otherwise loses to repeated common
        diseases). Spotted entities are preserved (so exact-entity matching still
        works); grouped members are LIFTED to their family's representative score
        so a clinically meaningful family is kept/cut as a unit. Orphans whose
        is_a rollup fails (adhesions / peliosis / foreign body — the §15.4 wall)
        are kept as-is, and in ``family+orphan`` mode floored so a lone rare gold
        survives the cut. The L1 family name is also surfaced as a candidate."""
        K = self._max_candidates
        ranked = sorted(scored, key=lambda m: -scored[m])
        if len(ranked) <= K:
            return scored  # cut never bites → rollup can only add noise
        cand = list(scored.keys())
        try:
            groups = self._taxonomy._taxonomy_groups(cand)  # {family_name: [members]}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("ontology rollup failed: %s", e)
            return scored
        member_to_family: dict[str, str] = {}
        for fam, members in (groups or {}).items():
            for m in members:
                member_to_family.setdefault(m, fam)

        def famkey(m: str) -> str:
            f = member_to_family.get(m)
            if f is not None:
                return f
            # family+orphan: each is_a-wall orphan (adhesions / peliosis — §15.4)
            # is its own family so a lone rare gold gets a reserved seat.
            return f"__orphan__{m}" if self._rollup_mode == "family+orphan" else "__orphans__"

        # COVERAGE-AUGMENTATION (strictly non-regressing): keep the strongest flat
        # hits, but reserve a few of the lowest slots for the BEST member of any
        # family that the flat top-K would otherwise drop entirely. Competition thus
        # happens at family level (§21.3) WITHOUT collapsing the within-axis
        # distinction (primary vs secondary are is_a siblings but separate L1 poles).
        flat_top = ranked[:K]
        fams_in_top = {famkey(m) for m in flat_top}
        missing_reps: list[str] = []
        for m in ranked:  # score-desc → first seen per family is its best member
            fk = famkey(m)
            if fk in fams_in_top:
                continue
            fams_in_top.add(fk)
            missing_reps.append(m)
        if not missing_reps:
            return scored
        n_reserve = min(len(missing_reps), max(1, K // 8))  # cap churn to ~12% of slots
        keep = flat_top[: K - n_reserve] + missing_reps[:n_reserve]
        base = max(scored.values()) + 1.0
        out: dict[str, float] = dict(scored)
        for i, m in enumerate(sorted(keep, key=lambda x: -scored[x])):
            out[m] = 2.0 * base - i * 1e-3  # force `keep` into the top-K, own order
        return out

    # --------------------------------------- IMP-60 mandatory axis-pole inject
    def _lookup_cant_miss(self, syn: str) -> list[str]:
        """Best-matching can't-miss entity list for ``syn`` (exact key, else max
        token-overlap key) from the injected ``cant_miss`` map."""
        if not self._cant_miss:
            return []
        if syn in self._cant_miss:
            return self._cant_miss[syn]
        st = {t for t in re.findall(r"[a-z0-9]+", syn) if len(t) > 3}
        best, best_ov = [], 0
        for k, v in self._cant_miss.items():
            kt = {t for t in re.findall(r"[a-z0-9]+", k) if len(t) > 3}
            ov = len(st & kt)
            if ov > best_ov:
                best_ov, best = ov, v
        return best

    def _nominate_from_context(self, syndrome: str, syn: str, context: str,
                               scored: dict[str, float],
                               forced: list[str]) -> dict[str, float]:
        """IMP-58 + pathognomonic 接入 recall: scan the clinical context (+ the
        syndrome label) for (a) pathognomonic-marker trigger terms → their
        ``target_diseases`` and (b) mechanism/morphology phrasings + broad-family
        keywords (via the resolver) → the canonical disease entity. These
        entities are phrased as a MECHANISM in the option and are therefore
        ABSENT from the retrieved DDx snippets (the §17 c1/c13 gap that no
        retrieval recovers). Directly nominated at a competitive floor (just
        above the IMP-60 pole floor) so the gold branch enters the candidate
        pool; recorded in ``forced`` for the optional hard-cut guarantee."""
        text = f"{syndrome} {syn} {context or ''}".lower()
        floor = 0.6 * (max(scored.values()) if scored else 1.0) or 1.0
        nominated: list[str] = []
        # (a) pathognomonic markers (WHO/textbook-sourced; LR+ defining)
        for mk in self._pathognomonic:
            terms = mk.get("terms", []) or []
            if any(t and t in text for t in terms):
                nominated.extend(mk.get("target_diseases", []) or [])
        # (b) mechanism / morphology / family phrasings
        if self._resolver is not None:
            try:
                nominated.extend(self._resolver.nominate_from_text(text))
            except Exception:  # pragma: no cover - defensive
                pass
        for name in nominated:
            nm = (name or "").strip().lower()
            if not nm or nm in _GENERIC_NAMES:
                continue
            # nominate slightly above the pole floor so a real mechanism cue
            # outranks generic injected poles, but below strong spotted hits.
            scored[nm] = max(scored.get(nm, 0.0), 1.05 * floor)
            forced.append(nm)
            if self._resolver is not None:
                try:
                    for ent in self._resolver.expand_to_entities(nm) or []:
                        if ent not in _GENERIC_NAMES:
                            scored[ent] = max(scored.get(ent, 0.0), 0.95 * floor)
                            forced.append(ent)
                except Exception:  # pragma: no cover
                    pass
        return scored

    def _inject_axis_poles(self, syndrome: str, syn: str,
                           scored: dict[str, float],
                           forced: Optional[list] = None) -> dict[str, float]:
        """§19.5 / IMP-56-60: inject the syndrome's can't-miss families (which
        span the opposite axis poles) at a competitive floor so BOTH poles are
        present in the candidate set — a precondition for a correct axis split
        (one-pole branches pollute LR direction). Injected below the strongest
        spotted hits (0.6×max) so real gold is not evicted, but above noise."""
        ents = self._lookup_cant_miss(syn)
        if not ents:
            return scored
        floor = 0.6 * (max(scored.values()) if scored else 1.0) or 1.0
        existing = [set(re.findall(r"[a-z0-9]+", d)) for d in scored]
        for name in ents:
            nm = (name or "").strip().lower()
            if not nm or nm in _GENERIC_NAMES:
                continue
            nt = {t for t in re.findall(r"[a-z0-9]+", nm) if len(t) > 3}
            if nt and any(nt <= ct for ct in existing):
                continue  # already represented
            scored[nm] = max(scored.get(nm, 0.0), floor)
            if forced is not None:
                forced.append(nm)
            if self._resolver is not None:
                try:
                    for ent in self._resolver.expand_to_entities(nm) or []:
                        if ent not in _GENERIC_NAMES:
                            scored[ent] = max(scored.get(ent, 0.0), 0.9 * floor)
                except Exception:  # pragma: no cover
                    pass
        return scored

    # ----------------------------------------------- GARMLE-G ② (LLM backup)
    def _retrieve_snippets(self, syndrome: str, context: str = "",
                           k: Optional[int] = None) -> list[str]:
        """Return the raw on-topic DDx/etiology snippet texts (grounding for the
        LLM extractor) — same retrieval+filter as recall(), without spotting."""
        if self._r is None or not getattr(self._r, "is_ready", False):
            return []
        k = k or self._top_k
        syn = (syndrome or "").strip().lower()
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", syn) if len(t) > 3}
        colloq = self._colloquial(syndrome)
        queries = [f"differential diagnosis of {syndrome}",
                   f"causes and etiology of {syndrome}"]
        if colloq and colloq != syn:
            queries.append(f"approach to {colloq}")
        if context.strip():
            queries.append(f"differential diagnosis of {colloq or syndrome}. "
                           f"clinical features: {context.strip()[:300]}")
        out: list[str] = []
        seen: set[str] = set()
        for q in queries:
            try:
                hits = self._r.search(q, top_k=k, score_threshold=0.0)
                if hasattr(self._r, "expand_ddx_siblings"):
                    hits = self._r.expand_ddx_siblings(hits)
            except Exception:
                continue
            for h in hits:
                title = str(h.get("title", "") or "")
                content = str(h.get("content", "") or "")
                if not snippet_on_topic(
                    title=title,
                    content=content,
                    syndrome_tokens=syn_toks,
                    chunk_type=h.get("chunk_type"),
                    entry_type=h.get("entry_type"),
                    syndrome_anchor=h.get("syndrome_anchor"),
                    section_path=h.get("section_path") or title,
                ):
                    continue
                sig = title[:60] + "|" + content[:40]
                if sig in seen:
                    continue
                seen.add(sig)
                out.append(f"[{title[:70]}] {content[:400]}")
        return out[:24]

    def recall_llm(self, syndrome: str, llm_client, *, context: str = "") -> dict[str, float]:
        """§31.13.12 GARMLE-G ② *backup*: LLM grounded extraction of the candidate
        disease families from the retrieved DDx/etiology snippets. The LLM is
        constrained to diseases that appear in the excerpts (grounded, no
        invention) and asked for SPECIFIC entities (regularises the spotter's
        generic-vs-specific failure). Returns {disease: score}. Empty on any
        failure → caller can fall back to the deterministic recall()."""
        snippets = self._retrieve_snippets(syndrome, context=context)
        if not snippets or llm_client is None:
            return {}
        prompt = (
            "You are a clinical knowledge extractor. From the reference excerpts, "
            "list the candidate diagnoses that constitute the DIFFERENTIAL DIAGNOSIS "
            "of the given presenting syndrome. RULES: (1) only include diseases that "
            "appear in the excerpts (grounded; do not invent); (2) prefer SPECIFIC "
            "disease entities (e.g. 'chronic myeloid leukemia', not 'leukemia'); "
            "(3) exclude the syndrome itself and pure symptom terms. "
            "Return strict JSON: {\"families\": [\"disease1\", \"disease2\", ...]}."
        )
        payload = {"presenting_syndrome": syndrome, "reference_excerpts": snippets}
        try:
            result = llm_client.call_module("GuidelineDDxExtractor", prompt, payload)
        except Exception as e:  # pragma: no cover - network/LLM defensive
            logger.warning("GARMLE-G LLM extraction failed: %s", e)
            return {}
        fams = result.get("families", []) if isinstance(result, dict) else []
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", (syndrome or "").lower()) if len(t) > 3}
        out: dict[str, float] = {}
        for i, fam in enumerate(fams):
            d = str(fam).strip().lower()
            dt = set(re.findall(r"[a-z0-9]+", d))
            if not d or dt <= syn_toks or d in _GENERIC_NAMES:
                continue
            out[d] = 1.0 - 0.01 * i  # preserve LLM ordering as a soft score
            # ③ resolver expansion still applies (broad family → members)
            if self._resolver is not None:
                try:
                    for ent in self._resolver.expand_to_entities(d) or []:
                        if ent not in _GENERIC_NAMES:
                            out.setdefault(ent, 0.9 * out[d])
                except Exception:
                    pass
        return dict(list(out.items())[: self._max_candidates])

    # ------------------------------------- §31.13.16 方案A: LLM axis (TODO-GL-11)
    @staticmethod
    def _domain_to_entry_domain(name: str, entities: list[str]) -> dict:
        """Convert one LLM domain {name, entities} into the SyndromeAxisMap
        domain contract (member_keywords drive project_entity)."""
        ents = [str(e).strip().lower() for e in (entities or []) if str(e).strip()]
        kws: set[str] = {name.strip().lower()} if name else set()
        for e in ents:
            kws.add(e)
            kws.update(t for t in re.findall(r"[a-z0-9]+", e) if len(t) > 3)
        kws.update(t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) > 3)
        return {"name": name or "domain", "member_keywords": sorted(kws),
                "_entities": ents}

    def build_branch_knowledge_llm(self, syndrome: str, llm_client, *,
                                   context: str = "",
                                   cache_path: Optional[str] = None) -> dict:
        """§31.13.16 方案A: have the LLM produce the full ``branch_knowledge``
        entry (axis + MECE domains + representative entities + mandatory flags)
        DIRECTLY, grounded in the retrieved DDx/etiology excerpts. This bypasses
        the SNOMED ``is_a`` partition (the proven wall) — the LLM does the
        clinical grouping that SNOMED cannot for mechanism/anatomy-phrased
        entities (adhesions/peliosis/foreign body).

        Emits the SAME entry shape as SyndromeAxisMap/KBAxisMap, so every
        downstream option (mandatory / phase-subaxis / taxonomy) is unchanged.
        Caches per-syndrome to ``cache_path`` (generation is automatic; the
        cache only avoids repeat LLM calls)."""
        syn_key = (syndrome or "").strip().lower()
        cache: dict = {}
        if cache_path and Path(cache_path).exists():
            try:
                cache = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            except Exception:
                cache = {}
            if syn_key in cache:
                return cache[syn_key]

        snippets = self._retrieve_snippets(syndrome, context=context)
        if not snippets or llm_client is None:
            return self._empty_entry(syndrome)
        prompt = (
            "You are a clinical taxonomist building the differential-diagnosis "
            "branch structure for a presenting syndrome. From the reference "
            "excerpts, produce a SINGLE-AXIS, MUTUALLY-EXCLUSIVE & COLLECTIVELY-"
            "EXHAUSTIVE partition of the differential. RULES: (1) choose ONE "
            "classification axis (etiology | anatomy | mechanism | morphology | "
            "lineage) appropriate to this syndrome; (2) 3-6 domains; (3) each "
            "domain lists SPECIFIC disease entities grounded in the excerpts "
            "(no invention); (4) mark mandatory=true for can't-miss families; "
            "(5) domains must not overlap. Return strict JSON: {\"axis\": \"...\", "
            "\"domains\": [{\"name\": \"...\", \"entities\": [\"...\"], "
            "\"mandatory\": true}]}."
        )
        payload = {"presenting_syndrome": syndrome, "reference_excerpts": snippets}
        try:
            result = llm_client.call_module("BranchKnowledgeBuilder", prompt, payload)
        except Exception as e:  # pragma: no cover
            logger.warning("LLM axis build failed: %s", e)
            return self._empty_entry(syndrome)
        if not isinstance(result, dict):
            return self._empty_entry(syndrome)
        axis = str(result.get("axis", "mechanism")).strip().lower() or "mechanism"
        raw_domains = result.get("domains", []) or []
        syn_toks = {t for t in re.findall(r"[a-z0-9]+", syn_key) if len(t) > 3}
        domains, mandatory = [], []
        for d in raw_domains:
            if not isinstance(d, dict):
                continue
            name = str(d.get("name", "")).strip()
            ents = [str(e).strip().lower() for e in (d.get("entities") or [])
                    if str(e).strip() and str(e).strip().lower() not in _GENERIC_NAMES]
            # resolver expansion still applies (broad family → members)
            if self._resolver is not None:
                expanded = list(ents)
                for e in ents:
                    try:
                        for m in self._resolver.expand_to_entities(e) or []:
                            if m not in _GENERIC_NAMES and m not in expanded:
                                expanded.append(m)
                    except Exception:
                        pass
                ents = expanded
            if not name or not ents:
                continue
            dom = self._domain_to_entry_domain(name, ents)
            domains.append(dom)
            if d.get("mandatory"):
                mandatory.append(dom["name"])
        if len(domains) < 2:
            return self._empty_entry(syndrome)
        entry = {
            "id": f"llmaxis::{syn_key[:40]}",
            "axis": axis,
            "axis_rationale": (f"LLM-derived (§31.13.16 方案A): grounded MECE "
                               f"partition of {len(domains)} domains on the "
                               f"'{axis}' axis from {len(snippets)} guideline "
                               f"excerpts."),
            "domains": domains,
            "mandatory_coverage": mandatory,
            "syndrome_keywords": sorted(syn_toks),
        }
        if cache_path:
            try:
                cache[syn_key] = entry
                Path(cache_path).write_text(
                    json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning("axis cache write failed: %s", e)
        return entry

    @staticmethod
    def _empty_entry(syndrome: str) -> dict:
        return {"id": f"llmaxis::{(syndrome or '')[:40].lower()}",
                "axis": "mechanism", "axis_rationale": "empty (LLM/retrieval failed)",
                "domains": [], "mandatory_coverage": [], "syndrome_keywords": []}
