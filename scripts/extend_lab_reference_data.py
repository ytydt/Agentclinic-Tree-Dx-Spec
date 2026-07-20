#!/usr/bin/env python3
"""Apply and validate the curated lab-reference extension.

The compact extension file is the reviewable source of truth.  This script
merges it into the three runtime JSON files without scraping clinical websites
at build time.  Source URLs, versions, and checksums live in
``lab_reference_sources.json``.

Examples
--------
Write the expanded runtime files::

    python scripts/extend_lab_reference_data.py --write

Verify that committed files are reproducible from the extension::

    python scripts/extend_lab_reference_data.py --check
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "knowledge_raw"
DEFAULT_EXTENSION = DATA / "lab_reference_range_extensions.json"
DEFAULT_SOURCES = DATA / "lab_reference_sources.json"
DEFAULT_RANGES = DATA / "lab_reference_ranges.json"
DEFAULT_CONVERSIONS = DATA / "unit_conversions.json"
DEFAULT_LOINC2HPO = DATA / "loinc2hpo_annotations.json"


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def _source_ids(sources: dict[str, Any]) -> set[str]:
    return set(sources.get("sources", {}))


def _iter_sourced_records(extension: dict[str, Any]):
    for name, entry in extension.get("additions", {}).items():
        for kind in ("reference_ranges", "decision_limits"):
            for record in entry.get(kind, []):
                yield f"additions.{name}.{kind}", record
    for name, patch in extension.get("patches", {}).items():
        for kind in ("replace_reference_ranges", "decision_limits"):
            for record in patch.get(kind, []):
                yield f"patches.{name}.{kind}", record


def validate_extension(extension: dict[str, Any], sources: dict[str, Any]) -> None:
    errors: list[str] = []
    known_sources = _source_ids(sources)

    if extension.get("schema_version") != "1.0":
        errors.append("unsupported extension schema_version")

    for source in extension.get("unit_conversion_sources", []):
        if source not in known_sources:
            errors.append(f"unit_conversion_sources: unknown source {source!r}")

    for location, record in _iter_sourced_records(extension):
        source = record.get("source")
        if not source:
            errors.append(f"{location}: missing source")
        elif source not in known_sources:
            errors.append(f"{location}: unknown source {source!r}")
        low, high = record.get("low"), record.get("high")
        if low is not None and high is not None and low > high:
            errors.append(f"{location}: low {low} exceeds high {high}")
        if "unit" not in record:
            errors.append(f"{location}: missing unit")

    for name, entry in extension.get("additions", {}).items():
        if not entry.get("aliases"):
            errors.append(f"additions.{name}: at least one alias is required")
        if entry.get("scale") not in {"Qn", "Ord", "Nom"}:
            errors.append(f"additions.{name}: invalid scale")
        if (
            not entry.get("reference_ranges")
            and not entry.get("decision_limits")
            and not entry.get("requires_local_or_clinical_context")
        ):
            errors.append(f"additions.{name}: no interval or decision limit")
        for source in entry.get("interpretation_sources", []):
            if source not in known_sources:
                errors.append(
                    f"additions.{name}.interpretation_sources: unknown source {source!r}"
                )

    for patch in extension.get("unit_conversion_patches", []):
        if not patch.get("test_group") or not patch.get("canonical_unit"):
            errors.append("unit conversion patch lacks test_group/canonical_unit")
        for conversion in patch.get("conversions", []):
            if not conversion.get("from") or not conversion.get("to"):
                errors.append(f"{patch.get('test_group')}: incomplete conversion")
            if not isinstance(conversion.get("factor"), (int, float)) or conversion["factor"] <= 0:
                errors.append(f"{patch.get('test_group')}: conversion factor must be positive")

    if errors:
        raise ValueError("Invalid lab extension:\n- " + "\n- ".join(errors))


def _apply_catalog_patch(catalog: dict[str, Any], name: str, patch: dict[str, Any]) -> None:
    if name not in catalog:
        raise KeyError(f"cannot patch missing lab test {name!r}")
    entry = catalog[name]
    remove = {alias.casefold() for alias in patch.get("remove_aliases", [])}
    if remove:
        entry["aliases"] = [
            alias for alias in entry.get("aliases", []) if alias.casefold() not in remove
        ]
    for alias in patch.get("add_aliases", []):
        if alias.casefold() not in {a.casefold() for a in entry.get("aliases", [])}:
            entry.setdefault("aliases", []).append(alias)
    if "replace_loinc_codes" in patch:
        entry["loinc_codes"] = copy.deepcopy(patch["replace_loinc_codes"])
    if "replace_reference_ranges" in patch:
        entry["reference_ranges"] = copy.deepcopy(patch["replace_reference_ranges"])
    entry.update(copy.deepcopy(patch.get("set", {})))


def build_outputs(
    catalog: dict[str, Any],
    conversions: list[dict[str, Any]],
    loinc2hpo: dict[str, Any],
    extension: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    catalog = copy.deepcopy(catalog)
    conversions = copy.deepcopy(conversions)
    loinc2hpo = copy.deepcopy(loinc2hpo)

    for name, patch in extension.get("patches", {}).items():
        _apply_catalog_patch(catalog, name, patch)
    for name, entry in extension.get("additions", {}).items():
        catalog[name] = copy.deepcopy(entry)

    conversion_index = {entry["test_group"]: i for i, entry in enumerate(conversions)}
    for patch in extension.get("unit_conversion_patches", []):
        clean = {k: copy.deepcopy(v) for k, v in patch.items() if k != "replace"}
        group = clean["test_group"]
        if group not in conversion_index:
            conversion_index[group] = len(conversions)
            conversions.append(clean)
            continue
        idx = conversion_index[group]
        if patch.get("replace"):
            conversions[idx] = clean
            continue
        existing = conversions[idx]
        existing["canonical_unit"] = clean["canonical_unit"]
        by_pair = {(c["from"], c["to"]): c for c in existing.get("conversions", [])}
        for conversion in clean.get("conversions", []):
            by_pair[(conversion["from"], conversion["to"])] = conversion
        existing["conversions"] = list(by_pair.values())

    for code, mapping in extension.get("loinc2hpo_patches", {}).items():
        loinc2hpo[code] = copy.deepcopy(mapping)

    return catalog, conversions, loinc2hpo


def validate_outputs(
    catalog: dict[str, Any],
    conversions: list[dict[str, Any]],
    sources: dict[str, Any],
) -> None:
    errors: list[str] = []
    known_sources = _source_ids(sources)
    aliases: dict[str, str] = {}
    for name, entry in catalog.items():
        if not isinstance(entry, dict):
            errors.append(f"catalog entry {name!r} is not an object")
            continue
        for alias in [name, *entry.get("aliases", [])]:
            key = alias.strip().casefold()
            previous = aliases.get(key)
            if previous and previous != name:
                errors.append(f"alias {alias!r} is shared by {previous!r} and {name!r}")
            aliases[key] = name
        for ref in entry.get("reference_ranges", []):
            low, high = ref.get("low"), ref.get("high")
            if low is not None and high is not None and low > high:
                errors.append(f"{name}: low exceeds high")
        for kind in ("reference_ranges", "decision_limits"):
            for record in entry.get(kind, []):
                source = record.get("source")
                if not source:
                    errors.append(f"{name}.{kind}: missing source")
                elif source not in known_sources:
                    errors.append(f"{name}.{kind}: unknown source {source!r}")
        for source in entry.get("interpretation_sources", []):
            if source not in known_sources:
                errors.append(f"{name}.interpretation_sources: unknown source {source!r}")

    groups: set[str] = set()
    for entry in conversions:
        group = entry.get("test_group")
        if group in groups:
            errors.append(f"duplicate conversion group {group!r}")
        groups.add(group)

    if errors:
        raise ValueError("Invalid expanded lab data:\n- " + "\n- ".join(errors))


def _check_file(path: Path, expected: Any) -> bool:
    actual = _load(path)
    if actual == expected:
        print(f"OK   {path.relative_to(ROOT)}")
        return True
    print(f"DIFF {path.relative_to(ROOT)}", file=sys.stderr)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write expanded runtime JSON files")
    mode.add_argument("--check", action="store_true", help="verify committed files match the extension")
    parser.add_argument("--extension", type=Path, default=DEFAULT_EXTENSION)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--ranges", type=Path, default=DEFAULT_RANGES)
    parser.add_argument("--conversions", type=Path, default=DEFAULT_CONVERSIONS)
    parser.add_argument("--loinc2hpo", type=Path, default=DEFAULT_LOINC2HPO)
    args = parser.parse_args()

    extension = _load(args.extension)
    sources = _load(args.sources)
    validate_extension(extension, sources)

    catalog = _load(args.ranges)
    conversions = _load(args.conversions)
    loinc2hpo = _load(args.loinc2hpo)

    expanded = build_outputs(catalog, conversions, loinc2hpo, extension)
    validate_outputs(expanded[0], expanded[1], sources)

    paths = (args.ranges, args.conversions, args.loinc2hpo)
    if args.check:
        return 0 if all(_check_file(path, value) for path, value in zip(paths, expanded)) else 1

    for path, value in zip(paths, expanded):
        path.write_text(_canonical_json(value), encoding="utf-8")
        print(f"WROTE {path.relative_to(ROOT)}")
    print(
        f"Expanded catalog: {len(expanded[0])} tests; "
        f"{len(expanded[1])} conversion groups; {len(expanded[2])} LOINC mappings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
