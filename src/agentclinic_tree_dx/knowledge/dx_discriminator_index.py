"""Layer 0: DxS DiagRL-Corpus discriminator index.

Builds disease → phenotype_set mapping from the flat DiagRL JSON files,
then computes phenotype set differences between competing disease pairs
to generate discriminative features.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DxDiscriminatorIndex:
    """In-memory index of disease → phenotype_set from DiagRL-Corpus.

    Supports O(1) per-disease lookup and O(|phenotype_set|) pairwise
    set-difference computation for discriminative feature generation.
    """

    def __init__(self) -> None:
        # disease_name (normalised lowercase) → set of symptom strings
        self._disease_phenotypes: dict[str, set[str]] = {}
        # disease_name → set of HPO IDs (when available)
        self._disease_hpo: dict[str, set[str]] = {}
        # disease_name → ICD-10 code
        self._disease_icd: dict[str, str] = {}
        # ICD-10 prefix → list of disease names (for fuzzy disease matching)
        self._icd_prefix_index: dict[str, list[str]] = {}

    @classmethod
    def from_files(
        cls,
        common_path: str | Path,
        rare_path: Optional[str | Path] = None,
    ) -> "DxDiscriminatorIndex":
        """Load from DiagRL-Corpus JSON files."""
        idx = cls()
        idx._load_common(Path(common_path))
        if rare_path:
            idx._load_rare(Path(rare_path))
        logger.info(
            "DxDiscriminatorIndex loaded: %d diseases, %d total phenotype pairs",
            len(idx._disease_phenotypes),
            sum(len(v) for v in idx._disease_phenotypes.values()),
        )
        return idx

    def _load_common(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for disease_name, entry in data.items():
            key = disease_name.strip().lower()
            symptoms = set(s.strip().lower() for s in entry.get("symptom_list", []) if s.strip())
            hpo_ids = set(h.strip() for h in entry.get("hpo_list", []) if h.strip())
            icd = entry.get("icd_code", "")
            self._disease_phenotypes[key] = symptoms
            if hpo_ids:
                self._disease_hpo[key] = hpo_ids
            if icd:
                self._disease_icd[key] = icd
                prefix = icd.split(".")[0]
                self._icd_prefix_index.setdefault(prefix, []).append(key)

    def _load_rare(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for orpha_id, entry in data.items():
            name = entry.get("name", orpha_id).strip().lower()
            hpo_assoc = entry.get("hpo_associations", [])
            symptoms: set[str] = set()
            hpo_ids: set[str] = set()
            for assoc in hpo_assoc:
                if isinstance(assoc, dict):
                    hpo_id = assoc.get("hpo_id", "")
                    hpo_name = assoc.get("hpo_name", "").strip().lower()
                    if hpo_name:
                        symptoms.add(hpo_name)
                    if hpo_id:
                        hpo_ids.add(hpo_id)
                elif isinstance(assoc, str):
                    symptoms.add(assoc.strip().lower())
            if symptoms:
                self._disease_phenotypes.setdefault(name, set()).update(symptoms)
            if hpo_ids:
                self._disease_hpo.setdefault(name, set()).update(hpo_ids)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    @property
    def disease_count(self) -> int:
        return len(self._disease_phenotypes)

    def get_phenotypes(self, disease: str) -> set[str]:
        """Return the phenotype set for a disease (empty set if unknown)."""
        return self._disease_phenotypes.get(disease.strip().lower(), set())

    def get_hpo_ids(self, disease: str) -> set[str]:
        return self._disease_hpo.get(disease.strip().lower(), set())

    def discriminators(
        self, disease_a: str, disease_b: str
    ) -> dict[str, set[str]]:
        """Compute discriminative features between two diseases.

        Returns:
            {
                "only_a": phenotypes present in A but not B,
                "only_b": phenotypes present in B but not A,
                "shared": phenotypes present in both,
            }
        """
        pa = self.get_phenotypes(disease_a)
        pb = self.get_phenotypes(disease_b)
        return {
            "only_a": pa - pb,
            "only_b": pb - pa,
            "shared": pa & pb,
        }

    def multi_discriminators(
        self, diseases: list[str], *, max_features: int = 10
    ) -> dict[str, list[str]]:
        """For each disease, compute features unique to it vs all others.

        Returns dict mapping disease → list of its most discriminative features
        (features present in that disease but absent from all others in the list).
        """
        pheno_sets = {d: self.get_phenotypes(d) for d in diseases}
        result: dict[str, list[str]] = {}
        for d in diseases:
            others_union: set[str] = set()
            for other, ps in pheno_sets.items():
                if other != d:
                    others_union |= ps
            unique = pheno_sets[d] - others_union
            result[d] = sorted(unique)[:max_features]
        return result

    def search_diseases(self, query: str, *, limit: int = 10) -> list[str]:
        """Fuzzy search for disease names containing the query substring."""
        q = query.strip().lower()
        matches = [d for d in self._disease_phenotypes if q in d]
        return sorted(matches)[:limit]

    def search_by_icd(self, icd_prefix: str) -> list[str]:
        """Find diseases matching an ICD-10 prefix (e.g. 'C92' for myeloid leukemias)."""
        return self._icd_prefix_index.get(icd_prefix, [])
