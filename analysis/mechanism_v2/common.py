"""Common, offline-safe helpers for the mechanism-v2 experiments.

The helpers in this module intentionally avoid importing the LLM client.  This
keeps audit/replay code usable in restricted environments and prevents a read
only analysis from starting provider/proxy machinery.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class DevelopmentSlice:
    slice_id: str
    family: str
    stage_dir: Path
    cases_json: Path


DEVELOPMENT_SLICES: tuple[DevelopmentSlice, ...] = (
    DevelopmentSlice(
        "DA_d2_seq100",
        "DA",
        ROOT / "logs/backbone_v1/diagnosisarena/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/normalized_cases.json",
    ),
    DevelopmentSlice(
        "DA_d2_heldout100",
        "DA",
        ROOT
        / "logs/backbone_v1/diagnosisarena_heldout/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1/normalized_cases.json",
    ),
    DevelopmentSlice(
        "DA_d2_heldout200b",
        "DA",
        ROOT
        / "logs/backbone_v1/diagnosisarena_heldout200b/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1/normalized_cases.json",
    ),
    DevelopmentSlice(
        "MCR_v1_seq100",
        "MCR",
        ROOT / "logs/backbone_v1/medcasereasoning/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json",
    ),
    DevelopmentSlice(
        "MCR_v2_seq100",
        "MCR",
        ROOT
        / "logs/backbone_v1/medcasereasoning_v2/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2/normalized_cases.json",
    ),
    DevelopmentSlice(
        "MCR_seq200b",
        "MCR",
        ROOT
        / "logs/backbone_v1/medcasereasoning_200b/mosaic_forest_v1/case_stages",
        ROOT
        / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1/normalized_cases.json",
    ),
)


def normalize_label(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return re.sub(r"[^\w\s\-/\+]", "", value)


def clean_vignette(case_text: str) -> str:
    """Return the runtime vignette without the benchmark option block."""
    text = str(case_text or "").strip()
    split = re.split(r"(?im)^\s*options?\s*:\s*$", text, maxsplit=1)
    return split[0].strip()


def json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def combined_file_sha256(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(p) for p in paths), key=lambda p: str(p)):
        relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def load_normalized_cases(path: Path) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("cases") if isinstance(document, Mapping) else document
    if not isinstance(rows, list):
        raise ValueError(f"expected case list in {path}")
    return {str(row["id"]): dict(row) for row in rows}


def iter_stage_cases(
    slices: Iterable[DevelopmentSlice] = DEVELOPMENT_SLICES,
) -> Iterator[tuple[DevelopmentSlice, dict[str, Any], dict[str, Any], Path]]:
    """Yield ``(slice, case, stage document, path)`` with strict joins."""
    for spec in slices:
        cases = load_normalized_cases(spec.cases_json)
        stage_paths = sorted(
            spec.stage_dir.glob("*.json"),
            key=lambda path: (not path.stem.isdigit(), int(path.stem) if path.stem.isdigit() else path.stem),
        )
        if not stage_paths:
            raise FileNotFoundError(f"no stage files under {spec.stage_dir}")
        for stage_path in stage_paths:
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            source_id = str(stage.get("source_id") or stage_path.stem)
            case = cases.get(source_id)
            if case is None:
                raise KeyError(
                    f"stage {stage_path} has source_id={source_id!r} absent from {spec.cases_json}"
                )
            yield spec, case, stage, stage_path


class FrozenExactSynonymBridge:
    """Exact-only view of ``disease_name_bridge.json``.

    The production ``DiseaseNameResolver.resolve`` deliberately has substring
    and fuzzy fallback tiers.  Those tiers are forbidden here because E7 asks
    whether *confirmed equivalence* differs from lexical containment.  This
    class therefore performs a single dictionary lookup after normalization.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        by_alias = document.get("by_alias") or {}
        by_canonical = document.get("by_canonical") or {}
        if not isinstance(by_alias, Mapping) or not isinstance(by_canonical, Mapping):
            raise ValueError(f"invalid bridge schema: {path}")
        aliases: dict[str, str] = {}
        collisions: dict[str, set[str]] = {}
        for alias, canonical in by_alias.items():
            alias_key = normalize_label(str(alias))
            canonical_key = normalize_label(str(canonical))
            if not alias_key or not canonical_key:
                continue
            previous = aliases.get(alias_key)
            if previous is not None and previous != canonical_key:
                collisions.setdefault(alias_key, {previous}).add(canonical_key)
                continue
            aliases[alias_key] = canonical_key
        for canonical, info in by_canonical.items():
            canonical_key = normalize_label(str(canonical))
            if canonical_key:
                aliases.setdefault(canonical_key, canonical_key)
            if not isinstance(info, Mapping):
                continue
            for alias in info.get("aliases") or []:
                alias_key = normalize_label(str(alias))
                if not alias_key or not canonical_key:
                    continue
                previous = aliases.get(alias_key)
                if previous is not None and previous != canonical_key:
                    collisions.setdefault(alias_key, {previous}).add(canonical_key)
                    continue
                aliases.setdefault(alias_key, canonical_key)
        # Ambiguous aliases are not safe equivalences.  Falling back to the
        # surface form is conservative and reproducible.
        for alias in collisions:
            aliases.pop(alias, None)
        self._aliases = aliases
        self.collisions = {
            alias: sorted(values) for alias, values in sorted(collisions.items())
        }
        self.sha256 = file_sha256(self.path)

    def canonical_key(self, label: str) -> str:
        surface = normalize_label(label)
        direct = self._aliases.get(surface)
        if direct:
            return direct
        # A full disease name followed by its own parenthetical initialism is
        # an explicit surface-form equivalence, not fuzzy matching.  Preserve
        # other parentheticals (stage, anatomy, phenotype) as distinct.
        match = re.match(r"^\s*(.*?)\s*\(([^()]+)\)\s*$", str(label or ""))
        if match:
            base = normalize_label(match.group(1))
            suffix = normalize_label(match.group(2)).replace(" ", "")
            tokens = re.findall(r"[a-z0-9]+", base)
            stop = {"and", "of", "the", "with", "for", "in", "due", "to"}
            initials = "".join(token[0] for token in tokens if token not in stop)
            suffix_letters = re.sub(r"\d+$", "", suffix)
            suffix_direct = self._aliases.get(normalize_label(match.group(2)))
            base_direct = self._aliases.get(base)
            explicit_bridge_agreement = bool(
                suffix_direct and base_direct and suffix_direct == base_direct
            )
            structural_initialism = bool(
                len(suffix_letters) >= 2 and suffix_letters == initials
            )
            if explicit_bridge_agreement or structural_initialism:
                return base_direct or base
        return surface

    def equivalent(self, left: str, right: str) -> bool:
        left_key = self.canonical_key(left)
        return bool(left_key and left_key == self.canonical_key(right))

    @property
    def n_aliases(self) -> int:
        return len(self._aliases)
