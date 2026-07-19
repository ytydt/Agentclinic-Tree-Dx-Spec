"""Candidate-blind compound finding representations for TALP experiments."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Mapping

_SPLIT = re.compile(r"\s*(?:;|,\s+and\s+|\band\b|\bwith\b|\bplus\b)\s*", re.I)
_PROTECTED = re.compile(r"\b(?:associated with|consistent with|treated with)\b", re.I)
_VALUE = re.compile(
    r"\b(high|low|normal|elevated|decreased|positive|negative|absent|present|"
    r"\d+(?:\.\d+)?\s*(?:%|mg/dl|mmol/l|u/l)?)\b", re.I)
_TIME = re.compile(
    r"\b(acute|abrupt|chronic|intermittent|progressive|"
    r"\d+\s+(?:hours?|days?|weeks?|months?|years?))\b", re.I)
_NEG = re.compile(r"\b(no|not|without|absent|negative|normal)\b", re.I)


@dataclass(frozen=True)
class FindingAtom:
    text: str
    polarity: int = 1
    value: str | None = None
    temporal: str | None = None


@dataclass(frozen=True)
class SyndromeResolution:
    concept_id: str
    label: str
    system: str
    provenance: str
    entailed: bool
    confidence: float


@dataclass
class CompoundRepresentation:
    original: str
    mode: str
    atoms: list[FindingAtom] = field(default_factory=list)
    syndrome: SyndromeResolution | None = None
    abstained: bool = False

    def prompt_text(self) -> str:
        atoms = "; ".join(a.text for a in self.atoms)
        if self.mode == "syndrome":
            return self.syndrome.label if self.syndrome else self.original
        if self.mode == "atomic":
            return atoms or self.original
        if self.mode == "dual" and self.syndrome:
            return f"{atoms or self.original}; verified syndrome: {self.syndrome.label}"
        return self.original

    def to_dict(self) -> dict:
        return asdict(self)


def atomize(text: str) -> list[FindingAtom]:
    protected = _PROTECTED.sub(lambda m: m.group(0).replace(" ", "\u00a0"), text)
    parts = [p.replace("\u00a0", " ").strip(" ,.;") for p in _SPLIT.split(protected)]
    parts = [p for p in parts if p]
    if len(parts) <= 1:
        return [FindingAtom(text=text.strip(), polarity=-1 if _NEG.search(text) else 1,
                            value=(m.group(1) if (m := _VALUE.search(text)) else None),
                            temporal=(m.group(1) if (m := _TIME.search(text)) else None))]
    return [
        FindingAtom(
            text=p, polarity=-1 if _NEG.search(p) else 1,
            value=(m.group(1) if (m := _VALUE.search(p)) else None),
            temporal=(m.group(1) if (m := _TIME.search(p)) else None),
        )
        for p in parts
    ]


class SyndromeResolver:
    """Resolve only provenance-bearing ontology/corpus entries and verify them."""

    def __init__(
        self,
        entries: Mapping[str, list[dict]] | None = None,
        entailment_validator: Callable[[str, list[FindingAtom], dict], bool] | None = None,
    ):
        self.entries = {" ".join(k.lower().split()): v
                        for k, v in (entries or {}).items()}
        self.validator = entailment_validator

    def resolve(self, text: str, atoms: list[FindingAtom]) -> SyndromeResolution | None:
        norm = " ".join(text.lower().split())
        candidates = self.entries.get(norm, [])
        for candidate in candidates:
            has_source = bool(candidate.get("concept_id")
                              and candidate.get("provenance"))
            if not has_source:
                continue
            entailed = bool(self.validator(text, atoms, candidate)) if self.validator else bool(
                candidate.get("entailed", False))
            if not entailed:
                continue
            return SyndromeResolution(
                concept_id=str(candidate["concept_id"]),
                label=str(candidate["label"]),
                system=str(candidate.get("system", "SNOMED_CT")),
                provenance=str(candidate["provenance"]),
                entailed=True,
                confidence=float(candidate.get("confidence", 1.0)),
            )
        return None


def represent(
    text: str, mode: str = "legacy", resolver: SyndromeResolver | None = None
) -> CompoundRepresentation:
    if mode not in {"legacy", "atomic", "syndrome", "dual"}:
        raise ValueError(f"unsupported compound mode: {mode}")
    atoms = atomize(text)
    syndrome = resolver.resolve(text, atoms) if resolver and mode in {"syndrome", "dual"} else None
    return CompoundRepresentation(
        original=text, mode=mode,
        atoms=atoms if mode in {"atomic", "dual"} else [],
        syndrome=syndrome,
        abstained=mode == "syndrome" and syndrome is None,
    )
