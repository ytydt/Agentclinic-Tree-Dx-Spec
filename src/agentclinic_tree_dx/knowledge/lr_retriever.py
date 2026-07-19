"""Layer 2: Likelihood Ratio (LR) cache and retriever.

Supports two cache formats:
  - Legacy: flat {key: entry} from lr_cache.json
  - Unified: {entries: {key: entry}, hpo_id_index: {...}} from build_unified_cache.py

When using the unified cache, multi-tier lookup is available:
  1. Exact hash lookup  (finding::disease)
  2. HPO synonym expansion (via HPO name → synonyms mapping)
  3. Substring/token overlap fuzzy match (fallback)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({
    "a", "an", "the", "of", "in", "on", "is", "was", "are", "were",
    "with", "for", "to", "and", "or", "no", "not", "has", "had",
    "by", "at", "from", "but", "be", "been", "patient", "patients",
    "abnormal", "abnormality", "increased", "decreased", "elevated",
    "reduced", "disorder", "finding", "morphology",
})

_DISEASE_SYNONYM_PAIRS: list[tuple[str, str]] = [
    ("myeloid", "myelogenous"),
    ("syndrome", "neoplasm"),
    ("syndrome", "disease"),
    ("disorder", "disease"),
    ("type", "subtype"),
    ("chronic", "chr"),
    ("acute", "acut"),
]

_DISEASE_GENERIC_TERMS = frozenset({
    "syndrome", "disease", "neoplasm", "disorder", "type", "subtype",
    "unclassified", "associated", "isolated", "chromosome", "abnormality",
    "positive", "negative", "phase", "crisis", "low", "high", "increased",
})

_STEM_MAP: dict[str, str] = {}

def _build_stem_map() -> None:
    """Build a simple medical suffix-stripping map for common patterns."""
    suffixes = [
        ("philia", "phil"), ("penia", "pen"), ("cytosis", "cyt"),
        ("emia", "em"), ("uria", "ur"), ("itis", "it"),
        ("osis", "os"), ("pathy", "path"), ("algia", "alg"),
        ("ectomy", "ect"), ("megaly", "megal"),
        ("ation", "at"), ("tion", "t"),
        ("ing", ""), ("ness", ""), ("ment", ""),
        ("ous", ""), ("ive", ""), ("al", ""),
        ("ed", ""), ("ly", ""), ("es", ""), ("s", ""),
    ]
    for suf, stem in suffixes:
        _STEM_MAP[suf] = stem

_build_stem_map()


def _medical_stem(word: str) -> str:
    """Reduce a medical term to a rough stem for matching."""
    if len(word) < 4:
        return word
    for suf, stem in _STEM_MAP.items():
        if word.endswith(suf) and len(word) - len(suf) + len(stem) >= 3:
            return word[: -len(suf)] + stem
    return word


def _tokenize(text: str) -> set[str]:
    raw = set(_TOKEN_RE.findall(text.lower())) - _STOP
    return raw


def _tokenize_stemmed(text: str) -> set[str]:
    raw = set(_TOKEN_RE.findall(text.lower())) - _STOP
    return {_medical_stem(w) for w in raw}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _stemmed_jaccard(text_a: str, text_b: str) -> float:
    """Jaccard on stemmed tokens — catches basophilia ≈ basophil etc."""
    sa = _tokenize_stemmed(text_a)
    sb = _tokenize_stemmed(text_b)
    return _jaccard(sa, sb)


def _normalize_disease_text(text: str) -> str:
    """Apply synonym normalization for disease name matching."""
    t = text.lower()
    for a, b in _DISEASE_SYNONYM_PAIRS:
        t = t.replace(b, a)
    return t


def _disease_key_tokens(text: str) -> set[str]:
    """Extract only the medically distinctive tokens from a disease name."""
    raw = set(_TOKEN_RE.findall(text.lower()))
    return raw - _STOP - _DISEASE_GENERIC_TERMS


_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")

# §25.2(#2): finding-match guards (precision-oriented; reject false positives the
# bag-of-words scorer would otherwise accept).
_NEGATION_RE = re.compile(
    r"\b(no|not|without|absent|absence|negative|denies|denied|"
    r"non[- ]?reactive|free of|rule[d]? out|r/o)\b"
)
_LEFT_RE = re.compile(r"\b(left|lt|l[- ]sided|sinistr\w*)\b")
_RIGHT_RE = re.compile(r"\b(right|rt|r[- ]sided|dextr\w*)\b")


def _is_negated_text(text: str) -> bool:
    return _NEGATION_RE.search(text or "") is not None


def _laterality(text: str) -> str:
    """Return 'left' | 'right' | 'both' | '' for a finding string."""
    t = text or ""
    l = _LEFT_RE.search(t) is not None
    r = _RIGHT_RE.search(t) is not None
    if l and r:
        return "both"
    if l:
        return "left"
    if r:
        return "right"
    return ""


def _match_guard_conflict(patient_finding: str, cached_finding: str) -> bool:
    """True if patient and cached findings CONFLICT on negation or laterality —
    i.e. the surface tokens may overlap but they assert opposite clinical facts
    ("chest pain" vs "no chest pain"; "left hemiparesis" vs "right hemiparesis").
    Such a fuzzy match is a false positive and should be rejected.
    """
    p = (patient_finding or "").lower()
    c = (cached_finding or "").lower()
    # Negation polarity must agree (XOR = conflict).
    if _is_negated_text(p) != _is_negated_text(c):
        return True
    # Laterality, when BOTH specify it, must agree.
    lp, lc = _laterality(p), _laterality(c)
    if lp and lc and lp != lc and "both" not in (lp, lc):
        return True
    return False


def _strip_parens(text: str) -> str:
    """Remove parenthetical abbreviations: 'Acute Myeloid Leukemia (AML)' → 'acute myeloid leukemia'."""
    return _PAREN_RE.sub(" ", text).strip()


def _disease_match_score(query: str, candidate: str) -> float:
    """Score how well a disease query matches a cached disease name.

    Uses a combination of: substring, key-token recall, and synonym-aware
    matching to handle WHO nomenclature changes (e.g. MDS "syndrome" → "neoplasm").
    Parenthetical abbreviations like "(AML)" are stripped before comparison.
    """
    q_lower = _strip_parens(query.strip().lower())
    c_lower = _strip_parens(candidate.strip().lower())

    if q_lower == c_lower:
        return 1.0
    if q_lower in c_lower or c_lower in q_lower:
        return 0.85

    q_norm = _normalize_disease_text(q_lower)
    c_norm = _normalize_disease_text(c_lower)
    if q_norm in c_norm or c_norm in q_norm:
        return 0.8

    q_key = _disease_key_tokens(q_lower)
    c_key = _disease_key_tokens(c_lower)
    if not q_key:
        return 0.0
    recall = len(q_key & c_key) / len(q_key) if q_key else 0.0
    if recall >= 0.8:
        return 0.7

    q_key_norm = _disease_key_tokens(q_norm)
    c_key_norm = _disease_key_tokens(c_norm)
    recall_norm = len(q_key_norm & c_key_norm) / len(q_key_norm) if q_key_norm else 0.0
    if recall_norm >= 0.8:
        return 0.65

    return 0.0


class LRRetriever:
    """Multi-source hash-lookup retriever for likelihood ratio data.

    Unified cache entry format:
    {
        "finding": "Splenomegaly",
        "disease": "Chronic myeloid leukemia",
        "sensitivity": 0.545,
        "specificity": 0.9,
        "lr_positive": 5.45,
        "lr_negative": 0.506,
        "source": "HPO",
        "confidence": "medium",
        "hpo_id": "HP:0001744",
        "raw_frequency": "HP:0040282"
    }
    """

    def __init__(self) -> None:
        self._cache: dict[str, dict] = {}
        self._disease_index: dict[str, list[str]] = {}
        self._finding_index: dict[str, list[str]] = {}
        self._hpo_id_index: dict[str, list[str]] = {}
        self._finding_tokens: dict[str, set[str]] = {}
        self._embedding_index = None
        self._hpo_index: Optional["HPOIndex"] = None
        self._finding_synonym_bridge: dict[str, dict] = {}
        self._disease_synonym_bridge: dict[str, str] = {}
        # Disease fuzzy matching is independent of the queried finding.  The
        # controller asks about several findings for the same branch labels, so
        # rescanning the complete disease index on every lookup turns one
        # EvidenceAnnotator pass into minutes of duplicate CPU work.
        self._disease_candidate_cache: dict[str, tuple[str, ...]] = {}
        # Character trigrams provide a lossless practical prefilter for every
        # match accepted by _disease_match_score (substring or shared disease
        # token), avoiding a full disease-index scan for each new branch label.
        self._disease_ngram_index: dict[str, set[str]] = {}
        # §25.2(#1): when True, a same-HPO-concept cache match (patient_hpo ==
        # cache_hpo) is treated as a near-exact synonym (score 0.95) and competes
        # for best_entry, instead of being demoted to a sub-threshold fallback
        # that any ≥0.35 token-Jaccard match shadows. Default False = legacy order.
        self._hpo_exact_priority: bool = False
        # §25.2(#2): finding-match guards — reject negation/laterality conflicts,
        # raise the pure-token acceptance bar (0.5), and downweight the subset
        # rule (0.6→0.5). Default False = legacy permissive matching.
        self._match_guards: bool = False

    @classmethod
    def from_cache(cls, cache_path: str | Path) -> "LRRetriever":
        """Load from either legacy flat cache or unified cache."""
        ret = cls()
        path = Path(cache_path)
        if not path.exists():
            logger.warning("LR cache not found at %s; starting empty", path)
            return ret
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, dict) and "entries" in raw:
            ret._cache = raw["entries"]
            ret._hpo_id_index = raw.get("hpo_id_index", {})
        else:
            ret._cache = raw

        ret._build_indices()

        cache_dir = path.parent
        emb_path = cache_dir / "hpo_embeddings.npy"
        meta_path = cache_dir / "hpo_embedding_metadata.json"
        if emb_path.exists() and meta_path.exists():
            try:
                from .embedding_index import EmbeddingIndex
                ret._embedding_index = EmbeddingIndex.from_files(emb_path, meta_path)
            except Exception as e:
                logger.warning("Failed to load embedding index: %s", e)

        logger.info("LRRetriever loaded: %d entries", len(ret._cache))

        supplement_path = cache_dir / "clinical_supplement_cache.json"
        if supplement_path.exists():
            ret._load_supplement(supplement_path)

        obo_path = cache_dir / "hp.obo"
        if obo_path.exists():
            try:
                from .hpo_index import HPOIndex
                ret._hpo_index = HPOIndex.from_obo(obo_path)
            except Exception as e:
                logger.warning("Failed to load HPO ontology: %s", e)

        finding_bridge_path = cache_dir / "finding_synonym_bridge.json"
        if finding_bridge_path.exists():
            try:
                with open(finding_bridge_path, encoding="utf-8") as f:
                    ret._finding_synonym_bridge = json.load(f)
                logger.info("Finding synonym bridge: %d entries", len(ret._finding_synonym_bridge))
            except Exception as e:
                logger.warning("Failed to load finding synonym bridge: %s", e)

        disease_bridge_path = cache_dir / "disease_name_bridge_flat.json"
        if disease_bridge_path.exists():
            try:
                with open(disease_bridge_path, encoding="utf-8") as f:
                    ret._disease_synonym_bridge = json.load(f)
                logger.info("Disease synonym bridge: %d entries", len(ret._disease_synonym_bridge))
            except Exception as e:
                logger.warning("Failed to load disease synonym bridge: %s", e)

        return ret

    def _load_supplement(self, path: Path) -> None:
        """Merge hand-curated clinical supplement entries into the cache."""
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        entries = raw.get("entries", {})
        added = 0
        for key, entry in entries.items():
            if key not in self._cache:
                self._cache[key] = entry
                added += 1
                disease = entry.get("disease", "").strip().lower()
                finding = entry.get("finding", "").strip().lower()
                if disease:
                    self._disease_index.setdefault(disease, []).append(key)
                    self._index_disease_ngrams(disease)
                if finding:
                    self._finding_index.setdefault(finding, []).append(key)
                    if finding not in self._finding_tokens:
                        self._finding_tokens[finding] = _tokenize(finding)
        logger.info("Clinical supplement: merged %d new entries", added)

    def _build_indices(self) -> None:
        for key, entry in self._cache.items():
            disease = entry.get("disease", "").strip().lower()
            finding = entry.get("finding", "").strip().lower()
            if disease:
                self._disease_index.setdefault(disease, []).append(key)
                self._index_disease_ngrams(disease)
            if finding:
                self._finding_index.setdefault(finding, []).append(key)
                if finding not in self._finding_tokens:
                    self._finding_tokens[finding] = _tokenize(finding)

    @staticmethod
    def _trigrams(text: str) -> set[str]:
        compact = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        return {
            compact[index:index + 3]
            for index in range(max(0, len(compact) - 2))
            if " " not in compact[index:index + 3]
        }

    def _index_disease_ngrams(self, disease: str) -> None:
        forms = {disease, _normalize_disease_text(disease)}
        for form in forms:
            for gram in self._trigrams(form):
                self._disease_ngram_index.setdefault(gram, set()).add(disease)

    def _fuzzy_disease_names(self, disease: str) -> set[str]:
        forms = {disease, _normalize_disease_text(disease)}
        names: set[str] = set()
        grams: set[str] = set()
        for form in forms:
            grams.update(self._trigrams(form))
        for gram in grams:
            names.update(self._disease_ngram_index.get(gram, ()))
        # Very short labels have no trigrams; preserve legacy behavior.
        return names if grams else set(self._disease_index)

    def lookup(
        self, finding: str, disease: str
    ) -> Optional[dict]:
        """Direct hash lookup for a finding-disease pair."""
        f_low = finding.strip().lower()
        d_low = disease.strip().lower()
        for sep in ("::", "|"):
            entry = self._cache.get(f"{f_low}{sep}{d_low}")
            if entry:
                return entry
        return None

    def _expand_disease_synonyms(self, disease: str) -> set[str]:
        """Expand a disease name to all known synonyms via the bridge."""
        d_low = disease.strip().lower()
        synonyms = {d_low}
        canonical = self._disease_synonym_bridge.get(d_low, d_low)
        synonyms.add(canonical)
        return synonyms

    def _expand_finding_synonyms(self, finding: str) -> set[str]:
        """Expand a finding to all known synonyms via the bridge."""
        f_low = finding.strip().lower()
        synonyms = {f_low}
        entry = self._finding_synonym_bridge.get(f_low)
        if entry and isinstance(entry, dict):
            synonyms.update(s.lower() for s in entry.get("synonyms", []))
        return synonyms

    def lookup_fuzzy(
        self,
        finding: str,
        disease: str,
        *,
        threshold: float = 0.35,
    ) -> Optional[dict]:
        """Multi-tier lookup: exact → synonym bridge → substring → token overlap.

        Also searches across disease name variants (substring matches).
        Returns the best-matching entry or None.
        """
        exact = self.lookup(finding, disease)
        if exact:
            return exact

        f_lower = finding.strip().lower()
        d_lower = disease.strip().lower()

        # Tier 1.5: Try synonym-expanded exact lookup before fuzzy
        f_synonyms = self._expand_finding_synonyms(f_lower)
        d_synonyms = self._expand_disease_synonyms(d_lower)
        for f_syn in f_synonyms:
            for d_syn in d_synonyms:
                if f_syn == f_lower and d_syn == d_lower:
                    continue
                entry = self.lookup(f_syn, d_syn)
                if entry:
                    return entry

        if f_lower.startswith("hp:"):
            hpo_entries = self.lookup_by_hpo_id(finding.strip(), disease)
            if hpo_entries:
                return hpo_entries[0]

        cached_candidates = self._disease_candidate_cache.get(d_lower)
        if cached_candidates is None:
            candidate_keys: list[str] = []
            # Collect candidates for all disease synonyms.
            all_d_names = d_synonyms.copy()
            exact_disease = self._disease_index.get(d_lower)
            if exact_disease:
                candidate_keys.extend(exact_disease)
            for d_syn in d_synonyms:
                if d_syn != d_lower:
                    candidate_keys.extend(self._disease_index.get(d_syn, []))

            fuzzy_names = self._fuzzy_disease_names(d_lower)
            for cached_disease in fuzzy_names:
                if cached_disease in all_d_names:
                    continue
                score = _disease_match_score(d_lower, cached_disease)
                if score >= 0.6:
                    candidate_keys.extend(self._disease_index[cached_disease])
            # Preserve historical order while removing duplicates.  Concurrent
            # controller workers may compute the same value once; assignment is
            # atomic and either identical tuple is safe.
            cached_candidates = tuple(dict.fromkeys(candidate_keys))
            self._disease_candidate_cache[d_lower] = cached_candidates
        candidate_keys = cached_candidates

        if not candidate_keys:
            # No disease match at all — try embedding-based finding normalization
            if self._embedding_index and self._embedding_index.is_ready:
                return self._lookup_via_embedding(f_lower, d_lower)
            return None

        best_score = 0.0
        best_entry = None
        f_tokens = _tokenize(f_lower)
        f_bridge_synonyms = self._expand_finding_synonyms(f_lower)

        patient_hpo = self._hpo_index.resolve_fuzzy(f_lower) if self._hpo_index else None

        hpo_exact_entry: Optional[dict] = None
        hpo_subsumption_entry: Optional[dict] = None
        hpo_subsumption_meta: Optional[dict] = None

        seen_keys: set[str] = set()
        for key in candidate_keys:
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entry = self._cache[key]
            cached_finding = entry.get("finding", "").strip().lower()

            if f_lower == cached_finding:
                score = 1.0
            elif cached_finding in f_bridge_synonyms:
                score = 0.9
            elif f_lower in cached_finding or cached_finding in f_lower:
                score = 0.8
            elif any(s in cached_finding or cached_finding in s
                     for s in f_bridge_synonyms if len(s) > 4):
                score = 0.75
            else:
                ct = self._finding_tokens.get(cached_finding, _tokenize(cached_finding))
                score = _jaccard(f_tokens, ct)
                subset_floor = 0.5 if self._match_guards else 0.6
                if len(f_tokens) >= 1 and f_tokens <= ct:
                    score = max(score, subset_floor)
                stem_score = _stemmed_jaccard(f_lower, cached_finding)
                score = max(score, stem_score)
                # §25.2(#2): raise the pure-token acceptance bar to 0.5 so a
                # single shared generic token cannot mint a spurious LR (exact/
                # synonym/substring tiers above are unaffected).
                if self._match_guards and score < 0.5:
                    score = 0.0

            # §25.2(#2): reject candidates that CONFLICT on negation/laterality
            # regardless of surface overlap ("no chest pain" vs "chest pain").
            if self._match_guards and score > 0.0 and f_lower != cached_finding \
                    and _match_guard_conflict(f_lower, cached_finding):
                score = 0.0

            # §25.2(#1): elevate a same-HPO-concept match to near-exact so it
            # joins best_entry competition (a same HP id == ontology synonym,
            # which must outrank a generic token-Jaccard hit). Gated; only when
            # the string score is not already near-perfect (avoids extra HPO
            # resolves on clear hits).
            if (self._hpo_exact_priority and patient_hpo and self._hpo_index
                    and score < 0.95):
                cache_hpo_e = entry.get("hpo_id", "") or (
                    self._hpo_index.resolve_fuzzy(cached_finding) or "")
                if cache_hpo_e and cache_hpo_e == patient_hpo:
                    score = max(score, 0.95)

            if score > best_score and score >= threshold:
                best_score = score
                best_entry = entry

            if patient_hpo and self._hpo_index and score < threshold:
                cache_hpo = entry.get("hpo_id", "")
                if not cache_hpo:
                    cache_hpo = self._hpo_index.resolve_fuzzy(cached_finding) or ""

                if cache_hpo and patient_hpo == cache_hpo:
                    if not hpo_exact_entry:
                        hpo_exact_entry = entry
                elif cache_hpo and not hpo_subsumption_entry:
                    if self._hpo_index.is_ancestor_of(cache_hpo, patient_hpo):
                        depth = self._hpo_index.subsumption_depth(cache_hpo, patient_hpo)
                        attn = max(0.3, 1.0 - 0.2 * depth)
                        hpo_subsumption_meta = {
                            "direction": "upward",
                            "patient_finding": f_lower,
                            "cache_finding": cached_finding,
                            "patient_hpo": patient_hpo,
                            "cache_hpo": cache_hpo,
                            "depth": depth,
                            "attenuation": attn,
                        }
                        hpo_subsumption_entry = entry

        if best_entry:
            return best_entry

        if hpo_exact_entry:
            return hpo_exact_entry

        if hpo_subsumption_entry and hpo_subsumption_meta:
            return self._attenuate_entry(
                hpo_subsumption_entry, hpo_subsumption_meta
            )

        if self._embedding_index and self._embedding_index.is_ready:
            return self._lookup_via_embedding(f_lower, d_lower, candidate_keys)

        return None

    def _attenuate_entry(self, entry: dict, meta: dict) -> dict:
        """Create an attenuated copy of a cache entry for upward subsumption matches.

        Valid syllogism:
          Major: D → F_broad (cache entry)
          Minor: F_specific IS-A F_broad (HPO ontology)
          ∴ D can manifest F_specific, but LR is attenuated by specificity penalty.

        The original entry is NOT modified; a new dict is returned.
        """
        attn = meta["attenuation"]
        depth = meta["depth"]
        patient_finding = meta["patient_finding"]
        cache_finding = meta["cache_finding"]

        result = dict(entry)
        lr_p = entry.get("lr_positive")

        # 16.9 P3: shrink toward the neutral point 1.0 in LOG space
        # (LR_out = LR_in ** attn). Log-space is the principled space for
        # likelihood ratios and is symmetric for LR>1 and LR<1, unlike the
        # former linear `1 + (LR-1)*attn`. `attn` itself remains a documented
        # heuristic (HPO subsumption depth, parameters uncalibrated).
        if lr_p is not None and lr_p > 0:
            result["lr_positive"] = round(lr_p ** attn, 4)

        # 16.9 P3: this match is PRESENCE-triggered (patient exhibits the more
        # specific finding). The absence likelihood (LR-) of the broader cached
        # finding does not transfer via subsumption, so we do NOT emit an
        # attenuated LR- here to avoid a misleading absence signal.
        result["lr_negative"] = None

        orig_conf = entry.get("confidence", "medium")
        result["confidence"] = "subsumption_upward"
        result["subsumption_meta"] = {
            "direction": "upward",
            "patient_finding": patient_finding,
            "cache_finding": cache_finding,
            "patient_hpo": meta.get("patient_hpo"),
            "cache_hpo": meta.get("cache_hpo"),
            "depth": depth,
            "attenuation": attn,
            "original_confidence": orig_conf,
        }
        result["source"] = f"subsumption_upward:{entry.get('source', '')}"
        return result

    def _lookup_via_embedding(
        self,
        f_lower: str,
        d_lower: str,
        candidate_keys: Optional[list[str]] = None,
    ) -> Optional[dict]:
        """Embedding-based finding normalization when Jaccard fails."""
        emb_results = self._embedding_index.search(f_lower, top_k=5, threshold=0.55)
        if not emb_results:
            return None

        for emb_hit in emb_results:
            normalized_finding = emb_hit["text"].lower()
            hpo_id = emb_hit.get("hpo_id", "")

            if candidate_keys:
                for key in candidate_keys:
                    entry = self._cache[key]
                    cf = entry.get("finding", "").strip().lower()
                    if cf == normalized_finding:
                        return entry
            else:
                result = self.lookup(normalized_finding, d_lower)
                if result:
                    return result

            if hpo_id:
                hpo_entries = self.lookup_by_hpo_id(hpo_id, d_lower)
                if hpo_entries:
                    return hpo_entries[0]

        return None

    def lookup_by_disease(self, disease: str) -> list[dict]:
        """Get all LR entries for a given disease."""
        keys = self._disease_index.get(disease.strip().lower(), [])
        return [self._cache[k] for k in keys]

    def lookup_by_finding(self, finding: str) -> list[dict]:
        """Get all LR entries for a given finding."""
        keys = self._finding_index.get(finding.strip().lower(), [])
        return [self._cache[k] for k in keys]

    def lookup_by_hpo_id(self, hpo_id: str, disease: str = "") -> list[dict]:
        """Look up entries by HPO ID, optionally filtered by disease."""
        keys = self._hpo_id_index.get(hpo_id, [])
        entries = [self._cache[k] for k in keys if k in self._cache]
        if disease:
            d_lower = disease.strip().lower()
            entries = [e for e in entries if d_lower in e.get("disease", "").lower()]
        return entries

    def get_lr_for_annotation(
        self,
        finding: str,
        diseases: list[str],
        *,
        fuzzy: bool = True,
    ) -> dict[str, Optional[dict]]:
        """For each disease, look up the LR of a finding.

        When fuzzy=True, falls back to substring/token matching on cache miss.
        """
        result = {}
        for d in diseases:
            if fuzzy:
                result[d] = self.lookup_fuzzy(finding, d)
            else:
                result[d] = self.lookup(finding, d)
        return result

    def get_comparative_lr(
        self,
        finding: str,
        disease_a: str,
        disease_b: str,
    ) -> Optional[dict]:
        """Compare LR of a finding between two diseases.

        Returns dict with both entries and a discrimination_power score.
        """
        entry_a = self.lookup_fuzzy(finding, disease_a)
        entry_b = self.lookup_fuzzy(finding, disease_b)
        if not entry_a and not entry_b:
            return None
        sn_a = entry_a["sensitivity"] if entry_a else 0.0
        sn_b = entry_b["sensitivity"] if entry_b else 0.0
        discrimination_power = abs(sn_a - sn_b)
        favors = disease_a if sn_a > sn_b else disease_b
        return {
            "finding": finding,
            "disease_a": disease_a,
            "disease_b": disease_b,
            "entry_a": entry_a,
            "entry_b": entry_b,
            "discrimination_power": round(discrimination_power, 4),
            "favors": favors if discrimination_power > 0.05 else "neutral",
        }

    @property
    def entry_count(self) -> int:
        return len(self._cache)

    @property
    def disease_count(self) -> int:
        return len(self._disease_index)

    @property
    def finding_count(self) -> int:
        return len(self._finding_index)

    def save_cache(self, path: str | Path) -> None:
        output = {
            "entries": self._cache,
            "hpo_id_index": self._hpo_id_index,
            "metadata": {
                "total_entries": len(self._cache),
                "total_diseases": len(self._disease_index),
                "total_findings": len(self._finding_index),
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

    def add_entry(
        self,
        finding: str,
        disease: str,
        sensitivity: float,
        specificity: float,
        source: str = "",
        confidence: str = "low",
        reference: str = "",
    ) -> None:
        lr_pos = sensitivity / (1 - specificity) if specificity < 1.0 else float("inf")
        lr_neg = (1 - sensitivity) / specificity if specificity > 0 else float("inf")
        key = f"{finding.strip().lower()}::{disease.strip().lower()}"
        entry = {
            "finding": finding.strip(),
            "disease": disease.strip(),
            "sensitivity": round(sensitivity, 4),
            "specificity": round(specificity, 4),
            "lr_positive": round(lr_pos, 4) if lr_pos != float("inf") else None,
            "lr_negative": round(lr_neg, 4) if lr_neg != float("inf") else None,
            "source": source,
            "confidence": confidence,
            "reference": reference,
        }
        self._cache[key] = entry
        d_low = disease.strip().lower()
        f_low = finding.strip().lower()
        self._disease_index.setdefault(d_low, []).append(key)
        self._finding_index.setdefault(f_low, []).append(key)
        self._finding_tokens[f_low] = _tokenize(f_low)
