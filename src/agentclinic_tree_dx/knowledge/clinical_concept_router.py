"""Typed, abstention-first routing for evaluation-time clinical findings.

FHIR is represented as an event shape, not treated as a terminology. Exact
concept mappings come only from licensed/project assets or provenance-bearing
caches supplied by callers; lexical event classification never fabricates IDs.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ConceptRef:
    system: str
    code: str
    display: str
    provenance: str
    confidence: float = 1.0


@dataclass(frozen=True)
class TemporalContext:
    onset: str | None = None
    duration: str | None = None
    relation: str | None = None
    anchor: str | None = None


@dataclass
class TypedClinicalFinding:
    text: str
    event_type: str
    fhir_resource: str
    concepts: list[ConceptRef] = field(default_factory=list)
    temporal: TemporalContext = field(default_factory=TemporalContext)
    polarity: int = 1
    value: str | None = None
    specimen: str | None = None
    abstained: bool = False
    audit: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_EVENT_RULES = [
    ("culture", re.compile(r"\b(culture|isolat(?:e|ed)|grew|organism|pathogen)\b", re.I),
     "Observation", ("LOINC", "SNOMED_CT", "NCBI_TAXONOMY")),
    ("laboratory", re.compile(
        r"\b(level|count|serum|plasma|urine|positive|negative|elevated|low|"
        r"glucose|sodium|potassium|triglyceride|ph|antibody|pcr)\b", re.I),
     "Observation", ("LOINC", "SNOMED_CT", "HPO")),
    ("imaging", re.compile(
        r"\b(x-?ray|radiograph|ct|mri|ultrasound|echo(?:cardiogram)?|imaging|sign)\b",
        re.I), "DiagnosticReport", ("RADLEX", "LOINC", "SNOMED_CT")),
    ("immunization", re.compile(r"\b(vaccin(?:e|ated|ation)|immuni[sz])\b", re.I),
     "Immunization", ("SNOMED_CT",)),
    ("medication", re.compile(
        r"\b(drug|medication|treated with|therapy|antibiotic|anesthetic|response to)\b",
        re.I), "MedicationAdministration", ("RXNORM", "SNOMED_CT")),
    ("disease", re.compile(r"\b(syndrome|disease|infection|deficiency|disorder)\b", re.I),
     "Condition", ("SNOMED_CT", "DOID", "MONDO")),
]
_NEG = re.compile(r"\b(no|not|without|absent|negative|normal)\b", re.I)
_DURATION = re.compile(
    r"\b((?:\d+|several|few)\s+(?:hours?|days?|weeks?|months?|years?)|"
    r"acute|abrupt|chronic|indolent|longstanding)\b", re.I)
_RELATION = re.compile(r"\b(before|after|following|preceded by)\b\s+([^,;.]+)", re.I)
_SPECIMEN = re.compile(
    r"\b(blood|urine|sputum|csf|cerebrospinal fluid|stool|wound|plasma|serum)\b", re.I)


class ClinicalConceptRouter:
    """Route text to event-specific terminology slices using exact mappings."""

    def __init__(
        self,
        concept_maps: Mapping[str, Mapping[str, list[ConceptRef] | ConceptRef]] | None = None,
        hpo_normalizer: Any | None = None,
    ):
        self.maps = {system.upper(): {self._norm(k): v for k, v in terms.items()}
                     for system, terms in (concept_maps or {}).items()}
        self.hpo_normalizer = hpo_normalizer

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())

    def route(self, text: str, mode: str = "multi") -> TypedClinicalFinding:
        if mode not in {"legacy", "hpo", "multi"}:
            raise ValueError(f"unsupported concept router mode: {mode}")
        event, resource, systems = "phenotype", "Observation", ("HPO",)
        if mode == "multi":
            for name, regex, fhir, routed_systems in _EVENT_RULES:
                if regex.search(text):
                    event, resource, systems = name, fhir, routed_systems
                    break
        concepts: list[ConceptRef] = []
        key = self._norm(text)
        lookup_systems = ("HPO",) if mode == "hpo" else systems
        if mode != "legacy":
            for system in lookup_systems:
                found = self.maps.get(system, {}).get(key, [])
                if isinstance(found, ConceptRef):
                    found = [found]
                concepts.extend(found)
            if "HPO" in lookup_systems and self.hpo_normalizer is not None:
                try:
                    nf = self.hpo_normalizer.normalize(text)
                    if nf and getattr(nf, "hpo_id", None):
                        concepts.append(ConceptRef(
                            "HPO", nf.hpo_id, nf.hpo_term,
                            "FindingNormalizer/LOINC2HPO",
                            {"high": 1.0, "medium": 0.75, "low": 0.5}.get(
                                str(nf.confidence).lower(), 0.5)))
                except Exception:  # fail-safe adapter
                    pass
        duration_match = _DURATION.search(text)
        relation_match = _RELATION.search(text)
        specimen_match = _SPECIMEN.search(text)
        temporal = TemporalContext(
            duration=duration_match.group(1) if duration_match else None,
            relation=relation_match.group(1).lower() if relation_match else None,
            anchor=relation_match.group(2).strip() if relation_match else None,
        )
        result = TypedClinicalFinding(
            text=text, event_type=event, fhir_resource=resource,
            concepts=concepts, temporal=temporal,
            polarity=-1 if _NEG.search(text) else 1,
            specimen=specimen_match.group(1).lower() if specimen_match else None,
            abstained=mode != "legacy" and not concepts,
            audit={"requested_systems": list(lookup_systems), "mode": mode},
        )
        return result


def route_fixture(payload: dict, router: ClinicalConceptRouter, mode: str) -> dict:
    """Attach typed audit records to a copied fixture and return coverage."""
    total = mapped = abstained = 0
    event_counts: dict[str, int] = {}
    system_counts: dict[str, int] = {}
    for case in payload.get("cases", []):
        for finding in case.get("findings", []):
            routed = router.route(finding["finding"], mode)
            finding["typed_finding"] = routed.to_dict()
            total += 1
            mapped += bool(routed.concepts)
            abstained += routed.abstained
            event_counts[routed.event_type] = event_counts.get(routed.event_type, 0) + 1
            for concept in routed.concepts:
                system_counts[concept.system] = system_counts.get(concept.system, 0) + 1
    return {
        "mode": mode, "n": total, "mapped": mapped, "abstained": abstained,
        "route_coverage": mapped / total if total else 0.0,
        "event_counts": event_counts, "system_counts": system_counts,
        "layer_a_lr_eligible": system_counts.get("HPO", 0),
    }
