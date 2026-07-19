"""HPO Ontology Index: synonym resolution + is_a hierarchy for directional matching.

Parses hp.obo to build:
  1. text → HPO ID mapping (canonical names + all synonyms)
  2. Ancestor / descendant sets for each HPO term (from is_a edges)
  3. Subsumption API with strict syllogistic direction enforcement

Syllogistic constraints (大前提/小前提不可倒置):

  VALID (upward / patient_specific → cache_broad):
    Major premise:  Disease D → F_broad   (from LR cache)
    Minor premise:  F_specific IS-A F_broad (from HPO ontology)
    Conclusion:     D can manifest F_specific ✓
    LR effect:      Attenuate by depth penalty (narrower finding = less certain)

  INVALID (downward / patient_broad → cache_specific):
    Cache:   D → F_specific (e.g. retinal hemorrhage)
    Patient: F_broad (e.g. visual disturbance)
    Conclusion: CANNOT inherit LR — at best qualitative hint
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HPOIndex:
    """In-memory index of HPO ontology terms, synonyms, and hierarchy."""

    def __init__(self) -> None:
        self._terms: dict[str, dict] = {}
        self._text_to_hpo: dict[str, str] = {}
        self._parents: dict[str, list[str]] = {}
        self._children: dict[str, list[str]] = {}
        self._ancestor_cache: dict[str, frozenset[str]] = {}

    @classmethod
    def from_obo(cls, obo_path: str | Path) -> "HPOIndex":
        idx = cls()
        path = Path(obo_path)
        if not path.exists():
            logger.warning("HPO obo not found at %s", path)
            return idx

        current_id: Optional[str] = None
        current: dict = {}
        obsolete = False

        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line == "[Term]":
                    if current_id and not obsolete:
                        idx._terms[current_id] = current
                    current_id = None
                    current = {"name": "", "synonyms": [], "is_a": []}
                    obsolete = False
                elif line.startswith("[Typedef]"):
                    if current_id and not obsolete:
                        idx._terms[current_id] = current
                    current_id = None
                elif line.startswith("id: HP:") and current_id is None:
                    current_id = line.split("id: ")[1].strip()
                elif line.startswith("name: "):
                    current["name"] = line[6:].strip()
                elif line.startswith("synonym: ") and '"' in line:
                    syn_text = line.split('"')[1]
                    current["synonyms"].append(syn_text)
                elif line.startswith("is_a: HP:"):
                    parent = line.split("is_a: ")[1].split(" !")[0].strip()
                    current["is_a"].append(parent)
                elif line.startswith("alt_id: HP:"):
                    alt = line.split("alt_id: ")[1].strip()
                    current.setdefault("alt_ids", []).append(alt)
                elif line == "is_obsolete: true":
                    obsolete = True

            if current_id and not obsolete:
                idx._terms[current_id] = current

        idx._build_indices()
        logger.info(
            "HPOIndex: %d terms, %d text→HPO mappings",
            len(idx._terms), len(idx._text_to_hpo),
        )
        return idx

    def _build_indices(self) -> None:
        for hpo_id, term in self._terms.items():
            name_lower = term["name"].lower().strip()
            if name_lower:
                self._text_to_hpo[name_lower] = hpo_id
            for syn in term["synonyms"]:
                sl = syn.lower().strip()
                if sl and sl not in self._text_to_hpo:
                    self._text_to_hpo[sl] = hpo_id
            for alt in term.get("alt_ids", []):
                if alt not in self._terms:
                    self._text_to_hpo[alt] = hpo_id

            for parent in term["is_a"]:
                self._parents.setdefault(hpo_id, []).append(parent)
                self._children.setdefault(parent, []).append(hpo_id)

    def resolve(self, text: str) -> Optional[str]:
        """Map free text to HPO ID via exact name/synonym match."""
        return self._text_to_hpo.get(text.strip().lower())

    def resolve_fuzzy(self, text: str) -> Optional[str]:
        """Map free text to HPO ID with substring fallback."""
        exact = self.resolve(text)
        if exact:
            return exact
        tl = text.strip().lower()
        for cached_text, hpo_id in self._text_to_hpo.items():
            if tl in cached_text or cached_text in tl:
                return hpo_id
        return None

    def get_name(self, hpo_id: str) -> str:
        t = self._terms.get(hpo_id)
        return t["name"] if t else ""

    def get_ancestors(self, hpo_id: str) -> frozenset[str]:
        """All transitive ancestors (excluding self) via is_a edges."""
        if hpo_id in self._ancestor_cache:
            return self._ancestor_cache[hpo_id]
        ancestors: set[str] = set()
        frontier = list(self._parents.get(hpo_id, []))
        while frontier:
            p = frontier.pop()
            if p not in ancestors:
                ancestors.add(p)
                frontier.extend(self._parents.get(p, []))
        result = frozenset(ancestors)
        self._ancestor_cache[hpo_id] = result
        return result

    def is_ancestor_of(self, ancestor_id: str, descendant_id: str) -> bool:
        """Check if ancestor_id is a transitive ancestor of descendant_id."""
        if ancestor_id == descendant_id:
            return False
        return ancestor_id in self.get_ancestors(descendant_id)

    def subsumption_depth(self, ancestor_id: str, descendant_id: str) -> int:
        """Minimum number of is_a hops from descendant to ancestor.

        Returns -1 if not an ancestor.
        """
        if ancestor_id == descendant_id:
            return 0
        if ancestor_id not in self.get_ancestors(descendant_id):
            return -1
        visited: set[str] = set()
        frontier = [(descendant_id, 0)]
        while frontier:
            node, depth = frontier.pop(0)
            if node == ancestor_id:
                return depth
            if node in visited:
                continue
            visited.add(node)
            for p in self._parents.get(node, []):
                frontier.append((p, depth + 1))
        return -1

    def classify_match(
        self, patient_finding: str, cache_finding: str
    ) -> dict:
        """Classify the ontological relationship between a patient finding and a cache finding.

        Returns a dict with:
          direction: "exact" | "upward" | "downward" | "sibling" | "unrelated"
          patient_hpo: HPO ID or None
          cache_hpo: HPO ID or None
          depth: hop count (for upward/downward)
          attenuation: log-space shrink EXPONENT for the LR, NOT a linear
            multiplier. The consumer applies it as ``LR_out = LR_in ** attn``
            (see LRRetriever._attenuate_entry), which shrinks the LR toward the
            neutral point 1.0 in log space — symmetric for LR>1 and LR<1. attn
            ∈ (0,1]: 1.0 = exact (no shrink); <1.0 = upward (partial shrink);
            0.0 here is a SENTINEL meaning "do not transfer this LR" (downward/
            sibling/unrelated are filtered out upstream and never reach
            _attenuate_entry) — it is NOT applied as ``LR * 0`` (that would
            wrongly drive the LR to 0). CAUTION: do not treat attn as a linear
            multiplier; ``LR * attn`` would push an exclusionary LR<1 AWAY from
            1.0 (strengthening the rule-out), the opposite of the intended
            "less reliable ⇒ weaker effect" semantics.

        Syllogistic rules:
          - "upward": patient is MORE SPECIFIC than cache → VALID, LR attenuated
          - "downward": patient is MORE GENERAL than cache → INVALID for LR
        """
        p_hpo = self.resolve_fuzzy(patient_finding)
        c_hpo = self.resolve_fuzzy(cache_finding)

        base = {
            "patient_hpo": p_hpo,
            "cache_hpo": c_hpo,
            "patient_finding": patient_finding,
            "cache_finding": cache_finding,
        }

        if not p_hpo or not c_hpo:
            return {**base, "direction": "unrelated", "depth": -1, "attenuation": 0.0}

        if p_hpo == c_hpo:
            return {**base, "direction": "exact", "depth": 0, "attenuation": 1.0}

        depth_up = self.subsumption_depth(c_hpo, p_hpo)
        if depth_up > 0:
            attn = max(0.3, 1.0 - 0.2 * depth_up)
            return {**base, "direction": "upward", "depth": depth_up, "attenuation": attn}

        depth_down = self.subsumption_depth(p_hpo, c_hpo)
        if depth_down > 0:
            return {**base, "direction": "downward", "depth": depth_down, "attenuation": 0.0}

        p_anc = self.get_ancestors(p_hpo)
        c_anc = self.get_ancestors(c_hpo)
        shared = p_anc & c_anc
        if shared:
            return {**base, "direction": "sibling", "depth": -1, "attenuation": 0.0}

        return {**base, "direction": "unrelated", "depth": -1, "attenuation": 0.0}

    @property
    def term_count(self) -> int:
        return len(self._terms)

    @property
    def synonym_count(self) -> int:
        return len(self._text_to_hpo)
