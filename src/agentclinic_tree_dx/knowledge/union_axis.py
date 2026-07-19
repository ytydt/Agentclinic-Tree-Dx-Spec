"""§31.13.18 — A∪C union axis map (BranchCreator automation, recommended mode).

``UnionAxisMap`` is a drop-in ``SyndromeAxisMap`` whose L1 axis/domain partition
comes from the UNION of two automated sources, while syndrome RECOGNITION reuses
the hand map's keyword matcher (the proven, small detection layer):

  A) LLM-built ``branch_knowledge`` entries, generated offline by
     ``GuidelineBranchSource.build_branch_knowledge_llm`` and cached per
     space-normalised syndrome key in ``llm_axis_cache_json``. The LLM does the
     clinical grouping SNOMED ``is_a`` cannot (mechanism/anatomy-phrased golds:
     adhesions / peliosis / foreign body / glucagonoma / pancoast).
  C) Curated mandatory-floor seeds in ``override_seeds_json`` — a few domains
     per hard syndrome that pin the standard differential (the hand map's
     退化 form), guaranteeing the gold family is never structurally missing.

The two are merged at the DOMAIN level: the curated seed (C) supplies the
authoritative skeleton + mandatory flags; LLM (A) entities are folded into the
best-overlapping C domain, and any A domain that matches no C domain is appended
(additive — a recalled family is never dropped). When neither A nor C knows the
syndrome, ``match`` returns the hand map's own entry, so coverage NEVER regresses
below the hand baseline.

§31.13.17 isolated eval: A∪C reached 100% gold-domain coverage with 0 axis
errors on the 8-case text set (= hand map), vs 0% for pure SNOMED auto.

Emits the SAME entry shape as ``SyndromeAxisMap`` (``domains[].member_keywords``
/ ``split_variants``), so the inherited ``domain_names`` / ``project_entity`` /
``_partition`` and the whole downstream ``_build_branch_candidates`` →
``_enforce_mandatory_branches`` contract work unchanged. Every optimisation flag
keeps working.

Deterministic in the hot path (cache + seeds only). Live LLM generation is
opt-in (``branch_llm_axis_live``) and write-through to the cache.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .syndrome_axis import SyndromeAxisMap

logger = logging.getLogger(__name__)


def _toks(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 3}


def _domain_keywords(name: str, entities: list[str]) -> list[str]:
    """member_keywords drive project_entity: full entity names + their tokens +
    the domain-name tokens."""
    kws: set[str] = {name.strip().lower()} if name else set()
    for e in entities:
        el = str(e).strip().lower()
        if not el:
            continue
        kws.add(el)
        kws.update(_toks(el))
    kws.update(_toks(name))
    return sorted(k for k in kws if k)


class UnionAxisMap(SyndromeAxisMap):
    """Hand-map syndrome detection + (LLM-cache ∪ curated-seed) partition."""

    def __init__(
        self,
        detector: SyndromeAxisMap,
        *,
        llm_cache: dict | None = None,
        override_seeds: dict | None = None,
        llm_cache_path: Optional[str] = None,
        # live generation (opt-in)
        llm_source=None,          # GuidelineBranchSource
        llm_client=None,
        enable_phase_subaxis: bool = False,
        overlap_min: int = 1,
    ) -> None:
        super().__init__([], fallback_axis=detector._fallback_axis)
        self._detector = detector
        self._llm_cache: dict[str, dict] = dict(llm_cache or {})
        self._llm_cache_path = llm_cache_path
        self._seeds: dict[str, dict] = ((override_seeds or {}).get("syndromes", {})
                                        if override_seeds else {})
        self._llm_source = llm_source
        self._llm_client = llm_client
        self._enable_phase = enable_phase_subaxis
        self._overlap_min = overlap_min
        self._entry_cache: dict[str, dict] = {}
        logger.info("UnionAxisMap ready: A-cache=%d syndromes, C-seeds=%d "
                    "syndromes, live=%s", len(self._llm_cache), len(self._seeds),
                    bool(llm_source and llm_client))

    # ----------------------------------------------------------------- loaders
    @classmethod
    def from_files(
        cls,
        syndrome_axis_map_json: str | Path,
        *,
        llm_axis_cache_json: str | Path | None = None,
        override_seeds_json: str | Path | None = None,
        **kw,
    ) -> "UnionAxisMap":
        det = SyndromeAxisMap.from_file(syndrome_axis_map_json)

        def _load(p):
            if p and Path(p).exists():
                try:
                    return json.loads(Path(p).read_text(encoding="utf-8"))
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("UnionAxisMap: failed to load %s (%s)", p, e)
            return {}
        return cls(
            det,
            llm_cache=_load(llm_axis_cache_json),
            override_seeds=_load(override_seeds_json),
            llm_cache_path=str(llm_axis_cache_json) if llm_axis_cache_json else None,
            **kw,
        )

    # ------------------------------------------------------- C: seed → entry
    def _seed_entry(self, syn_key: str, seed: dict) -> dict:
        domains, mandatory = [], []
        for d in seed.get("domains", []):
            name = str(d.get("name", "")).strip()
            ents = [str(e).strip().lower() for e in (d.get("entities") or [])
                    if str(e).strip()]
            if not name or not ents:
                continue
            dom = {"name": name, "member_keywords": _domain_keywords(name, ents),
                   "_entities": ents, "_mandatory": bool(d.get("mandatory"))}
            domains.append(dom)
            if d.get("mandatory"):
                mandatory.append(name)
        return {"id": syn_key, "axis": seed.get("axis", "mechanism"),
                "axis_rationale": "§31.13.18 curated mandatory-floor seed (C)",
                "domains": domains, "mandatory_coverage": mandatory,
                "syndrome_keywords": [syn_key]}

    # --------------------------------------------------------- A: cache lookup
    def _llm_entry(self, syn_key: str, text: str) -> Optional[dict]:
        entry = self._llm_cache.get(syn_key)
        if entry is not None:
            return entry
        # opt-in live generation (write-through)
        if self._llm_source is not None and self._llm_client is not None:
            try:
                entry = self._llm_source.build_branch_knowledge_llm(
                    syn_key, self._llm_client, context=text,
                    cache_path=self._llm_cache_path)
            except Exception as e:  # pragma: no cover - network/LLM defensive
                logger.warning("UnionAxisMap live LLM-axis failed for '%s': %s",
                               syn_key, e)
                return None
            if entry and entry.get("domains"):
                self._llm_cache[syn_key] = entry
                return entry
        return None

    # ------------------------------------------------------------- union merge
    @staticmethod
    def _entity_set(dom: dict) -> set[str]:
        ents = {str(e).lower() for e in (dom.get("_entities") or [])}
        # fall back to multi-word member_keywords as entity proxies
        if not ents:
            ents = {k.lower() for k in (dom.get("member_keywords") or [])
                    if " " in k}
        return ents

    def _merge(self, a_entry: Optional[dict], c_entry: Optional[dict]) -> Optional[dict]:
        """C is the authoritative skeleton; fold A entities into the best
        overlapping C domain; append A domains that match no C domain."""
        if c_entry is None and a_entry is None:
            return None
        if c_entry is None:
            return a_entry
        if a_entry is None:
            return c_entry

        domains = [dict(d) for d in c_entry.get("domains", [])]
        c_ent_sets = [self._entity_set(d) for d in domains]
        # token-sets of every CURATED entity → C placement is authoritative; an
        # appended A domain must not steal an entity the seed already owns (even
        # under a longer, more verbose phrasing that would win longest-keyword).
        c_owned_toks = [_toks(e) for s in c_ent_sets for e in s if _toks(e)]

        def _curated_owns(ae: str) -> bool:
            at = _toks(ae)
            return bool(at) and any(ct <= at for ct in c_owned_toks)

        for ad in a_entry.get("domains", []):
            a_ents = self._entity_set(ad)
            # find the C domain with the largest entity overlap
            best_i, best_ov = -1, 0
            for i, cs in enumerate(c_ent_sets):
                ov = len(a_ents & cs)
                if ov > best_ov:
                    best_i, best_ov = i, ov
            if best_i >= 0 and best_ov >= self._overlap_min:
                # merge A entities into the matched C domain (additive)
                merged_ents = list(dict.fromkeys(
                    list(domains[best_i].get("_entities", [])) + sorted(a_ents)))
                domains[best_i]["_entities"] = merged_ents
                domains[best_i]["member_keywords"] = _domain_keywords(
                    domains[best_i]["name"], merged_ents)
                c_ent_sets[best_i] = self._entity_set(domains[best_i])
            else:
                # A domain with no C counterpart → append (never drop a family),
                # but strip entities a curated seed already places elsewhere so
                # C keeps projection precedence over A's verbose phrasings.
                kept = [e for e in sorted(a_ents) if not _curated_owns(e)]
                if not kept:
                    continue
                new_dom = dict(ad)
                new_dom["_entities"] = kept
                new_dom["member_keywords"] = _domain_keywords(
                    new_dom.get("name", ""), kept)
                domains.append(new_dom)
                c_ent_sets.append(self._entity_set(new_dom))

        mandatory = list(c_entry.get("mandatory_coverage", []))
        for ad in a_entry.get("domains", []):
            if ad.get("_mandatory") or ad.get("mandatory"):
                nm = ad.get("name", "")
                if nm and nm not in mandatory:
                    mandatory.append(nm)
        return {
            "id": c_entry.get("id") or a_entry.get("id", ""),
            "axis": c_entry.get("axis") or a_entry.get("axis", "mechanism"),
            "axis_rationale": ("§31.13.18 A∪C union: curated floor (C) ∪ "
                               "LLM-built partition (A)"),
            "domains": domains,
            "mandatory_coverage": mandatory,
            "syndrome_keywords": c_entry.get("syndrome_keywords", []),
        }

    # --------------------------------------------------------------- core match
    def match(self, text: str) -> dict:  # type: ignore[override]
        key = (text or "")[:400]
        if key in self._entry_cache:
            return self._entry_cache[key]
        det_entry = self._detector.match(text)
        syn_id = (det_entry.get("id", "") or "")
        syn_key = syn_id.replace("_", " ").lower()

        a_entry = self._llm_entry(syn_key, text) if syn_key else None
        seed = self._seeds.get(syn_key)
        c_entry = self._seed_entry(syn_key, seed) if seed else None

        merged = self._merge(a_entry, c_entry)
        # Never regress below the hand map: if A∪C produced nothing usable, use
        # the detector's own partition.
        if not merged or not merged.get("domains"):
            merged = det_entry
        self._entry_cache[key] = merged
        return merged
