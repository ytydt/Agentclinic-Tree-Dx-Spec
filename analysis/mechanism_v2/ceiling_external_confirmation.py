#!/usr/bin/env python3
"""Offline freeze and no-entry audit for a MedCaseReasoning test confirmation.

This module deliberately does *not* download data, call a model/provider, or run
an experimental arm.  It answers the narrower question that must be settled
before any result is opened: is the pinned MCR test split locally present,
unchanged, sufficiently uncontaminated, cue-masked, powered, and attached to a
passed prerequisite gate?

The split has a deliberately narrow scientific label:

    same-dataset independent-split confirmation

It is not a source-external or time-external cohort.  Passing this audit can
therefore authorize a frozen MCR-test run, but cannot by itself close the
source/time-external-confirmation limitation in Chapter 12.

All inspection is local and read-only unless ``--output`` is explicitly given.
The default output is JSON on stdout.  Network modules and the repository LLM
client are intentionally not imported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "ceiling_external_confirmation_freeze_v1"
MCR_DATASET_ID = "medcasereasoning"
MCR_TEST_RELATIVE_PATH = "raw/test-00000-of-00001.parquet"
MCR_TEST_ROWS = 897
MCR_UPSTREAM = "https://github.com/kevinwu23/stanford-medcasereasoning"
MCR_DATASET_LICENSE = "CC BY 4.0"
MCR_CODE_LICENSE = "MIT"

_PASS = {"pass", "passed", "go", "green", "eligible"}
_FAIL = {"fail", "failed", "no-go", "nogo", "red", "blocked", "ineligible", "stop"}
_TEXT_FIELDS = (
    "case_prompt",
    "case_text",
    "vignette",
    "clinical_vignette",
    "presenting",
    "Case Information",
)
_GOLD_FIELDS = ("final_diagnosis", "Final Diagnosis", "gold", "reference")
_PMCID_RE = re.compile(r"\bPMC\s*\d+\b", re.I)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_STRUCTURED_NAMES = {
    "normalized_cases.json",
    "normalized_cases_clean.json",
    "case_results.jsonl",
    "predictions.jsonl",
    "case_reports.jsonl",
    "case_report_chunks.jsonl",
}
_TEXT_SUFFIXES = {
    ".json", ".jsonl", ".csv", ".tsv", ".md", ".txt", ".log", ".py",
    ".toml", ".yaml", ".yml", ".sha256",
}


@dataclass(frozen=True)
class CaseRecord:
    case_key: str
    source_row_key: str
    case_text: str
    gold: str
    pmcid: str = ""
    doi: str = ""
    title: str = ""


@dataclass(frozen=True)
class ExposureRecord:
    source: str
    record_key: str
    text: str
    pmcid: str = ""
    doi: str = ""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(str(text).encode("utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(_TOKEN_RE.findall(value))


def canonical_pmcid(value: str) -> str:
    match = _PMCID_RE.search(str(value or ""))
    return re.sub(r"\s+", "", match.group(0)).upper() if match else ""


def canonical_doi(value: str) -> str:
    match = _DOI_RE.search(str(value or ""))
    if not match:
        return ""
    return match.group(0).rstrip(".,;)]}").casefold()


def _first(row: Mapping[str, Any], fields: Sequence[str]) -> str:
    for field in fields:
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _identifier_from_row(row: Mapping[str, Any], kind: str) -> str:
    names = ("pmcid", "PMC_ID", "source_pmcid") if kind == "pmcid" else (
        "doi", "DOI", "source_doi", "url", "source_url",
    )
    for name in names:
        value = row.get(name)
        normalized = canonical_pmcid(str(value)) if kind == "pmcid" else canonical_doi(str(value))
        if normalized:
            return normalized
    annotation = row.get("annotation")
    if isinstance(annotation, Mapping):
        return _identifier_from_row(annotation, kind)
    return ""


def _row_key(row: Mapping[str, Any], index: int) -> str:
    for field in ("source_row_key", "Unnamed: 0", "id", "case_id", "source_id", "pmcid"):
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(index)


def case_record(row: Mapping[str, Any], index: int) -> CaseRecord:
    source_row_key = _row_key(row, index)
    text = _first(row, _TEXT_FIELDS)
    gold = _first(row, _GOLD_FIELDS)
    if not text:
        raise ValueError(f"MCR test row {source_row_key!r} has no case_prompt")
    if not gold:
        raise ValueError(f"MCR test row {source_row_key!r} has no final_diagnosis")
    return CaseRecord(
        case_key=f"MCR_test/{source_row_key}",
        source_row_key=source_row_key,
        case_text=text,
        gold=gold,
        pmcid=_identifier_from_row(row, "pmcid"),
        doi=_identifier_from_row(row, "doi"),
        title=str(row.get("title") or "").strip(),
    )


def _load_json_rows(path: Path) -> list[Mapping[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, Mapping):
        rows = document.get("cases") or document.get("rows") or document.get("data")
    else:
        rows = document
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError(f"expected a JSON case list in {path}")
    return rows


def load_mcr_test_cases(path: Path) -> list[CaseRecord]:
    """Load MCR rows without applying disease-name, KB, or outcome gates."""
    path = Path(path)
    suffix = path.suffix.casefold()
    rows: Iterable[Mapping[str, Any]]
    if suffix == ".json":
        rows = _load_json_rows(path)
    elif suffix == ".jsonl":
        rows = (
            row for row in (
                json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            ) if isinstance(row, Mapping)
        )
    elif suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    elif suffix in {".parquet", ".pqt"}:
        try:
            import pandas as pd  # local optional dependency; no network side effects
            frame = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "reading the pinned parquet requires the local lab-audit dependency "
                "(pyarrow); this tool will not install or download it"
            ) from exc
        rows = (row.to_dict() for _, row in frame.iterrows())
    else:
        raise ValueError(f"unsupported MCR input: {path}")
    cases = [case_record(row, index) for index, row in enumerate(rows, 1)]
    cases.sort(key=lambda row: (_natural_key(row.source_row_key), row.case_key))
    if len({row.case_key for row in cases}) != len(cases):
        raise ValueError("duplicate MCR test source_row_key values")
    return cases


def _natural_key(value: str) -> tuple[int, int | str]:
    value = str(value)
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _replace_literal(text: str, literal: str, token: str) -> tuple[str, bool]:
    literal = str(literal or "").strip()
    if len(canonical_text(literal).split()) < 2 and len(literal) < 8:
        return text, False
    updated, count = re.subn(re.escape(literal), token, text, flags=re.I)
    return updated, count > 0


def mask_answer_cues(case: CaseRecord) -> dict[str, Any]:
    """Mask answer-bearing diagnosis/title text and report unresolved cues."""
    masked = case.case_text
    rules: list[str] = []
    masked, changed = _replace_literal(masked, case.title, "[SOURCE_TITLE_MASKED]")
    if changed:
        rules.append("source_title_literal")
    masked, changed = _replace_literal(masked, case.gold, "[DIAGNOSIS_MASKED]")
    if changed:
        rules.append("gold_literal")

    cue = re.compile(
        r"(?is)\b(?:final|definitive|confirmed|pathologic(?:al)?)\s+diagnosis\s*"
        r"(?:was|is|of|:)?\s*[^\n.;?]{1,180}"
    )
    masked, cue_n = cue.subn("[ANSWER_CUE_MASKED]", masked)
    if cue_n:
        rules.append("diagnostic_conclusion_clause")

    normalized_masked = canonical_text(masked)
    gold_norm = canonical_text(case.gold)
    title_norm = canonical_text(case.title)
    unresolved: list[str] = []
    if gold_norm and len(gold_norm.split()) >= 2 and gold_norm in normalized_masked:
        unresolved.append("gold_literal_remains")
    if title_norm and len(title_norm.split()) >= 3 and title_norm in normalized_masked:
        unresolved.append("source_title_remains")
    return {
        "case_key": case.case_key,
        "raw_text_sha256": sha256_text(case.case_text),
        "masked_text_sha256": sha256_text(masked),
        "gold_sha256": sha256_text(canonical_text(case.gold)),
        "rules": rules,
        "unresolved": unresolved,
        "masked_text": masked,
    }


def shingle_sketch(text: str, *, width: int = 5, size: int = 48) -> tuple[int, ...]:
    tokens = canonical_text(text).split()
    if not tokens:
        return ()
    width = max(1, min(width, len(tokens)))
    values = {
        int.from_bytes(
            hashlib.blake2b(" ".join(tokens[i:i + width]).encode("utf-8"), digest_size=8).digest(),
            "big",
        )
        for i in range(len(tokens) - width + 1)
    }
    return tuple(sorted(values)[:size])


def sketch_containment(left: Sequence[int], right: Sequence[int]) -> float:
    if not left or not right:
        return 0.0
    return len(set(left) & set(right)) / min(len(left), len(right))


def _iter_mapping_records(value: Any) -> Iterator[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        if _first(value, _TEXT_FIELDS):
            yield value
        for child in value.values():
            if isinstance(child, (Mapping, list)):
                yield from _iter_mapping_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mapping_records(child)


def exposure_records_from_path(path: Path, *, source_name: str | None = None) -> list[ExposureRecord]:
    path = Path(path)
    source_name = source_name or str(path)
    records: list[ExposureRecord] = []
    suffix = path.suffix.casefold()
    try:
        if suffix == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                mappings = (
                    item for item in (json.loads(line) for line in stream if line.strip())
                    if isinstance(item, Mapping)
                )
                for index, row in enumerate(mappings, 1):
                    for nested in _iter_mapping_records(row):
                        text = _first(nested, _TEXT_FIELDS)
                        records.append(ExposureRecord(
                            source=source_name,
                            record_key=_row_key(nested, index),
                            text=text,
                            pmcid=_identifier_from_row(nested, "pmcid"),
                            doi=_identifier_from_row(nested, "doi"),
                        ))
        elif suffix == ".json":
            document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            for index, row in enumerate(_iter_mapping_records(document), 1):
                records.append(ExposureRecord(
                    source=source_name,
                    record_key=_row_key(row, index),
                    text=_first(row, _TEXT_FIELDS),
                    pmcid=_identifier_from_row(row, "pmcid"),
                    doi=_identifier_from_row(row, "doi"),
                ))
        elif suffix == ".csv":
            with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
                for index, row in enumerate(csv.DictReader(stream), 1):
                    text = _first(row, _TEXT_FIELDS)
                    if text:
                        records.append(ExposureRecord(
                            source=source_name,
                            record_key=_row_key(row, index),
                            text=text,
                            pmcid=_identifier_from_row(row, "pmcid"),
                            doi=_identifier_from_row(row, "doi"),
                        ))
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error):
        return []
    return records


def discover_exposure_files(repo_root: Path, *, excluded: Sequence[Path] = ()) -> list[Path]:
    repo_root = Path(repo_root).resolve()
    excluded_resolved = {Path(path).resolve() for path in excluded}
    candidates: set[Path] = set()
    for base in (
        repo_root / "data/benchmarks",
        repo_root / "data/case_reports",
        repo_root / "data/cpg/processed",
        repo_root / "logs",
        repo_root / "runs",
        repo_root / "analysis/mechanism_v2/results",
    ):
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.resolve() in excluded_resolved:
                continue
            if path.name in _STRUCTURED_NAMES or (
                path.suffix.casefold() == ".jsonl" and any(part in {"logs", "runs", "results"} for part in path.parts)
            ):
                candidates.add(path)
    return sorted(candidates)


def audit_case_overlap(
    cases: Sequence[CaseRecord],
    exposures: Sequence[ExposureRecord],
    *,
    near_threshold: float = 0.80,
) -> dict[str, Any]:
    by_pmcid: dict[str, list[int]] = defaultdict(list)
    by_doi: dict[str, list[int]] = defaultdict(list)
    by_hash: dict[str, list[int]] = defaultdict(list)
    sketches: list[tuple[int, ...]] = []
    inverted: dict[int, list[int]] = defaultdict(list)
    for index, record in enumerate(exposures):
        if record.pmcid:
            by_pmcid[record.pmcid].append(index)
        if record.doi:
            by_doi[record.doi].append(index)
        normalized = canonical_text(record.text)
        if normalized:
            by_hash[sha256_text(normalized)].append(index)
        sketch = shingle_sketch(record.text)
        sketches.append(sketch)
        for token in sketch:
            inverted[token].append(index)

    rows: list[dict[str, Any]] = []
    excluded: set[str] = set()
    for case in cases:
        kinds: set[str] = set()
        source_indexes: set[int] = set()
        if case.pmcid and case.pmcid in by_pmcid:
            kinds.add("pmcid")
            source_indexes.update(by_pmcid[case.pmcid])
        if case.doi and case.doi in by_doi:
            kinds.add("doi")
            source_indexes.update(by_doi[case.doi])
        normalized = canonical_text(case.case_text)
        exact_hash = sha256_text(normalized)
        if exact_hash in by_hash:
            kinds.add("exact_text_hash")
            source_indexes.update(by_hash[exact_hash])
        case_sketch = shingle_sketch(case.case_text)
        candidates: Counter[int] = Counter()
        for token in case_sketch:
            candidates.update(inverted.get(token, ()))
        near: list[tuple[float, int]] = []
        for source_index, shared in candidates.items():
            # Three shared bottom-k shingles is only a cheap candidate screen;
            # the actual decision below uses the declared containment threshold.
            # Scaling this screen by the test sketch alone would miss a shorter
            # source excerpt that is wholly contained in a longer case prompt.
            if shared < min(3, len(case_sketch), len(sketches[source_index])):
                continue
            score = sketch_containment(case_sketch, sketches[source_index])
            if score >= near_threshold and exact_hash not in by_hash:
                near.append((score, source_index))
        if near:
            kinds.add("near_text_sketch")
            source_indexes.update(index for _, index in near)
        if kinds:
            excluded.add(case.case_key)
            rows.append({
                "case_key": case.case_key,
                "match_kinds": sorted(kinds),
                "sources": sorted({exposures[index].source for index in source_indexes})[:20],
                "near_max": max((score for score, _ in near), default=None),
            })
    return {
        "n_test_cases": len(cases),
        "n_exposure_records": len(exposures),
        "near_threshold": near_threshold,
        "n_excluded": len(excluded),
        "excluded_case_keys": sorted(excluded),
        "matches": rows,
    }


def _git_paths(repo_root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if proc.returncode:
        return []
    return [repo_root / os.fsdecode(item) for item in proc.stdout.split(b"\0") if item]


def _needle_pattern(needles: Mapping[str, str]) -> re.Pattern[bytes] | None:
    values = sorted({value.casefold() for value in needles.values() if len(value) >= 6}, key=len, reverse=True)
    if not values:
        return None
    return re.compile(b"|".join(re.escape(value.encode("utf-8")) for value in values), re.I)


def _scan_bytes(data: bytes, pattern: re.Pattern[bytes] | None, reverse: Mapping[str, list[str]]) -> set[str]:
    if pattern is None:
        return set()
    found: set[str] = set()
    for match in pattern.finditer(data):
        found.update(reverse.get(match.group(0).decode("utf-8", errors="ignore").casefold(), ()))
    return found


def scan_worktree_references(
    repo_root: Path,
    needles: Mapping[str, str],
    *,
    excluded: Sequence[Path] = (),
) -> list[dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    excluded_resolved = {Path(path).resolve() for path in excluded}
    reverse: dict[str, list[str]] = defaultdict(list)
    for label, value in needles.items():
        if len(value) >= 6:
            reverse[value.casefold()].append(label)
    pattern = _needle_pattern(needles)
    hits: list[dict[str, Any]] = []
    values = sorted({value for value in needles.values() if len(value) >= 6})
    candidates: list[Path] | None = None
    if values:
        # Let ripgrep perform the full-tree scan; Python only re-opens matched
        # files to attribute each hit to its named needle.  This matters for a
        # repository with multi-gigabyte JSONL run ledgers.
        try:
            found = subprocess.run(
                [
                    "rg", "-l", "-i", "-F", "-f", "-", "--hidden",
                    "--glob", "!.git/**", ".",
                ],
                cwd=repo_root,
                input="\n".join(values) + "\n",
                text=True,
                check=False,
                capture_output=True,
            )
            if found.returncode in {0, 1}:
                candidates = [repo_root / line for line in found.stdout.splitlines() if line]
        except OSError:
            candidates = None
    for path in candidates if candidates is not None else _git_paths(repo_root):
        try:
            if not path.is_file() or path.resolve() in excluded_resolved:
                continue
            if path.suffix.casefold() not in _TEXT_SUFFIXES:
                continue
            found = _scan_bytes(path.read_bytes(), pattern, reverse)
        except OSError:
            continue
        for label in sorted(found):
            hits.append({"needle": label, "path": str(path.relative_to(repo_root))})
    return hits


def _historical_candidate(path: str) -> bool:
    candidate = Path(path)
    return candidate.suffix.casefold() in _TEXT_SUFFIXES and (
        candidate.name in _STRUCTURED_NAMES
        or any(part in {"logs", "runs", "results", "subsets"} for part in candidate.parts)
    )


def scan_git_history(
    repo_root: Path,
    needles: Mapping[str, str],
    *,
    max_blob_bytes: int = 128 * 1024 * 1024,
) -> tuple[list[dict[str, Any]], list[ExposureRecord], dict[str, Any]]:
    """Scan unique historical case-bearing blobs through local ``git cat-file``."""
    repo_root = Path(repo_root).resolve()
    rev = subprocess.run(
        ["git", "rev-list", "--objects", "--all", "--", "logs", "runs", "analysis", "data"],
        cwd=repo_root,
        text=True,
        check=False,
        capture_output=True,
    )
    if rev.returncode:
        return [], [], {"performed": False, "error": rev.stderr.strip()}
    paths_by_sha: dict[str, set[str]] = defaultdict(set)
    for line in rev.stdout.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2 and _historical_candidate(parts[1]):
            paths_by_sha[parts[0]].add(parts[1])
    reverse: dict[str, list[str]] = defaultdict(list)
    for label, value in needles.items():
        if len(value) >= 6:
            reverse[value.casefold()].append(label)
    pattern = _needle_pattern(needles)
    collect_case_records = any(label.startswith("MCR_test/") for label in needles)
    hits: list[dict[str, Any]] = []
    records: list[ExposureRecord] = []
    scanned = skipped_large = non_blob = 0
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=repo_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        for sha, paths in paths_by_sha.items():
            process.stdin.write((sha + "\n").encode("ascii"))
            process.stdin.flush()
            header = process.stdout.readline().decode("utf-8", errors="replace").strip()
            fields = header.split()
            if len(fields) < 3 or fields[1] != "blob":
                non_blob += 1
                continue
            size = int(fields[2])
            data = process.stdout.read(size)
            process.stdout.read(1)  # trailing LF emitted by cat-file --batch
            if size > max_blob_bytes:
                skipped_large += 1
                continue
            scanned += 1
            for label in sorted(_scan_bytes(data, pattern, reverse)):
                hits.append({"needle": label, "blob_sha": sha, "paths": sorted(paths)})
            if not collect_case_records:
                continue
            text = data.decode("utf-8", errors="replace")
            for path in sorted(paths):
                if Path(path).name not in _STRUCTURED_NAMES:
                    continue
                suffix = Path(path).suffix.casefold()
                try:
                    if suffix == ".jsonl":
                        docs = [json.loads(line) for line in text.splitlines() if line.strip()]
                    else:
                        docs = [json.loads(text)]
                except json.JSONDecodeError:
                    continue
                for doc in docs:
                    for index, row in enumerate(_iter_mapping_records(doc), 1):
                        records.append(ExposureRecord(
                            source=f"git:{sha}:{path}",
                            record_key=_row_key(row, index),
                            text=_first(row, _TEXT_FIELDS),
                            pmcid=_identifier_from_row(row, "pmcid"),
                            doi=_identifier_from_row(row, "doi"),
                        ))
    finally:
        process.stdin.close()
        process.stdout.close()
        process.terminate()
        process.wait(timeout=5)
    return hits, records, {
        "performed": True,
        "candidate_blobs": len(paths_by_sha),
        "scanned_blobs": scanned,
        "skipped_large_blobs": skipped_large,
        "non_blob_objects": non_blob,
    }


def paired_sample_size(
    *,
    min_effect: float,
    discordance: float,
    alpha: float = 0.05,
    power: float = 0.80,
    missingness: float = 0.0,
) -> dict[str, Any]:
    """Normal-approximation planning for a two-sided paired McNemar contrast."""
    if not 0 < min_effect < 1:
        raise ValueError("min_effect must be in (0, 1)")
    if not min_effect <= discordance <= 1:
        raise ValueError("discordance must be in [min_effect, 1]")
    if not 0 < alpha < 1 or not 0 < power < 1 or not 0 <= missingness < 1:
        raise ValueError("invalid alpha/power/missingness")
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    z_power = normal.inv_cdf(power)
    variance_alt = max(discordance - min_effect * min_effect, 0.0)
    complete = (
        (z_alpha * math.sqrt(discordance) + z_power * math.sqrt(variance_alt)) ** 2
        / (min_effect * min_effect)
    )
    complete_n = math.ceil(complete)
    enrolled_n = math.ceil(complete / (1 - missingness))
    return {
        "method": "two_sided_paired_mcnemar_normal_approximation",
        "alpha": alpha,
        "power": power,
        "min_effect": min_effect,
        "discordance": discordance,
        "missingness": missingness,
        "complete_pairs_required": complete_n,
        "enrolled_cases_required": enrolled_n,
    }


def achieved_paired_power(*, n: int, min_effect: float, discordance: float, alpha: float = 0.05) -> float:
    if n <= 0 or not min_effect <= discordance <= 1:
        return 0.0
    normal = NormalDist()
    z_alpha = normal.inv_cdf(1 - alpha / 2)
    variance_alt = max(discordance - min_effect * min_effect, 1e-12)
    z = (math.sqrt(n) * min_effect - z_alpha * math.sqrt(discordance)) / math.sqrt(variance_alt)
    return max(0.0, min(1.0, normal.cdf(z)))


def _gate_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        token = value.strip().casefold().replace("_", "-")
        if token in _PASS:
            return True
        if token in _FAIL:
            return False
    return None


def read_gate_result(path: Path | None, track: str) -> dict[str, Any]:
    """Read a frozen prerequisite result, failing closed on ambiguity."""
    if path is None:
        return {"track": track, "present": False, "passed": False, "reason": "gate_result_missing"}
    path = Path(path)
    if not path.is_file():
        return {"track": track, "present": False, "passed": False, "reason": "gate_result_not_found", "path": str(path)}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"track": track, "present": True, "passed": False, "reason": f"gate_result_unreadable:{type(exc).__name__}", "path": str(path)}
    node: Any = document
    if isinstance(document, Mapping):
        for key in (track, f"{track}_gate"):
            if key in document:
                node = document[key]
                break
        else:
            gates = document.get("gates") or document.get("gate_results")
            if isinstance(gates, Mapping) and track in gates:
                node = gates[track]
    candidates: list[tuple[str, bool]] = []
    if isinstance(node, Mapping):
        for key in ("entry_allowed", "passed", "go", "status", "decision", "result"):
            parsed = _gate_value(node.get(key))
            if parsed is not None:
                candidates.append((key, parsed))
    else:
        parsed = _gate_value(node)
        if parsed is not None:
            candidates.append(("value", parsed))
    values = {value for _, value in candidates}
    passed = len(values) == 1 and values == {True}
    reason = "passed" if passed else ("conflicting_gate_fields" if len(values) > 1 else "gate_not_passed_or_ambiguous")
    return {
        "track": track,
        "present": True,
        "passed": passed,
        "reason": reason,
        "path": str(path),
        "sha256": file_sha256(path),
        "evidence_fields": [{"field": key, "value": value} for key, value in candidates],
    }


def _manifest_artifact(manifest: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for artifact in manifest.get("artifacts") or []:
        if (
            isinstance(artifact, Mapping)
            and artifact.get("dataset_id") == MCR_DATASET_ID
            and artifact.get("relative_path") == MCR_TEST_RELATIVE_PATH
        ):
            return artifact
    return None


def inspect_pinned_artifact(repo_root: Path, manifest_path: Path, raw_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "reason": f"download_manifest_unreadable:{type(exc).__name__}"}
    artifact = _manifest_artifact(manifest)
    if artifact is None:
        return {"passed": False, "reason": "pinned_mcr_test_artifact_missing"}
    expected_sha = str(artifact.get("sha256") or "")
    expected_bytes = int(artifact.get("bytes") or 0)
    expected_rows = int(artifact.get("rows") or 0)
    license_note = str(artifact.get("license_note") or "")
    license_ok = "cc" in license_note.casefold() and "by" in license_note.casefold() and "4" in license_note
    raw_path = Path(raw_path)
    present = raw_path.is_file()
    actual_sha = file_sha256(raw_path) if present else ""
    actual_bytes = raw_path.stat().st_size if present else 0
    reasons: list[str] = []
    if not present:
        reasons.append("pinned_raw_file_absent")
    if present and expected_sha and actual_sha != expected_sha:
        reasons.append("raw_sha256_mismatch")
    if present and expected_bytes and actual_bytes != expected_bytes:
        reasons.append("raw_byte_size_mismatch")
    if expected_rows != MCR_TEST_ROWS:
        reasons.append("unexpected_manifest_row_count")
    if not license_ok:
        reasons.append("license_note_mislabels_dataset_as_code_license")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "manifest_path": str(Path(manifest_path)),
        "raw_path": str(raw_path),
        "present": present,
        "expected_sha256": expected_sha,
        "actual_sha256": actual_sha,
        "expected_bytes": expected_bytes,
        "actual_bytes": actual_bytes,
        "expected_rows": expected_rows,
        "revision": artifact.get("revision"),
        "recorded_license_note": license_note,
        "authoritative_dataset_license": MCR_DATASET_LICENSE,
        "authoritative_code_license": MCR_CODE_LICENSE,
        "authoritative_source": MCR_UPSTREAM,
    }


def _git_state(repo_root: Path, architecture_commit: str | None) -> dict[str, Any]:
    def run(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=repo_root, text=True).strip()
    try:
        head = run("rev-parse", "HEAD")
        dirty = bool(run("status", "--porcelain"))
    except (OSError, subprocess.CalledProcessError) as exc:
        return {"passed": False, "reason": f"git_state_unavailable:{type(exc).__name__}"}
    requested_input = architecture_commit or head
    try:
        requested = run("rev-parse", requested_input)
    except (OSError, subprocess.CalledProcessError):
        requested = requested_input
    passed = not dirty and requested == head
    reasons = []
    if dirty:
        reasons.append("worktree_not_clean")
    if requested != head:
        reasons.append("architecture_commit_not_head")
    return {
        "passed": passed,
        "head": head,
        "architecture_commit": requested,
        "architecture_commit_input": requested_input,
        "dirty": dirty,
        "reasons": reasons,
    }


def _execution_reference(hit: Mapping[str, Any]) -> bool:
    paths = [str(hit.get("path") or "")] + [str(path) for path in hit.get("paths") or []]
    for value in paths:
        parts = Path(value).parts
        # This audit necessarily records the pinned test path/hash.  Its own
        # reports are provenance evidence, not evidence that a diagnostic arm
        # opened or executed the split.
        if "CEILING_EXTERNAL_CONFIRMATION" in parts:
            continue
        if "logs" in parts or "runs" in parts or "results" in parts:
            return True
    return False


def build_freeze(
    *,
    repo_root: Path = ROOT,
    raw_path: Path | None = None,
    manifest_path: Path | None = None,
    track: str = "static",
    static_gate: Path | None = None,
    active_gate: Path | None = None,
    architecture_commit: str | None = None,
    min_effect: float = 0.05,
    discordance: float = 0.12,
    missingness: float = 0.10,
    near_threshold: float = 0.80,
    exposure_paths: Sequence[Path] | None = None,
    include_git_history: bool = True,
    scope_waiver: bool = False,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    raw_path = Path(raw_path) if raw_path else repo_root / "data/benchmarks/medcasereasoning/raw/test-00000-of-00001.parquet"
    manifest_path = Path(manifest_path) if manifest_path else repo_root / "data/benchmarks/download_manifest.json"
    if track not in {"static", "active"}:
        raise ValueError("track must be static or active")

    artifact = inspect_pinned_artifact(repo_root, manifest_path, raw_path)
    git_state = _git_state(repo_root, architecture_commit)
    gates = {
        "static": read_gate_result(static_gate, "static"),
        "active": read_gate_result(active_gate, "active"),
    }
    required_gate = gates[track]
    cases: list[CaseRecord] = []
    load_error = ""
    if artifact.get("present") and artifact.get("actual_sha256") == artifact.get("expected_sha256"):
        try:
            cases = load_mcr_test_cases(raw_path)
        except Exception as exc:  # noqa: BLE001
            load_error = f"{type(exc).__name__}: {exc}"

    cue_rows = [mask_answer_cues(case) for case in cases]
    cue_excluded = {row["case_key"] for row in cue_rows if row["unresolved"]}
    needles: dict[str, str] = {
        "mcr_test_raw_path": str(Path(MCR_TEST_RELATIVE_PATH)),
        "mcr_test_raw_sha256": str(artifact.get("expected_sha256") or ""),
    }
    for case in cases:
        if case.pmcid:
            needles[f"{case.case_key}:pmcid"] = case.pmcid
        if case.doi:
            needles[f"{case.case_key}:doi"] = case.doi
        needles[f"{case.case_key}:text_sha256"] = sha256_text(canonical_text(case.case_text))

    worktree_hits = scan_worktree_references(repo_root, needles, excluded=(raw_path, Path(__file__)))
    git_hits: list[dict[str, Any]] = []
    git_records: list[ExposureRecord] = []
    git_coverage: dict[str, Any] = {"performed": False, "reason": "disabled"}
    if include_git_history:
        git_hits, git_records, git_coverage = scan_git_history(repo_root, needles)

    paths = (
        list(exposure_paths)
        if exposure_paths is not None
        else discover_exposure_files(repo_root, excluded=(raw_path,))
    ) if cases else []
    exposures: list[ExposureRecord] = []
    for path in paths:
        exposures.extend(exposure_records_from_path(path))
    exposures.extend(git_records)
    # Repeated run rows carry the same vignette.  One exposure per source/text/id
    # is sufficient and prevents historical replication count from dominating.
    deduped: dict[tuple[str, str, str, str], ExposureRecord] = {}
    for record in exposures:
        key = (sha256_text(canonical_text(record.text)), record.pmcid, record.doi, record.source)
        deduped.setdefault(key, record)
    overlap = audit_case_overlap(cases, list(deduped.values()), near_threshold=near_threshold)
    source_id_missing = sorted(case.case_key for case in cases if not (case.pmcid or case.doi))

    history_case_excluded = {
        hit["needle"].rsplit(":", 1)[0]
        for hit in [*worktree_hits, *git_hits]
        if str(hit.get("needle") or "").startswith("MCR_test/")
    }
    excluded_cases = set(overlap["excluded_case_keys"]) | cue_excluded | history_case_excluded
    eligible_n = max(0, len(cases) - len(excluded_cases))
    plan = paired_sample_size(
        min_effect=min_effect,
        discordance=discordance,
        missingness=missingness,
    )
    plan["eligible_cases"] = eligible_n
    plan["achieved_power_at_eligible_n"] = achieved_paired_power(
        n=math.floor(eligible_n * (1 - missingness)),
        min_effect=min_effect,
        discordance=discordance,
    )
    plan["adequately_powered"] = eligible_n >= plan["enrolled_cases_required"]

    split_execution_hits = [
        hit for hit in [*worktree_hits, *git_hits]
        if hit.get("needle") in {"mcr_test_raw_path", "mcr_test_raw_sha256"} and _execution_reference(hit)
    ]
    queue_rows = [
        {
            "case_key": row["case_key"],
            "source_row_key": case.source_row_key,
            "raw_text_sha256": row["raw_text_sha256"],
            "masked_text_sha256": row["masked_text_sha256"],
            "gold_sha256": row["gold_sha256"],
            "pmcid_sha256": sha256_text(case.pmcid) if case.pmcid else "",
            "doi_sha256": sha256_text(case.doi) if case.doi else "",
            "mask_rules": row["rules"],
            "eligible": row["case_key"] not in excluded_cases,
        }
        for case, row in zip(cases, cue_rows)
    ]
    queue_digest = sha256_text(json.dumps(queue_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    no_entry: list[str] = []
    if not artifact.get("passed"):
        no_entry.extend(artifact.get("reasons") or [artifact.get("reason") or "artifact_contract_failed"])
    if load_error:
        no_entry.append("mcr_test_load_failed")
    if cases and len(cases) != int(artifact.get("expected_rows") or 0):
        no_entry.append("loaded_row_count_mismatch")
    if not cases:
        no_entry.append("case_level_contamination_audit_unavailable")
    if not git_state.get("passed"):
        no_entry.extend(git_state.get("reasons") or [git_state.get("reason") or "git_freeze_failed"])
    if not required_gate.get("passed"):
        no_entry.append(f"{track}_prerequisite_gate_not_passed")
    if include_git_history and not git_coverage.get("performed"):
        no_entry.append("git_history_audit_unavailable")
    if include_git_history and int(git_coverage.get("skipped_large_blobs") or 0):
        no_entry.append("git_history_audit_skipped_large_blobs")
    if not overlap["n_exposure_records"]:
        no_entry.append("exposure_corpus_audit_empty")
    if source_id_missing:
        no_entry.append("pmcid_or_doi_missing_for_test_cases")
    if split_execution_hits:
        no_entry.append("mcr_test_split_previously_referenced_by_execution_artifact")
    if cue_excluded:
        no_entry.append("unresolved_answer_cues")
    if not plan["adequately_powered"]:
        no_entry.append("insufficient_eligible_paired_sample")
    no_entry = sorted(set(no_entry))
    underlying_decision = "GO" if not no_entry else "NO_ENTRY"
    final_decision = "NOT_EXECUTED_SCOPE_WAIVER" if scope_waiver else underlying_decision

    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "offline_read_only_audit": True,
        "network_or_api_calls": False,
        "scientific_scope": {
            "label": "same-dataset independent-split confirmation",
            "same_dataset": True,
            "independent_split_from_current_validation_development": True,
            "source_external": False,
            "time_external": False,
            "chapter12_source_time_external_confirmation_closed": False,
            "allowed_claim_if_successful": "independent MCR split confirmation under the frozen contract",
            "prohibited_claims": [
                "source-external confirmation",
                "time-external confirmation",
                "cross-benchmark universal superiority",
                "clinical deployment readiness",
            ],
        },
        "artifact": artifact,
        "git_freeze": git_state,
        "prerequisite_gates": gates,
        "required_track": track,
        "case_load": {"n_cases": len(cases), "error": load_error},
        "cue_masking": {
            "n_masked_by_rule": dict(Counter(rule for row in cue_rows for rule in row["rules"])),
            "n_unresolved": len(cue_excluded),
            "unresolved_case_keys": sorted(cue_excluded),
            "gold_and_reasoning_not_in_runtime_input_contract": True,
        },
        "repository_exposure_audit": {
            "worktree_hits": worktree_hits,
            "git_history_hits": git_hits,
            "git_history_coverage": git_coverage,
            "split_execution_hits": split_execution_hits,
        },
        "duplicate_audit": overlap,
        "source_identifier_coverage": {
            "n_cases": len(cases),
            "n_with_pmcid": sum(bool(case.pmcid) for case in cases),
            "n_with_doi": sum(bool(case.doi) for case in cases),
            "n_missing_both": len(source_id_missing),
            "missing_case_keys": source_id_missing,
        },
        "excluded_case_keys": sorted(excluded_cases),
        "power_plan": plan,
        "queue": {
            "n_rows": len(queue_rows),
            "n_eligible": eligible_n,
            "queue_sha256": queue_digest,
            "case_hash_manifest": queue_rows,
            "selection_is_outcome_blind": True,
            "forbidden_selection_gates": ["gold disease-name gate", "KB-coverage gate", "arm outcome"],
        },
        "entry_decision": {
            "allowed": not scope_waiver and not no_entry,
            "decision": final_decision,
            "reasons": no_entry,
            "underlying_decision_without_waiver": underlying_decision,
            "underlying_no_entry_reasons": no_entry,
            "scope_waiver_applied": scope_waiver,
            "not_executed_reason": (
                "user_authorized_large_external_rerun_scope_waiver" if scope_waiver else ""
            ),
            "scope_waiver_effect": (
                "execution omitted; scientific limitations and prerequisite findings remain open"
                if scope_waiver else "none"
            ),
        },
        "irreducible_public_benchmark_limit": (
            "Public-case foundation-model pretraining exposure cannot be ruled out; "
            "the audit addresses repository/retrieval/development exposure only."
        ),
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--raw-path", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--track", choices=("static", "active"), default="static")
    parser.add_argument("--static-gate", type=Path)
    parser.add_argument("--active-gate", type=Path)
    parser.add_argument("--architecture-commit")
    parser.add_argument("--min-effect", type=float, default=0.05)
    parser.add_argument("--discordance", type=float, default=0.12)
    parser.add_argument("--missingness", type=float, default=0.10)
    parser.add_argument("--near-threshold", type=float, default=0.80)
    parser.add_argument("--exposure-path", type=Path, action="append")
    parser.add_argument("--skip-git-history", action="store_true")
    parser.add_argument(
        "--scope-waiver",
        action="store_true",
        help=(
            "record that the large external rerun is intentionally not executed; "
            "preserves the underlying NO_ENTRY/GO audit and does not close external validity"
        ),
    )
    parser.add_argument("--output", type=Path, help="optional JSON output; stdout is the default")
    parser.add_argument(
        "--require-entry",
        action="store_true",
        help="exit 2 unless execution is authorized (NO_ENTRY and scope waiver both fail)",
    )
    args = parser.parse_args(argv)
    payload = build_freeze(
        repo_root=args.repo_root,
        raw_path=args.raw_path,
        manifest_path=args.manifest,
        track=args.track,
        static_gate=args.static_gate,
        active_gate=args.active_gate,
        architecture_commit=args.architecture_commit,
        min_effect=args.min_effect,
        discordance=args.discordance,
        missingness=args.missingness,
        near_threshold=args.near_threshold,
        exposure_paths=args.exposure_path,
        include_git_history=not args.skip_git_history,
        scope_waiver=args.scope_waiver,
    )
    if args.output:
        _write_json(args.output, payload)
    else:
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 2 if args.require_entry and not payload["entry_decision"]["allowed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
