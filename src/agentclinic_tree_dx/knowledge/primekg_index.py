"""Layer 1: PrimeKG knowledge graph index.

Parses the PrimeKG kg.csv to build in-memory indices for:
- disease → phenotype (positive and negative associations)
- disease → disease (subtypes, related diseases)
- phenotype → phenotype (hierarchical/associative relationships)
- gene/protein ↔ disease (associated with)
"""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_RELEVANT_EDGE_TYPES = {
    "disease_phenotype_positive",
    "disease_phenotype_negative",
    "disease_disease",
    "phenotype_phenotype",
}


class PrimeKGIndex:
    """In-memory index of PrimeKG's clinically relevant edges.

    Selectively loads disease-phenotype, disease-disease, phenotype-phenotype,
    and gene/protein-disease edges to keep memory footprint manageable.
    """

    def __init__(self) -> None:
        self.disease_phenotype_pos: dict[str, set[str]] = defaultdict(set)
        self.disease_phenotype_neg: dict[str, set[str]] = defaultdict(set)
        self.disease_disease: dict[str, set[str]] = defaultdict(set)
        self.phenotype_phenotype: dict[str, set[str]] = defaultdict(set)
        self._disease_to_genes: dict[str, set[str]] = defaultdict(set)
        self._gene_to_diseases: dict[str, set[str]] = defaultdict(set)
        self._gene_disease_count: dict[str, int] = {}
        self._disease_ids: dict[str, int] = {}
        self._phenotype_ids: dict[str, int] = {}
        self._stats: dict[str, int] = {}

    @classmethod
    def from_csv(cls, kg_csv_path: str | Path) -> "PrimeKGIndex":
        """Parse PrimeKG kg.csv and build the index.

        Only loads edges of relevant types to avoid parsing 8M+ rows into memory.
        """
        idx = cls()
        path = Path(kg_csv_path)
        counts: dict[str, int] = defaultdict(int)

        logger.info("Loading PrimeKG from %s ...", path)
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rel = row["relation"]
                display_rel = row.get("display_relation", "")

                x_type = row["x_type"].strip().lower()
                y_type = row["y_type"].strip().lower()

                is_gene_disease = (
                    display_rel == "associated with"
                    and (
                        (x_type == "gene/protein" and y_type == "disease")
                        or (x_type == "disease" and y_type == "gene/protein")
                    )
                )

                if rel not in _RELEVANT_EDGE_TYPES and not is_gene_disease:
                    continue

                x_name = row["x_name"].strip()
                y_name = row["y_name"].strip()
                x_idx = int(row["x_index"])
                y_idx = int(row["y_index"])

                if is_gene_disease:
                    if x_type == "gene/protein":
                        gene_sym = x_name.upper()
                        disease_name = y_name.lower()
                    else:
                        gene_sym = y_name.upper()
                        disease_name = x_name.lower()
                    idx._disease_to_genes[disease_name].add(gene_sym)
                    idx._gene_to_diseases[gene_sym].add(disease_name)
                    counts["gene_disease_associated"] += 1
                    continue

                x_name_lower = x_name.lower()
                y_name_lower = y_name.lower()

                if rel == "disease_phenotype_positive":
                    d, p = (x_name_lower, y_name_lower) if "disease" in x_type else (y_name_lower, x_name_lower)
                    idx.disease_phenotype_pos[d].add(p)
                    idx._disease_ids.setdefault(d, x_idx if "disease" in x_type else y_idx)
                    idx._phenotype_ids.setdefault(p, y_idx if "disease" in x_type else x_idx)

                elif rel == "disease_phenotype_negative":
                    d, p = (x_name_lower, y_name_lower) if "disease" in x_type else (y_name_lower, x_name_lower)
                    idx.disease_phenotype_neg[d].add(p)

                elif rel == "disease_disease":
                    idx.disease_disease[x_name_lower].add(y_name_lower)
                    idx.disease_disease[y_name_lower].add(x_name_lower)
                    idx._disease_ids.setdefault(x_name_lower, x_idx)
                    idx._disease_ids.setdefault(y_name_lower, y_idx)

                elif rel == "phenotype_phenotype":
                    idx.phenotype_phenotype[x_name_lower].add(y_name_lower)
                    idx.phenotype_phenotype[y_name_lower].add(x_name_lower)

                counts[rel] += 1

        for gene, diseases in idx._gene_to_diseases.items():
            idx._gene_disease_count[gene] = len(diseases)

        idx._stats = dict(counts)
        logger.info(
            "PrimeKG loaded: %d diseases, %d phenotypes, %d gene-disease edges (%d genes), edges=%s",
            len(idx._disease_ids),
            len(idx._phenotype_ids),
            counts.get("gene_disease_associated", 0),
            len(idx._gene_to_diseases),
            dict(counts),
        )

        inherited = idx._inherit_parent_phenotypes()
        if inherited:
            logger.info("PrimeKG: inherited phenotypes for %d zero-phenotype diseases", inherited)

        return idx

    def _inherit_parent_phenotypes(self) -> int:
        """For diseases with 0 phenotypes, inherit from related parent diseases.

        Uses disease_disease edges to find parents that have phenotypes.
        Marks inherited phenotypes in a separate dict for provenance tracking.
        """
        self._inherited_phenotypes: dict[str, tuple[str, set[str]]] = {}
        count = 0
        for disease, related in self.disease_disease.items():
            if self.disease_phenotype_pos.get(disease):
                continue
            best_parent = ""
            best_phenos: set[str] = set()
            for parent in related:
                parent_phenos = self.disease_phenotype_pos.get(parent, set())
                if len(parent_phenos) > len(best_phenos):
                    best_parent = parent
                    best_phenos = parent_phenos
            if best_phenos:
                self.disease_phenotype_pos[disease] = set(best_phenos)
                self._inherited_phenotypes[disease] = (best_parent, best_phenos)
                count += 1
        return count

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def get_disease_genes(self, disease: str) -> set[str]:
        """Return gene symbols associated with a disease (supports fuzzy match)."""
        d_lower = disease.strip().lower()
        exact = self._disease_to_genes.get(d_lower)
        if exact:
            return exact
        result: set[str] = set()
        for key, genes in self._disease_to_genes.items():
            if d_lower in key or key in d_lower:
                result |= genes
        return result

    def get_gene_diseases(self, gene_symbol: str) -> set[str]:
        """Return diseases associated with a gene."""
        return self._gene_to_diseases.get(gene_symbol.strip().upper(), set())

    def gene_disease_specificity(self, gene_symbol: str) -> float:
        """Return specificity score: 1.0 / number_of_associated_diseases.

        Higher = more disease-specific gene.
        """
        count = self._gene_disease_count.get(gene_symbol.strip().upper(), 0)
        if count == 0:
            return 0.0
        return 1.0 / count

    def check_gene_disease_link(self, gene_symbol: str, disease: str) -> Optional[dict]:
        """Check if a gene is associated with a disease (supports fuzzy matching).

        Returns dict with gene, disease, specificity score, or None.
        """
        gene_upper = gene_symbol.strip().upper()
        disease_lower = disease.strip().lower()
        diseases = self._gene_to_diseases.get(gene_upper, set())
        if not diseases:
            return None

        _SYNONYM_PAIRS = [
            ("myeloid", "myelogenous"),
            ("lymphoid", "lymphocytic"),
            ("lymphoblastic", "lymphocytic"),
        ]

        def _normalize_disease(name: str) -> str:
            n = name
            for a, b in _SYNONYM_PAIRS:
                n = n.replace(a, b)
            return n

        matched_disease = None
        if disease_lower in diseases:
            matched_disease = disease_lower
        else:
            norm_query = _normalize_disease(disease_lower)
            for d in diseases:
                if disease_lower in d or d in disease_lower:
                    matched_disease = d
                    break
                norm_d = _normalize_disease(d)
                if norm_query in norm_d or norm_d in norm_query:
                    matched_disease = d
                    break
            if not matched_disease:
                d_tokens = set(disease_lower.split())
                for d in diseases:
                    d_tok = set(d.split())
                    if len(d_tokens & d_tok) >= 2:
                        matched_disease = d
                        break

        if matched_disease is None:
            return None
        return {
            "gene": gene_upper,
            "disease": matched_disease,
            "specificity": self.gene_disease_specificity(gene_upper),
            "total_associations": self._gene_disease_count.get(gene_upper, 0),
        }

    def get_positive_phenotypes(self, disease: str) -> set[str]:
        return self.disease_phenotype_pos.get(disease.strip().lower(), set())

    def get_negative_phenotypes(self, disease: str) -> set[str]:
        """Phenotypes explicitly NOT associated with this disease."""
        return self.disease_phenotype_neg.get(disease.strip().lower(), set())

    def get_related_diseases(self, disease: str) -> set[str]:
        return self.disease_disease.get(disease.strip().lower(), set())

    def get_related_phenotypes(self, phenotype: str) -> set[str]:
        return self.phenotype_phenotype.get(phenotype.strip().lower(), set())

    def discriminators(
        self, disease_a: str, disease_b: str
    ) -> dict[str, set[str]]:
        """Compute discriminative features between two diseases using PrimeKG.

        Includes negative-edge-based exclusion features.
        """
        pa = self.get_positive_phenotypes(disease_a)
        pb = self.get_positive_phenotypes(disease_b)
        na = self.get_negative_phenotypes(disease_a)
        nb = self.get_negative_phenotypes(disease_b)

        only_a = (pa - pb) | (nb & pa)
        only_b = (pb - pa) | (na & pb)

        return {
            "only_a": only_a,
            "only_b": only_b,
            "shared": pa & pb,
            "excluded_from_a": na,
            "excluded_from_b": nb,
        }

    def phenotype_multihop(
        self, phenotype: str, *, max_depth: int = 2
    ) -> set[str]:
        """BFS traversal of phenotype_phenotype edges up to max_depth."""
        visited: set[str] = set()
        frontier = {phenotype.strip().lower()}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for p in frontier:
                if p in visited:
                    continue
                visited.add(p)
                next_frontier |= self.phenotype_phenotype.get(p, set())
            frontier = next_frontier - visited
        visited |= frontier
        visited.discard(phenotype.strip().lower())
        return visited

    def find_2hop_chains(
        self,
        evidence_phenotype: str,
        candidate_diseases: list[str],
        *,
        max_results: int = 10,
    ) -> list[dict]:
        """Find 2-hop chains connecting evidence to diseases.

        Searches two path types:
        1. Phenotype path: evidence → intermediate_phenotype → disease
           (phenotype_phenotype hop 1, disease_phenotype_positive hop 2)
        2. Disease-as-intermediate path: evidence → intermediate_disease → target_disease
           (evidence is a phenotype of intermediate_disease, which relates to target)

        Ranked by intermediate specificity.
        """
        ev_lower = evidence_phenotype.strip().lower()
        chains: list[dict] = []

        # --- Path type 1: phenotype → phenotype → disease ---
        neighbors = self.phenotype_phenotype.get(ev_lower, set())
        if not neighbors:
            for pheno in self.phenotype_phenotype:
                if ev_lower in pheno or pheno in ev_lower:
                    neighbors = neighbors | self.phenotype_phenotype[pheno]

        for intermediate in (neighbors - {ev_lower}):
            n_diseases_with_inter = sum(
                1 for d_phenos in self.disease_phenotype_pos.values()
                if intermediate in d_phenos
            )
            for disease in candidate_diseases:
                d_lower = disease.strip().lower()
                for matched_disease in self._resolve_disease_keys(d_lower):
                    if intermediate in self.disease_phenotype_pos[matched_disease]:
                        chains.append({
                            "finding": evidence_phenotype,
                            "intermediate": intermediate,
                            "target_disease": disease,
                            "matched_disease_key": matched_disease,
                            "is_direct": ev_lower in self.disease_phenotype_pos.get(matched_disease, set()),
                            "intermediate_disease_count": n_diseases_with_inter,
                            "chain_type": "phenotype",
                        })
                        break

        # --- Path type 2: phenotype → disease(intermediate) → disease(target) ---
        inter_diseases = self._find_diseases_with_phenotype(ev_lower)
        for inter_d in inter_diseases:
            related = self.disease_disease.get(inter_d, set())
            for disease in candidate_diseases:
                d_lower = disease.strip().lower()
                for related_d in related:
                    if d_lower in related_d or related_d in d_lower:
                        chains.append({
                            "finding": evidence_phenotype,
                            "intermediate": inter_d,
                            "target_disease": disease,
                            "matched_disease_key": related_d,
                            "is_direct": False,
                            "intermediate_disease_count": 1,
                            "chain_type": "disease_intermediate",
                        })
                        break

        chains.sort(key=lambda c: c["intermediate_disease_count"])
        return chains[:max_results]

    def _find_diseases_with_phenotype(self, phenotype: str) -> list[str]:
        """Find diseases that have a given phenotype (exact or fuzzy)."""
        p_lower = phenotype.strip().lower()
        results = []
        for disease, phenos in self.disease_phenotype_pos.items():
            if p_lower in phenos:
                results.append(disease)
            elif any(p_lower in p or p in p_lower for p in phenos):
                results.append(disease)
        return results[:20]

    def _resolve_disease_keys(self, d_lower: str) -> list[str]:
        """Find all PrimeKG disease keys matching a query, ordered by phenotype count.

        Includes the exact match plus all subtypes (keys containing d_lower)
        so that the richest disease variant is tried first.
        """
        matches = []
        for d_key in self.disease_phenotype_pos:
            if d_key == d_lower or d_lower in d_key or d_key in d_lower:
                if len(d_key) < 4 and d_key != d_lower:
                    continue
                n_phenos = len(self.disease_phenotype_pos[d_key])
                matches.append((d_key, n_phenos))
        matches.sort(key=lambda x: -x[1])
        return [m[0] for m in matches]

    def search_diseases(self, query: str, *, limit: int = 10) -> list[str]:
        q = query.strip().lower()
        matches = [d for d in self._disease_ids if q in d]
        return sorted(matches)[:limit]

    def search_phenotypes(self, query: str, *, limit: int = 10) -> list[str]:
        q = query.strip().lower()
        matches = [p for p in self._phenotype_ids if q in p]
        return sorted(matches)[:limit]
