"""Disease name resolver: fuzzy normalization across heterogeneous knowledge sources.

Solves the critical P-1 blocker where TALP branch labels (e.g. "Acute Myeloid
Leukemia (AML)") fail to match any knowledge layer index key.

Strategy:
  1. Strip parenthetical abbreviations and normalize whitespace
  2. Exact match against each source's disease index
  3. UMLS CUI bridging via docLogica umlsId and manual alias table
  4. Token-level Jaccard fuzzy match with medical abbreviation expansion
  5. ICD-10 prefix fallback (DxS only)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional, Sequence

logger = logging.getLogger(__name__)

_ABBREV_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
_DASH_QUALIFIER_RE = re.compile(r"\s*[-–—]\s*(blast crisis|bc|accelerated phase|ap|chronic phase|cp)\s*$", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"a", "an", "the", "of", "in", "on", "with", "and", "or", "for", "to", "type"})

_ABBREVIATION_EXPANSIONS: dict[str, list[str]] = {
    "aml": ["acute myeloid leukemia", "acute myelogenous leukemia"],
    "cml": ["chronic myeloid leukemia", "chronic myelogenous leukemia"],
    "all": ["acute lymphoblastic leukemia", "acute lymphocytic leukemia"],
    "cll": ["chronic lymphocytic leukemia", "chronic lymphoblastic leukemia"],
    "mds": ["myelodysplastic syndrome", "myelodysplasia"],
    "nhl": ["non-hodgkin lymphoma"],
    "hl": ["hodgkin lymphoma", "hodgkin disease"],
    "dlbcl": ["diffuse large b-cell lymphoma"],
    "copd": ["chronic obstructive pulmonary disease"],
    "chf": ["congestive heart failure"],
    "mi": ["myocardial infarction"],
    "pe": ["pulmonary embolism"],
    "dvt": ["deep vein thrombosis", "deep venous thrombosis"],
    "uti": ["urinary tract infection"],
    "sle": ["systemic lupus erythematosus"],
    "ra": ["rheumatoid arthritis"],
    "dm": ["diabetes mellitus"],
    "htn": ["hypertension"],
    "cad": ["coronary artery disease"],
    "itp": ["immune thrombocytopenic purpura", "idiopathic thrombocytopenic purpura"],
    "ttp": ["thrombotic thrombocytopenic purpura"],
    "dic": ["disseminated intravascular coagulation"],
    "bc": ["blast crisis"],
    "cmml": ["chronic myelomonocytic leukemia"],
    "mpn": ["myeloproliferative neoplasm"],
    "gvhd": ["graft-versus-host disease"],
    "ards": ["acute respiratory distress syndrome"],
}

_MANUAL_ALIAS_TABLE: dict[str, list[str]] = {
    "chronic myeloid leukemia": [
        "chronic myelogenous leukemia, bcr-abl1 positive",
        "chronic myelogenous leukemia",
        "chronic myeloid leukaemia",
    ],
    "chronic myeloid leukemia in blast crisis": [
        "blast phase chronic myelogenous leukemia, bcr-abl1 positive",
        "chronic myeloid leukemia - blast crisis",
        "cml blast crisis",
        "cml-bc",
    ],
    "acute myeloid leukemia": [
        "acute myelogenous leukemia",
        "acute myeloid leukaemia",
        "acute myelomonocytic leukemia",
        "acute monoblastic/monocytic leukemia",
    ],
    "acute lymphoblastic leukemia": [
        "acute lymphocytic leukemia",
        "acute lymphoblastic leukaemia",
    ],
    "myelodysplastic syndrome": [
        "myelodysplastic syndromes",
        "myelodysplasia",
        "myelodysplastic/myeloproliferative disease",
    ],
    "chronic myelomonocytic leukemia": [
        "myelomonocytic leukemia",
        "chronic myelomonocytic leukaemia",
    ],
}

_REVERSE_ALIAS: dict[str, str] = {}
for canonical, aliases in _MANUAL_ALIAS_TABLE.items():
    _REVERSE_ALIAS[canonical.lower()] = canonical.lower()
    for alias in aliases:
        _REVERSE_ALIAS[alias.lower()] = canonical.lower()


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower())) - _STOP


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _normalize_label(label: str) -> str:
    """Strip parenthetical abbreviations and trailing qualifiers."""
    s = _ABBREV_PAREN_RE.sub(" ", label)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _extract_abbreviation(label: str) -> Optional[str]:
    """Extract abbreviation from parentheses, e.g. 'Acute Myeloid Leukemia (AML)' → 'aml'."""
    m = re.search(r"\(([A-Z]{2,6}(?:-[A-Z]{1,3})?)\)", label)
    return m.group(1).lower() if m else None


def _extract_qualifier(label: str) -> Optional[str]:
    """Extract trailing qualifier like 'Blast Crisis' or 'BC'."""
    m = _DASH_QUALIFIER_RE.search(label)
    return m.group(1).lower() if m else None


class DiseaseNameResolver:
    """Resolves free-text disease labels to canonical index keys across knowledge sources.

    Maintains per-source indices and resolves a query label to the best
    matching key in each source independently (different sources may use
    different canonical names for the same disease).
    """

    def __init__(self) -> None:
        self._source_keys: dict[str, list[str]] = {}
        self._source_tokens: dict[str, dict[str, set[str]]] = {}
        self._umls_cui_to_names: dict[str, list[str]] = {}
        self._name_to_cui: dict[str, str] = {}
        self._cache: dict[tuple[str, str], Optional[str]] = {}
        # mechanism / pathophysiology / morphology phrasing → canonical disease
        self._mechanism_map: dict[str, str] = {}
        # §22.2 (A′): broad family label keyword → list of canonical entities.
        # Each entry maps a set of trigger keywords (substrings of a branch
        # label) to the specific disease entities that family covers, so a
        # SYNDROME-granularity branch label can be expanded MECHANICALLY (no LLM)
        # into entities the disease-keyed LR cache can hit.
        self._family_expansions: list[dict] = []

    def load_mechanism_map(self, path: str | Path) -> None:
        """Load the mechanism/morphology → canonical-disease normalisation table.

        Benchmark answer options are often phrased as a causal mechanism
        ("Increased parathyroid hormone") or a cell/tissue morphology
        ("Beta cell tumor") rather than a disease name, leaving them with ZERO
        disease-keyed cache entries. This table maps such phrasings to the
        disease entity the knowledge sources actually index, so the option can
        accrue numeric LR evidence instead of only qualitative RAG context.
        """
        p = Path(path)
        if not p.exists():
            logger.warning("mechanism_to_disease map not found: %s", p)
            return
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        exact = data.get("exact", {}) if isinstance(data, dict) else {}
        self._mechanism_map = {k.strip().lower(): v.strip().lower() for k, v in exact.items()}
        # §22.2 (A′): family-label → canonical entities expansion table.
        fam = data.get("family_expansions", []) if isinstance(data, dict) else []
        self._family_expansions = []
        for item in fam:
            if not isinstance(item, dict):
                continue
            kws = [str(k).strip().lower() for k in item.get("any_keywords", []) if str(k).strip()]
            ents = [str(e).strip().lower() for e in item.get("entities", []) if str(e).strip()]
            if kws and ents:
                self._family_expansions.append({"any_keywords": kws, "entities": ents})
        self._cache.clear()
        logger.info("DiseaseNameResolver: mechanism→disease map loaded (%d exact, %d family)",
                    len(self._mechanism_map), len(self._family_expansions))

    def expand_to_entities(self, label: str, limit: int = 4) -> list[str]:
        """§22.2 (A′): mechanically expand a (broad) branch label into up to
        ``limit`` canonical disease entities for KB/LR lookup — WITHOUT touching
        the label or the branch tree.

        Order of precedence:
          1. exact mechanism/morphology map (1 canonical entity), and
          2. family-expansion keyword table (any trigger keyword in the label →
             that family's entities).
        Returns a deduplicated, lowercased list. Empty when nothing matches
        (a miss must stay cheap — never invents entities).
        """
        norm = _normalize_label(label)
        if not norm:
            return []
        out: list[str] = []
        seen: set[str] = set()

        def _add(ent: str) -> None:
            e = (ent or "").strip().lower()
            if e and e != norm and e not in seen:
                seen.add(e)
                out.append(e)

        mapped = self._mechanism_map.get(norm)
        if mapped:
            _add(mapped)
        for item in self._family_expansions:
            if any(kw in norm for kw in item["any_keywords"]):
                for ent in item["entities"]:
                    _add(ent)
        return out[:limit]

    def nominate_from_text(self, text: str, limit: int = 12) -> list[str]:
        """IMP-58: scan FREE TEXT (the clinical context) for mechanism /
        morphology phrasings and broad-family keywords, returning the canonical
        disease entities they directly imply (substring match, no LLM).

        This is the inverse of :meth:`expand_to_entities` (which takes a single
        label): the option/answer is phrased as a *mechanism* ("apical lung
        tumor", "catecholamine excess") inside the upstream context, leaving the
        disease entity absent from the retrieved DDx snippets. Direct nomination
        injects that entity into the candidate pool so the gold branch is not
        missed (the §17 c1 Pancoast / c13 mechanism-gap lever). Returns a
        deduplicated, lowercased list; empty when nothing matches (cheap miss).
        """
        t = (text or "").lower()
        if not t:
            return []
        out: list[str] = []
        seen: set[str] = set()

        def _add(ent: str) -> None:
            e = (ent or "").strip().lower()
            if e and e not in seen:
                seen.add(e)
                out.append(e)

        for key, dz in self._mechanism_map.items():
            # require a word-ish boundary so short keys do not over-trigger
            if key and len(key) >= 6 and key in t:
                _add(dz)
        for item in self._family_expansions:
            if any(kw in t for kw in item["any_keywords"]):
                for ent in item["entities"]:
                    _add(ent)
        return out[:limit]

    def canonicalize_entity(self, label: str) -> str:
        """Return the canonical disease name for a (possibly mechanism/morphology)
        label, or the normalised label unchanged when no mapping applies.

        This is source-independent: it only rewrites the *surface form* so the
        downstream tiered :meth:`resolve` (and the LR cache's own fuzzy/synonym
        matching) operate on a disease entity rather than a pathophysiology
        phrase. Safe to call on any disease/branch/option label.
        """
        norm = _normalize_label(label)
        return self._mechanism_map.get(norm, norm)

    def register_source(self, source_name: str, disease_keys: Sequence[str]) -> None:
        """Register a knowledge source's disease key vocabulary."""
        keys = [k.strip().lower() for k in disease_keys]
        self._source_keys[source_name] = keys
        self._source_tokens[source_name] = {k: _tokenize(k) for k in keys}
        self._cache.clear()
        logger.info("DiseaseNameResolver: registered '%s' with %d keys", source_name, len(keys))

    def load_umls_from_doclogica(self, doclogica_path: str | Path) -> None:
        """Extract UMLS CUI mappings from docLogica cache."""
        path = Path(doclogica_path)
        if not path.exists():
            logger.warning("docLogica cache not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        diseases_raw = data.get("diseases", {})
        entries = diseases_raw.values() if isinstance(diseases_raw, dict) else diseases_raw
        for disease_entry in entries:
            if not isinstance(disease_entry, dict):
                continue
            name = (disease_entry.get("name") or "").strip().lower()
            cui = (disease_entry.get("umlsId") or "").strip()
            if name and cui:
                self._umls_cui_to_names.setdefault(cui, []).append(name)
                self._name_to_cui[name] = cui
                count += 1
            # Also index synonyms under the same CUI
            for syn in disease_entry.get("synonyms", []):
                if isinstance(syn, str) and syn.strip() and cui:
                    syn_low = syn.strip().lower()
                    self._umls_cui_to_names.setdefault(cui, []).append(syn_low)
                    self._name_to_cui[syn_low] = cui

        logger.info("UMLS CUI mappings loaded from docLogica: %d diseases, %d CUIs",
                     count, len(self._umls_cui_to_names))

    def load_bridge(self, bridge_path: str | Path) -> None:
        """Load comprehensive disease name bridge for cross-source resolution."""
        path = Path(bridge_path)
        if not path.exists():
            logger.warning("Disease name bridge not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        self._bridge_by_alias = data.get("by_alias", {})
        self._bridge_by_canonical = data.get("by_canonical", {})

        for canonical, info in self._bridge_by_canonical.items():
            canon_name = canonical.lower()
            self._name_to_cui.setdefault(canon_name, canon_name)
            self._umls_cui_to_names.setdefault(canon_name, [canon_name])
            for alias in info.get("aliases", []):
                alias_lower = alias.lower()
                self._name_to_cui.setdefault(alias_lower, canon_name)
                self._umls_cui_to_names[canon_name].append(alias_lower)

        logger.info("Disease name bridge loaded: %d canonical, %d aliases",
                    len(self._bridge_by_canonical), len(self._bridge_by_alias))

    def resolve(self, label: str, source_name: str) -> Optional[str]:
        """Resolve a free-text disease label to the best matching key in a source.

        Returns the matched key or None.
        """
        cache_key = (label.strip().lower(), source_name)
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._resolve_impl(label, source_name)
        self._cache[cache_key] = result
        return result

    def resolve_all_sources(self, label: str) -> dict[str, Optional[str]]:
        """Resolve a label against all registered sources."""
        return {src: self.resolve(label, src) for src in self._source_keys}

    def _resolve_impl(self, label: str, source_name: str) -> Optional[str]:
        keys = self._source_keys.get(source_name, [])
        if not keys:
            return None

        normalized = _normalize_label(label)
        abbrev = _extract_abbreviation(label)
        qualifier = _extract_qualifier(label)

        # Tier 0: mechanism / morphology → canonical disease entity. When the
        # label is a pathophysiology phrasing ("increased parathyroid hormone",
        # "beta cell tumor") rewrite it to the disease the sources index, then
        # let the normal tiers resolve THAT to a source key.
        mapped = self._mechanism_map.get(normalized)
        if mapped and mapped != normalized:
            if mapped in keys:
                return mapped
            normalized = mapped
            abbrev = _extract_abbreviation(mapped) or abbrev

        # Tier 1: exact match on normalized label
        if normalized in keys:
            return normalized

        # Tier 1b: check reverse alias table → canonical → source match
        canonical = _REVERSE_ALIAS.get(normalized)
        if canonical and canonical in keys:
            return canonical

        for alias_canonical, aliases in _MANUAL_ALIAS_TABLE.items():
            if normalized == alias_canonical.lower() or normalized in [a.lower() for a in aliases]:
                for candidate in [alias_canonical.lower()] + [a.lower() for a in aliases]:
                    if candidate in keys:
                        return candidate

        # Tier 2: abbreviation expansion
        if abbrev:
            expansions = _ABBREVIATION_EXPANSIONS.get(abbrev, [])
            if qualifier:
                qualified = [f"{exp} {qualifier}" for exp in expansions]
                qualified += [f"{exp} in {qualifier}" for exp in expansions]
                qualified += [f"{qualifier} {exp}" for exp in expansions]
                expansions = qualified + expansions
            for exp in expansions:
                exp_low = exp.lower()
                if exp_low in keys:
                    return exp_low
                exp_canonical = _REVERSE_ALIAS.get(exp_low)
                if exp_canonical:
                    for candidate in [exp_canonical] + [a.lower() for a in _MANUAL_ALIAS_TABLE.get(exp_canonical, [])]:
                        if candidate in keys:
                            return candidate

        # Tier 2.5: Bridge alias lookup
        if hasattr(self, '_bridge_by_alias'):
            bridge_canonical = self._bridge_by_alias.get(normalized)
            if bridge_canonical:
                bridge_entry = self._bridge_by_canonical.get(bridge_canonical, {})
                candidates = [bridge_canonical] + [a.lower() for a in bridge_entry.get("aliases", [])]
                for candidate in candidates:
                    if candidate in keys:
                        return candidate

        # Tier 3: UMLS CUI bridging
        cui = self._name_to_cui.get(normalized)
        if cui:
            for umls_name in self._umls_cui_to_names.get(cui, []):
                if umls_name in keys:
                    return umls_name

        # Tier 4: substring containment — collect all candidates and pick best overlap
        substr_candidates: list[tuple[float, str]] = []
        for k in keys:
            longer_len = max(len(normalized), len(k))
            shorter_len = min(len(normalized), len(k))
            if shorter_len < 8:
                continue
            ratio = shorter_len / longer_len
            if normalized in k or k in normalized:
                if ratio > 0.5:
                    substr_candidates.append((ratio, k))
        if substr_candidates:
            substr_candidates.sort(key=lambda x: -x[0])
            return substr_candidates[0][1]

        # Tier 5: token Jaccard with threshold (require at least 2 shared tokens)
        query_tokens = _tokenize(normalized)
        if abbrev:
            for exp in _ABBREVIATION_EXPANSIONS.get(abbrev, []):
                query_tokens |= _tokenize(exp)

        token_map = self._source_tokens.get(source_name, {})
        best_score = 0.0
        best_key = None
        for k, kt in token_map.items():
            shared = query_tokens & kt
            if len(shared) < 2:
                continue
            score = _jaccard(query_tokens, kt)
            if score > best_score:
                best_score = score
                best_key = k
        if best_score >= 0.45 and best_key:
            return best_key

        return None
