"""DiagnosticMarkerIndex: highest-priority pathognomonic / diagnostic-criterion lookup.

Loads two data files:
  1. pathognomonic_markers.json  – hand-curated disease-defining markers (Layer C)
  2. diagnostic_markers.json     – Orphadata pathognomonic signs + diagnostic criteria (Layer A)

Also integrates PrimeKG gene-disease edges (Layer B) when a PrimeKGIndex with
gene data is available.

Runtime priority: Layer C (manual) > Layer A (Orphadata) > Layer B (PrimeKG gene)
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, TYPE_CHECKING

_WORD_BOUNDARY_RE_CACHE: dict[str, re.Pattern] = {}

# 16.9 P2-prereq: negation cues. A marker mention preceded by one of these
# within a short window is treated as NEGATED, so neither a pathognomonic hit
# nor a reverse-exclusion signal fires from "no Auer rods" / "denies ...".
_NEGATION_CUES = (
    "no ", "not ", "without ", "absent", "absence of", "negative for",
    "neg for", "ruled out", "rule out", "denies", "denied", "free of",
    "lack of", "lacking", "no evidence of", "no sign of", "unremarkable for",
    "non-", "non ",
)
# Cues that follow a marker mention, e.g. "Auer rods ABSENT", "RS cells NEGATIVE".
_TRAILING_NEGATION_CUES = (
    "absent", "negative", "not seen", "not present", "not detected",
    "not found", "not identified", "are absent", "is absent", "were absent",
    "was absent", "ruled out", "not appreciated", "not observed",
)
_NEGATION_WINDOW = 30  # chars before the term occurrence to scan for a cue
_TRAILING_WINDOW = 20  # chars after the term occurrence to scan for a cue

# 16.9.8 (T0–T4): the former hand-written `_AMBIGUOUS_ABBREV` blacklist is now
# generated automatically (scripts/build_auto_ambiguity_map.py →
# auto_ambiguity_map.json) and resolved by MarkerDisambiguator. The constants
# below are kept ONLY as a self-contained fallback for when no disambiguator is
# wired in (e.g. the JSON is missing and marker derivation also failed).
_LEGACY_AMBIGUOUS_ABBREV = {"sma", "ema", "ama", "hbs", "hb s"}
_LEGACY_ABBREV_CONTEXT_CUES = (
    "antibod", "antibody", "antibodies", "positive", "negative", "titer",
    "titre", "iga", "igg", "igm", "anti-", "anti ", "serolog", "autoantib",
    "stain", "seropositive", "elevated", "autoimmune",
)
_ABBREV_WINDOW = 50  # chars on each side to scan for a disambiguating cue


def _legacy_abbrev_context_ok(term: str, text: str, idx: int, term_len: int) -> bool:
    """Fallback disambiguation when no MarkerDisambiguator is available."""
    if term not in _LEGACY_AMBIGUOUS_ABBREV:
        return True
    ctx = text[max(0, idx - _ABBREV_WINDOW): idx + term_len + _ABBREV_WINDOW]
    return any(cue in ctx for cue in _LEGACY_ABBREV_CONTEXT_CUES)


def _context_allows(term: str, text: str, idx: int, term_len: int, disambig) -> bool:
    """Route the occurrence through the MarkerDisambiguator (T0–T4) if present,
    else the legacy blacklist fallback."""
    if disambig is not None:
        return disambig.allows(term, text, idx, term_len)
    return _legacy_abbrev_context_ok(term, text, idx, term_len)


def _occurrence_negated(text: str, idx: int, term_len: int) -> bool:
    """True if the occurrence of a term at `idx` sits in a negation context.

    Checks both a preceding window (pre-negation: "no Auer rods") and a short
    trailing window (post-negation: "Auer rods absent").
    """
    pre = text[max(0, idx - _NEGATION_WINDOW): idx]
    if any(cue in pre for cue in _NEGATION_CUES):
        return True
    post = text[idx + term_len: idx + term_len + _TRAILING_WINDOW]
    return any(cue in post for cue in _TRAILING_NEGATION_CUES)


def _term_matches(term: str, text: str, disambig=None) -> bool:
    """Check if term appears in text with word-boundary awareness.

    Short terms (≤5 chars) require word boundaries to avoid spurious
    substring matches like 'igh' inside 'weight'.

    16.9 P2-prereq: occurrences in a negation context ("no Auer rods") are
    NOT counted as matches.
    16.9.8 (T0–T4): ambiguous occurrences are gated by the MarkerDisambiguator.
    """
    if len(term) <= 5:
        pat = _WORD_BOUNDARY_RE_CACHE.get(term)
        if pat is None:
            pat = re.compile(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])")
            _WORD_BOUNDARY_RE_CACHE[term] = pat
        for m in pat.finditer(text):
            if not _occurrence_negated(text, m.start(), len(term)) \
                    and _context_allows(term, text, m.start(), len(term), disambig):
                return True
        return False
    if term not in text:
        return False
    return _positive_occurrence_exists(term, text, disambig)


def _positive_occurrence_exists(term: str, text: str, disambig=None) -> bool:
    """True if at least one occurrence of `term` is NOT negated and is allowed
    by the disambiguator (marker sense, not a same-spelled competing sense)."""
    start = 0
    while True:
        idx = text.find(term, start)
        if idx == -1:
            return False
        if not _occurrence_negated(text, idx, len(term)) \
                and _context_allows(term, text, idx, len(term), disambig):
            return True
        start = idx + len(term)

if TYPE_CHECKING:
    from .primekg_index import PrimeKGIndex

logger = logging.getLogger(__name__)

_GENE_PATTERN = re.compile(
    r"\b([A-Z][A-Z0-9]{1,10}(?:::?[A-Z][A-Z0-9]{1,10})?)\b"
)


class DiagnosticMarkerIndex:
    """Lookup index for pathognomonic signs, diagnostic criteria, and gene-disease links."""

    def __init__(
        self,
        pathognomonic_markers_path: str | Path | None = None,
        diagnostic_markers_path: str | Path | None = None,
        primekg_index: Optional["PrimeKGIndex"] = None,
        *,
        auto_ambiguity_map_path: str | Path | None = None,
        embedding_index=None,
        rag_retriever=None,
        llm_fn=None,
        ontology_index=None,
    ) -> None:
        self._manual_markers: list[dict] = []
        self._manual_term_index: dict[str, list[dict]] = {}

        self._orphadata_entries: list[dict] = []
        self._orphadata_hpo_disease: dict[str, dict[str, dict]] = {}

        self._primekg = primekg_index

        if pathognomonic_markers_path:
            self._load_manual_markers(Path(pathognomonic_markers_path))
        if diagnostic_markers_path:
            self._load_orphadata_markers(Path(diagnostic_markers_path))

        # 16.9.8 (T0–T4): build the marker disambiguator. Prefer the pre-built
        # auto_ambiguity_map.json; fall back to deriving it from the loaded
        # markers so behaviour stays deterministic even without the JSON.
        self._disambiguator = self._build_disambiguator(
            auto_ambiguity_map_path,
            embedding_index=embedding_index,
            rag_retriever=rag_retriever,
            llm_fn=llm_fn,
            ontology_index=ontology_index,
        )

    def _build_disambiguator(
        self,
        auto_ambiguity_map_path: str | Path | None,
        **kwargs,
    ):
        try:
            from .marker_disambiguator import MarkerDisambiguator
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("MarkerDisambiguator unavailable (%s); using legacy "
                           "blacklist fallback", e)
            return None
        map_path = auto_ambiguity_map_path
        if map_path is None:
            # default: sibling of the markers data file
            default = Path(__file__).resolve().parents[3] / "data" \
                / "knowledge_raw" / "auto_ambiguity_map.json"
            if default.exists():
                map_path = default
        if map_path and Path(map_path).exists():
            return MarkerDisambiguator.from_file(map_path, **kwargs)
        if self._manual_markers:
            return MarkerDisambiguator.from_markers(self._manual_markers, **kwargs)
        return MarkerDisambiguator({}, **kwargs)

    def _load_manual_markers(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Manual pathognomonic markers not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        markers = data.get("markers", [])
        for m in markers:
            for term in m.get("terms", []):
                t_lower = term.strip().lower()
                self._manual_term_index.setdefault(t_lower, []).append(m)
            for gene in m.get("gene_symbols", []):
                g_upper = gene.strip().upper()
                self._manual_term_index.setdefault(g_upper.lower(), []).append(m)
        self._manual_markers = markers
        logger.info(
            "Loaded %d manual pathognomonic markers (%d term variants)",
            len(markers), len(self._manual_term_index),
        )

    def _load_orphadata_markers(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Orphadata diagnostic markers not found: %s", path)
            return
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("entries", [])
        for e in entries:
            hpo_id = e.get("hpo_id", "")
            disease = e.get("disease", "").strip().lower()
            if hpo_id and disease:
                self._orphadata_hpo_disease.setdefault(hpo_id, {})[disease] = e
        self._orphadata_entries = entries
        n_pathog = sum(1 for e in entries if e.get("marker_type") == "pathognomonic")
        n_diag = sum(1 for e in entries if e.get("marker_type") == "diagnostic_criterion")
        logger.info(
            "Loaded %d Orphadata markers (%d pathognomonic, %d diagnostic criteria)",
            len(entries), n_pathog, n_diag,
        )

    @staticmethod
    def _exclusion_lr_for(marker: dict) -> float:
        """Graded reverse-exclusion LR+ (16.9 P0).

        Replaces the former hard-coded 0.15 with a confidence-tiered value, so a
        truly defining marker excludes competing diseases more strongly than a
        merely highly-specific one. A per-marker `exclusion_lr` override wins.
        Never returns 0 (an exclusion must not zero out a rare entity).
        """
        override = marker.get("exclusion_lr")
        if override is not None:
            return float(override)
        conf = marker.get("confidence", "")
        if conf == "pathognomonic":
            return 0.1
        if conf == "highly_specific":
            return 0.3
        return 0.15

    def lookup_manual(self, finding: str, disease: str) -> Optional[dict]:
        """Layer C: check hand-curated pathognomonic markers.

        Returns an LR-style entry dict if the finding matches a known marker.
        - If disease IS in target_diseases: returns high LR+ (pathognomonic hit).
        - If disease is in `compatible_diseases` (the marker is KNOWN to occur
          there): the exclusion signal is SUPPRESSED (this marker is skipped) to
          avoid falsely ruling out a valid differential (16.9 P0).
        - Otherwise: returns a graded exclusion LR+ (argues AGAINST the disease).

        A target hit always wins over an exclusion; exclusion fires only if no
        matched marker targets the disease and none gates it as compatible.
        """
        f_lower = finding.strip().lower()
        d_lower = disease.strip().lower()

        exclusion_marker: Optional[dict] = None

        for term, markers in self._manual_term_index.items():
            if _term_matches(term, f_lower, self._disambiguator):
                for m in markers:
                    target_diseases = [t.lower() for t in m.get("target_diseases", [])]
                    is_target = any(
                        td in d_lower or d_lower in td for td in target_diseases
                    )
                    if is_target:
                        # 16.9 Issue A: preserve the marker's own confidence
                        # tier. Formerly every target hit was hard-labeled
                        # "pathognomonic", overstating merely highly-specific
                        # markers (anti-CCP, smudge cells, JAK2, ...).
                        conf = m.get("confidence", "pathognomonic")
                        return {
                            "finding": finding,
                            "disease": disease,
                            "lr_positive": m.get("lr_positive"),
                            "lr_negative": m.get("lr_negative"),
                            "sensitivity": None,
                            "specificity": None,
                            "confidence": conf,
                            "source": f"manual_{conf}:{m.get('source', '')}",
                            "marker_type": conf,
                            "note": m.get("note", ""),
                        }
                    compatible = [c.lower() for c in m.get("compatible_diseases", [])]
                    is_compatible = any(
                        cd in d_lower or d_lower in cd for cd in compatible
                    )
                    if is_compatible:
                        # Marker is known to occur in this disease → not an
                        # exclusion signal; skip it (16.9 P0 gating).
                        continue
                    if exclusion_marker is None:
                        exclusion_marker = m

        if exclusion_marker is not None:
            m = exclusion_marker
            target_str = ", ".join(m.get("target_diseases", [])[:3])
            excl_lr = self._exclusion_lr_for(m)
            return {
                "finding": finding,
                "disease": disease,
                "lr_positive": excl_lr,
                "lr_negative": None,
                "sensitivity": None,
                "specificity": None,
                "confidence": "pathognomonic_exclusion",
                "source": f"manual_pathognomonic_exclusion:{m.get('source', '')}",
                "marker_type": "pathognomonic_exclusion",
                "note": (
                    f"This marker is pathognomonic for [{target_str}], "
                    f"not {disease}. Its presence argues against {disease} "
                    f"(graded exclusion LR+={excl_lr}; soft signal — confirm no "
                    f"cross-disease overlap before ruling out)."
                ),
            }
        return None

    def lookup_orphadata(
        self, hpo_id: str, disease: str
    ) -> Optional[dict]:
        """Layer A: check Orphadata pathognomonic signs and diagnostic criteria.

        Requires an HPO ID (e.g. 'HP:0025508') and disease name.
        If the HPO is pathognomonic for a DIFFERENT disease, returns an exclusion signal.
        """
        if not hpo_id:
            return None
        disease_map = self._orphadata_hpo_disease.get(hpo_id)
        if not disease_map:
            return None

        d_lower = disease.strip().lower()
        entry = disease_map.get(d_lower)
        if not entry:
            for cached_disease, e in disease_map.items():
                if d_lower in cached_disease or cached_disease in d_lower:
                    entry = e
                    break

        if entry:
            marker_type = entry.get("marker_type", "diagnostic_criterion")
            lr_pos = entry.get("lr_positive")
            if marker_type == "pathognomonic" and lr_pos is None:
                lr_pos = 100.0
            return {
                "finding": entry.get("hpo_term", ""),
                "disease": disease,
                "hpo_id": hpo_id,
                "lr_positive": lr_pos,
                "lr_negative": entry.get("lr_negative"),
                "sensitivity": None,
                "specificity": None,
                "confidence": marker_type,
                "source": f"orphadata_{marker_type}:ORPHA{entry.get('orpha_code', '')}",
                "frequency": entry.get("frequency", ""),
                "marker_type": marker_type,
            }

        pathog_for = [
            e.get("disease", "")
            for e in disease_map.values()
            if e.get("marker_type") == "pathognomonic"
        ]
        if pathog_for:
            target_str = ", ".join(pathog_for[:3])
            hpo_term = next(
                (e.get("hpo_term", "") for e in disease_map.values()), ""
            )
            return {
                "finding": hpo_term,
                "disease": disease,
                "hpo_id": hpo_id,
                "lr_positive": 0.1,
                "lr_negative": None,
                "sensitivity": None,
                "specificity": None,
                "confidence": "pathognomonic_exclusion",
                "source": "orphadata_pathognomonic_exclusion",
                "marker_type": "pathognomonic_exclusion",
                "note": (
                    f"This HPO ({hpo_id}) is pathognomonic for [{target_str}], "
                    f"not {disease}. Soft exclusion signal (LR+=0.1) — confirm "
                    f"no cross-disease overlap before ruling out."
                ),
            }
        return None

    def lookup_gene_disease(
        self, finding: str, disease: str
    ) -> Optional[dict]:
        """Layer B: check PrimeKG gene-disease associations.

        Extracts gene symbols from the finding text and checks if any are
        associated with the disease in PrimeKG.
        """
        if not self._primekg or not hasattr(self._primekg, "check_gene_disease_link"):
            return None

        gene_candidates = _GENE_PATTERN.findall(finding.upper())
        if not gene_candidates:
            return None

        best_result = None
        best_specificity = 0.0

        for gene in gene_candidates:
            if len(gene) < 2:
                continue
            link = self._primekg.check_gene_disease_link(gene, disease)
            if link and link["specificity"] > best_specificity:
                best_specificity = link["specificity"]
                best_result = link

        if not best_result:
            return None

        spec = best_result["specificity"]
        if spec >= 0.5:
            lr_pos = 50.0 * spec
        elif spec >= 0.1:
            lr_pos = 10.0 * spec
        else:
            lr_pos = 2.0

        return {
            "finding": finding,
            "disease": disease,
            "gene_symbol": best_result["gene"],
            "lr_positive": round(lr_pos, 1),
            "lr_negative": None,
            "sensitivity": None,
            "specificity": None,
            "confidence": "gene_association",
            "source": f"primekg_gene:{best_result['gene']}",
            "gene_specificity": round(spec, 4),
            "marker_type": "gene_association",
        }

    def lookup(
        self,
        finding: str,
        disease: str,
        hpo_id: str = "",
    ) -> Optional[dict]:
        """Full cascade: Layer C → Layer A → Layer B.

        Returns the highest-confidence match or None.
        """
        result = self.lookup_manual(finding, disease)
        if result:
            return result

        if hpo_id:
            result = self.lookup_orphadata(hpo_id, disease)
            if result:
                return result

        result = self.lookup_gene_disease(finding, disease)
        if result:
            return result

        return None

    @property
    def manual_marker_count(self) -> int:
        return len(self._manual_markers)

    @property
    def orphadata_entry_count(self) -> int:
        return len(self._orphadata_entries)

    @property
    def has_gene_lookup(self) -> bool:
        return self._primekg is not None and hasattr(
            self._primekg, "check_gene_disease_link"
        )
