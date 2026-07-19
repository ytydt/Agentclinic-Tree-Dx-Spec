"""§23.14 Step-0: deterministic syndrome → L1 classification-axis selection.

Loads ``syndrome_axis_map.json`` (see data/knowledge_raw) and provides:
  - ``match(text)``   : pick the syndrome entry for a vignette (longest-keyword
                        substring match; falls back to the 'undifferentiated'
                        entry whose axis is the configured fallback, mechanism).
  - ``project_entity``: project a disease entity onto a syndrome's MECE
                        single-axis L1 domain partition via member_keywords.

Pure / deterministic: identical input → identical output. No LLM, no network.
This is the production form of scripts/probe_axis_recall.py (§24.2).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SyndromeAxisMap:
    def __init__(self, syndromes: list[dict], fallback_axis: str = "mechanism") -> None:
        self._syndromes = syndromes
        self._fallback_axis = fallback_axis
        self._fallback_entry = next(
            (e for e in syndromes if e.get("id") == "undifferentiated"),
            {"id": "undifferentiated", "axis": fallback_axis, "domains": [],
             "syndrome_keywords": [], "axis_rationale": "fallback"},
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "SyndromeAxisMap":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        syndromes = raw.get("syndromes", [])
        fallback = raw.get("metadata", {}).get("fallback_axis", "mechanism")
        logger.info("SyndromeAxisMap loaded: %d syndrome classes", len(syndromes))
        return cls(syndromes, fallback_axis=fallback)

    def match(self, text: str) -> dict:
        """Return the best syndrome entry for ``text`` (longest keyword wins)."""
        tl = (text or "").lower()
        best, best_len = None, -1
        for entry in self._syndromes:
            for kw in entry.get("syndrome_keywords", []):
                k = (kw or "").lower()
                if k and k in tl and len(k) > best_len:
                    best, best_len = entry, len(k)
        return best if best is not None else self._fallback_entry

    @staticmethod
    def _partition(entry: dict, split: bool) -> list[dict]:
        """Return the effective L1 domain partition.

        §27.2 fix (ADDITIVE, was REPLACE): when ``split`` is True, a domain
        carrying ``split_variants`` is KEPT as the broad parent AND its variants
        are ADDED alongside it — NOT replaced by them. The old replace semantics
        narrowed the parent (e.g. "Chronic Myeloproliferative Neoplasm" →
        "(chronic phase, low blasts)"), which EJECTED blast-crisis CML from the
        gold entity's only home branch and routed a 35%-blast CML to the myeloid-
        blast branch (→AML). Keeping the broad parent guarantees the gold entity
        always has a home, while the variants add the opposite-direction
        can't-miss subset (e.g. blast crisis). Entity projection
        (longest-keyword-wins) still routes a specific blast-crisis entity to the
        variant; generic/chronic entities stay in the parent. When False, only
        the original lumped domain is used (legacy)."""
        out: list[dict] = []
        for dom in entry.get("domains", []):
            variants = dom.get("split_variants") if split else None
            out.append(dom)
            if variants:
                # additive: keep parent (already appended) + add variants whose
                # key-finding LR direction opposes it.
                out.extend(variants)
        return out

    @staticmethod
    def project_entity(entity: str, entry: dict, split: bool = False) -> Optional[str]:
        """Project a disease entity onto the entry's L1 domain partition.

        Returns the domain name whose member_keywords match the entity, else
        None (entity falls outside the partition — left for the residual/other).
        """
        el = (entity or "").strip().lower()
        if not el:
            return None
        # Longest-keyword-wins (mirrors match()) so a short, generic keyword in
        # one domain (e.g. "blast") never out-grabs a more specific keyword in
        # another (e.g. "lymphoblastic"); resolves overlap deterministically.
        best_name, best_len = None, -1
        for dom in SyndromeAxisMap._partition(entry, split):
            for kw in dom.get("member_keywords", []):
                k = (kw or "").lower()
                if k and (k in el or el in k) and len(k) > best_len:
                    best_name, best_len = dom.get("name"), len(k)
        return best_name

    @staticmethod
    def domain_names(entry: dict, split: bool = False) -> list[str]:
        return [d.get("name", "") for d in SyndromeAxisMap._partition(entry, split)
                if d.get("name")]
