"""Unified DxFeatureRetriever: routes queries through Layer 0 → Layer 1 → Layer 2 → Layer 3.

Layer 0: DxDiscriminatorIndex (DiagRL-Corpus flat set differences)
Layer 1: PrimeKGIndex (HPO-based KG with negative edges, disease relations)
Layer 2: LRRetriever (structured LR cache)
Layer 3: RAG fallback — three sub-layers:
  3a. StatPearls/Textbooks FAISS vector search (RAGRetriever)
  3b. PubMed E-utilities live search (PubMedRetriever)
  3c. LLM ChainDiscoverer (indirect reasoning chain generation)

Disease name resolution via DiseaseNameResolver handles the critical mismatch
between TALP branch labels and knowledge source index keys.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from .disease_name_resolver import DiseaseNameResolver
from .dx_discriminator_index import DxDiscriminatorIndex
from .evidence_matcher import EvidenceMatcher
from .lr_retriever import LRRetriever
from .primekg_index import PrimeKGIndex

if TYPE_CHECKING:
    from .diagnostic_marker_index import DiagnosticMarkerIndex
    from .finding_normalizer import FindingNormalizer
    from .rag_retriever import RAGRetriever
    from .pubmed_retriever import PubMedRetriever

logger = logging.getLogger(__name__)


def ebm_lr_band(lr_positive: Any = None, lr_negative: Any = None) -> str:
    """Map a likelihood ratio to its evidence-based-medicine strength band.

    16.9 P1: provides a deterministic, literature-grounded anchor (Jaeschke 1994 /
    McGee 2002) so the LLM annotator does not have to invent the LR→strength
    mapping itself. Returned as an advisory hint that pairs a qualitative band
    with the suggested ordinal label; the LLM remains free to override using the
    clinical note. Returns "" when no usable LR is present.
    """

    def _band_for_positive(lr: float) -> str:
        if lr >= 10:
            return "large/conclusive increase → suggests strong_for"
        if lr >= 5:
            return "moderate increase → suggests moderate_for"
        if lr >= 2:
            return "small increase → suggests weak_for"
        if lr > 1:
            return "minimal increase → suggests neutral/weak_for"
        if lr == 1:
            return "no change → neutral"
        if lr > 0.5:
            return "minimal decrease → suggests neutral/weak_against"
        if lr > 0.2:
            return "small decrease → suggests weak_against"
        if lr > 0.1:
            return "moderate decrease → suggests moderate_against"
        return "large/conclusive decrease → suggests strong_against"

    try:
        if lr_positive is not None:
            return _band_for_positive(float(lr_positive))
    except (TypeError, ValueError):
        pass

    try:
        if lr_negative is not None:
            lr = float(lr_negative)
            if lr <= 0.1:
                return "absence strongly argues against (LR- ≤0.1)"
            if lr <= 0.2:
                return "absence moderately argues against (LR- ≤0.2)"
            if lr <= 0.5:
                return "absence mildly argues against (LR- ≤0.5)"
            return "absence weakly informative (LR- >0.5)"
    except (TypeError, ValueError):
        pass

    return ""


class DxFeatureRetriever:
    """Orchestrates knowledge retrieval across all layers.

    Provides three main query types:
    1. discriminator_hints: For TALP — "what differentiates disease A from B?"
    2. lr_reference: For EvidenceAnnotator — "what is the LR of finding X for disease Y?"
    3. indirect_chains: For TALP — "what intermediate concepts link finding X to disease Y?"
    """

    def __init__(
        self,
        dxs_index: Optional[DxDiscriminatorIndex] = None,
        primekg_index: Optional[PrimeKGIndex] = None,
        lr_retriever: Optional[LRRetriever] = None,
        evidence_matcher: Optional[EvidenceMatcher] = None,
        name_resolver: Optional[DiseaseNameResolver] = None,
        chain_discoverer_fn: Optional[Callable[..., dict[str, Any]]] = None,
        rag_retriever: Optional["RAGRetriever"] = None,
        pubmed_retriever: Optional["PubMedRetriever"] = None,
        diagnostic_marker_index: Optional["DiagnosticMarkerIndex"] = None,
        finding_normalizer: Optional["FindingNormalizer"] = None,
        snomed_index: Optional["SnomedIndex"] = None,
        secondary_lr_cache: Optional["SecondaryLRCache"] = None,
    ) -> None:
        self.dxs = dxs_index
        self.primekg = primekg_index
        self.lr = lr_retriever
        self.matcher = evidence_matcher
        self.resolver = name_resolver or DiseaseNameResolver()
        self._chain_discoverer_fn = chain_discoverer_fn
        self.rag = rag_retriever
        self.pubmed = pubmed_retriever
        self.diagnostic_markers = diagnostic_marker_index
        self.finding_normalizer = finding_normalizer
        self.snomed = snomed_index
        self.secondary_lr_cache = secondary_lr_cache
        # §25.2(#3): when True, a LOW-confidence cache hit (HPO subsumption /
        # context-only) does NOT short-circuit RAG; RAG is allowed to override
        # it with a higher-confidence numeric LR. Default False = strict tier
        # order (any cache hit blocks RAG).
        self._confidence_gated_cascade: bool = False

        self._register_sources()

    def _snomed_disease_aliases(self, disease: str) -> list[str]:
        """SNOMED synonym surface forms for *disease* (vocabulary bridging)."""
        if not self.snomed:
            return []
        try:
            return self.snomed.expand_synonyms(disease, max_terms=8)
        except Exception:
            return []

    def _register_sources(self) -> None:
        """Register all available knowledge source disease vocabularies."""
        if self.dxs:
            self.resolver.register_source(
                "dxs", list(self.dxs._disease_phenotypes.keys())
            )
        if self.primekg:
            self.resolver.register_source(
                "primekg", list(self.primekg._disease_ids.keys())
            )
        if self.lr:
            self.resolver.register_source(
                "lr", list(self.lr._disease_index.keys())
            )

    def _resolve_disease(self, label: str, source: str) -> Optional[str]:
        """Resolve a TALP label to a source-specific key."""
        return self.resolver.resolve(label, source)

    def _resolve_for_all(self, label: str) -> dict[str, Optional[str]]:
        """Resolve a label against all registered sources."""
        return self.resolver.resolve_all_sources(label)

    # ------------------------------------------------------------------
    # TALP query: discriminator_hints
    # ------------------------------------------------------------------

    def get_discriminator_hints(
        self,
        diseases: list[str],
        *,
        seen_evidence: Optional[set[str]] = None,
        max_features_per_disease: int = 8,
    ) -> dict:
        """Generate discriminative feature hints for TALP.

        Uses DiseaseNameResolver to match TALP labels to source keys.
        """
        result: dict = {
            "pairwise": {},
            "unique_per_disease": {},
            "exclusion_features": {},
            "related_diseases": {},
            "layer_used": "none",
            "coverage_ratio": 0.0,
            "name_resolutions": {},
        }
        seen = seen_evidence or set()

        resolved_dxs: dict[str, str] = {}
        resolved_primekg: dict[str, str] = {}

        for d in diseases:
            dxs_key = self._resolve_disease(d, "dxs") if self.dxs else None
            pkg_key = self._resolve_disease(d, "primekg") if self.primekg else None
            if dxs_key:
                resolved_dxs[d] = dxs_key
            if pkg_key:
                resolved_primekg[d] = pkg_key
            result["name_resolutions"][d] = {
                "dxs": dxs_key,
                "primekg": pkg_key,
                "lr": self._resolve_disease(d, "lr") if self.lr else None,
            }

        # Layer 0: DxS discriminators
        dxs_phenos: dict[str, set[str]] = {}
        if self.dxs:
            for orig, key in resolved_dxs.items():
                ps = self.dxs.get_phenotypes(key)
                if ps:
                    dxs_phenos[orig] = ps

        # Layer 1: PrimeKG
        primekg_phenos: dict[str, set[str]] = {}
        if self.primekg:
            for orig, key in resolved_primekg.items():
                ps = self.primekg.get_positive_phenotypes(key)
                if ps:
                    primekg_phenos[orig] = ps
                neg = self.primekg.get_negative_phenotypes(key)
                if neg:
                    result["exclusion_features"][orig] = sorted(neg)[:max_features_per_disease]
                related = self.primekg.get_related_diseases(key)
                if related:
                    result["related_diseases"][orig] = sorted(related)[:5]

        # Merge: prefer DxS, supplement with PrimeKG
        merged: dict[str, set[str]] = {}
        for d in diseases:
            s = dxs_phenos.get(d, set()) | primekg_phenos.get(d, set())
            if s:
                merged[d] = s

        total = len(diseases)
        covered = len(merged)
        result["coverage_ratio"] = covered / total if total > 0 else 0.0

        found_dxs = len(dxs_phenos)
        found_primekg = len(primekg_phenos)
        if found_dxs > 0 and found_primekg > 0:
            result["layer_used"] = "both"
        elif found_dxs > 0:
            result["layer_used"] = "dxs"
        elif found_primekg > 0:
            result["layer_used"] = "primekg"

        # Pairwise discriminators
        disease_list = list(merged.keys())
        for i, da in enumerate(disease_list):
            for db in disease_list[i + 1:]:
                pa, pb = merged[da], merged[db]
                only_a = pa - pb - seen
                only_b = pb - pa - seen
                shared = pa & pb
                pair_key = f"{da} vs {db}"
                result["pairwise"][pair_key] = {
                    "only_a": sorted(only_a)[:max_features_per_disease],
                    "only_b": sorted(only_b)[:max_features_per_disease],
                    "shared_count": len(shared),
                }

        # Unique per disease (vs all others combined)
        for d in disease_list:
            others_union = set()
            for other, ps in merged.items():
                if other != d:
                    others_union |= ps
            unique = merged[d] - others_union - seen
            result["unique_per_disease"][d] = sorted(unique)[:max_features_per_disease]

        return result

    # ------------------------------------------------------------------
    # 2-hop reasoning chains via PrimeKG
    # ------------------------------------------------------------------

    def get_2hop_chains(
        self,
        unmatched_findings: list[str],
        diseases: list[str],
        *,
        max_depth: int = 2,
    ) -> list[dict]:
        """Find indirect paths: finding → intermediate phenotype → disease.

        For each unmatched finding, check if any PrimeKG phenotype reachable
        within max_depth hops overlaps with any disease's phenotype set.
        """
        if not self.primekg or not self.matcher:
            return []

        chains: list[dict] = []

        disease_phenos: dict[str, set[str]] = {}
        for d in diseases:
            key = self._resolve_disease(d, "primekg")
            if key:
                disease_phenos[d] = self.primekg.get_positive_phenotypes(key)

        if not disease_phenos:
            return []

        for finding in unmatched_findings:
            matched = self.matcher.match(finding, threshold=0.3, max_matches=3)
            if not matched:
                continue
            for m in matched:
                phenotype = m["phenotype"]
                reachable = self.primekg.phenotype_multihop(phenotype, max_depth=max_depth)
                for disease_label, d_phenos in disease_phenos.items():
                    overlaps = reachable & d_phenos
                    for intermediate in overlaps:
                        chains.append({
                            "finding": finding,
                            "matched_phenotype": phenotype,
                            "intermediate": intermediate,
                            "target_disease": disease_label,
                            "hop_count": max_depth,
                            "source": "primekg_multihop",
                        })

        return chains

    # ------------------------------------------------------------------
    # 2-hop LR estimation (for Annotator channel)
    # ------------------------------------------------------------------

    def get_2hop_lr(
        self,
        finding: str,
        diseases: list[str],
    ) -> list[dict]:
        """Compute estimated LR for 2-hop chains (finding → intermediate → disease).

        Uses Strategy B (cross-disease co-occurrence) for P(finding|intermediate)
        and chain decomposition for LR calculation.
        Returns results with confidence='indirect_chain'.
        """
        if not self.primekg or not self.lr:
            return []

        chains = self.primekg.find_2hop_chains(finding, diseases)
        results = []

        for chain in chains:
            intermediate = chain["intermediate"]
            disease = chain["target_disease"]
            chain_type = chain.get("chain_type", "phenotype")

            if chain_type == "disease_intermediate":
                inter_lr = self.lr.lookup_fuzzy(finding, intermediate) if self.lr else None
                sn_ev = inter_lr.get("sensitivity", 0.5) if inter_lr else 0.3
                try:
                    sn_ev = float(sn_ev) if sn_ev is not None else 0.3
                except (TypeError, ValueError):
                    sn_ev = 0.3
                lr_pos = round(sn_ev * 2.0, 3)
                lr_neg = round(max(1.0 - sn_ev, 0.3), 3)
                results.append({
                    "finding": finding,
                    "disease": disease,
                    "chain": [finding, f"[disease]{intermediate}", disease],
                    "hops": 2,
                    "lr_positive": lr_pos,
                    "lr_negative": lr_neg,
                    "confidence": "disease_bridge_chain",
                    "source": f"PrimeKG disease-bridge via {intermediate}",
                    "intermediate_disease_count": chain.get("intermediate_disease_count", 0),
                })
                continue

            inter_entry = self.lr.lookup_fuzzy(intermediate, disease)
            if not inter_entry:
                continue

            # Entries may carry an explicit null sensitivity/specificity; coerce
            # to safe defaults so the chain math never sees None.
            try:
                sn_intermediate = float(inter_entry.get("sensitivity") or 0.0)
            except (TypeError, ValueError):
                sn_intermediate = 0.0
            try:
                sp_intermediate = float(inter_entry.get("specificity") or 0.9)
            except (TypeError, ValueError):
                sp_intermediate = 0.9

            if sn_intermediate <= 0:
                continue

            p_e_given_m = self._estimate_conditional(finding, intermediate)

            sn_chain = p_e_given_m * sn_intermediate
            sp_chain = sp_intermediate

            lr_pos = sn_chain / (1 - sp_chain) if sp_chain < 1.0 else None
            lr_neg = (1 - sn_chain) / sp_chain if sp_chain > 0 else None

            results.append({
                "finding": finding,
                "disease": disease,
                "chain": [finding, intermediate, disease],
                "hops": 2,
                "p_evidence_given_intermediate": round(p_e_given_m, 3),
                "intermediate_sensitivity": round(sn_intermediate, 4),
                "sensitivity_chain": round(sn_chain, 4),
                "specificity_chain": round(sp_chain, 4),
                "lr_positive": round(lr_pos, 3) if lr_pos is not None else None,
                "lr_negative": round(lr_neg, 3) if lr_neg is not None else None,
                "confidence": "indirect_chain",
                "source": f"PrimeKG 2-hop via {intermediate}",
                "intermediate_disease_count": chain.get("intermediate_disease_count", 0),
            })

        results.sort(key=lambda r: r.get("lr_positive") or 0, reverse=True)
        return results

    def _estimate_conditional(self, evidence: str, intermediate: str) -> float:
        """Strategy B: Cross-disease co-occurrence rate to estimate P(evidence|intermediate).

        Counts how many diseases that have the intermediate phenotype also have the
        evidence phenotype, using the unified LR cache.
        """
        _DEFAULT = 0.3

        if not self.lr:
            return _DEFAULT

        inter_entries = self.lr.lookup_by_finding(intermediate)
        if not inter_entries:
            return _DEFAULT

        inter_diseases = {e["disease"].strip().lower() for e in inter_entries}
        if not inter_diseases:
            return _DEFAULT

        co_occur = sum(
            1 for d in inter_diseases
            if self.lr.lookup_fuzzy(evidence, d)
        )
        estimated = co_occur / len(inter_diseases)

        return max(estimated, 0.1)

    # ------------------------------------------------------------------
    # Phase 3 RAG: LLM-based ChainDiscoverer
    # ------------------------------------------------------------------

    def discover_indirect_chains(
        self,
        unmatched_findings: list[str],
        diseases: list[str],
        vignette_context: str = "",
    ) -> list[dict]:
        """Use LLM to discover indirect reasoning chains for unmatched findings.

        This is the Phase 3 RAG fallback when structured knowledge (PrimeKG,
        DxS, LR) cannot provide 2-hop chains.
        """
        if not self._chain_discoverer_fn:
            return []
        if not unmatched_findings:
            return []

        payload = {
            "unmatched_findings": unmatched_findings,
            "candidate_diseases": diseases,
            "vignette_context": vignette_context[:500],
            "known_disease_features": {},
        }

        for d in diseases:
            features: list[str] = []
            dxs_key = self._resolve_disease(d, "dxs")
            if dxs_key and self.dxs:
                features.extend(sorted(self.dxs.get_phenotypes(dxs_key))[:10])
            pkg_key = self._resolve_disease(d, "primekg")
            if pkg_key and self.primekg:
                features.extend(sorted(self.primekg.get_positive_phenotypes(pkg_key))[:10])
            payload["known_disease_features"][d] = features[:15]

        try:
            result = self._chain_discoverer_fn(payload)
            return result.get("chains", [])
        except Exception as e:
            logger.warning("ChainDiscoverer failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Annotator query: lr_reference
    # ------------------------------------------------------------------

    def get_lr_reference(
        self,
        finding: str,
        diseases: list[str],
        hpo_id: str = "",
        fast: bool = False,
    ) -> dict:
        """Look up LR data for a finding across competing diseases.

        Cascade: FindingNormalizer → Pathognomonic markers → Layer 2 (cache) → Layer 3a (RAG) → Layer 3b (PubMed) → 2-hop.

        When ``fast=True`` only the deterministic, in-memory layers run
        (normalizer + pathognomonic markers + structured cache, optionally with
        the SNOMED synonym bridge). The expensive RAG / PubMed / 2-hop fallbacks
        are skipped. Used by the per-turn KB direction reconciliation (F1), which
        only needs HIGH-confidence signals and must stay cheap because it runs
        once per branch per turn.
        """
        lr_data: dict[str, Optional[dict]] = {}
        sources: set[str] = set()
        normalized_finding = finding
        normalized_hpo_id = hpo_id

        # Canonicalise mechanism/morphology disease phrasing once. lr_data is
        # always keyed by the ORIGINAL label (the controller maps it back to
        # branches), but every retrieval layer queries the canonical entity so
        # mechanism-style options ("Increased parathyroid hormone") reach the
        # disease the sources index ("primary hyperparathyroidism").
        dq = {d: self.resolver.canonicalize_entity(d) for d in diseases}

        # Pre-process: normalize numeric lab values to HPO terms
        if self.finding_normalizer:
            norm = self.finding_normalizer.normalize(finding)
            if norm and norm.hpo_term:
                normalized_finding = norm.hpo_term
                normalized_hpo_id = norm.hpo_id or hpo_id
                sources.add(f"lab_normalized:{norm.source}")
                logger.debug(
                    "FindingNormalizer: '%s' → '%s' (%s)",
                    finding, normalized_finding, normalized_hpo_id,
                )

        # Layer 0 (highest priority): Pathognomonic / diagnostic marker lookup
        if self.diagnostic_markers:
            for d in diseases:
                cq = dq[d]
                entry = self.diagnostic_markers.lookup(
                    finding, cq, hpo_id=normalized_hpo_id
                )
                if not entry and normalized_finding != finding:
                    entry = self.diagnostic_markers.lookup(
                        normalized_finding, cq, hpo_id=normalized_hpo_id
                    )
                if entry:
                    lr_data[d] = entry
                    sources.add(entry.get("source", "diagnostic_marker"))

        # Layer 2: structured cache (skip diseases already resolved by markers)
        if self.lr:
            for d in diseases:
                if lr_data.get(d):
                    continue
                lr_key = self._resolve_disease(d, "lr")
                disease_query = lr_key or dq[d]
                entry = self.lr.lookup_fuzzy(normalized_finding, disease_query)
                if not entry and normalized_finding != finding:
                    entry = self.lr.lookup_fuzzy(finding, disease_query)
                # SNOMED synonym bridge: retry the cache under alternative disease
                # surface forms (e.g. "chronic myelogenous"↔"chronic myeloid").
                if not entry:
                    for alias in self._snomed_disease_aliases(d):
                        entry = self.lr.lookup_fuzzy(normalized_finding, alias)
                        if entry:
                            sources.add("snomed_bridge")
                            break
                lr_data[d] = entry
                if entry:
                    sources.add(entry.get("source", "unknown"))

        # Layer 3a: RAG fallback for cache misses
        # ``fast`` skips only the EXPENSIVE fallbacks (RAG embedding search +
        # live PubMed); the cheap in-memory 2-hop hypernym chain below still
        # runs so symptom→intermediate→disease (上位症状) mapping is preserved.
        # §25.2(#3): treat a LOW-confidence cache hit as still-eligible for RAG
        # so an attenuated subsumption / context-only entry does not block a
        # higher-confidence numeric RAG LR. Gated; default = true misses only.
        def _is_low_conf(e: Optional[dict]) -> bool:
            if not e:
                return True
            conf = str(e.get("confidence", ""))
            src = str(e.get("source", ""))
            return (
                conf in ("subsumption_upward", "context-only", "rag_qualitative")
                or src.startswith("subsumption_upward")
                or src.startswith("RAG-context")
                or src.startswith("PubMed-context")
            )

        if self._confidence_gated_cascade:
            cache_misses = [d for d in diseases if _is_low_conf(lr_data.get(d))]
        else:
            cache_misses = [d for d in diseases if not lr_data.get(d)]
        if not fast and cache_misses and self.rag and self.rag.is_ready:
            sc = self.secondary_lr_cache
            for d in cache_misses:
                # NOTE (#3): an existing low-confidence entry is preserved as a
                # fallback — the context-only fill below is gated by
                # ``if not lr_data[d]`` so a truthy subsumption entry is only ever
                # OVERRIDDEN by a numeric RAG hit, never downgraded to RAG-context.
                # Tier-2 cache: reuse a previously RAG-quantified LR (keyed by
                # the canonical query) instead of re-running embedding search +
                # extraction. A stored null means "RAG had no numeric signal".
                ckey_f = normalized_finding
                if sc is not None and sc.contains(ckey_f, dq[d]):
                    cached = sc.get(ckey_f, dq[d])
                    if cached:
                        lr_data[d] = {**cached, "disease": d}
                        sources.add(cached.get("source", "RAG-quant"))
                        continue
                    # else fall through to context-only handling below
                    snippets = self.rag.search_for_disease(dq[d], finding, top_k=3)
                    entry = None
                else:
                    snippets = self.rag.search_for_disease(dq[d], finding, top_k=3)
                    entry = self.rag.extract_lr_from_snippets(snippets, finding, d) if snippets else None
                    if sc is not None:
                        # memoize hit OR miss (null) under the canonical key
                        sc.put(ckey_f, dq[d], {**entry, "disease": dq[d]} if entry else None)
                if snippets:
                    if entry:
                        lr_data[d] = entry
                        sources.add(entry.get("source", "RAG"))
                    elif snippets:
                        lr_data.setdefault(d, None)
                        if not lr_data[d]:
                            lr_data[d] = {
                                "finding": finding,
                                "disease": d,
                                "source": f"RAG-context:{snippets[0].get('article_id', '')}",
                                "confidence": "context-only",
                                "context_snippet": snippets[0].get("content", "")[:300],
                                "snippet_title": snippets[0].get("title", ""),
                            }
                            sources.add("RAG-context")

        # Layer 3b: PubMed live search for remaining misses (skipped when fast)
        still_missing = [d for d in diseases if not lr_data.get(d)]
        if not fast and still_missing and self.pubmed:
            for d in still_missing[:2]:
                entry = self.pubmed.lookup_lr(finding, d)
                if entry:
                    lr_data[d] = entry
                    sources.add(entry.get("source", "PubMed"))
                else:
                    abstracts = self.pubmed.search_abstracts(finding, d, max_results=2)
                    if abstracts:
                        snippet = abstracts[0].get("abstract", "")[:300]
                        lr_data[d] = {
                            "finding": finding,
                            "disease": d,
                            "source": f"PubMed-context:PMID{abstracts[0].get('pmid', '')}",
                            "confidence": "context-only",
                            "context_snippet": snippet,
                            "snippet_title": abstracts[0].get("title", ""),
                        }
                        sources.add("PubMed-context")

        # Layer 2-hop: indirect chain LR for remaining misses
        final_missing = [d for d in diseases if not lr_data.get(d)]
        if final_missing:
            hop_results = self.get_2hop_lr(finding, final_missing)
            for entry in hop_results:
                d = entry["disease"]
                if not lr_data.get(d):
                    lr_data[d] = entry
                    sources.add("PrimeKG-2hop")

        hit_count = sum(1 for v in lr_data.values() if v)
        return {
            "finding": finding,
            "lr_data": lr_data,
            "source": ", ".join(sorted(sources)) if sources else "none",
            "hit_count": hit_count,
        }

    def get_comparative_lr(
        self,
        finding: str,
        disease_a: str,
        disease_b: str,
    ) -> Optional[dict]:
        if not self.lr:
            return None
        lr_key_a = self._resolve_disease(disease_a, "lr") or disease_a
        lr_key_b = self._resolve_disease(disease_b, "lr") or disease_b
        return self.lr.get_comparative_lr(finding, lr_key_a, lr_key_b)

    def match_evidence_to_phenotypes(
        self,
        evidence_items: list[str],
        *,
        threshold: float = 0.35,
    ) -> dict[str, list[dict]]:
        if not self.matcher:
            return {}
        augmented = list(evidence_items)
        if self.finding_normalizer:
            for item in evidence_items:
                norm = self.finding_normalizer.normalize(item)
                if norm and norm.hpo_term and norm.hpo_term not in augmented:
                    augmented.append(norm.hpo_term)
        return self.matcher.match_batch(augmented, threshold=threshold)

    # ------------------------------------------------------------------
    # Convenience: format hints for prompt injection
    # ------------------------------------------------------------------

    def format_discriminator_hints_for_prompt(
        self,
        diseases: list[str],
        *,
        seen_evidence: Optional[set[str]] = None,
        max_lines: int = 25,
        vignette_text: str = "",
        include_chains: bool = True,
    ) -> str:
        """Generate a compact text block for injection into TALP prompt.

        Includes 1-hop pairwise differences + 2-hop chain info + LLM chains.
        """
        hints = self.get_discriminator_hints(
            diseases, seen_evidence=seen_evidence
        )
        lines: list[str] = []
        lines.append(f"[Knowledge Layer: coverage={hints['coverage_ratio']:.0%}, source={hints['layer_used']}]")

        for pair_key, data in hints["pairwise"].items():
            if data["only_a"] or data["only_b"]:
                lines.append(f"\n{pair_key}:")
                if data["only_a"]:
                    lines.append(f"  Favours first:  {', '.join(data['only_a'][:5])}")
                if data["only_b"]:
                    lines.append(f"  Favours second: {', '.join(data['only_b'][:5])}")

        for d, feats in hints.get("exclusion_features", {}).items():
            if feats:
                lines.append(f"\nNOT typically seen in {d}: {', '.join(feats[:5])}")

        for d, related in hints.get("related_diseases", {}).items():
            if related:
                lines.append(f"\nRelated to {d}: {', '.join(related[:3])}")

        # Phase 3: indirect reasoning chains
        if include_chains and len(lines) < max_lines:
            chain_lines = self._format_chain_section(
                diseases, vignette_text, seen_evidence, max_lines - len(lines)
            )
            if chain_lines:
                lines.append("")
                lines.extend(chain_lines)

        return "\n".join(lines[:max_lines])

    def _format_chain_section(
        self,
        diseases: list[str],
        vignette_text: str,
        seen_evidence: Optional[set[str]],
        budget: int,
    ) -> list[str]:
        """Build the indirect reasoning chains section for TALP hints."""
        if budget <= 2:
            return []

        # Identify unmatched findings from vignette
        unmatched = self._find_unmatched_evidence(diseases, vignette_text, seen_evidence)
        if not unmatched:
            return []

        lines: list[str] = []

        # Try PrimeKG 2-hop first
        kg_chains = self.get_2hop_chains(unmatched, diseases)
        if kg_chains:
            lines.append("[Indirect reasoning chains (PrimeKG 2-hop):]")
            for chain in kg_chains[:3]:
                lines.append(
                    f"  {chain['finding']} → {chain['intermediate']} → {chain['target_disease']}"
                )

        # Layer 3a: RAG context for unmatched findings
        if not kg_chains and self.rag and self.rag.is_ready:
            for finding_text in unmatched[:2]:
                rag_results = self.rag.search(
                    f"{finding_text} differential diagnosis {' '.join(diseases[:3])}",
                    top_k=2,
                )
                for r in rag_results:
                    if r.get("score", 0) > 0.4:
                        lines.append(f"[RAG context for '{finding_text}' (score={r['score']:.2f}):]")
                        lines.append(f"  Source: {r.get('title', 'unknown')}")
                        content = r.get("content", "")[:200]
                        lines.append(f"  {content}")

        # Layer 3c: LLM ChainDiscoverer
        if not kg_chains and self._chain_discoverer_fn:
            llm_chains = self.discover_indirect_chains(unmatched, diseases, vignette_text)
            if llm_chains:
                lines.append("[Indirect reasoning chains (clinical inference):]")
                for chain in llm_chains[:3]:
                    finding = chain.get("finding", "?")
                    intermediate = chain.get("intermediate", "?")
                    target = chain.get("target_disease", "?")
                    freq = chain.get("intermediate_frequency", "unknown")
                    suggestion = chain.get("suggestion", "")
                    lines.append(f"  {finding} → {intermediate} → {target}")
                    lines.append(f"    (frequency: {freq})")
                    if suggestion:
                        lines.append(f"    Suggestion: {suggestion}")

                lines.append(
                    "\nWhen indirect_reasoning_chains are present, generate "
                    "candidates that investigate the INTERMEDIATE phenotype "
                    "to confirm or rule out the indirect association."
                )

        return lines[:budget]

    def _find_unmatched_evidence(
        self,
        diseases: list[str],
        vignette_text: str,
        seen_evidence: Optional[set[str]],
    ) -> list[str]:
        """Extract vignette findings not matching any disease's known phenotypes."""
        if not vignette_text or not self.matcher:
            return []

        import re
        sentences = re.split(r"[.,;]", vignette_text)
        findings = [s.strip() for s in sentences if len(s.strip()) > 5]

        all_disease_phenos: set[str] = set()
        for d in diseases:
            dxs_key = self._resolve_disease(d, "dxs")
            if dxs_key and self.dxs:
                all_disease_phenos |= self.dxs.get_phenotypes(dxs_key)
            pkg_key = self._resolve_disease(d, "primekg")
            if pkg_key and self.primekg:
                all_disease_phenos |= self.primekg.get_positive_phenotypes(pkg_key)

        if not all_disease_phenos:
            return findings[:5]

        unmatched: list[str] = []
        for finding in findings:
            matched = self.matcher.match(finding, threshold=0.4, max_matches=1)
            if matched:
                phenotype = matched[0]["phenotype"]
                if phenotype in all_disease_phenos or (seen_evidence and phenotype in seen_evidence):
                    continue
            unmatched.append(finding)

        return unmatched[:5]

    def format_lr_reference_for_prompt(
        self,
        finding: str,
        diseases: list[str],
        hpo_id: str = "",
        fast: bool = False,
    ) -> str:
        """Generate a compact text block for injection into Annotator prompt.

        ``fast=True`` restricts the lookup to the cheap in-memory tiers (markers
        + cache + synonym bridge + 2-hop), skipping RAG/PubMed — important when
        called per atomic finding (several times per turn)."""
        ref = self.get_lr_reference(finding, diseases, hpo_id=hpo_id, fast=fast)
        if ref["source"] == "none":
            return ""
        lines = [f"[LR Reference for '{finding}' (source: {ref['source']})]"]
        for disease, entry in ref["lr_data"].items():
            if entry:
                conf = entry.get("confidence", "?")
                marker_type = entry.get("marker_type", "")
                if conf == "pathognomonic_exclusion" or marker_type == "pathognomonic_exclusion":
                    lr_p = entry.get("lr_positive")
                    note = entry.get("note", "")
                    band = ebm_lr_band(lr_p)
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: ✗ ARGUES AGAINST — LR+={lr_p}, "
                        f"confidence=pathognomonic_exclusion{band_str}"
                    )
                    if note:
                        lines.append(f"    Note: {note}")
                elif conf == "pathognomonic" or marker_type == "pathognomonic":
                    lr_p = entry.get("lr_positive")
                    note = entry.get("note", "")
                    band = ebm_lr_band(lr_p)
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: ★ PATHOGNOMONIC — LR+={lr_p}, "
                        f"confidence=pathognomonic{band_str}"
                    )
                    if note:
                        lines.append(f"    Note: {note}")
                elif conf == "highly_specific" or marker_type == "highly_specific":
                    lr_p = entry.get("lr_positive")
                    note = entry.get("note", "")
                    band = ebm_lr_band(lr_p)
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: ⊕ HIGHLY SPECIFIC — LR+={lr_p}, "
                        f"confidence=highly_specific (specific but NOT "
                        f"pathognomonic){band_str}"
                    )
                    if note:
                        lines.append(f"    Note: {note}")
                elif conf == "diagnostic_criterion" or marker_type == "diagnostic_criterion":
                    freq = entry.get("frequency", "")
                    lines.append(
                        f"  {disease}: DIAGNOSTIC CRITERION (freq: {freq}), "
                        f"confidence=diagnostic_criterion"
                    )
                elif conf == "gene_association" or marker_type == "gene_association":
                    gene = entry.get("gene_symbol", "")
                    gene_spec = entry.get("gene_specificity", 0)
                    lr_p = entry.get("lr_positive")
                    lines.append(
                        f"  {disease}: gene {gene} associated "
                        f"(specificity={gene_spec:.2f}, LR+≈{lr_p})"
                    )
                elif conf == "subsumption_upward":
                    lr_p = entry.get("lr_positive")
                    sub_meta = entry.get("subsumption_meta", {})
                    p_finding = sub_meta.get("patient_finding", "?")
                    c_finding = sub_meta.get("cache_finding", "?")
                    depth = sub_meta.get("depth", "?")
                    attn = sub_meta.get("attenuation", "?")
                    band = ebm_lr_band(lr_p, entry.get("lr_negative"))
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: LR+≈{lr_p} (subsumption: "
                        f"'{p_finding}' IS-A '{c_finding}', "
                        f"depth={depth}, attenuation={attn}){band_str}"
                    )
                elif conf == "qualitative":
                    lines.append(
                        f"  {disease}: qualitative association (no LR available)"
                    )
                elif conf in ("indirect_chain", "disease_bridge_chain"):
                    lr_p = entry.get("lr_positive")
                    chain = entry.get("chain", [])
                    chain_str = " → ".join(str(c) for c in chain) if chain else "?"
                    band = ebm_lr_band(lr_p)
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: indirect chain LR+≈{lr_p} "
                        f"(path: {chain_str}, confidence={conf}){band_str}"
                    )
                elif conf == "context-only":
                    snippet = entry.get("context_snippet", "")[:150]
                    title = entry.get("snippet_title", "")
                    lines.append(f"  {disease}: [RAG context from {title}]")
                    lines.append(f"    \"{snippet}...\"")
                else:
                    lr_p = entry.get("lr_positive")
                    lr_n = entry.get("lr_negative")
                    sn = entry.get("sensitivity")
                    sp = entry.get("specificity")
                    band = ebm_lr_band(lr_p, lr_n)
                    band_str = f" [EBM: {band}]" if band else ""
                    lines.append(
                        f"  {disease}: LR+={lr_p}, LR-={lr_n} "
                        f"(Sn={sn}, Sp={sp}, confidence={conf}){band_str}"
                    )
            else:
                lines.append(f"  {disease}: no data")
        return "\n".join(lines)
