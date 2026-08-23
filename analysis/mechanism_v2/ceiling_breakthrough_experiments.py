#!/usr/bin/env python3
"""Frozen, outcome-blind experiments for the conversion-ceiling hypotheses.

This module deliberately separates four operations:

``freeze`` builds target-blind inputs; ``gate`` decides whether an experiment
is admissible; ``run`` compiles immutable online jobs; and ``analyse`` joins
responses to separately held adjudicated relations under intention-to-analyse
(ITA).  The provenance of those relations is always explicit in analysis
output; the default is a three-model-panel sensitivity endpoint, not human-root
truth.

The module never imports or calls an LLM client.  ``run`` means *compile the
validated jobs to be submitted by the repository's audited online runner*.
This makes freeze/gate/analyse safe to replay and prevents an exploratory
command from silently spending API budget or observing outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict, deque
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import (  # noqa: E402
    ROOT,
    FrozenExactSynonymBridge,
    file_sha256,
    normalize_label,
    source_commit,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    assert_target_blind,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    stable_seed,
)


SCHEMA = "ceiling_breakthrough_experiments_v1"
E4_POOLS = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/canonical_pools.jsonl"
E4_JOINED = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/E4_JOINED_RESULTS.tar.gz"
E5_JOINED = ROOT / "analysis/mechanism_v2/results/E5_candidate_interference/E5_JOINED_RESULTS.tar.gz"
BRIDGE = ROOT / "data/knowledge_raw/disease_name_bridge.json"
SNOMED_CONCEPTS = ROOT / "data/knowledge_raw/snomed_concepts.json"
SNOMED_TERMS = ROOT / "data/knowledge_raw/snomed_term_index.json"
SNOMED_RELATIONS = ROOT / "data/knowledge_raw/snomed_relations.json"

ADMISSION_ARMS = ("fixed_k", "typed_fixed_k", "qualified_frontier", "sham_qualification")
ADMISSION_CONSTRUCTION_MODEL = "google/gemini-2.5-flash"
ADMISSION_OPERATIONAL_NO_GO = "NOT_EXECUTED_OPERATIONAL_NO_GO"
CLOSURE_GATE_REVIEW_MODELS = frozenset({
    "anthropic/claude-sonnet-4.6",
    "openai/gpt-5.6-sol",
})
CLOSURE_COMPARATOR_MODEL = "google/gemini-2.5-flash"
FACTORIZATION_ARMS = (
    "flat",
    "exact_identity",
    "factorized_lattice",
    "structure_sham",
    "corrupted_modifier_mapping",
)
ACTIVE_ARMS = ("no_acquisition", "typed_action", "cost_matched_random")
RELATION_ARMS = ("no_relation", "validated_relation", "inverse_corrupted", "node_only_sham")

RELATION_EXPECTED_CASES = 96
RELATION_PRECOLLAPSE_EDGES = 124
RELATION_EXPECTED_EDGES = 122
RELATION_EXPECTED_DUPLICATE_COLLAPSE = 2
RELATION_EXPECTED_FAMILY = {"DA": 53, "MCR": 43}
SNOMED_RELEASE_ID = "SnomedCT_ManagedServiceUS_PRODUCTION_US1000124_20260301T120000Z"
SNOMED_SOURCE_ARCHIVE = f"{SNOMED_RELEASE_ID}.zip"
DEFAULT_TRUTH_PROVENANCE = "three_model_adjudicated_panel_sensitivity"
FACTORIZATION_PAIR_PRECISION_MIN = 0.95
FACTORIZATION_MODIFIER_AXIS_MIN = 0.85

RELATION_CODES = frozenset({"C", "P", "X", "M", "N", "U"})
MODIFIER_AXES = (
    "etiology",
    "anatomy",
    "time_stage",
    "subtype",
    "complication",
    "composite_components",
)
ACTION_STATUSES = frozenset({"performed", "not_available", "not_performed"})
NEED_TYPES = frozenset({
    "etiology", "anatomy", "time_stage", "subtype", "complication",
    "object_identity", "disease_presence", "other", "unresolved",
})
ALL_ARM_IDS = ADMISSION_ARMS + FACTORIZATION_ARMS + ACTIVE_ARMS + RELATION_ARMS + ("typed_policy",)
FORBIDDEN_PROMPT_MARKERS = frozenset(
    {
        "arm=",
        "arm =",
        "gold",
        "ground truth",
        "reference diagnosis",
        "historical champion",
        "previous champion",
        "observed outcome",
        "correct answer",
        "audit_is_gold",
        "source_option",
        *(arm.lower() for arm in ALL_ARM_IDS),
        *(arm.lower().replace("_", " ") for arm in ALL_ARM_IDS),
    }
)

# Stronger than the generic online-runner list because historical E4/E5 rows
# contain additional audit-only and post-treatment fields.
LOCAL_FORBIDDEN_KEYS = frozenset(
    {
        "gold",
        "gold_candidate_ids",
        "audit_is_gold",
        "source_option",
        "champion",
        "champion_id",
        "champion_label",
        "champion_relation",
        "historical_champions",
        "response",
        "success",
        "strict_top1",
        "gold_rank",
        "gold_top1",
        "gold_top1_by_id",
        "outcome",
    }
)

COMMON_SELECTOR_CONTRACT = """Choose exactly one supplied candidate ID.  Candidate order is
arbitrary.  Patient observations must come only from exact supplied vignette spans; medical
background must be marked as background.  Do not invent, rename, merge, or compose a diagnosis.
Return strict JSON: {"champion_id":"...","runner_up_id":"... or empty","margin":"high|medium|low",
"decisive_spans":[{"start":0,"end":1,"text":"exact vignette substring"}],"rationale":"brief"}."""

FACTORIZATION_SELECTOR_CONTRACT = """Choose exactly one supplied candidate ID. Candidate order is
arbitrary. Patient observations must come only from exact supplied vignette spans; medical
background must be marked as background. Do not invent, rename, merge, or compose a diagnosis.
Report modifier_hallucination=true only if the decision introduces a modifier absent from the
supplied surface label or treats an unsupported supplied modifier obligation as supported; this
boolean is mandatory. Return strict JSON: {"champion_id":"...","runner_up_id":"... or empty",
"margin":"high|medium|low","modifier_hallucination":false,"decisive_spans":[{"start":0,
"end":1,"text":"exact vignette substring"}],"rationale":"brief"}."""

LATTICE_SELECTOR_CONTRACT = """Execute the supplied core/member lattice. First select exactly one
supplied core_id, then choose an existing surface candidate connected to that core. For every
modifier-obligation axis on the chosen surface candidate, report whether the visible patient
evidence supports it; an unsupported obligation must remain unsupported and must never be erased or
filled. Candidate order is arbitrary. Patient observations must come only from exact supplied
vignette spans; medical background must be marked as background. Do not invent, rename, merge, or
compose a diagnosis. Return strict JSON: {"selected_core_id":"...","champion_id":"...",
"runner_up_id":"... or empty","margin":"high|medium|low","modifier_hallucination":false,
"obligation_check":
{"axis":"supported|unsupported"},"decisive_spans":[{"start":0,"end":1,
"text":"exact vignette substring"}],"rationale":"brief"}."""

PROMPTS = {
    "admission": {
        # The four membership treatments use a byte-identical comparator.
        # Neither the treatment name nor the admission rule is disclosed.
        arm: "Compare only the supplied main candidate frontier. The residual ledger preserves coverage and must not participate in this first-pass decision.\n"
        + COMMON_SELECTOR_CONTRACT
        for arm in ADMISSION_ARMS
    },
    "factorization": {
        "flat": "Compare the supplied candidate labels.\n" + FACTORIZATION_SELECTOR_CONTRACT,
        "exact_identity": "Use only the supplied exact-identity core/member lattice.\n" + LATTICE_SELECTOR_CONTRACT,
        # Byte-identical instructions isolate the supplied topology/mapping;
        # the treatment name is never disclosed to the comparator.
        "factorized_lattice": LATTICE_SELECTOR_CONTRACT,
        "structure_sham": LATTICE_SELECTOR_CONTRACT,
        "corrupted_modifier_mapping": LATTICE_SELECTOR_CONTRACT,
    },
    "active_policy": """From the supplied initial presentation and action menu, state the top pair,
the one missing discriminator type, and select exactly one available action.  Do not infer a hidden
result. Return strict JSON: {"top_pair":["ID","ID"],"need_type":"...","action_id":"A#",
"expected_result_and_odds_shift":"brief","abstain":false}.""",
    "active_post": {
        # The evidence release itself is the treatment; all post-release
        # comparators receive exactly the same instruction.
        arm: "Use only patient evidence explicitly present or released in this payload.\n"
        + COMMON_SELECTOR_CONTRACT
        for arm in ACTIVE_ARMS
    },
    "relation": {
        # Edge semantics/availability vary in the payload, never in an arm tag.
        arm: "Any supplied relations are taxonomy background, never patient observations or votes.\n"
        + COMMON_SELECTOR_CONTRACT
        for arm in RELATION_ARMS
    },
}


def _json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _tar_jsonl(path: Path, member: str = "case_conditions.jsonl") -> list[dict[str, Any]]:
    with tarfile.open(path, "r:gz") as archive:
        handle = archive.extractfile(member)
        if handle is None:
            raise FileNotFoundError(f"{member} absent from {path}")
        return [json.loads(line) for line in handle if line.strip()]


def _write_freeze(out: Path, component: str, rows: list[dict[str, Any]], sources: Sequence[Path], **extra: Any) -> dict[str, Any]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        _assert_blind(row)
    write_jsonl(out / "cases.jsonl", rows)
    source_artifacts: list[dict[str, str]] = []
    for source in sources:
        source_path = Path(source).resolve()
        try:
            display_path = str(source_path.relative_to(ROOT))
        except ValueError:
            display_path = str(source_path)
        source_artifacts.append({"path": display_path, "sha256": file_sha256(source_path)})
    manifest = {
        "schema": SCHEMA,
        "kind": "freeze",
        "component": component,
        "source_commit": source_commit(),
        "generator_code_sha256": file_sha256(Path(__file__)),
        "source_artifacts": source_artifacts,
        "case_n": len(rows),
        "family_n": dict(sorted(Counter(str(r.get("family")) for r in rows).items())),
        "cases_sha256": canonical_sha256(rows),
        "outcome_blind": True,
        **extra,
    }
    manifest["freeze_id"] = canonical_sha256(manifest)
    atomic_json(out / "freeze.json", manifest)
    return manifest


def _formal_freeze_validation(
    freeze_dir: Path,
    component: str,
    arms: Sequence[str],
    *,
    expected_case_n: int | None = None,
    expected_family_n: Mapping[str, int] | None = None,
    expected_sources: Sequence[Path] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Revalidate the immutable freeze contract at every scientific gate."""
    freeze_dir = Path(freeze_dir)
    manifest_path = freeze_dir / "freeze.json"
    cases_path = freeze_dir / "cases.jsonl"
    failures: list[str] = []
    if not manifest_path.is_file() or not cases_path.is_file():
        return {}, read_jsonl(cases_path), ["freeze_artifact_missing"]
    freeze = _json(manifest_path)
    cases = read_jsonl(cases_path)
    observed_family = dict(sorted(Counter(str(row.get("family")) for row in cases).items()))
    if (
        freeze.get("schema") != SCHEMA
        or freeze.get("kind") != "freeze"
        or freeze.get("component") != component
        or not bool(freeze.get("outcome_blind"))
        or int(freeze.get("case_n") or -1) != len(cases)
        or str(freeze.get("cases_sha256") or "") != canonical_sha256(cases)
        or freeze.get("arms") != list(arms)
    ):
        failures.append("freeze_contract_identity_invalid")
    if expected_case_n is not None and len(cases) != expected_case_n:
        failures.append("freeze_expected_case_count_invalid")
    if expected_family_n is not None and (
        observed_family != dict(expected_family_n)
        or freeze.get("family_n") != dict(expected_family_n)
    ):
        failures.append("freeze_expected_family_contract_invalid")
    case_keys = [str(row.get("case_key") or "") for row in cases]
    if "" in case_keys or len(case_keys) != len(set(case_keys)):
        failures.append("freeze_case_key_identity_invalid")
    for index, case in enumerate(cases):
        try:
            _assert_blind(case, f"freeze.cases[{index}]")
        except AssertionError:
            failures.append("freeze_outcome_blinding_contract_invalid")
            break
    if str(freeze.get("freeze_id") or "") != canonical_sha256(
        {key: value for key, value in freeze.items() if key != "freeze_id"}
    ):
        failures.append("freeze_id_mismatch")
    if (
        not str(freeze.get("source_commit") or "")
        or str(freeze.get("generator_code_sha256") or "") != file_sha256(Path(__file__))
    ):
        failures.append("freeze_generator_code_binding_invalid")
    source_artifacts = freeze.get("source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        failures.append("freeze_source_artifacts_missing")
    else:
        declared_sources: dict[Path, str] = {}
        for index, artifact in enumerate(source_artifacts):
            if not isinstance(artifact, Mapping):
                failures.append(f"freeze_source_artifact_{index}_invalid")
                continue
            source_path = Path(str(artifact.get("path") or ""))
            if not source_path.is_absolute():
                source_path = ROOT / source_path
            source_path = source_path.resolve()
            if source_path in declared_sources:
                failures.append("freeze_source_artifact_identity_duplicate")
            declared_sources[source_path] = str(artifact.get("sha256") or "")
            if (
                not source_path.is_file()
                or file_sha256(source_path) != str(artifact.get("sha256") or "")
            ):
                failures.append(f"freeze_source_artifact_{index}_hash_mismatch")
        if expected_sources is not None:
            expected_source_map = {
                Path(path).resolve(): file_sha256(Path(path).resolve())
                for path in expected_sources
            }
            if declared_sources != expected_source_map:
                failures.append("freeze_expected_source_identity_invalid")
    return freeze, cases, failures


def _assert_blind(value: Any, path: str = "payload") -> None:
    assert_target_blind(value, path)
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in LOCAL_FORBIDDEN_KEYS:
                raise AssertionError(f"post-treatment/target leak at {path}.{key}")
            _assert_blind(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_blind(child, f"{path}[{index}]")


def _assert_prompt_blind(prompt: str) -> None:
    """Fail closed if a selector instruction discloses treatment or outcome."""
    normalized = " ".join(str(prompt).lower().split())
    for marker in sorted(FORBIDDEN_PROMPT_MARKERS, key=lambda value: (-len(value), value)):
        if marker and marker in normalized:
            raise AssertionError(f"selector prompt leaks treatment/outcome marker: {marker!r}")


def _e4_vignettes(path: Path = E4_JOINED) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in _tar_jsonl(path):
        output.setdefault(str(row["case_key"]), str(row["vignette"]))
    return output


def _clean_candidates(candidates: Iterable[Mapping[str, Any]], *, evidence: bool) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for raw in candidates:
        row = {"candidate_id": str(raw["candidate_id"]), "label": str(raw["label"])}
        if evidence:
            row["support_items"] = [str(x) for x in raw.get("support_items") or []]
            row["contradict_items"] = [str(x) for x in raw.get("contradict_items") or []]
        clean.append(row)
    return clean


def _e5_base4(path: Path = E5_JOINED) -> list[dict[str, Any]]:
    rows = [row for row in _tar_jsonl(path) if row.get("arm") == "base4"]
    if len(rows) != 200 or Counter(row["family"] for row in rows) != {"DA": 100, "MCR": 100}:
        raise AssertionError("frozen E5 base4 pool must be exactly 200 cases (DA100/MCR100)")
    return sorted(rows, key=lambda r: str(r["case_key"]))


def _spans(vignette: str, text: str) -> list[dict[str, Any]]:
    """Return case-sensitive literal offsets; normalization is forbidden."""
    output: list[dict[str, Any]] = []
    start = 0
    while text and (index := vignette.find(text, start)) >= 0:
        output.append({"start": index, "end": index + len(text), "text": text})
        start = index + max(1, len(text))
    return output


def _load_typing(path: Path | None) -> dict[str, dict[str, Any]]:
    return {str(row["case_key"]): row for row in read_jsonl(path)} if path else {}


def _admission_type_match(requested_kind: Any, candidate_kind: Any) -> bool:
    """Match only positively resolved object kinds; ``unresolved`` never admits."""
    requested = str(requested_kind or "").strip()
    candidate = str(candidate_kind or "").strip()
    return requested not in {"", "unresolved"} and candidate not in {"", "unresolved"} and candidate == requested


def _build_admission_cases(
    *, pools: Path, joined: Path, typings: Mapping[str, Mapping[str, Any]], k: int
) -> list[dict[str, Any]]:
    """Deterministically project E4 proposals and typing rows into C1 arms."""
    vignettes = _e4_vignettes(joined)
    rows: list[dict[str, Any]] = []
    for raw in read_jsonl(pools):
        case_key = str(raw["case_key"])
        vignette = vignettes[case_key]
        candidates = _clean_candidates(raw["pool"]["candidates"], evidence=True)
        span_counts: Counter[tuple[int, int, str]] = Counter()
        grounded: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            hits: list[dict[str, Any]] = []
            for item in candidate["support_items"]:
                hits.extend(_spans(vignette, item))
            # Duplicate source paraphrases pointing at the same literal span
            # are one proposition and never multiple admission votes.
            unique_hits = list({(h["start"], h["end"], h["text"]): h for h in hits}.values())
            grounded[candidate["candidate_id"]] = sorted(unique_hits, key=lambda h: (h["start"], h["end"]))
            span_counts.update((h["start"], h["end"], normalize_label(h["text"])) for h in unique_hits)
        type_row = typings.get(case_key) or {}
        requested_kind = str((type_row.get("requested_object") or {}).get("kind") or "")
        type_by_id = {str(x["candidate_id"]): str(x.get("object_kind") or "") for x in type_row.get("candidates") or []}
        typed_eligible_ids = [
            c["candidate_id"]
            for c in candidates
            if _admission_type_match(requested_kind, type_by_id.get(c["candidate_id"]))
        ]
        qualified_ids = [
            c["candidate_id"] for c in candidates
            if c["candidate_id"] in typed_eligible_ids
            and any(span_counts[(h["start"], h["end"], normalize_label(h["text"]))] == 1 for h in grounded[c["candidate_id"]])
        ]
        # Fail closed: never untyped-backfill or manufacture a minimum width.
        sham_ids = sorted(
            typed_eligible_ids,
            key=lambda cid: (stable_seed("admission-sham-v1", case_key, cid), cid),
        )[: len(qualified_ids)]
        fixed_ids = [c["candidate_id"] for c in candidates[:k]]
        typed_ids = typed_eligible_ids[:k]
        # No untyped backfill: an absent typing annotation remains an explicit
        # readiness failure rather than silently reducing to fixed-k.
        arms = {
            "fixed_k": fixed_ids,
            "typed_fixed_k": typed_ids,
            "qualified_frontier": qualified_ids,
            "sham_qualification": sham_ids,
        }
        candidate_by_id = {c["candidate_id"]: c for c in candidates}
        rows.append({
            "case_key": case_key,
            "family": str(raw["family"]),
            "vignette": vignette,
            "requested_object": type_row.get("requested_object") or {"kind": "unresolved", "explicit_modifier_axes": []},
            "proposal_union": candidates,
            "typing_eligible_ids": typed_eligible_ids,
            "object_kind_by_id": type_by_id,
            "grounded_spans": grounded,
            "arms": {
                arm: {
                    "main_frontier": [candidate_by_id[cid] for cid in ids],
                    "residual_ledger": [candidate_by_id[cid] for cid in candidate_by_id if cid not in set(ids)],
                }
                for arm, ids in arms.items()
            },
        })
    return rows


def freeze_admission(out: Path, *, pools: Path = E4_POOLS, joined: Path = E4_JOINED, typing: Path | None = None, k: int = 4) -> dict[str, Any]:
    """Freeze four admission arms without consulting candidate/reference truth."""
    rows = _build_admission_cases(
        pools=pools, joined=joined, typings=_load_typing(typing), k=k
    )
    return _write_freeze(out, "admission", rows, [pools, joined] + ([typing] if typing else []), arms=list(ADMISSION_ARMS), k=k)


def gate_admission(freeze_dir: Path, out: Path) -> dict[str, Any]:
    rows = read_jsonl(Path(freeze_dir) / "cases.jsonl")
    freeze_path = Path(freeze_dir) / "freeze.json"
    freeze = _json(freeze_path) if freeze_path.is_file() else {}
    k = int(freeze.get("k") or 4)
    failures: list[str] = []
    substantively_empty_typed: list[str] = []
    if not freeze_path.is_file():
        failures.append("freeze_manifest_missing")
    cases_sha256 = canonical_sha256(rows)
    if freeze_path.is_file():
        if (
            freeze.get("schema") != SCHEMA
            or freeze.get("kind") != "freeze"
            or freeze.get("component") != "admission"
            or not bool(freeze.get("outcome_blind"))
            or int(freeze.get("case_n") or -1) != len(rows)
            or str(freeze.get("cases_sha256") or "") != cases_sha256
            or freeze.get("family_n") != {"DA": 200, "MCR": 200}
            or freeze.get("arms") != list(ADMISSION_ARMS)
        ):
            failures.append("freeze_contract_binding_invalid")
        manifest_without_id = {key: value for key, value in freeze.items() if key != "freeze_id"}
        if str(freeze.get("freeze_id") or "") != canonical_sha256(manifest_without_id):
            failures.append("freeze_id_mismatch")
        source_artifacts = freeze.get("source_artifacts")
        if not isinstance(source_artifacts, list) or not source_artifacts:
            failures.append("freeze_source_artifacts_missing")
        for index, artifact in enumerate(source_artifacts or []):
            if not isinstance(artifact, Mapping):
                failures.append(f"freeze_source_artifact_{index}_invalid")
                continue
            source_path = Path(str(artifact.get("path") or ""))
            if not source_path.is_absolute():
                source_path = ROOT / source_path
            if (
                not source_path.is_file()
                or file_sha256(source_path) != str(artifact.get("sha256") or "")
            ):
                failures.append(f"freeze_source_artifact_{index}_hash_mismatch")
    for row in rows:
        universe = {c["candidate_id"] for c in row["proposal_union"]}
        if str(row["requested_object"].get("kind")) in {"", "unresolved"}:
            failures.append(f"{row['case_key']}:requested_object_unresolved")
        for arm in ADMISSION_ARMS:
            main = [c["candidate_id"] for c in row["arms"][arm]["main_frontier"]]
            residual = [c["candidate_id"] for c in row["arms"][arm]["residual_ledger"]]
            if set(main) & set(residual) or set(main) | set(residual) != universe or len(main) + len(residual) != len(universe):
                failures.append(f"{row['case_key']}:{arm}:ledger_partition")
        if len(row["arms"]["typed_fixed_k"]["main_frontier"]) == 0:
            # Pre-arm amendment 2026-08-18: an empty typed frontier blocks
            # readiness only when annotation is missing, since the arm would
            # otherwise collapse silently into fixed-k.  When the request is
            # positively resolved and every candidate is positively typed, the
            # emptiness is the frozen strict-equality rule's own outcome; the
            # case is carried into the arm, where it yields no evaluable Top-1
            # under the frozen ITA rule.
            kinds = row.get("object_kind_by_id") or {}
            request_resolved = str(row["requested_object"].get("kind")) not in {"", "unresolved"}
            all_positively_typed = bool(universe) and all(
                str(kinds.get(candidate_id) or "") not in {"", "unresolved"}
                for candidate_id in universe
            )
            if request_resolved and all_positively_typed:
                substantively_empty_typed.append(str(row["case_key"]))
            else:
                failures.append(f"{row['case_key']}:typed_frontier_empty")
        expected_typed_width = min(k, len(row.get("typing_eligible_ids") or []))
        if len(row["arms"]["typed_fixed_k"]["main_frontier"]) != expected_typed_width:
            failures.append(f"{row['case_key']}:typed_fixed_k_not_filled")
        qn = len(row["arms"]["qualified_frontier"]["main_frontier"])
        if qn != len(row["arms"]["sham_qualification"]["main_frontier"]):
            failures.append(f"{row['case_key']}:sham_width_mismatch")
    return _gate_write(out, "admission", not failures, failures, {
        "ledger_partition_rate": 1.0 if not any("ledger_partition" in x for x in failures) else 0.0,
        "requested_object_coverage": 1 - sum("requested_object_unresolved" in x for x in failures) / max(1, len(rows)),
        "freeze_id": freeze.get("freeze_id"),
        "cases_sha256": cases_sha256,
        "case_n": len(rows),
        "substantively_empty_typed_frontier_n": len(substantively_empty_typed),
        "substantively_empty_typed_frontier_cases": sorted(substantively_empty_typed),
    }, "pre-online structural readiness only; final admission efficacy gate is owned by analyse")


def gate_admission_operational(
    freeze_dir: Path,
    typing_dir: Path,
    readiness_gate: Path,
    c0_analysis: Path,
    operational_incident: Path,
    out: Path,
    *,
    report: Path | None = None,
    decision_out: Path | None = None,
) -> dict[str, Any]:
    """Record a C1 pre-execution No-Go without pretending to test efficacy.

    This path is intentionally narrow.  It accepts only a cache-only run of
    the preregistered construction model, an explicit failed admission
    readiness gate, the failed C0 release gate, and the recorded OpenRouter
    credit incident.  Any mismatch raises instead of silently broadening the
    meaning of ``NOT_EXECUTED_OPERATIONAL_NO_GO``.
    """
    freeze_dir = Path(freeze_dir)
    typing_dir = Path(typing_dir)
    paths = {
        "freeze_manifest": freeze_dir / "freeze.json",
        "freeze_cases": freeze_dir / "cases.jsonl",
        "typing_rows": typing_dir / "typing.jsonl",
        "typing_product_manifest": typing_dir / "admission_typing.manifest.json",
        "typing_stage_manifest": typing_dir / "online" / "manifest.json",
        "typing_raw_results": typing_dir / "online" / "raw_results.jsonl",
        "typing_telemetry_log": typing_dir / "online" / "telemetry.jsonl",
        "typing_telemetry_summary": typing_dir / "online" / "telemetry_summary.json",
        "readiness_gate": Path(readiness_gate),
        "c0_analysis": Path(c0_analysis),
        "operational_incident": Path(operational_incident),
        "gate_code": Path(__file__),
        "typing_runner_code": ROOT / "analysis/mechanism_v2/ceiling_closure_online.py",
        "online_runner_code": ROOT / "analysis/mechanism_v2/online_runner.py",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"C1 operational gate inputs missing: {', '.join(missing)}")

    freeze = _json(paths["freeze_manifest"])
    cases = read_jsonl(paths["freeze_cases"])
    typing_rows = read_jsonl(paths["typing_rows"])
    typing_manifest = _json(paths["typing_product_manifest"])
    typing_stage = _json(paths["typing_stage_manifest"])
    typing_raw = read_jsonl(paths["typing_raw_results"])
    typing_telemetry_log = read_jsonl(paths["typing_telemetry_log"])
    typing_telemetry = _json(paths["typing_telemetry_summary"])
    readiness = _json(paths["readiness_gate"])
    c0 = _json(paths["c0_analysis"])
    incident = _json(paths["operational_incident"])

    if (
        freeze.get("schema") != SCHEMA
        or freeze.get("kind") != "freeze"
        or freeze.get("component") != "admission"
        or not bool(freeze.get("outcome_blind"))
        or int(freeze.get("case_n") or -1) != len(cases)
        or freeze.get("family_n") != {"DA": 200, "MCR": 200}
        or freeze.get("arms") != list(ADMISSION_ARMS)
        or int(freeze.get("k") or -1) != 4
    ):
        raise AssertionError("invalid admission freeze manifest")
    if canonical_sha256(cases) != str(freeze.get("cases_sha256") or ""):
        raise AssertionError("admission freeze cases hash mismatch")
    if str(freeze.get("freeze_id") or "") != canonical_sha256(
        {key: value for key, value in freeze.items() if key != "freeze_id"}
    ):
        raise AssertionError("admission freeze ID mismatch")
    source_artifacts = freeze.get("source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        raise AssertionError("admission freeze source artifacts missing")
    declared_freeze_sources: dict[Path, str] = {}
    for artifact in source_artifacts:
        if not isinstance(artifact, Mapping):
            raise AssertionError("admission freeze source artifact invalid")
        source_path = Path(str(artifact.get("path") or ""))
        if not source_path.is_absolute():
            source_path = ROOT / source_path
        source_path = source_path.resolve()
        if source_path in declared_freeze_sources:
            raise AssertionError("duplicate admission freeze source artifact")
        declared_freeze_sources[source_path] = str(artifact.get("sha256") or "")
        if (
            not source_path.is_file()
            or file_sha256(source_path) != str(artifact.get("sha256") or "")
        ):
            raise AssertionError("admission freeze source artifact hash mismatch")
    expected_freeze_sources = {
        E4_POOLS.resolve(): file_sha256(E4_POOLS),
        E4_JOINED.resolve(): file_sha256(E4_JOINED),
        paths["typing_rows"].resolve(): file_sha256(paths["typing_rows"]),
    }
    if declared_freeze_sources != expected_freeze_sources:
        raise AssertionError("admission freeze source identity mismatch")
    case_keys = [str(case["case_key"]) for case in cases]
    if len(case_keys) != len(set(case_keys)):
        raise AssertionError("duplicate admission freeze case_key")
    typing_keys = [str(row["case_key"]) for row in typing_rows]
    if len(typing_keys) != len(set(typing_keys)) or set(typing_keys) != set(case_keys):
        raise AssertionError("typing rows do not exactly cover the admission freeze")
    typing_by_key = {str(row["case_key"]): row for row in typing_rows}

    if typing_manifest.get("product") != "admission_typing":
        raise AssertionError("invalid admission typing product manifest")
    declared_typing_inputs: dict[Path, str] = {}
    for item in typing_manifest.get("input_files") or []:
        if not isinstance(item, Mapping):
            raise AssertionError("invalid admission typing input binding")
        input_path = Path(str(item.get("path") or ""))
        if not input_path.is_absolute():
            input_path = ROOT / input_path
        declared_typing_inputs[input_path.resolve()] = str(item.get("sha256") or "")
    if declared_typing_inputs != {
        E4_POOLS.resolve(): file_sha256(E4_POOLS),
        E4_JOINED.resolve(): file_sha256(E4_JOINED),
    }:
        raise AssertionError("admission typing source identity mismatch")
    declared_commits = {
        str(freeze.get("source_commit") or ""),
        str(typing_manifest.get("source_commit") or ""),
        str(typing_stage.get("source_commit") or ""),
    }
    if len(declared_commits) != 1 or "" in declared_commits:
        raise AssertionError("admission freeze/typing source commits do not match")
    if (
        str(freeze.get("generator_code_sha256") or "") != file_sha256(paths["gate_code"])
        or str(typing_manifest.get("generator_code_sha256") or "")
        != file_sha256(paths["typing_runner_code"])
        or str(typing_stage.get("runner_code_sha256") or "")
        != file_sha256(paths["typing_runner_code"])
        or str(typing_stage.get("online_runner_code_sha256") or "")
        != file_sha256(paths["online_runner_code"])
    ):
        raise AssertionError("admission generator code binding mismatch")
    if str(typing_manifest.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL:
        raise AssertionError("typing product did not use the frozen construction model")
    if int(typing_manifest.get("row_n") or -1) != len(typing_rows):
        raise AssertionError("typing product row count mismatch")
    if file_sha256(paths["typing_rows"]) != str(typing_manifest.get("file_sha256") or ""):
        raise AssertionError("typing product file hash mismatch")
    if canonical_sha256(typing_rows) != str(typing_manifest.get("rows_sha256") or ""):
        raise AssertionError("typing product semantic hash mismatch")
    if str(typing_stage.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL:
        raise AssertionError("typing stage did not use the frozen construction model")
    telemetry = typing_stage.get("telemetry_summary") or {}
    if not bool(typing_stage.get("cache_only")):
        raise AssertionError("C1 operational gate requires cache-only typing")
    if bool(typing_stage.get("api_called")) or int(telemetry.get("semantic_calls") or 0) or int(telemetry.get("physical_attempts") or 0):
        raise AssertionError("cache-only typing manifest records an API call")
    task_n = int(typing_stage.get("task_n") or -1)
    success_n = int(typing_stage.get("success_n") or 0)
    failure_n = int(typing_stage.get("failure_n") or 0)
    if task_n != 2 * len(cases) or success_n + failure_n != task_n:
        raise AssertionError("typing stage task denominator mismatch")
    # Reconstruct every immutable task identity from the frozen cases and the
    # exact current prompt/module contracts.  This prevents a self-consistent
    # but fabricated raw-results/manifest pair from establishing cache lookup.
    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
        CANDIDATE_TYPER_PROMPT,
        REQUESTED_OBJECT_PROMPT,
    )

    task_contracts: list[dict[str, Any]] = []
    expected_by_task: dict[str, dict[str, Any]] = {}
    stage_specs = (
        ("requested_object", "CeilingAdmissionRequestedObject", REQUESTED_OBJECT_PROMPT),
        ("candidate_typer", "CeilingAdmissionCandidateTyper", CANDIDATE_TYPER_PROMPT),
    )
    for case in sorted(cases, key=lambda row: str(row["case_key"])):
        proposal_rows = case.get("proposal_union") or []
        proposal_ids = [str(row.get("candidate_id") or "") for row in proposal_rows]
        if "" in proposal_ids or len(proposal_ids) != len(set(proposal_ids)):
            raise AssertionError(f"duplicate or empty admission candidate ID: {case['case_key']}")
        candidates = [
            {"candidate_id": str(row["candidate_id"]), "label": str(row["label"])}
            for row in proposal_rows
        ]
        payloads = {
            "requested_object": {
                "case_key": str(case["case_key"]),
                "vignette": str(case["vignette"]),
            },
            "candidate_typer": {
                "case_key": str(case["case_key"]),
                "candidates": candidates,
            },
        }
        for stage_name, module, prompt in stage_specs:
            task_id = f"{case['case_key']}|{stage_name}"
            prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            payload_sha = canonical_sha256(payloads[stage_name])
            cache_key = canonical_sha256({
                "schema": "mechanism_v2_online_call_v1",
                "model": ADMISSION_CONSTRUCTION_MODEL,
                "module": module,
                "prompt_sha256": prompt_sha,
                "payload_sha256": payload_sha,
                "temperature": 0.0,
            })
            expected_by_task[task_id] = {
                "case_key": str(case["case_key"]),
                "stage": stage_name,
                "module": module,
                "prompt": prompt,
                "prompt_sha256": prompt_sha,
                "payload": payloads[stage_name],
                "payload_sha256": payload_sha,
                "cache_key": cache_key,
            }
            task_contracts.append({
                "task_id": task_id,
                "module": module,
                "prompt": prompt,
                "payload": payloads[stage_name],
            })

    raw_task_ids = [str(row.get("task_id") or "") for row in typing_raw]
    observed_raw_keys = {
        (str(row.get("case_key") or ""), str(row.get("stage") or ""))
        for row in typing_raw
    }
    expected_raw_keys = {
        (str(value["case_key"]), str(value["stage"]))
        for value in expected_by_task.values()
    }
    if (
        len(typing_raw) != task_n
        or len(raw_task_ids) != len(set(raw_task_ids))
        or "" in raw_task_ids
        or set(raw_task_ids) != set(expected_by_task)
        or observed_raw_keys != expected_raw_keys
        or any(str(row.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL for row in typing_raw)
        or sum(bool(row.get("success")) for row in typing_raw) != success_n
        or sum(not bool(row.get("success")) for row in typing_raw) != failure_n
        or sum(bool(row.get("cache_hit")) for row in typing_raw)
        != int(typing_stage.get("cache_hit_n") or 0)
    ):
        raise AssertionError("typing raw-results identity or count mismatch")
    for row in typing_raw:
        expected = expected_by_task[str(row["task_id"])]
        cache_hit = bool(row.get("cache_hit"))
        if (
            str(row.get("case_key") or "") != expected["case_key"]
            or str(row.get("stage") or "") != expected["stage"]
            or str(row.get("prompt_sha256") or "") != expected["prompt_sha256"]
            or str(row.get("payload_sha256") or "") != expected["payload_sha256"]
            or (
                cache_hit
                and str(row.get("cache_key") or "") != expected["cache_key"]
            )
            or (
                not cache_hit
                and (
                    str(row.get("cache_key") or "") != ""
                    or bool(row.get("success"))
                    or bool(row.get("response"))
                    or str(row.get("error") or "")
                    != "FileNotFoundError: required immutable cache record missing: "
                    + expected["cache_key"]
                )
            )
        ):
            raise AssertionError(f"typing immutable task binding mismatch: {row.get('task_id')}")
    raw_by_task = {str(row["task_id"]): row for row in typing_raw}
    for case in cases:
        case_key = str(case["case_key"])
        parser = raw_by_task[f"{case_key}|requested_object"]
        typer = raw_by_task[f"{case_key}|candidate_typer"]
        requested = (
            parser["response"].get("requested_object") if parser["success"] else None
        ) or {"kind": "unresolved", "explicit_modifier_axes": []}
        typed = {
            str(row["candidate_id"]): row
            for row in (typer["response"].get("candidates") or [])
        } if typer["success"] else {}
        expected_typing_row = {
            "case_key": case_key,
            "requested_object": requested,
            "candidates": [
                {
                    "candidate_id": str(candidate["candidate_id"]),
                    "object_kind": str(
                        (typed.get(str(candidate["candidate_id"])) or {}).get("object_kind")
                        or "unresolved"
                    ),
                }
                for candidate in case.get("proposal_union") or []
            ],
            "annotation_success": bool(parser["success"] and typer["success"]),
            "stage_errors": {
                "requested_object": parser["error"],
                "candidate_typer": typer["error"],
            },
            "provenance": "outcome_blind_model_annotation",
        }
        if canonical_sha256(typing_by_key[case_key]) != canonical_sha256(expected_typing_row):
            raise AssertionError(f"typing derived product mismatch: {case_key}")
    if (
        file_sha256(paths["typing_raw_results"])
        != str(typing_stage.get("results_file_sha256") or "")
        or canonical_sha256(typing_raw) != str(typing_stage.get("results_sha256") or "")
        or canonical_sha256(task_contracts)
        != str(typing_stage.get("semantic_input_sha256") or "")
        or sorted({value["prompt_sha256"] for value in expected_by_task.values()})
        != list(typing_stage.get("prompt_sha256s") or [])
    ):
        raise AssertionError("typing raw-results hash mismatch")
    if (
        typing_telemetry_log
        or typing_telemetry != aggregate_telemetry([])
        or
        file_sha256(paths["typing_telemetry_log"])
        != str(typing_stage.get("telemetry_sha256") or "")
        or aggregate_telemetry(typing_telemetry_log) != typing_telemetry
        or typing_telemetry != telemetry
    ):
        raise AssertionError("typing telemetry summary mismatch")
    if (
        int(typing_telemetry.get("semantic_calls") or 0) != 0
        or int(typing_telemetry.get("physical_attempts") or 0) != 0
    ):
        raise AssertionError("typing telemetry records provider calls")
    stage_hash = file_sha256(paths["typing_stage_manifest"])
    if not any(
        str(item.get("sha256") or "") == stage_hash
        for item in typing_manifest.get("online_stage_manifests") or []
    ):
        raise AssertionError("typing product does not bind the cache-only stage manifest")
    typing_hash = file_sha256(paths["typing_rows"])
    if not any(
        str(item.get("sha256") or "") == typing_hash
        for item in freeze.get("source_artifacts") or []
    ):
        raise AssertionError("admission freeze does not bind the typing rows")

    # Re-run the complete deterministic projection from the immutable E4
    # sources and the bound typing rows.  Checking only ledger partitions or
    # typed-set membership would allow a self-consistent but different
    # qualified/sham subset to masquerade as the preregistered freeze.
    expected_cases = _build_admission_cases(
        pools=E4_POOLS,
        joined=E4_JOINED,
        typings=typing_by_key,
        k=4,
    )
    if canonical_sha256(cases) != canonical_sha256(expected_cases):
        raise AssertionError("admission freeze deterministic projection mismatch")

    if readiness.get("component") != "admission" or bool(readiness.get("passed")):
        raise AssertionError("C1 operational gate requires an explicit failed admission readiness gate")
    readiness_metrics = readiness.get("metrics") or {}
    if (
        str(readiness_metrics.get("freeze_id") or "") != str(freeze.get("freeze_id") or "")
        or str(readiness_metrics.get("cases_sha256") or "")
        != str(freeze.get("cases_sha256") or "")
        or int(readiness_metrics.get("case_n") or -1) != len(cases)
    ):
        raise AssertionError("admission readiness gate is not bound to this freeze")
    c0_status = str(c0.get("release_status") or "")
    c0_reliability = c0.get("reliability_gate") or {}
    if (
        c0_status != "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY"
        or bool(c0.get("clinical_width_outputs_released"))
        or bool(c0_reliability.get("pass"))
    ):
        raise AssertionError("C0 evidence does not establish the frozen reliability No-Go")
    if (
        str(incident.get("provider_gateway") or "") != "OpenRouter"
        or str(incident.get("observed_error_class") or "") != "HTTP_402_INSUFFICIENT_CREDITS"
    ):
        raise AssertionError("operational incident does not establish OpenRouter credit exhaustion")

    annotation_success_n = sum(bool(row.get("annotation_success")) for row in typing_rows)
    requested_resolved_n = sum(
        str((row.get("requested_object") or {}).get("kind") or "") not in {"", "unresolved"}
        for row in typing_rows
    )
    candidate_n = sum(len(case.get("proposal_union") or []) for case in cases)
    candidate_typed_n = sum(
        str(candidate.get("object_kind") or "") not in {"", "unresolved"}
        for row in typing_rows
        for candidate in row.get("candidates") or []
    )
    for case in cases:
        proposal_rows = case.get("proposal_union") or []
        proposal_ids = [str(candidate["candidate_id"]) for candidate in proposal_rows]
        expected_ids = set(proposal_ids)
        typing_case = typing_by_key[str(case["case_key"])]
        typing_candidates = typing_case.get("candidates") or []
        observed_id_list = [str(candidate["candidate_id"]) for candidate in typing_candidates]
        observed_ids = set(observed_id_list)
        if (
            len(proposal_ids) != len(expected_ids)
            or len(observed_id_list) != len(observed_ids)
            or expected_ids != observed_ids
        ):
            raise AssertionError(f"typing candidate coverage mismatch: {case['case_key']}")
        requested_kind = str((typing_case.get("requested_object") or {}).get("kind") or "")
        type_by_id = {
            str(candidate["candidate_id"]): str(candidate.get("object_kind") or "")
            for candidate in typing_candidates
        }
        expected_typed = [
            candidate_id for candidate_id in proposal_ids
            if _admission_type_match(requested_kind, type_by_id.get(candidate_id))
        ]
        if (
            canonical_sha256(case.get("requested_object") or {})
            != canonical_sha256(typing_case.get("requested_object") or {})
            or case.get("object_kind_by_id") != type_by_id
            or list(case.get("typing_eligible_ids") or []) != expected_typed
        ):
            raise AssertionError(f"typing-to-freeze projection mismatch: {case['case_key']}")
        for arm in ADMISSION_ARMS:
            arm_state = (case.get("arms") or {}).get(arm) or {}
            main_ids = [str(row.get("candidate_id") or "") for row in arm_state.get("main_frontier") or []]
            residual_ids = [str(row.get("candidate_id") or "") for row in arm_state.get("residual_ledger") or []]
            if (
                len(main_ids) != len(set(main_ids))
                or len(residual_ids) != len(set(residual_ids))
                or set(main_ids) & set(residual_ids)
                or set(main_ids) | set(residual_ids) != expected_ids
                or len(main_ids) + len(residual_ids) != len(proposal_ids)
            ):
                raise AssertionError(f"admission arm ledger partition mismatch: {case['case_key']}:{arm}")
        fixed_ids = [
            str(row.get("candidate_id") or "")
            for row in case["arms"]["fixed_k"]["main_frontier"]
        ]
        typed_ids = [
            str(row.get("candidate_id") or "")
            for row in case["arms"]["typed_fixed_k"]["main_frontier"]
        ]
        qualified_ids = {
            str(row.get("candidate_id") or "")
            for row in case["arms"]["qualified_frontier"]["main_frontier"]
        }
        sham_ids = {
            str(row.get("candidate_id") or "")
            for row in case["arms"]["sham_qualification"]["main_frontier"]
        }
        if (
            fixed_ids != proposal_ids[:4]
            or typed_ids != expected_typed[:4]
            or not qualified_ids <= set(expected_typed)
            or not sham_ids <= set(expected_typed)
            or len(qualified_ids) != len(sham_ids)
        ):
            raise AssertionError(f"admission arm projection mismatch: {case['case_key']}")
    arm_slot_n = {
        arm: sum(len(case["arms"][arm]["main_frontier"]) for case in cases)
        for arm in ADMISSION_ARMS
    }
    failure_classes = Counter(str(value).rsplit(":", 1)[-1] for value in readiness.get("failures") or [])
    failures = [
        "upstream_c0_reliability_no_go",
        "openrouter_http_402_insufficient_credits",
        "admission_readiness_gate_not_passed",
    ]
    if annotation_success_n != len(cases) or success_n != task_n:
        failures.append("typing_cache_incomplete")

    def artifact(path: Path) -> dict[str, str]:
        resolved = path.resolve()
        try:
            display = str(resolved.relative_to(ROOT))
        except ValueError:
            display = str(resolved)
        return {"path": display, "sha256": file_sha256(resolved)}

    gate = {
        "schema": "ceiling_closure_admission_operational_gate_v1",
        "kind": "gate",
        "component": "admission",
        "gate_stage": "pre_execution_operational_admission",
        "decision": ADMISSION_OPERATIONAL_NO_GO,
        "status": ADMISSION_OPERATIONAL_NO_GO,
        "passed": False,
        "fail_closed": True,
        "offline_preflight_executed": True,
        "online_scientific_arms_executed": False,
        "selector_jobs_compiled": False,
        "efficacy_analysis_executed": False,
        "scientific_efficacy_evaluated": False,
        "scientific_invalidity_claimed": False,
        "scientific_result": "NOT_EVALUATED",
        "scientific_negative": False,
        "scientific_effect_interpretation_allowed": False,
        "model_substitution_allowed": False,
        "model_substitution_observed": False,
        "construction_model": ADMISSION_CONSTRUCTION_MODEL,
        "typing_execution_mode": "cache_only",
        "api_called": False,
        "implementation_corrections": [{
            "id": "unresolved_object_kind_is_never_an_admission_match",
            "rule": "both requested and candidate object kinds must be positively resolved and equal",
            "online_jobs_affected": 0,
        }],
        "failures": failures,
        "prerequisite_checks": {
            "c0_release_status": c0_status,
            "c0_reliability_gate_passed": False,
            "c0_clinical_width_outputs_released": False,
            "provider_gateway": "OpenRouter",
            "provider_error_class": "HTTP_402_INSUFFICIENT_CREDITS",
            "typing_cache_complete": annotation_success_n == len(cases) and success_n == task_n,
            "readiness_gate_passed": False,
        },
        "metrics": {
            "case_n": len(cases),
            "family_n": dict(sorted(Counter(str(case.get("family")) for case in cases).items())),
            "proposal_candidate_n": candidate_n,
            "typing_task_n": task_n,
            "typing_success_n": success_n,
            "typing_failure_n": failure_n,
            "typing_cache_hit_n": int(typing_stage.get("cache_hit_n") or 0),
            "annotation_success_n": annotation_success_n,
            "requested_object_resolved_n": requested_resolved_n,
            "candidate_typed_n": candidate_typed_n,
            "arm_main_frontier_slot_n": arm_slot_n,
            "readiness_failure_n": len(readiness.get("failures") or []),
            "readiness_failure_class_n": dict(sorted(failure_classes.items())),
            "scientific": {
                "fixed_k_service_rate": None,
                "fixed_k_ita_complete_rate": None,
                "fixed_k_complete_exposure_rate": None,
                "typed_fixed_k_service_rate": None,
                "typed_fixed_k_ita_complete_rate": None,
                "typed_fixed_k_complete_exposure_rate": None,
                "qualified_frontier_service_rate": None,
                "qualified_frontier_ita_complete_rate": None,
                "qualified_frontier_complete_exposure_rate": None,
                "sham_qualification_service_rate": None,
                "sham_qualification_ita_complete_rate": None,
                "sham_qualification_complete_exposure_rate": None,
                "qualified_vs_fixed_difference": None,
                "qualified_vs_fixed_bootstrap_95_lower": None,
                "qualified_vs_sham_difference": None,
                "qualified_vs_sham_bootstrap_95_lower": None,
                "qualified_complete_exposure_rate": None,
                "fixed_complete_exposure_rate": None,
                "complete_rescues": None,
                "catastrophic_substitutions": None,
            },
        },
        "input_artifacts": {name: artifact(path) for name, path in paths.items()},
        "claim_scope": (
            "C1 offline freeze/typing/readiness audit only. The four admission arms and their "
            "clinical efficacy were not executed; this operational No-Go neither validates nor "
            "invalidates the qualified-frontier hypothesis."
        ),
        "resume_conditions": [
            "restore OpenRouter capacity without changing the preregistered model",
            "complete the same immutable typing task identities",
            "pass the admission readiness gate before compiling selector jobs",
            "execute all four frozen arms before any efficacy claim",
        ],
    }
    atomic_json(Path(out), gate)

    if decision_out is not None:
        atomic_json(Path(decision_out), {
            "schema": "ceiling_closure_admission_operational_decision_v1",
            "kind": "decision",
            "component": "admission",
            "decision": ADMISSION_OPERATIONAL_NO_GO,
            "decision_class": "operational_no_go",
            "gate_sha256": file_sha256(Path(out)),
            "online_scientific_arms_executed": False,
            "scientific_result": "NOT_EVALUATED",
            "scientific_negative": False,
            "scientific_effect_interpretation_allowed": False,
            "construction_model": ADMISSION_CONSTRUCTION_MODEL,
            "model_substitution_observed": False,
            "api_called": False,
            "resume_conditions": gate["resume_conditions"],
            "claim_scope": gate["claim_scope"],
        })

    if report is not None:
        report = Path(report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "# C1 qualified-frontier admission closure\n\n"
            f"Status: **{ADMISSION_OPERATIONAL_NO_GO}**\n\n"
            "## Offline path executed\n\n"
            f"The outcome-blind E4 admission freeze contains {len(cases)} cases "
            f"({gate['metrics']['family_n'].get('DA', 0)} DA / "
            f"{gate['metrics']['family_n'].get('MCR', 0)} MCR) and {candidate_n:,} proposal "
            f"candidates. Under the preregistered construction-model identity "
            f"`{ADMISSION_CONSTRUCTION_MODEL}`, {task_n} immutable typing task identities were "
            f"checked in cache-only mode; no model inference was run. There were "
            f"{success_n} successes, {failure_n} explicit failures, "
            f"{gate['metrics']['typing_cache_hit_n']} cache hits, and zero API calls.\n\n"
            "The fail-closed typing projection retained every case and candidate but marked missing "
            "annotations unresolved. The structural readiness gate therefore did not pass; no "
            "selector jobs or four-arm clinical calls were compiled.\n\n"
            "## Fail-closed implementation correction\n\n"
            "The offline preflight exposed that the original matcher could treat the literal "
            "fallback value `unresolved` as a matching object type. It was corrected before any "
            "selector job was compiled: requested and candidate kinds must now both be positively "
            "resolved and equal. The bound main-frontier slot counts are: fixed-k "
            f"{gate['metrics']['arm_main_frontier_slot_n']['fixed_k']:,}, typed fixed-k "
            f"{gate['metrics']['arm_main_frontier_slot_n']['typed_fixed_k']:,}, qualified "
            f"{gate['metrics']['arm_main_frontier_slot_n']['qualified_frontier']:,}, and sham "
            f"{gate['metrics']['arm_main_frontier_slot_n']['sham_qualification']:,}.\n\n"
            "## Bound prerequisites\n\n"
            f"C0 remains `{c0_status}` with `clinical_width_outputs_released=false`. The recorded "
            "provider incident is `OpenRouter / HTTP_402_INSUFFICIENT_CREDITS`. No model substitution, "
            "threshold change, imputation, or uncached provider call was used. The machine-readable "
            "gate binds the generator code, freeze, typing rows, raw cache-lookup results, telemetry "
            "summary, stage/product manifests, readiness gate, C0 analysis and incident by SHA-256.\n\n"
            "## Interpretation boundary\n\n"
            "This is an operational pre-execution No-Go, not a failed C1 efficacy result and not "
            "evidence that qualified admission is scientifically invalid. C1 can resume only with "
            "the same frozen model/task identities after capacity is restored; the readiness gate "
            "must pass before arm execution.\n",
            encoding="utf-8",
        )
    return gate


def freeze_factorization(out: Path, *, joined: Path = E5_JOINED) -> dict[str, Any]:
    """Freeze separate object-factorizer and requested-object-parser jobs."""
    rows: list[dict[str, Any]] = []
    for raw in _e5_base4(joined):
        candidates = _clean_candidates(raw["candidates"], evidence=False)
        rows.append({
            "case_key": str(raw["case_key"]),
            "family": str(raw["family"]),
            "vignette": str(raw["vignette"]),
            "candidates": candidates,
            "annotation_jobs": [
                {"job_kind": "object_factorizer", "case_key": str(raw["case_key"]), "candidates": candidates},
                {"job_kind": "requested_object_parser", "case_key": str(raw["case_key"]), "vignette": str(raw["vignette"])},
            ],
        })
    return _write_freeze(out, "factorization", rows, [joined, BRIDGE], arms=list(FACTORIZATION_ARMS), estimand="conditional conversion given E5 gold-conditioned exposure; not recall or open-diagnosis accuracy")


def _annotation_index(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path)
    if len({str(r["case_key"]) for r in rows}) != len(rows):
        raise AssertionError("duplicate annotation case_key")
    return {str(r["case_key"]): r for r in rows}


def _factor_review_payload(case: Mapping[str, Any], ann: Mapping[str, Any]) -> dict[str, Any]:
    """Build the canonical, outcome-blind C2 map-review payload.

    Reviewers must see the original surface label and the exact modifier
    obligations extracted from that label.  Explicit pair/axis unit IDs make
    downstream two-reviewer coverage auditable without reverse-engineering a
    candidate-level summary response.
    """
    surface_by_id = {
        str(candidate["candidate_id"]): str(candidate["label"])
        for candidate in case.get("candidates") or []
    }
    mapped_by_id = {
        str(candidate["candidate_id"]): candidate
        for candidate in ann.get("candidates") or []
    }
    if set(mapped_by_id) != set(surface_by_id) or len(mapped_by_id) != len(surface_by_id):
        raise AssertionError("factor review candidate coverage mismatch")

    candidates: list[dict[str, Any]] = []
    by_core: dict[str, list[dict[str, Any]]] = defaultdict(list)
    modifier_units: list[dict[str, Any]] = []
    for candidate_id in [str(row["candidate_id"]) for row in case.get("candidates") or []]:
        mapped = mapped_by_id[candidate_id]
        modifiers = {
            axis: list((mapped.get("modifiers") or {}).get(axis) or [])
            for axis in MODIFIER_AXES
        }
        surface_label = str(mapped.get("surface_label") or surface_by_id[candidate_id])
        if surface_label != surface_by_id[candidate_id]:
            raise AssertionError(f"factor review surface label drift: {candidate_id}")
        bound = mapped.get("modifier_source_obligations")
        normalized_bound = (
            {axis: list(bound.get(axis) or []) for axis in MODIFIER_AXES}
            if isinstance(bound, Mapping) else None
        )
        if normalized_bound is not None and canonical_sha256(normalized_bound) != canonical_sha256(modifiers):
            raise AssertionError(f"factor review modifier source drift: {candidate_id}")
        row = {
            "candidate_id": candidate_id,
            "surface_label": surface_label,
            "proposed_core_id": str(mapped.get("core_id") or ""),
            "proposed_core_label": str(mapped.get("core_label") or ""),
            "object_kind": str(mapped.get("object_kind") or ""),
            "relation_to_core": str(mapped.get("relation_to_core") or ""),
            "modifier_source_obligations": modifiers,
        }
        candidates.append(row)
        by_core[row["proposed_core_id"]].append(row)
        for axis, obligations in modifiers.items():
            if not obligations:
                continue
            unit = {
                "review_kind": "modifier_axis",
                "case_key": str(case["case_key"]),
                "candidate_id": candidate_id,
                "core_id": row["proposed_core_id"],
                "modifier_axis": axis,
                "surface_label": surface_label,
                "modifier_source_obligations": obligations,
            }
            unit["unit_id"] = "FM-" + canonical_sha256(unit)[:20]
            unit["unit_sha256"] = canonical_sha256(unit)
            modifier_units.append(unit)

    pair_units: list[dict[str, Any]] = []
    for core_id, members in sorted(by_core.items()):
        for left, right in combinations(
            sorted(members, key=lambda row: row["candidate_id"]), 2
        ):
            unit = {
                "review_kind": "core_pair",
                "case_key": str(case["case_key"]),
                "left_id": left["candidate_id"],
                "right_id": right["candidate_id"],
                "core_id": core_id,
                "left_surface_label": left["surface_label"],
                "right_surface_label": right["surface_label"],
            }
            unit["unit_id"] = "FP-" + canonical_sha256(unit)[:20]
            unit["unit_sha256"] = canonical_sha256(unit)
            pair_units.append(unit)

    return {
        "case_key": str(case["case_key"]),
        "vignette": str(case["vignette"]),
        "requested_object": ann.get("requested_object"),
        "candidates": candidates,
        "core_pair_units": pair_units,
        "modifier_axis_units": modifier_units,
    }


def _factor_review_units(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for field in ("core_pair_units", "modifier_axis_units"):
        rows = payload.get(field)
        if not isinstance(rows, list):
            raise AssertionError(f"factor review payload missing {field}")
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise AssertionError("factor review unit must be an object")
            row = dict(raw)
            unit_id = str(row.get("unit_id") or "")
            declared_sha = str(row.pop("unit_sha256", ""))
            expected_sha = canonical_sha256(row)
            if not unit_id or declared_sha != expected_sha or unit_id in units:
                raise AssertionError("invalid or duplicate factor review unit binding")
            row["unit_sha256"] = declared_sha
            units[unit_id] = row
    return units


def _factor_payloads(case: Mapping[str, Any], ann: Mapping[str, Any], bridge: FrozenExactSynonymBridge) -> dict[str, dict[str, Any]]:
    candidates = case["candidates"]
    by_id = {str(x["candidate_id"]): x for x in ann.get("candidates") or []}
    ordered = [by_id[str(c["candidate_id"])] for c in candidates]
    exact_core: dict[str, str] = {}
    for candidate in candidates:
        key = bridge.canonical_key(candidate["label"])
        exact_core[candidate["candidate_id"]] = "X" + hashlib.sha256(key.encode()).hexdigest()[:8]
    factorized = []
    for candidate, mapped in zip(candidates, ordered):
        factorized.append({
            "candidate_id": candidate["candidate_id"], "label": candidate["label"],
            "surface_label": candidate["label"],
            "core_id": str(mapped["core_id"]), "core_label": str(mapped["core_label"]),
            "object_kind": str(mapped["object_kind"]),
            "relation_to_core": str(mapped["relation_to_core"]),
            # These are obligations asserted by the existing surface label,
            # not merely evidence-supported attributes.  Unsupported
            # obligations must survive into the comparator payload.
            "modifier_obligations": {
                axis: list((mapped.get("modifiers") or {}).get(axis) or []) for axis in MODIFIER_AXES
            },
        })
    # Deterministic cyclic derangement; modifiers move but node/group topology,
    # field count and candidate order stay fixed.
    order = sorted(range(len(factorized)), key=lambda i: (stable_seed("modifier-corrupt-v1", case["case_key"], factorized[i]["candidate_id"]), i))
    rotated = order[1:] + order[:1]
    source_for = {target: source for target, source in zip(order, rotated)}
    corrupt = [
        {**row, "modifier_obligations": factorized[source_for[i]]["modifier_obligations"]}
        for i, row in enumerate(factorized)
    ]
    sham = [{**row, "core_id": f"S-{row['candidate_id']}", "core_label": row["label"], "relation_to_core": "singleton"} for row in factorized]
    exact_rows = [
        {
            "candidate_id": candidate["candidate_id"],
            "label": candidate["label"],
            "surface_label": candidate["label"],
            "core_id": exact_core[candidate["candidate_id"]],
            "core_label": candidate["label"],
            "object_kind": "unresolved",
            "relation_to_core": "exact_identity",
            "modifier_obligations": {axis: [] for axis in MODIFIER_AXES},
        }
        for candidate in candidates
    ]

    def lattice(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        core_order: list[str] = []
        members: dict[str, list[str]] = defaultdict(list)
        core_meta: dict[str, Mapping[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        for row in rows:
            core_id = str(row["core_id"])
            candidate_id = str(row["candidate_id"])
            if core_id not in members:
                core_order.append(core_id)
                core_meta[core_id] = row
            members[core_id].append(candidate_id)
            edges.append({
                "core_id": core_id,
                "candidate_id": candidate_id,
                "surface_label": str(row["surface_label"]),
                "relation_to_core": str(row["relation_to_core"]),
                "modifier_obligations": row["modifier_obligations"],
            })
        return {
            "core_nodes": [
                {
                    "core_id": core_id,
                    "core_label": str(core_meta[core_id]["core_label"]),
                    "object_kind": str(core_meta[core_id]["object_kind"]),
                    "member_candidate_ids": members[core_id],
                }
                for core_id in core_order
            ],
            "member_edges": edges,
        }

    requested = ann["requested_object"]
    return {
        "flat": {"candidates": candidates},
        "exact_identity": {"requested_object": requested, "candidates": exact_rows, "lattice": lattice(exact_rows)},
        "factorized_lattice": {"requested_object": requested, "candidates": factorized, "lattice": lattice(factorized)},
        "structure_sham": {"requested_object": requested, "candidates": sham, "lattice": lattice(sham)},
        "corrupted_modifier_mapping": {"requested_object": requested, "candidates": corrupt, "lattice": lattice(corrupt)},
    }


def _review_metrics(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    pair_rows = [row for row in reviews if row.get("review_kind") == "core_pair"]
    modifier_rows = [row for row in reviews if row.get("review_kind") == "modifier_axis"]
    return {
        # Empty review classes are not measurements and can never default to
        # perfect precision.  The gate below records explicit empty-class
        # failures before considering thresholds.
        "grouped_pair_precision": (
            statistics.fmean(bool(r.get("grouped_correct")) for r in pair_rows)
            if pair_rows else None
        ),
        "modifier_axis_precision": (
            statistics.fmean(bool(r.get("modifier_correct")) for r in modifier_rows)
            if modifier_rows else None
        ),
        "unsafe_synonym_merges": float(sum(bool(r.get("unsafe_synonym_merge")) for r in pair_rows)),
        "reviewed_group_pair_n": float(len(pair_rows)),
        "reviewed_modifier_axis_n": float(len(modifier_rows)),
    }


def _manifest_input_hashes(manifest: Mapping[str, Any]) -> set[str]:
    return {
        str(row.get("sha256") or "")
        for row in manifest.get("input_files") or []
        if isinstance(row, Mapping)
    }


def _online_task_contract(
    *, task_id: str, module: str, prompt: str, payload: Mapping[str, Any],
    model: str, metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild one immutable OnlineJSONCaller identity without making a call."""
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    payload_dict = dict(payload)
    payload_sha = canonical_sha256(payload_dict)
    return {
        "task_id": task_id,
        "module": module,
        "prompt": prompt,
        "payload": payload_dict,
        "prompt_sha256": prompt_sha,
        "payload_sha256": payload_sha,
        "cache_key": canonical_sha256({
            "schema": "mechanism_v2_online_call_v1",
            "model": model,
            "module": module,
            "prompt_sha256": prompt_sha,
            "payload_sha256": payload_sha,
            "temperature": 0.0,
        }),
        "metadata": dict(metadata),
    }


def _online_raw_identity_valid(
    row: Mapping[str, Any], expected: Mapping[str, Any], *, model: str
) -> bool:
    """Validate the immutable input identity and typed runner envelope."""
    cache_key = str(row.get("cache_key") or "")
    return bool(
        str(row.get("task_id") or "") == str(expected["task_id"])
        and str(row.get("model") or "") == model
        and isinstance(row.get("success"), bool)
        and isinstance(row.get("cache_hit"), bool)
        and isinstance(row.get("response"), Mapping)
        and isinstance(row.get("error"), str)
        and str(row.get("prompt_sha256") or "") == str(expected["prompt_sha256"])
        and str(row.get("payload_sha256") or "") == str(expected["payload_sha256"])
        and all(row.get(key) == value for key, value in expected["metadata"].items())
        and (
            cache_key == str(expected["cache_key"])
            or (not cache_key and not bool(row.get("success")) and not bool(row.get("cache_hit")))
        )
    )


def _online_semantic_input_sha256(contracts: Sequence[Mapping[str, Any]]) -> str:
    return canonical_sha256([
        {
            "task_id": row["task_id"],
            "module": row["module"],
            "prompt": row["prompt"],
            "payload": row["payload"],
        }
        for row in contracts
    ])


def gate_factorization(freeze_dir: Path, annotations: Path, reviews: Path, admission_gate: Path, out: Path) -> dict[str, Any]:
    freeze_dir = Path(freeze_dir)
    freeze_cases_path = freeze_dir / "cases.jsonl"
    freeze_manifest_path = freeze_dir / "freeze.json"
    freeze_manifest, cases, freeze_failures = _formal_freeze_validation(
        freeze_dir,
        "factorization",
        FACTORIZATION_ARMS,
        expected_case_n=200,
        expected_family_n={"DA": 100, "MCR": 100},
        expected_sources=[E5_JOINED, BRIDGE],
    )
    anns = _annotation_index(annotations)
    review_rows = read_jsonl(reviews)
    upstream = _json(admission_gate)
    upstream_passed = bool(upstream.get("passed"))
    bridge = FrozenExactSynonymBridge(BRIDGE)
    failures: list[str] = list(freeze_failures)
    if not cases:
        failures.append("empty_factorization_freeze")
    if len({str(case.get("case_key")) for case in cases}) != len(cases):
        failures.append("duplicate_freeze_case_key")

    annotation_manifest_path = Path(annotations).parent / "factorization_annotations.manifest.json"
    review_manifest_path = Path(reviews).parent / "factorization_reviews.manifest.json"
    annotation_manifest = _json(annotation_manifest_path) if annotation_manifest_path.is_file() else {}
    review_manifest = _json(review_manifest_path) if review_manifest_path.is_file() else {}
    if not annotation_manifest:
        failures.append("annotation_manifest_missing")
    elif (
        annotation_manifest.get("product") != "factorization_annotations"
        or str(annotation_manifest.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL
        or int(annotation_manifest.get("row_n") or -1) != len(anns)
        or str(annotation_manifest.get("file_sha256") or "") != file_sha256(Path(annotations))
        or str(annotation_manifest.get("rows_sha256") or "") != canonical_sha256(read_jsonl(annotations))
        or file_sha256(freeze_cases_path) not in _manifest_input_hashes(annotation_manifest)
    ):
        failures.append("annotation_manifest_binding_invalid")

    annotation_stage_bindings = annotation_manifest.get("online_stage_manifests") or []
    annotation_stage_names: set[str] = set()
    annotation_raw_by_case_stage: dict[tuple[str, str], dict[str, Any]] = {}
    annotation_stage_docs: dict[str, dict[str, Any]] = {}
    annotation_stage_raw_rows: dict[str, list[dict[str, Any]]] = {}
    annotation_stage_source_commits: set[str] = set()
    if len(annotation_stage_bindings) != 2:
        failures.append("annotation_stage_manifest_coverage_invalid")
    for stage_binding in annotation_stage_bindings:
        if not isinstance(stage_binding, Mapping):
            failures.append("annotation_stage_manifest_binding_invalid")
            continue
        stage_path = Path(str(stage_binding.get("path") or ""))
        if not stage_path.is_absolute():
            stage_path = annotation_manifest_path.parent / stage_path
        if not stage_path.is_file() or file_sha256(stage_path) != str(stage_binding.get("sha256") or ""):
            failures.append("annotation_stage_manifest_binding_invalid")
            continue
        stage_name = stage_path.parent.name
        annotation_stage_names.add(stage_name)
        stage_doc = _json(stage_path)
        raw_path = stage_path.parent / "raw_results.jsonl"
        telemetry_path = stage_path.parent / "telemetry_summary.json"
        raw_rows = read_jsonl(raw_path) if raw_path.is_file() else []
        annotation_stage_docs[stage_name] = stage_doc
        annotation_stage_raw_rows[stage_name] = raw_rows
        telemetry_doc = _json(telemetry_path) if telemetry_path.is_file() else {}
        raw_telemetry_path = stage_path.parent / "telemetry.jsonl"
        raw_telemetry = read_jsonl(raw_telemetry_path)
        task_n = int(stage_doc.get("task_n") or -1)
        success_n = int(stage_doc.get("success_n") or 0)
        failure_n = int(stage_doc.get("failure_n") or 0)
        annotation_stage_source_commits.add(str(stage_doc.get("source_commit") or ""))
        if (
            str(stage_doc.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL
            or not raw_path.is_file()
            or not telemetry_path.is_file()
            or not raw_telemetry_path.is_file()
            or task_n != len(raw_rows)
            or success_n + failure_n != task_n
            or file_sha256(raw_path) != str(stage_doc.get("results_file_sha256") or "")
            or canonical_sha256(raw_rows) != str(stage_doc.get("results_sha256") or "")
            or telemetry_doc != (stage_doc.get("telemetry_summary") or {})
            or file_sha256(raw_telemetry_path) != str(stage_doc.get("telemetry_sha256") or "")
            or aggregate_telemetry(raw_telemetry) != telemetry_doc
            or str(stage_doc.get("runner_code_sha256") or "")
            != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
            or str(stage_doc.get("online_runner_code_sha256") or "")
            != file_sha256(ROOT / "analysis/mechanism_v2/online_runner.py")
            or len({str(row.get("task_id") or "") for row in raw_rows}) != len(raw_rows)
            or any(str(row.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL for row in raw_rows)
        ):
            failures.append("annotation_stage_product_binding_invalid")
        for raw_row in raw_rows:
            key = (str(raw_row.get("case_key") or ""), str(raw_row.get("stage") or ""))
            if key in annotation_raw_by_case_stage:
                failures.append("annotation_stage_raw_identity_duplicate")
            annotation_raw_by_case_stage[key] = raw_row
        if stage_name == "factorizer_parser" and task_n != 2 * len(cases):
            failures.append("factorizer_parser_task_denominator_invalid")
        if stage_name == "modifier_binder" and not (0 <= task_n <= len(cases)):
            failures.append("modifier_binder_task_denominator_invalid")
    if annotation_stage_names != {"factorizer_parser", "modifier_binder"}:
        failures.append("annotation_stage_identity_invalid")
    if (
        str(annotation_manifest.get("generator_code_sha256") or "")
        != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
        or {
            str(annotation_manifest.get("source_commit") or ""),
            str(freeze_manifest.get("source_commit") or ""),
            *annotation_stage_source_commits,
        } != {str(freeze_manifest.get("source_commit") or "")}
    ):
        failures.append("annotation_generator_or_source_commit_binding_invalid")

    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
        FACTORIZER_PROMPT,
        MODIFIER_BINDER_PROMPT,
        REQUESTED_OBJECT_PROMPT,
        _factorizer_validator,
        _modifier_validator,
        _requested_object_validator,
    )

    first_contracts: list[dict[str, Any]] = []
    first_contract_by_task: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_key = str(case["case_key"])
        for stage_name, module, prompt, payload in (
            (
                "factorizer", "CeilingObjectFactorizer", FACTORIZER_PROMPT,
                {"case_key": case_key, "candidates": case["candidates"]},
            ),
            (
                "requested_object", "CeilingFactorRequestedObject", REQUESTED_OBJECT_PROMPT,
                {"case_key": case_key, "vignette": case["vignette"]},
            ),
        ):
            contract = _online_task_contract(
                task_id=f"{case_key}|{stage_name}", module=module, prompt=prompt,
                payload=payload, model=ADMISSION_CONSTRUCTION_MODEL,
                metadata={"case_key": case_key, "stage": stage_name},
            )
            first_contracts.append(contract)
            first_contract_by_task[str(contract["task_id"])] = contract
    first_raw = annotation_stage_raw_rows.get("factorizer_parser") or []
    first_stage = annotation_stage_docs.get("factorizer_parser") or {}
    if (
        {str(row.get("task_id") or "") for row in first_raw} != set(first_contract_by_task)
        or any(
            not _online_raw_identity_valid(
                row, first_contract_by_task.get(str(row.get("task_id") or ""), {}),
                model=ADMISSION_CONSTRUCTION_MODEL,
            )
            for row in first_raw
            if str(row.get("task_id") or "") in first_contract_by_task
        )
        or str(first_stage.get("semantic_input_sha256") or "")
        != _online_semantic_input_sha256(first_contracts)
        or list(first_stage.get("prompt_sha256s") or [])
        != sorted({str(row["prompt_sha256"]) for row in first_contracts})
    ):
        failures.append("factorizer_parser_immutable_task_binding_invalid")
    for raw_row in first_raw:
        if raw_row.get("success") is not True:
            continue
        case = next(
            (value for value in cases if str(value["case_key"]) == str(raw_row.get("case_key") or "")),
            None,
        )
        if case is None:
            continue
        validator = (
            _factorizer_validator({str(row["candidate_id"]) for row in case["candidates"]})
            if str(raw_row.get("stage") or "") == "factorizer"
            else _requested_object_validator
        )
        if validator(raw_row.get("response") or {}) is not None:
            failures.append(f"{case['case_key']}:{raw_row.get('stage')}:raw_response_schema_invalid")

    case_by_key = {str(case["case_key"]): case for case in cases}
    binder_contracts: list[dict[str, Any]] = []
    binder_contract_by_task: dict[str, dict[str, Any]] = {}
    factor_raw_by_case = {
        str(row.get("case_key") or ""): row
        for row in first_raw
        if str(row.get("stage") or "") == "factorizer"
    }
    for case in cases:
        case_key = str(case["case_key"])
        raw_row = factor_raw_by_case.get(case_key) or {}
        if raw_row.get("success") is not True:
            continue
        labels = {str(row["candidate_id"]): str(row["label"]) for row in case["candidates"]}
        factor_rows = (raw_row.get("response") or {}).get("candidates") or []
        factor_candidates = [
            {**dict(row), "surface_label": labels[str(row["candidate_id"])]}
            for row in factor_rows
            if isinstance(row, Mapping) and str(row.get("candidate_id") or "") in labels
        ]
        contract = _online_task_contract(
            task_id=f"{case_key}|modifier_binder", module="CeilingModifierBinder",
            prompt=MODIFIER_BINDER_PROMPT,
            payload={
                "case_key": case_key,
                "vignette": case["vignette"],
                "candidates": factor_candidates,
            },
            model=ADMISSION_CONSTRUCTION_MODEL,
            metadata={"case_key": case_key, "stage": "modifier_binder"},
        )
        binder_contracts.append(contract)
        binder_contract_by_task[str(contract["task_id"])] = contract
    binder_raw = annotation_stage_raw_rows.get("modifier_binder") or []
    binder_stage = annotation_stage_docs.get("modifier_binder") or {}
    if (
        {str(row.get("task_id") or "") for row in binder_raw} != set(binder_contract_by_task)
        or any(
            not _online_raw_identity_valid(
                row, binder_contract_by_task.get(str(row.get("task_id") or ""), {}),
                model=ADMISSION_CONSTRUCTION_MODEL,
            )
            for row in binder_raw
            if str(row.get("task_id") or "") in binder_contract_by_task
        )
        or str(binder_stage.get("semantic_input_sha256") or "")
        != _online_semantic_input_sha256(binder_contracts)
        or list(binder_stage.get("prompt_sha256s") or [])
        != sorted({str(row["prompt_sha256"]) for row in binder_contracts})
    ):
        failures.append("modifier_binder_immutable_task_binding_invalid")
    for raw_row in binder_raw:
        if raw_row.get("success") is not True:
            continue
        case = case_by_key.get(str(raw_row.get("case_key") or ""))
        if case is None:
            continue
        labels = {str(row["candidate_id"]): str(row["label"]) for row in case["candidates"]}
        if _modifier_validator(
            set(labels), str(case["vignette"]), labels
        )(raw_row.get("response") or {}) is not None:
            failures.append(f"{case['case_key']}:modifier_binder:raw_response_schema_invalid")
    if not review_manifest:
        failures.append("review_manifest_missing")
    elif (
        review_manifest.get("product") != "factorization_reviews"
        or int(review_manifest.get("row_n") or -1) != len(review_rows)
        or str(review_manifest.get("file_sha256") or "") != file_sha256(Path(reviews))
        or str(review_manifest.get("rows_sha256") or "") != canonical_sha256(review_rows)
        or not {
            file_sha256(freeze_cases_path), file_sha256(Path(annotations))
        }.issubset(_manifest_input_hashes(review_manifest))
    ):
        failures.append("review_manifest_binding_invalid")

    reviewer_specs = review_manifest.get("reviewers") or []
    reviewer_model_by_id = {
        str(row.get("reviewer_id") or ""): str(row.get("model") or "")
        for row in reviewer_specs if isinstance(row, Mapping)
    }
    reviewer_ids = set(reviewer_model_by_id)
    if (
        len(reviewer_specs) != 2
        or len(reviewer_ids) != 2
        or "" in reviewer_ids
        or len(set(reviewer_model_by_id.values())) != 2
        or "" in set(reviewer_model_by_id.values())
    ):
        failures.append("reviewers_not_exactly_two_heterogeneous_models")
    if set(reviewer_model_by_id.values()) != set(CLOSURE_GATE_REVIEW_MODELS):
        failures.append("reviewer_model_substitution_forbidden")

    bound_stage_models: set[str] = set()
    review_raw_by_reviewer_case: dict[tuple[str, str], dict[str, Any]] = {}
    review_stage_docs: dict[str, dict[str, Any]] = {}
    review_stage_raw_rows: dict[str, list[dict[str, Any]]] = {}
    review_stage_source_commits: set[str] = set()
    stage_bindings = review_manifest.get("online_stage_manifests") or []
    if len(stage_bindings) != 2:
        failures.append("review_stage_manifest_coverage_invalid")
    for stage_binding in stage_bindings:
        if not isinstance(stage_binding, Mapping):
            failures.append("review_stage_manifest_binding_invalid")
            continue
        stage_path = Path(str(stage_binding.get("path") or ""))
        if not stage_path.is_absolute():
            stage_path = review_manifest_path.parent / stage_path
        if not stage_path.is_file() or file_sha256(stage_path) != str(stage_binding.get("sha256") or ""):
            failures.append("review_stage_manifest_binding_invalid")
            continue
        stage_doc = _json(stage_path)
        stage_model = str(stage_doc.get("model") or "")
        reviewer_id = stage_path.parent.name
        review_stage_docs[reviewer_id] = stage_doc
        bound_stage_models.add(stage_model)
        review_stage_source_commits.add(str(stage_doc.get("source_commit") or ""))
        raw_path = stage_path.parent / "raw_results.jsonl"
        telemetry_path = stage_path.parent / "telemetry_summary.json"
        raw_telemetry_path = stage_path.parent / "telemetry.jsonl"
        raw_rows = read_jsonl(raw_path)
        review_stage_raw_rows[reviewer_id] = raw_rows
        telemetry_doc = _json(telemetry_path) if telemetry_path.is_file() else {}
        raw_telemetry = read_jsonl(raw_telemetry_path)
        task_n = int(stage_doc.get("task_n") or -1)
        success_n = int(stage_doc.get("success_n") or 0)
        failure_n = int(stage_doc.get("failure_n") or 0)
        if (
            reviewer_model_by_id.get(reviewer_id) != stage_model
            or task_n != len(cases)
            or len(raw_rows) != task_n
            or success_n + failure_n != task_n
            or not raw_path.is_file()
            or not telemetry_path.is_file()
            or not raw_telemetry_path.is_file()
            or file_sha256(raw_path) != str(stage_doc.get("results_file_sha256") or "")
            or canonical_sha256(raw_rows) != str(stage_doc.get("results_sha256") or "")
            or file_sha256(raw_telemetry_path) != str(stage_doc.get("telemetry_sha256") or "")
            or aggregate_telemetry(raw_telemetry) != telemetry_doc
            or telemetry_doc != (stage_doc.get("telemetry_summary") or {})
            or str(stage_doc.get("runner_code_sha256") or "")
            != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
            or str(stage_doc.get("online_runner_code_sha256") or "")
            != file_sha256(ROOT / "analysis/mechanism_v2/online_runner.py")
            or len({str(row.get("task_id") or "") for row in raw_rows}) != len(raw_rows)
            or {str(row.get("case_key") or "") for row in raw_rows}
            != {str(case["case_key"]) for case in cases}
            or any(str(row.get("model") or "") != stage_model for row in raw_rows)
        ):
            failures.append("review_stage_product_binding_invalid")
        for raw_row in raw_rows:
            key = (reviewer_id, str(raw_row.get("case_key") or ""))
            if key in review_raw_by_reviewer_case:
                failures.append("review_stage_raw_identity_duplicate")
            review_raw_by_reviewer_case[key] = raw_row
    if bound_stage_models != set(reviewer_model_by_id.values()):
        failures.append("review_stage_model_binding_invalid")
    if (
        str(review_manifest.get("generator_code_sha256") or "")
        != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
        or {
            str(review_manifest.get("source_commit") or ""),
            str(freeze_manifest.get("source_commit") or ""),
            *review_stage_source_commits,
        } != {str(freeze_manifest.get("source_commit") or "")}
    ):
        failures.append("review_generator_or_source_commit_binding_invalid")

    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
        FACTOR_REVIEW_PROMPT,
        _factor_review_validator,
    )

    for reviewer_id, model in reviewer_model_by_id.items():
        contracts: list[dict[str, Any]] = []
        by_task: dict[str, dict[str, Any]] = {}
        for case in cases:
            ann = anns.get(str(case["case_key"]))
            if ann is None:
                continue
            payload = _factor_review_payload(case, ann)
            task_id = f"{case['case_key']}|factor_review|{reviewer_id}"
            contract = _online_task_contract(
                task_id=task_id,
                module=f"CeilingFactorModelPanel_{reviewer_id}",
                prompt=FACTOR_REVIEW_PROMPT,
                payload=payload,
                model=model,
                metadata={
                    "case_key": str(case["case_key"]),
                    "reviewer_id": reviewer_id,
                    "stage": "factorization_model_panel",
                },
            )
            contracts.append(contract)
            by_task[task_id] = contract
        raw_rows = review_stage_raw_rows.get(reviewer_id) or []
        stage_doc = review_stage_docs.get(reviewer_id) or {}
        if (
            {str(row.get("task_id") or "") for row in raw_rows} != set(by_task)
            or any(
                not _online_raw_identity_valid(
                    row, by_task.get(str(row.get("task_id") or ""), {}), model=model
                )
                for row in raw_rows
                if str(row.get("task_id") or "") in by_task
            )
            or str(stage_doc.get("semantic_input_sha256") or "")
            != _online_semantic_input_sha256(contracts)
            or list(stage_doc.get("prompt_sha256s") or [])
            != sorted({str(row["prompt_sha256"]) for row in contracts})
        ):
            failures.append(f"{reviewer_id}:review_immutable_task_binding_invalid")
        for raw_row in raw_rows:
            if raw_row.get("success") is not True:
                continue
            case = case_by_key.get(str(raw_row.get("case_key") or ""))
            ann = anns.get(str(raw_row.get("case_key") or ""))
            if case is None or ann is None:
                continue
            expected_review_units = _factor_review_units(_factor_review_payload(case, ann))
            if _factor_review_validator(expected_review_units)(raw_row.get("response") or {}) is not None:
                failures.append(
                    f"{case['case_key']}:{reviewer_id}:raw_review_response_schema_invalid"
                )

    expected_first_stage_keys = {
        (str(case["case_key"]), stage_name)
        for case in cases
        for stage_name in ("factorizer", "requested_object")
    }
    observed_first_stage_keys = {
        key for key in annotation_raw_by_case_stage if key[1] in {"factorizer", "requested_object"}
    }
    if observed_first_stage_keys != expected_first_stage_keys:
        failures.append("factorizer_parser_raw_case_coverage_invalid")
    expected_binder_keys = {
        (case_key, "modifier_binder")
        for case_key, stage_name in expected_first_stage_keys
        if stage_name == "factorizer"
        and bool((annotation_raw_by_case_stage.get((case_key, stage_name)) or {}).get("success"))
    }
    observed_binder_keys = {
        key for key in annotation_raw_by_case_stage if key[1] == "modifier_binder"
    }
    if observed_binder_keys != expected_binder_keys:
        failures.append("modifier_binder_raw_case_coverage_invalid")

    unresolved = 0
    total = 0
    modifier_claim_n = 0
    modifier_source_closed_n = 0
    modifier_evidence_supported_n = 0
    nontrivial_corrupt_cases = 0
    expected_units: dict[str, dict[str, Any]] = {}
    for case in cases:
        ann = anns.get(case["case_key"])
        if not ann:
            failures.append(f"{case['case_key']}:missing_annotation")
            continue
        factor = annotation_raw_by_case_stage.get((str(case["case_key"]), "factorizer"))
        parser = annotation_raw_by_case_stage.get((str(case["case_key"]), "requested_object"))
        bound = annotation_raw_by_case_stage.get((str(case["case_key"]), "modifier_binder"))
        if factor is None or parser is None:
            failures.append(f"{case['case_key']}:annotation_raw_source_missing")
            continue
        merged = [
            {
                "candidate_id": str(candidate["candidate_id"]),
                "core_id": f"UNRESOLVED-{candidate['candidate_id']}",
                "core_label": str(candidate["label"]),
                "object_kind": "unresolved",
                "relation_to_core": "other",
                "surface_label": str(candidate["label"]),
                "modifiers": {axis: [] for axis in MODIFIER_AXES},
                "modifier_source_obligations": {axis: [] for axis in MODIFIER_AXES},
                "unresolved": True,
            }
            for candidate in case["candidates"]
        ]
        if bool(factor.get("success")) and bound is not None and bool(bound.get("success")):
            factor_by_id = {
                str(row["candidate_id"]): row
                for row in (factor.get("response") or {}).get("candidates") or []
            }
            bind_by_id = {
                str(row["candidate_id"]): row
                for row in (bound.get("response") or {}).get("candidates") or []
            }
            merged = []
            try:
                for candidate in case["candidates"]:
                    candidate_id = str(candidate["candidate_id"])
                    mapped, binding = factor_by_id[candidate_id], bind_by_id[candidate_id]
                    surface_label = str(candidate["label"])
                    modifiers = {}
                    for axis in MODIFIER_AXES:
                        normalized_claims = []
                        for claim in (binding.get("modifiers") or {}).get(axis) or []:
                            surface_text = str((claim.get("surface_span") or {}).get("text") or "")
                            surface_start = surface_label.find(surface_text)
                            if not surface_text or surface_start < 0:
                                raise ValueError("nonliteral surface quotation")
                            support_spans = []
                            for span in claim.get("support_spans") or []:
                                support_text = str((span or {}).get("text") or "")
                                support_start = str(case["vignette"]).find(support_text)
                                if not support_text or support_start < 0:
                                    raise ValueError("nonliteral vignette quotation")
                                support_spans.append({
                                    "start": support_start,
                                    "end": support_start + len(support_text),
                                    "text": support_text,
                                })
                            normalized_claims.append({
                                **claim,
                                "surface_span": {
                                    "start": surface_start,
                                    "end": surface_start + len(surface_text),
                                    "text": surface_text,
                                },
                                "support_spans": support_spans,
                            })
                        modifiers[axis] = normalized_claims
                    merged.append({
                        "candidate_id": candidate_id,
                        "core_id": str(mapped["core_id"]),
                        "core_label": str(mapped["core_label"]),
                        "object_kind": str(mapped["object_kind"]),
                        "relation_to_core": str(mapped["relation_to_core"]),
                        "surface_label": surface_label,
                        "modifiers": modifiers,
                        "modifier_source_obligations": modifiers,
                        "unresolved": bool(mapped.get("unresolved") or binding.get("unresolved")),
                    })
            except (KeyError, TypeError):
                failures.append(f"{case['case_key']}:annotation_raw_response_invalid")
                continue
        expected_annotation = {
            "case_key": str(case["case_key"]),
            "requested_object": (
                (parser.get("response") or {}).get("requested_object")
                if bool(parser.get("success")) else None
            ) or {"kind": "unresolved", "explicit_modifier_axes": []},
            "candidates": merged,
            "annotation_success": bool(
                factor.get("success") and parser.get("success")
                and bound is not None and bound.get("success")
            ),
            "stage_errors": {
                "factorizer": factor.get("error"),
                "requested_object": parser.get("error"),
                "modifier_binder": (
                    "missing_after_factorizer_failure" if bound is None else bound.get("error")
                ),
            },
            "provenance": "outcome_blind_model_annotation",
        }
        if canonical_sha256(ann) != canonical_sha256(expected_annotation):
            failures.append(f"{case['case_key']}:annotation_derivation_binding_invalid")
        expected = {c["candidate_id"] for c in case["candidates"]}
        mapped = ann.get("candidates") or []
        if {str(x.get("candidate_id")) for x in mapped} != expected or len(mapped) != len(expected):
            failures.append(f"{case['case_key']}:candidate_coverage")
            continue
        if str((ann.get("requested_object") or {}).get("kind") or "") in {"", "unresolved"}:
            failures.append(f"{case['case_key']}:requested_object")
        total += len(mapped)
        unresolved += sum(bool(x.get("unresolved")) for x in mapped)
        label_by_id = {str(candidate["candidate_id"]): str(candidate["label"]) for candidate in case["candidates"]}
        for mapped_candidate in mapped:
            candidate_id = str(mapped_candidate.get("candidate_id") or "")
            if str(mapped_candidate.get("surface_label") or "") != label_by_id.get(candidate_id):
                failures.append(f"{case['case_key']}:{candidate_id}:surface_label_binding_invalid")
            unknown_axes = set((mapped_candidate.get("modifiers") or {}).keys()) - set(MODIFIER_AXES)
            if unknown_axes:
                failures.append(f"{case['case_key']}:{mapped_candidate.get('candidate_id')}:unknown_modifier_axis")
            bound_obligations = mapped_candidate.get("modifier_source_obligations")
            if (
                not isinstance(bound_obligations, Mapping)
                or set(map(str, bound_obligations)) - set(MODIFIER_AXES)
                or canonical_sha256({
                    axis: list(bound_obligations.get(axis) or []) for axis in MODIFIER_AXES
                }) != canonical_sha256({
                    axis: list((mapped_candidate.get("modifiers") or {}).get(axis) or [])
                    for axis in MODIFIER_AXES
                })
            ):
                failures.append(f"{case['case_key']}:{candidate_id}:modifier_source_binding_invalid")
            for values in (mapped_candidate.get("modifiers") or {}).values():
                for modifier in values or []:
                    modifier_claim_n += 1
                    surface_span = modifier.get("surface_span") or {}
                    if _valid_segment(label_by_id[candidate_id], surface_span):
                        modifier_source_closed_n += 1
                    support_spans = modifier.get("support_spans") or []
                    if support_spans and all(_valid_segment(case["vignette"], span) for span in support_spans):
                        modifier_evidence_supported_n += 1
        try:
            payloads = _factor_payloads(case, ann, bridge)
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(f"{case['case_key']}:schema:{exc}")
            continue
        source_mods = [x["modifier_obligations"] for x in payloads["factorized_lattice"]["candidates"]]
        corrupt_mods = [x["modifier_obligations"] for x in payloads["corrupted_modifier_mapping"]["candidates"]]
        if source_mods != corrupt_mods:
            nontrivial_corrupt_cases += 1
        if Counter(canonical_sha256(x) for x in source_mods) != Counter(canonical_sha256(x) for x in corrupt_mods):
            failures.append(f"{case['case_key']}:corruption_not_bijection")
        try:
            review_payload = _factor_review_payload(case, ann)
            for unit_id, unit in _factor_review_units(review_payload).items():
                if unit_id in expected_units:
                    failures.append("duplicate_expected_review_unit_id")
                expected_units[unit_id] = {
                    **unit,
                    "case_key": str(case["case_key"]),
                    "payload_sha256": canonical_sha256(review_payload),
                }
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            failures.append(f"{case['case_key']}:review_payload:{exc}")

    expected_pair_ids = {
        unit_id for unit_id, unit in expected_units.items()
        if unit.get("review_kind") == "core_pair"
    }
    expected_modifier_ids = {
        unit_id for unit_id, unit in expected_units.items()
        if unit.get("review_kind") == "modifier_axis"
    }
    if not expected_pair_ids:
        failures.append("core_pair_review_class_empty")
    if not expected_modifier_ids:
        failures.append("modifier_axis_review_class_empty")
    expected_unit_binding = canonical_sha256([
        {"unit_id": unit_id, "unit_sha256": expected_units[unit_id]["unit_sha256"]}
        for unit_id in sorted(expected_units)
    ])
    if (
        int(review_manifest.get("review_unit_n") or -1) != len(expected_units)
        or str(review_manifest.get("review_units_sha256") or "") != expected_unit_binding
        or int(review_manifest.get("required_reviews_per_unit") or -1) != 2
    ):
        failures.append("review_manifest_unit_binding_invalid")
    for reviewer_id in reviewer_ids:
        for case in cases:
            case_key = str(case["case_key"])
            raw_source = review_raw_by_reviewer_case.get((reviewer_id, case_key))
            if raw_source is None or not bool(raw_source.get("success")):
                continue
            response = raw_source.get("response") or {}
            pair_rows = response.get("core_pair_reviews") or []
            modifier_rows = response.get("modifier_axis_reviews") or []
            observed_pair_ids = {
                str(item.get("unit_id") or "")
                for item in pair_rows
                if isinstance(item, Mapping)
            }
            observed_modifier_ids = {
                str(item.get("unit_id") or "")
                for item in modifier_rows
                if isinstance(item, Mapping)
            }
            expected_case_pair_ids = {
                unit_id for unit_id, unit in expected_units.items()
                if unit.get("case_key") == case_key and unit.get("review_kind") == "core_pair"
            }
            expected_case_modifier_ids = {
                unit_id for unit_id, unit in expected_units.items()
                if unit.get("case_key") == case_key and unit.get("review_kind") == "modifier_axis"
            }
            if (
                not isinstance(pair_rows, list)
                or not isinstance(modifier_rows, list)
                or len(pair_rows) != len(observed_pair_ids)
                or len(modifier_rows) != len(observed_modifier_ids)
                or observed_pair_ids != expected_case_pair_ids
                or observed_modifier_ids != expected_case_modifier_ids
                or any(
                    not isinstance(item, Mapping)
                    or any(
                        not isinstance(item.get(field), bool)
                        for field in ("grouped_correct", "unsafe_synonym_merge", "unresolved")
                    )
                    for item in pair_rows
                )
                or any(
                    not isinstance(item, Mapping)
                    or any(
                        not isinstance(item.get(field), bool)
                        for field in ("modifier_correct", "unresolved")
                    )
                    for item in modifier_rows
                )
            ):
                failures.append(f"{case_key}:{reviewer_id}:review_raw_unit_coverage_invalid")

    review_groups: dict[str, list[str]] = defaultdict(list)
    rows_by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in review_rows:
        unit_id = str(review.get("unit_id") or "")
        expected_unit = expected_units.get(unit_id)
        if expected_unit is None:
            failures.append(f"unexpected_review_unit:{unit_id or 'missing'}")
            continue
        rows_by_unit[unit_id].append(review)
        reviewer_id = str(review.get("reviewer_id") or "")
        if reviewer_model_by_id.get(reviewer_id) != str(review.get("reviewer_model") or ""):
            failures.append(f"{unit_id}:reviewer_model_binding_invalid")
        raw_source = review_raw_by_reviewer_case.get((reviewer_id, str(review.get("case_key") or "")))
        if raw_source is None:
            failures.append(f"{unit_id}:{reviewer_id}:review_raw_source_missing")
        else:
            if (
                str(review.get("response_sha256") or "")
                != canonical_sha256(raw_source.get("response") or {})
                or bool(review.get("success")) != bool(raw_source.get("success"))
                or str(review.get("error") or "") != str(raw_source.get("error") or "")
                or str(review.get("cache_key") or "") != str(raw_source.get("cache_key") or "")
                or str(review.get("prompt_sha256") or "") != str(raw_source.get("prompt_sha256") or "")
                or str(review.get("payload_sha256") or "") != str(raw_source.get("payload_sha256") or "")
            ):
                failures.append(f"{unit_id}:{reviewer_id}:review_raw_product_binding_invalid")
            response = raw_source.get("response") if raw_source.get("success") else {}
            pair_response = {
                str(item.get("unit_id") or ""): item
                for item in (response or {}).get("core_pair_reviews") or []
                if isinstance(item, Mapping)
            }
            modifier_response = {
                str(item.get("unit_id") or ""): item
                for item in (response or {}).get("modifier_axis_reviews") or []
                if isinstance(item, Mapping)
            }
            if expected_unit.get("review_kind") == "core_pair":
                item = pair_response.get(unit_id) or {
                    "grouped_correct": False,
                    "unsafe_synonym_merge": False,
                    "unresolved": True,
                }
                grouped_correct = bool(item.get("grouped_correct"))
                unsafe_merge = bool(item.get("unsafe_synonym_merge"))
                unresolved_value = bool(item.get("unresolved", True))
                derived_fields = {
                    "grouped_correct": grouped_correct,
                    "modifier_correct": True,
                    "unsafe_synonym_merge": unsafe_merge,
                    "unresolved": unresolved_value,
                    "decision": (
                        "accept" if grouped_correct and not unsafe_merge and not unresolved_value
                        else "reject_grouping"
                    ),
                }
            else:
                item = modifier_response.get(unit_id) or {
                    "modifier_correct": False,
                    "unresolved": True,
                }
                modifier_correct = bool(item.get("modifier_correct"))
                unresolved_value = bool(item.get("unresolved", True))
                derived_fields = {
                    "grouped_correct": True,
                    "modifier_correct": modifier_correct,
                    "unsafe_synonym_merge": False,
                    "unresolved": unresolved_value,
                    "decision": (
                        "accept" if modifier_correct and not unresolved_value
                        else "reject_modifiers"
                    ),
                }
            if any(review.get(field) != value for field, value in derived_fields.items()):
                failures.append(f"{unit_id}:{reviewer_id}:review_flat_derivation_invalid")
        if not bool(review.get("success")):
            failures.append(f"{unit_id}:{reviewer_id}:review_not_successful")
        if str(review.get("payload_sha256") or "") != str(expected_unit["payload_sha256"]):
            failures.append(f"{unit_id}:{reviewer_id}:review_payload_hash_mismatch")
        if str(review.get("unit_sha256") or "") != str(expected_unit["unit_sha256"]):
            failures.append(f"{unit_id}:{reviewer_id}:review_unit_hash_mismatch")
        for field in ("case_key", "review_kind"):
            if str(review.get(field) or "") != str(expected_unit.get(field) or ""):
                failures.append(f"{unit_id}:{reviewer_id}:{field}_binding_mismatch")
        expected_fields = (
            ("left_id", "right_id", "core_id")
            if expected_unit.get("review_kind") == "core_pair"
            else ("candidate_id", "core_id", "modifier_axis")
        )
        for field in expected_fields:
            observed_field = "left_id" if field == "candidate_id" else field
            if str(review.get(observed_field) or "") != str(expected_unit.get(field) or ""):
                failures.append(f"{unit_id}:{reviewer_id}:{field}_binding_mismatch")
        boolean_fields = (
            ("grouped_correct", "unsafe_synonym_merge", "unresolved")
            if expected_unit.get("review_kind") == "core_pair"
            else ("modifier_correct", "unresolved")
        )
        if any(not isinstance(review.get(field), bool) for field in boolean_fields):
            failures.append(f"{unit_id}:{reviewer_id}:review_response_contract_invalid")
        review_groups[unit_id].append(str(review.get("decision") or ""))
    for unit_id in expected_units:
        unit_rows = rows_by_unit.get(unit_id) or []
        if (
            len(unit_rows) != 2
            or {str(row.get("reviewer_id") or "") for row in unit_rows} != reviewer_ids
        ):
            failures.append(f"{unit_id}:reviewer_coverage_not_exactly_two")

    metrics = _review_metrics(review_rows)
    metrics["unresolved_rate"] = unresolved / max(1, total)
    metrics["candidate_coverage"] = 1 - sum("candidate_coverage" in x or "missing_annotation" in x for x in failures) / max(1, len(cases))
    metrics["modifier_citation_closure"] = modifier_source_closed_n / max(1, modifier_claim_n)
    metrics["modifier_evidence_support_rate"] = modifier_evidence_supported_n / max(1, modifier_claim_n)
    metrics["nontrivial_corruption_case_rate"] = nontrivial_corrupt_cases / max(1, len(cases))
    metrics["upstream_admission_gate_passed"] = upstream_passed
    metrics["expected_group_pair_unit_n"] = len(expected_pair_ids)
    metrics["expected_modifier_axis_unit_n"] = len(expected_modifier_ids)
    metrics["reviewer_model_n"] = len(set(reviewer_model_by_id.values()))
    metrics["raw_agreement"], metrics["gwet_ac1"] = _gwet_ac1(review_groups)
    if metrics["grouped_pair_precision"] is None:
        failures.append("grouped_pair_precision_not_evaluable")
    elif metrics["grouped_pair_precision"] < FACTORIZATION_PAIR_PRECISION_MIN:
        failures.append("grouped_pair_precision_below_0.95")
    if metrics["modifier_axis_precision"] is None:
        failures.append("modifier_axis_precision_not_evaluable")
    elif metrics["modifier_axis_precision"] < FACTORIZATION_MODIFIER_AXIS_MIN:
        failures.append("modifier_axis_precision_below_0.85")
    if metrics["unsafe_synonym_merges"] != 0:
        failures.append("unsafe_synonym_merge_nonzero")
    if metrics["unresolved_rate"] > .10:
        failures.append("unresolved_rate_above_0.10")
    if modifier_claim_n and metrics["modifier_citation_closure"] < 1.0:
        failures.append("modifier_citation_closure_below_1.0")
    if metrics["nontrivial_corruption_case_rate"] < .90:
        failures.append("nontrivial_corruption_case_rate_below_0.90")
    if metrics["raw_agreement"] < .90 or metrics["gwet_ac1"] < .75:
        failures.append("reviewer_reliability_below_gate")
    scope = "conditional conversion only on gold-conditioned E5 base4; no recall/open-diagnosis claim"
    if not upstream_passed:
        scope += "; isolated topology probe because the upstream admission gate did not pass"
    gate = _gate_write(out, "factorization", not failures, failures, metrics, scope)
    gate["isolated_topology_probe"] = not upstream_passed
    gate["deployment_integration_eligible"] = bool(upstream_passed and gate["passed"])
    gate["provenance"] = {
        "gate_code_sha256": file_sha256(Path(__file__)),
        "source_commit": freeze_manifest.get("source_commit"),
        "freeze_id": freeze_manifest.get("freeze_id"),
        "freeze_manifest_sha256": file_sha256(freeze_manifest_path),
        "freeze_cases_sha256": file_sha256(freeze_cases_path),
        "annotation_rows_sha256": file_sha256(Path(annotations)),
        "annotation_manifest_sha256": file_sha256(annotation_manifest_path),
        "review_rows_sha256": file_sha256(Path(reviews)),
        "review_manifest_sha256": file_sha256(review_manifest_path),
        "upstream_admission_gate_sha256": file_sha256(Path(admission_gate)),
    }
    atomic_json(out, gate)
    return gate


def freeze_active(out: Path, *, joined: Path = E5_JOINED) -> dict[str, Any]:
    """Freeze builder inputs.  Builders see raw text only, never candidates."""
    rows = [{
        "case_key": str(raw["case_key"]), "family": str(raw["family"]),
        "builder_payload": {"case_key": str(raw["case_key"]), "raw_vignette": str(raw["vignette"])},
        # Kept outside builder_payload for the later target-blind policy stage.
        "policy_candidates": _clean_candidates(raw["candidates"], evidence=False),
    } for raw in _e5_base4(joined)]
    return _write_freeze(out, "active", rows, [joined], arms=list(ACTIVE_ARMS), selection="after builder validity, SHA-balanced 32 DA/32 MCR", estimand="retrospective off-policy action benchmark; conditional conversion only")


def _valid_segment(text: str, segment: Mapping[str, Any]) -> bool:
    start, end = int(segment.get("start", -1)), int(segment.get("end", -1))
    return 0 <= start < end <= len(text) and text[start:end] == str(segment.get("text") or "")


def _majority(values: Sequence[Any]) -> Any:
    counts = Counter(values)
    return sorted(counts, key=lambda x: (-counts[x], str(x)))[0] if counts else None


def _strict_consensus(values: Sequence[Any]) -> Any:
    """Return a strict majority; two-reviewer disagreement remains unresolved."""
    counts = Counter(values)
    if not counts:
        return None
    winner, n = sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))[0]
    return winner if n > len(values) / 2 else None


def _gwet_ac1(groups: Mapping[str, Sequence[str]]) -> tuple[float, float]:
    usable = [list(v) for v in groups.values() if len(v) >= 2]
    if not usable:
        return 0.0, 0.0
    agreements = []
    all_values: list[str] = []
    for values in usable:
        all_values.extend(values)
        pairs = len(values) * (len(values) - 1) / 2
        agreements.append(sum(n * (n - 1) / 2 for n in Counter(values).values()) / pairs)
    po = statistics.fmean(agreements)
    prevalence = [n / len(all_values) for n in Counter(all_values).values()]
    k = len(prevalence)
    pe = (sum(p * (1 - p) for p in prevalence) / (k - 1)) if k > 1 else 0.0
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def _macro_f1(expected: Mapping[str, str], predicted: Mapping[str, str]) -> float:
    labels = sorted(set(expected.values()) | set(predicted.values()))
    if not labels:
        return 0.0
    scores = []
    for label in labels:
        tp = sum(expected[k] == label and predicted.get(k) == label for k in expected)
        fp = sum(expected.get(k) != label and value == label for k, value in predicted.items())
        fn = sum(value == label and predicted.get(k) != label for k, value in expected.items())
        scores.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return statistics.fmean(scores)


def gate_active(freeze_dir: Path, annotations: Path, reviews: Path, predictions: Path, out: Path) -> dict[str, Any]:
    freeze_dir = Path(freeze_dir)
    freeze_manifest, case_rows, freeze_failures = _formal_freeze_validation(
        freeze_dir,
        "active",
        ACTIVE_ARMS,
        expected_case_n=200,
        expected_family_n={"DA": 100, "MCR": 100},
        expected_sources=[E5_JOINED],
    )
    cases = {str(row["case_key"]): row for row in case_rows}
    anns = _annotation_index(annotations)
    review_rows = read_jsonl(reviews)
    prediction_rows = read_jsonl(predictions)
    predictions_by_case = {str(r["case_key"]): r for r in prediction_rows}
    failures: list[str] = list(freeze_failures)
    case_keys = set(cases)
    freeze_cases_path = freeze_dir / "cases.jsonl"
    runner_code = ROOT / "analysis/mechanism_v2/ceiling_closure_online.py"
    online_runner_code = ROOT / "analysis/mechanism_v2/online_runner.py"
    runner_hash = file_sha256(runner_code)
    online_runner_hash = file_sha256(online_runner_code)
    frozen_commit = str(freeze_manifest.get("source_commit") or "")
    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
        ACTIVE_BUILDER_PROMPT,
        ACTIVE_POLICY_PROMPT,
        ACTIVE_REVIEW_PROMPT,
        _active_builder_validator,
        _active_review_validator,
        _policy_job_validator,
    )

    builder_manifest_path = Path(annotations).parent / "active_builder_annotations.manifest.json"
    review_manifest_path = Path(reviews).parent / "active_reviews.manifest.json"
    prediction_manifest_path = Path(predictions).parent / "active_predictions.manifest.json"
    product_specs = (
        (
            "builder", builder_manifest_path, "active_builder_annotations",
            Path(annotations), anns, ADMISSION_CONSTRUCTION_MODEL, 1,
            {file_sha256(freeze_cases_path)},
        ),
        (
            "reviews", review_manifest_path, "active_reviews",
            Path(reviews), review_rows, None, 2,
            {file_sha256(freeze_cases_path), file_sha256(Path(annotations))},
        ),
        (
            "predictions", prediction_manifest_path, "active_predictions",
            Path(predictions), prediction_rows, ADMISSION_CONSTRUCTION_MODEL, 1,
            {file_sha256(freeze_cases_path), file_sha256(Path(annotations))},
        ),
    )
    product_manifests: dict[str, dict[str, Any]] = {}
    product_stage_raw: dict[str, list[tuple[str, dict[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    for product_name, manifest_path, product_id, product_path, product_rows, model, stage_n, required_inputs in product_specs:
        manifest = _json(manifest_path) if manifest_path.is_file() else {}
        product_manifests[product_name] = manifest
        if (
            not manifest
            or manifest.get("product") != product_id
            or int(manifest.get("row_n") or -1) != len(product_rows)
            or str(manifest.get("file_sha256") or "") != file_sha256(product_path)
            or str(manifest.get("rows_sha256") or "")
            != canonical_sha256(list(product_rows.values()) if isinstance(product_rows, Mapping) else product_rows)
            or str(manifest.get("generator_code_sha256") or "") != runner_hash
            or str(manifest.get("source_commit") or "") != frozen_commit
            or not required_inputs.issubset(_manifest_input_hashes(manifest))
            or (model is not None and str(manifest.get("model") or "") != model)
        ):
            failures.append(f"active_{product_name}_manifest_binding_invalid")
        stage_bindings = manifest.get("online_stage_manifests") or []
        if len(stage_bindings) != stage_n:
            failures.append(f"active_{product_name}_stage_coverage_invalid")
        for binding in stage_bindings:
            if not isinstance(binding, Mapping):
                failures.append(f"active_{product_name}_stage_binding_invalid")
                continue
            stage_path = Path(str(binding.get("path") or ""))
            if not stage_path.is_absolute():
                stage_path = manifest_path.parent / stage_path
            if not stage_path.is_file() or file_sha256(stage_path) != str(binding.get("sha256") or ""):
                failures.append(f"active_{product_name}_stage_binding_invalid")
                continue
            stage_doc = _json(stage_path)
            raw_path = stage_path.parent / "raw_results.jsonl"
            telemetry_path = stage_path.parent / "telemetry_summary.json"
            raw_telemetry_path = stage_path.parent / "telemetry.jsonl"
            raw_rows = read_jsonl(raw_path)
            telemetry_doc = _json(telemetry_path) if telemetry_path.is_file() else {}
            raw_telemetry = read_jsonl(raw_telemetry_path)
            task_n = int(stage_doc.get("task_n") or -1)
            success_n = int(stage_doc.get("success_n") or 0)
            failure_n = int(stage_doc.get("failure_n") or 0)
            reviewer_id = stage_path.parent.name
            expected_task_contracts: list[dict[str, Any]] = []
            expected_task_by_id: dict[str, dict[str, Any]] = {}
            for case in case_rows:
                case_key = str(case["case_key"])
                if product_name == "builder":
                    task_stage = "active_builder"
                    module = "CeilingActiveEvidenceBuilder"
                    prompt = ACTIVE_BUILDER_PROMPT
                    payload = {
                        "case_key": case_key,
                        "raw_vignette": case["builder_payload"]["raw_vignette"],
                    }
                    task_id = f"{case_key}|active_builder"
                elif product_name == "predictions":
                    task_stage = "active_prediction"
                    module = "CeilingActiveTypedPolicyCalibration"
                    prompt = ACTIVE_POLICY_PROMPT
                    ann = anns.get(case_key) or {}
                    actions = [
                        {
                            key: action[key]
                            for key in (
                                "action_id", "action_type", "action_name", "cost",
                                "cost_band", "delay", "risk",
                            )
                            if key in action
                        }
                        for action in ann.get("actions") or []
                        if action.get("status") == "performed"
                    ]
                    payload = {
                        "case_key": case_key,
                        "initial_vignette": ann.get("initial_text"),
                        "candidates": case["policy_candidates"],
                        "action_menu": actions,
                    }
                    task_id = f"{case_key}|active_prediction"
                else:
                    task_stage = "active_model_panel"
                    module = f"CeilingActiveModelPanel_{reviewer_id}"
                    prompt = ACTIVE_REVIEW_PROMPT
                    payload = {
                        "case_key": case_key,
                        "raw_vignette": case["builder_payload"]["raw_vignette"],
                        "policy_candidates": case["policy_candidates"],
                        "builder_annotation": anns.get(case_key),
                    }
                    task_id = f"{case_key}|active_review|{reviewer_id}"
                prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                payload_sha = canonical_sha256(payload)
                cache_key = canonical_sha256({
                    "schema": "mechanism_v2_online_call_v1",
                    "model": str(stage_doc.get("model") or ""),
                    "module": module,
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                    "temperature": 0.0,
                })
                expected_task_by_id[task_id] = {
                    "case_key": case_key,
                    "stage": task_stage,
                    "payload": payload,
                    "prompt_sha256": prompt_sha,
                    "payload_sha256": payload_sha,
                    "cache_key": cache_key,
                }
                expected_task_contracts.append({
                    "task_id": task_id, "module": module, "prompt": prompt, "payload": payload,
                })
            if (
                not raw_path.is_file()
                or not telemetry_path.is_file()
                or not raw_telemetry_path.is_file()
                or task_n != len(case_rows)
                or len(raw_rows) != task_n
                or success_n + failure_n != task_n
                or sum(bool(row.get("success")) for row in raw_rows) != success_n
                or sum(not bool(row.get("success")) for row in raw_rows) != failure_n
                or any(
                    str(row.get("model") or "") != str(stage_doc.get("model") or "")
                    for row in raw_rows
                )
                or {str(row.get("task_id") or "") for row in raw_rows}
                != set(expected_task_by_id)
                or canonical_sha256(expected_task_contracts)
                != str(stage_doc.get("semantic_input_sha256") or "")
                or sorted({value["prompt_sha256"] for value in expected_task_by_id.values()})
                != list(stage_doc.get("prompt_sha256s") or [])
                or any(
                    str(row.get("case_key") or "") != expected_task_by_id[str(row.get("task_id") or "")]["case_key"]
                    or str(row.get("stage") or "") != expected_task_by_id[str(row.get("task_id") or "")]["stage"]
                    or str(row.get("prompt_sha256") or "")
                    != expected_task_by_id[str(row.get("task_id") or "")]["prompt_sha256"]
                    or str(row.get("payload_sha256") or "")
                    != expected_task_by_id[str(row.get("task_id") or "")]["payload_sha256"]
                    or (
                        bool(row.get("success") or row.get("cache_hit"))
                        and str(row.get("cache_key") or "")
                        != expected_task_by_id[str(row.get("task_id") or "")]["cache_key"]
                    )
                    for row in raw_rows
                    if str(row.get("task_id") or "") in expected_task_by_id
                )
                or file_sha256(raw_path) != str(stage_doc.get("results_file_sha256") or "")
                or canonical_sha256(raw_rows) != str(stage_doc.get("results_sha256") or "")
                or file_sha256(raw_telemetry_path) != str(stage_doc.get("telemetry_sha256") or "")
                or aggregate_telemetry(raw_telemetry) != telemetry_doc
                or telemetry_doc != (stage_doc.get("telemetry_summary") or {})
                or str(stage_doc.get("runner_code_sha256") or "") != runner_hash
                or str(stage_doc.get("online_runner_code_sha256") or "") != online_runner_hash
                or str(stage_doc.get("source_commit") or "") != frozen_commit
                or len({str(row.get("task_id") or "") for row in raw_rows}) != len(raw_rows)
                or {str(row.get("case_key") or "") for row in raw_rows} != case_keys
            ):
                failures.append(f"active_{product_name}_stage_product_binding_invalid")
            for row in raw_rows:
                if not row.get("success"):
                    continue
                task_id = str(row.get("task_id") or "")
                expected = expected_task_by_id.get(task_id) or {}
                response = row.get("response")
                if not isinstance(response, Mapping):
                    failures.append(f"active_{product_name}_raw_response_contract_invalid")
                    continue
                case_key = str(expected.get("case_key") or "")
                if product_name == "builder":
                    validator = _active_builder_validator(
                        str(cases.get(case_key, {}).get("builder_payload", {}).get("raw_vignette") or "")
                    )
                elif product_name == "reviews":
                    validator = _active_review_validator({
                        str(action.get("action_id") or ""): action
                        for action in (anns.get(case_key) or {}).get("actions") or []
                    })
                else:
                    validator = _policy_job_validator(expected.get("payload") or {})
                if validator(response) is not None:
                    failures.append(f"active_{product_name}_raw_response_contract_invalid")
            product_stage_raw[product_name].append((stage_path.parent.name, stage_doc, raw_rows))

    review_specs = product_manifests.get("reviews", {}).get("reviewers") or []
    review_model_by_id = {
        str(row.get("reviewer_id") or ""): str(row.get("model") or "")
        for row in review_specs if isinstance(row, Mapping)
    }
    if (
        len(review_specs) != 2
        or set(review_model_by_id.values()) != set(CLOSURE_GATE_REVIEW_MODELS)
        or len(review_model_by_id) != 2
    ):
        failures.append("active_reviewer_model_contract_invalid")
    if {
        str(stage_doc.get("model") or "")
        for _, stage_doc, _ in product_stage_raw.get("reviews", [])
    } != set(CLOSURE_GATE_REVIEW_MODELS):
        failures.append("active_review_stage_model_binding_invalid")
    for product_name in ("builder", "predictions"):
        if any(
            str(stage_doc.get("model") or "") != ADMISSION_CONSTRUCTION_MODEL
            for _, stage_doc, _ in product_stage_raw.get(product_name, [])
        ):
            failures.append(f"active_{product_name}_model_substitution_forbidden")

    builder_raw = {
        str(row.get("case_key") or ""): row
        for _, _, rows in product_stage_raw.get("builder", []) for row in rows
    }
    prediction_raw = {
        str(row.get("case_key") or ""): row
        for _, _, rows in product_stage_raw.get("predictions", []) for row in rows
    }
    review_raw: dict[tuple[str, str], dict[str, Any]] = {}
    for reviewer_id, stage_doc, rows in product_stage_raw.get("reviews", []):
        if review_model_by_id.get(reviewer_id) != str(stage_doc.get("model") or ""):
            failures.append("active_review_directory_model_binding_invalid")
        for row in rows:
            key = (reviewer_id, str(row.get("case_key") or ""))
            if key in review_raw:
                failures.append("active_review_raw_identity_duplicate")
            review_raw[key] = row

    for case_key, case in cases.items():
        raw_row = builder_raw.get(case_key)
        ann = anns.get(case_key)
        if raw_row is None or ann is None:
            failures.append(f"{case_key}:active_builder_raw_or_product_missing")
            continue
        response = raw_row.get("response") if raw_row.get("success") else {}
        initial_span = (response or {}).get("initial_span") or {}
        expected_ann = {
            "case_key": case_key,
            "initial_text": str(initial_span.get("text") or ""),
            "initial_span": initial_span,
            "actions": list((response or {}).get("actions") or []),
            "annotation_success": bool(raw_row.get("success")),
            "error": raw_row.get("error"),
            "provenance": "outcome_blind_model_builder",
        }
        if canonical_sha256(ann) != canonical_sha256(expected_ann):
            failures.append(f"{case_key}:active_builder_derivation_binding_invalid")

        raw_prediction = prediction_raw.get(case_key)
        prediction = predictions_by_case.get(case_key)
        if raw_prediction is None or prediction is None:
            failures.append(f"{case_key}:active_prediction_raw_or_product_missing")
        else:
            prediction_response = raw_prediction.get("response") or {}
            expected_prediction = {
                "case_key": case_key,
                "top_pair": list(prediction_response.get("top_pair") or []),
                "need_type": str(prediction_response.get("need_type") or "unresolved"),
                "action_id": str(prediction_response.get("action_id") or ""),
                "expected_result_and_odds_shift": str(
                    prediction_response.get("expected_result_and_odds_shift") or ""
                ),
                "abstain": bool(prediction_response.get("abstain", True)),
                "success": bool(raw_prediction.get("success")),
                "error": raw_prediction.get("error"),
                "provenance": "outcome_blind_model_policy_calibration",
            }
            if canonical_sha256(prediction) != canonical_sha256(expected_prediction):
                failures.append(f"{case_key}:active_prediction_derivation_binding_invalid")

    expected_review_rows: dict[tuple[str, str], dict[str, Any]] = {}
    for reviewer_id, reviewer_model in review_model_by_id.items():
        for case_key in cases:
            raw_row = review_raw.get((reviewer_id, case_key))
            ann = anns.get(case_key) or {}
            if raw_row is None:
                failures.append(f"{case_key}:{reviewer_id}:active_review_raw_missing")
                continue
            if str(raw_row.get("model") or "") != reviewer_model:
                failures.append(f"{case_key}:{reviewer_id}:active_review_raw_model_invalid")
            response = raw_row.get("response") if raw_row.get("success") else {}
            response = response or {}
            raw_action_rows = response.get("action_reviews") or []
            action_ids = [
                str(item.get("action_id") or "")
                for item in raw_action_rows if isinstance(item, Mapping)
            ]
            expected_action_ids = sorted(
                str(action["action_id"]) for action in ann.get("actions") or []
            )
            response_contract_valid = bool(
                isinstance(raw_action_rows, list)
                and len(action_ids) == len(raw_action_rows) == len(set(action_ids))
                and sorted(action_ids) == expected_action_ids
                and str(response.get("need_type") or "") in NEED_TYPES
                and isinstance(response.get("direct_answer_leak"), bool)
                and all(
                    isinstance(item, Mapping)
                    and all(
                        isinstance(item.get(field), bool)
                        for field in (
                            "availability_valid", "cost_valid", "risk_valid", "relevant",
                            "resolves_need", "wrong_episode_or_object_binding",
                            "unnecessary_high_risk_action",
                        )
                    )
                    and isinstance(item.get("information_gain"), int)
                    and not isinstance(item.get("information_gain"), bool)
                    and item.get("information_gain") in {0, 1, 2, 3}
                    for item in raw_action_rows
                )
            ) if raw_row.get("success") else not raw_action_rows
            if not response_contract_valid:
                failures.append(f"{case_key}:{reviewer_id}:active_review_raw_contract_invalid")
            action_review = {
                str(item.get("action_id") or ""): item
                for item in raw_action_rows if isinstance(item, Mapping)
            }
            relevant = sorted(
                action_id for action_id, item in action_review.items()
                if item.get("relevant") and item.get("availability_valid")
            )
            available = sorted(
                action_id for action_id, item in action_review.items()
                if item.get("availability_valid")
            )
            resolving = sorted(
                action_id for action_id, item in action_review.items()
                if item.get("resolves_need") and item.get("availability_valid")
            )
            cost_valid = sorted(
                action_id for action_id, item in action_review.items() if item.get("cost_valid")
            )
            risk_valid = sorted(
                action_id for action_id, item in action_review.items() if item.get("risk_valid")
            )
            expected_review_rows[(case_key, reviewer_id)] = {
                "case_key": case_key,
                "reviewer_id": reviewer_id,
                "reviewer_model": reviewer_model,
                "panel_provenance": "independent_model_panel",
                "need_type": str(response.get("need_type") or "unresolved"),
                "relevant_action_ids": relevant,
                "direct_answer_leak": bool(response.get("direct_answer_leak", True)),
                "available_action_ids": available,
                "resolving_action_ids": resolving,
                "cost_valid_action_ids": cost_valid,
                "risk_valid_action_ids": risk_valid,
                "action_audits": [
                    {
                        "action_id": action_id,
                        "availability_valid": bool(item.get("availability_valid")),
                        "cost_valid": bool(item.get("cost_valid")),
                        "risk_valid": bool(item.get("risk_valid")),
                        "relevant": bool(item.get("relevant")),
                        "resolves_need": bool(item.get("resolves_need")),
                        "information_gain": int(item.get("information_gain", 0)),
                        "wrong_episode_or_object_binding": bool(
                            item.get("wrong_episode_or_object_binding")
                        ),
                        "unnecessary_high_risk_action": bool(
                            item.get("unnecessary_high_risk_action")
                        ),
                    }
                    for action_id, item in sorted(action_review.items())
                ],
                "reviewed_action_ids": sorted(action_review),
                "expected_action_ids": expected_action_ids,
                "success": bool(raw_row.get("success")),
                "error": raw_row.get("error"),
                "cache_key": raw_row.get("cache_key"),
                "payload_sha256": raw_row.get("payload_sha256"),
                "prompt_sha256": raw_row.get("prompt_sha256"),
                "response_sha256": canonical_sha256(raw_row.get("response") or {}),
            }
    observed_review_rows = {
        (str(row.get("case_key") or ""), str(row.get("reviewer_id") or "")): row
        for row in review_rows
    }
    if set(observed_review_rows) != set(expected_review_rows) or any(
        canonical_sha256(observed_review_rows[key]) != canonical_sha256(expected)
        for key, expected in expected_review_rows.items()
        if key in observed_review_rows
    ):
        failures.append("active_review_flat_derivation_binding_invalid")
    if (
        len(prediction_rows) != len(predictions_by_case)
        or len(prediction_rows) != len(cases)
        or set(predictions_by_case) != set(cases)
        or any(row.get("success") is not True for row in predictions_by_case.values())
    ):
        failures.append("active_prediction_full_success_required")
    builder_valid_by_family: dict[str, list[str]] = defaultdict(list)
    availability_ok = 0
    action_n = 0
    for case_key, case in cases.items():
        ann = anns.get(case_key)
        if not ann:
            failures.append(f"{case_key}:missing_builder_annotation")
            continue
        raw = case["builder_payload"]["raw_vignette"]
        initial = str(ann.get("initial_text") or "")
        initial_span = ann.get("initial_span") or {}
        if not _valid_segment(raw, initial_span) or str(initial_span.get("text") or "") != initial:
            failures.append(f"{case_key}:initial_span_closure")
            continue
        initial_end = int(initial_span["end"])
        actions = ann.get("actions") or []
        ids = [str(a.get("action_id")) for a in actions]
        if len(set(ids)) != len(ids):
            failures.append(f"{case_key}:duplicate_action_id")
        valid_actions = []
        intervals = []
        for action in actions:
            action_n += 1
            status = str(action.get("status"))
            if status in ACTION_STATUSES:
                availability_ok += 1
            else:
                failures.append(f"{case_key}:{action.get('action_id')}:bad_status")
            if status == "performed":
                segment = action.get("result_span") or {}
                if not _valid_segment(raw, segment):
                    failures.append(f"{case_key}:{action.get('action_id')}:offset_closure")
                    continue
                if int(segment["start"]) < initial_end:
                    failures.append(f"{case_key}:{action.get('action_id')}:result_not_later_than_initial")
                    continue
                interval = (int(segment["start"]), int(segment["end"]))
                intervals.append(interval)
                if segment["text"] in initial:
                    failures.append(f"{case_key}:{action.get('action_id')}:result_visible_initially")
                valid_actions.append(action)
        if any(a[0] < b[1] and b[0] < a[1] for i, a in enumerate(intervals) for b in intervals[i + 1 :]):
            failures.append(f"{case_key}:overlapping_results")
        if len(valid_actions) >= 3 and len({str(a.get("action_type")) for a in valid_actions}) >= 2:
            builder_valid_by_family[case["family"]].append(case_key)
    by_review_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in review_rows:
        by_review_case[str(row["case_key"])].append(row)
    for case_key in cases:
        rows = by_review_case.get(case_key, [])
        if (
            len(rows) != 2
            or len({str(row.get("reviewer_id")) for row in rows}) != 2
            or len({str(row.get("reviewer_model")) for row in rows}) != 2
            or any(row.get("panel_provenance") != "independent_model_panel" for row in rows)
        ):
            failures.append(f"{case_key}:requires_two_independent_reviews")
    need_groups = {key: [str(r.get("need_type")) for r in rows] for key, rows in by_review_case.items()}
    agreement, ac1 = _gwet_ac1(need_groups)
    adjudicated_need = {
        key: str(value) if (value := _strict_consensus(values)) is not None else "unresolved"
        for key, values in need_groups.items()
    }
    pred_need = {key: str(row.get("need_type")) for key, row in predictions_by_case.items()}
    f1 = _macro_f1(adjudicated_need, pred_need)
    relevance_hits = relevance_n = leakage = 0
    historical_availability_hits = historical_availability_n = 0
    reviewed_cost_valid_hits = reviewed_risk_valid_hits = 0
    cost_match_hits = cost_match_n = 0
    cost_match_valid_cases: set[str] = set()
    review_valid_cases: set[str] = set()
    for case_key, rows in by_review_case.items():
        row_valid = len(rows) == 2
        for row in rows:
            expected_ids = {str(value) for value in row.get("expected_action_ids") or []}
            reviewed_ids = {str(value) for value in row.get("reviewed_action_ids") or []}
            available_ids = {str(value) for value in row.get("available_action_ids") or []}
            cost_valid_ids = {str(value) for value in row.get("cost_valid_action_ids") or []}
            risk_valid_ids = {str(value) for value in row.get("risk_valid_action_ids") or []}
            if reviewed_ids != expected_ids or not available_ids <= expected_ids:
                row_valid = False
            historical_availability_n += len(expected_ids)
            historical_availability_hits += len(available_ids & expected_ids)
            reviewed_cost_valid_hits += len(cost_valid_ids & expected_ids)
            reviewed_risk_valid_hits += len(risk_valid_ids & expected_ids)
            if (
                available_ids != expected_ids or cost_valid_ids != expected_ids or risk_valid_ids != expected_ids
                or row.get("success") is not True or bool(row.get("direct_answer_leak"))
            ):
                row_valid = False
        if row_valid:
            review_valid_cases.add(case_key)
    for case_key, prediction in predictions_by_case.items():
        reviews_for_case = by_review_case.get(case_key, [])
        action_id = str(prediction.get("action_id"))
        actions = {
            str(action.get("action_id")): action
            for action in (anns.get(case_key) or {}).get("actions") or []
            if action.get("status") == "performed"
        }
        chosen = actions.get(action_id)
        cost_match_n += 1
        has_cost_peer = bool(chosen) and any(
            peer_id != action_id and peer.get("cost_band") == chosen.get("cost_band")
            for peer_id, peer in actions.items()
        )
        cost_match_hits += has_cost_peer
        if has_cost_peer:
            cost_match_valid_cases.add(case_key)
        votes = [action_id in {str(x) for x in r.get("relevant_action_ids") or []} for r in reviews_for_case]
        if votes:
            relevance_n += 1
            relevance_hits += bool(_majority(votes))
        leakage += sum(bool(r.get("direct_answer_leak")) for r in reviews_for_case)
    metrics = {
        "action_availability_rate": availability_ok / max(1, action_n),
        "raw_agreement": agreement,
        "gwet_ac1": ac1,
        "missing_need_macro_f1": f1,
        "typed_action_relevance_precision": relevance_hits / max(1, relevance_n),
        "reviewed_historical_availability_rate": historical_availability_hits / max(1, historical_availability_n),
        "reviewed_cost_validity_rate": reviewed_cost_valid_hits / max(1, historical_availability_n),
        "reviewed_risk_validity_rate": reviewed_risk_valid_hits / max(1, historical_availability_n),
        "cost_matched_control_availability_rate": cost_match_hits / max(1, cost_match_n),
        "direct_answer_leak_reviews": leakage,
    }
    thresholds = {
        "action_availability_rate": 1.0, "raw_agreement": .90, "gwet_ac1": .75,
        "missing_need_macro_f1": .70, "typed_action_relevance_precision": .75,
        "reviewed_historical_availability_rate": 1.0,
        "reviewed_cost_validity_rate": 1.0,
        "reviewed_risk_validity_rate": 1.0,
        "cost_matched_control_availability_rate": 1.0,
    }
    for name, threshold in thresholds.items():
        if metrics[name] < threshold:
            failures.append(f"{name}_below_{threshold}")
    if leakage:
        failures.append("direct_answer_leak_nonzero")
    selected: list[str] = []
    for family in ("DA", "MCR"):
        eligible = [
            case_key for case_key in builder_valid_by_family[family]
            if case_key in review_valid_cases and case_key in cost_match_valid_cases
        ]
        ranked = sorted(eligible, key=lambda x: (stable_seed("active64-v1", x), x))
        if len(ranked) < 32:
            failures.append(f"{family}:fewer_than_32_builder_valid")
        selected.extend(ranked[:32])
    gate = _gate_write(out, "active", not failures, failures, metrics, "benchmark construction / retrospective off-policy capability only; not end-to-end ceiling breakthrough")
    gate["gate_stage"] = "construction"
    gate["selected_case_keys"] = sorted(selected)
    gate["selected_case_sha256"] = canonical_sha256(sorted(selected))
    gate["provenance"] = {
        "gate_code_sha256": file_sha256(Path(__file__)),
        "freeze_id": freeze_manifest.get("freeze_id"),
        "freeze_manifest_sha256": file_sha256(freeze_dir / "freeze.json") if (freeze_dir / "freeze.json").is_file() else None,
        "freeze_cases_sha256": file_sha256(freeze_cases_path) if freeze_cases_path.is_file() else None,
        "builder_rows_sha256": file_sha256(Path(annotations)) if Path(annotations).is_file() else None,
        "builder_manifest_sha256": file_sha256(builder_manifest_path) if builder_manifest_path.is_file() else None,
        "review_rows_sha256": file_sha256(Path(reviews)) if Path(reviews).is_file() else None,
        "review_manifest_sha256": file_sha256(review_manifest_path) if review_manifest_path.is_file() else None,
        "prediction_rows_sha256": file_sha256(Path(predictions)) if Path(predictions).is_file() else None,
        "prediction_manifest_sha256": file_sha256(prediction_manifest_path) if prediction_manifest_path.is_file() else None,
        "source_commit": frozen_commit,
        "input_artifacts": {
            "freeze_manifest": _active_artifact_binding(freeze_dir / "freeze.json"),
            "freeze_cases": _active_artifact_binding(freeze_cases_path),
            "builder_rows": _active_artifact_binding(Path(annotations)),
            "builder_manifest": _active_artifact_binding(builder_manifest_path),
            "review_rows": _active_artifact_binding(Path(reviews)),
            "review_manifest": _active_artifact_binding(review_manifest_path),
            "prediction_rows": _active_artifact_binding(Path(predictions)),
            "prediction_manifest": _active_artifact_binding(prediction_manifest_path),
            "gate_code": _active_artifact_binding(Path(__file__)),
            "closure_runner_code": _active_artifact_binding(runner_code),
            "online_runner_code": _active_artifact_binding(online_runner_code),
        },
    }
    atomic_json(out, gate)
    return gate


def _active_action_audits(row: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    audits = row.get("action_audits")
    if not isinstance(audits, list) or not all(isinstance(item, Mapping) for item in audits):
        return {}
    output = {str(item.get("action_id") or ""): item for item in audits}
    return output if "" not in output and len(output) == len(audits) else {}


def _portable_artifact_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _active_artifact_binding(path: Path) -> dict[str, Any]:
    """Return a portable, content-addressed binding for a C3 artifact."""
    resolved = Path(path).resolve()
    return {
        "path": _portable_artifact_path(resolved),
        "sha256": file_sha256(resolved) if resolved.is_file() else None,
    }


def _active_bound_path(binding: Any) -> Path | None:
    if not isinstance(binding, Mapping) or not str(binding.get("path") or ""):
        return None
    path = Path(str(binding["path"]))
    return path if path.is_absolute() else ROOT / path


def _active_binding_valid(binding: Any, expected: Path | None = None) -> bool:
    path = _active_bound_path(binding)
    if path is None or not path.is_file():
        return False
    if expected is not None and path.resolve() != Path(expected).resolve():
        return False
    return str(binding.get("sha256") or "") == file_sha256(path)


def _active_policy_jobs(
    case_rows: Sequence[Mapping[str, Any]],
    anns: Mapping[str, Mapping[str, Any]],
    selected_case_keys: set[str],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for case in case_rows:
        case_key = str(case["case_key"])
        if case_key not in selected_case_keys:
            continue
        ann = anns[case_key]
        menu = [
            {
                key: action[key]
                for key in (
                    "action_id", "action_type", "action_name", "cost",
                    "cost_band", "delay", "risk",
                )
                if key in action
            }
            for action in ann["actions"]
            if action.get("status") == "performed"
        ]
        payload = {
            "case_key": case_key,
            "initial_vignette": ann["initial_text"],
            "candidates": case["policy_candidates"],
            "action_menu": menu,
        }
        jobs.append(_job("active", "typed_policy", case, PROMPTS["active_policy"], payload, stage="policy"))
    return jobs


def _active_post_jobs(
    case_rows: Sequence[Mapping[str, Any]],
    anns: Mapping[str, Mapping[str, Any]],
    selections: Mapping[str, Mapping[str, Any]],
    selected_case_keys: set[str],
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for case in case_rows:
        case_key = str(case["case_key"])
        if case_key not in selected_case_keys:
            continue
        ann = anns[case_key]
        action_by_id = {
            str(action["action_id"]): action
            for action in ann["actions"] if action.get("status") == "performed"
        }
        selection = selections.get(case_key) or {}
        response = selection.get("response") if isinstance(selection.get("response"), Mapping) else {}
        chosen = str(selection.get("action_id") or response.get("action_id") or "")
        if chosen not in action_by_id:
            raise RuntimeError(f"invalid/missing typed action for {case_key}")
        typed = action_by_id[chosen]
        peers = [
            action for action_id, action in action_by_id.items()
            if action_id != chosen and action.get("cost_band") == typed.get("cost_band")
        ]
        if not peers:
            raise RuntimeError(f"no cost-matched random action for {case_key}")
        random_action = sorted(
            peers,
            key=lambda action: (
                stable_seed("active-random-v1", case_key, action["action_id"]),
                action["action_id"],
            ),
        )[0]
        released = {
            "no_acquisition": None,
            "typed_action": typed,
            "cost_matched_random": random_action,
        }
        for arm in ACTIVE_ARMS:
            action = released[arm]
            evidence = None
            visible_vignette = ann["initial_text"]
            if action is not None:
                evidence = {
                    "action_id": action["action_id"],
                    "action_type": action["action_type"],
                    "action_name": action.get("action_name", ""),
                    "historical_status": "performed",
                    "raw_vignette_result_span": action["result_span"],
                }
                visible_vignette += (
                    f"\n\nReleased historically performed {action['action_type']} result: "
                    f"{action['result_span']['text']}"
                )
            payload = {
                "case_key": case_key,
                "vignette": visible_vignette,
                "candidates": case["policy_candidates"],
                "released_evidence": evidence,
            }
            jobs.append(_job("active", arm, case, PROMPTS["active_post"][arm], payload, stage="post"))
    return jobs


def _active_construction_gate_contract_failures(
    construction: Mapping[str, Any],
    freeze_dir: Path,
    annotations: Path,
    reviews: Path | None = None,
) -> list[str]:
    """Verify the transitive inputs that established the C3 construction gate."""
    failures: list[str] = []
    freeze_dir = Path(freeze_dir)
    freeze_manifest_path = freeze_dir / "freeze.json"
    freeze_cases_path = freeze_dir / "cases.jsonl"
    freeze = _json(freeze_manifest_path) if freeze_manifest_path.is_file() else {}
    case_rows = read_jsonl(freeze_cases_path)
    cases = {str(row.get("case_key") or ""): row for row in case_rows}
    provenance = construction.get("provenance") or {}
    artifacts = provenance.get("input_artifacts") or {}
    expected_names = {
        "freeze_manifest", "freeze_cases", "builder_rows", "builder_manifest",
        "review_rows", "review_manifest", "prediction_rows", "prediction_manifest",
        "gate_code", "closure_runner_code", "online_runner_code",
    }
    if (
        construction.get("component") != "active"
        or construction.get("gate_stage") != "construction"
        or not construction.get("passed")
    ):
        failures.append("active_construction_gate_not_passed")
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_names:
        failures.append("active_construction_artifact_set_invalid")
    else:
        for name in sorted(expected_names):
            if not _active_binding_valid(artifacts.get(name)):
                failures.append(f"active_construction_{name}_binding_invalid")
        if not _active_binding_valid(artifacts.get("freeze_manifest"), freeze_manifest_path):
            failures.append("active_construction_freeze_manifest_identity_invalid")
        if not _active_binding_valid(artifacts.get("freeze_cases"), freeze_cases_path):
            failures.append("active_construction_freeze_cases_identity_invalid")
        if not _active_binding_valid(artifacts.get("builder_rows"), Path(annotations)):
            failures.append("active_construction_annotation_identity_invalid")
        if reviews is not None and not _active_binding_valid(artifacts.get("review_rows"), Path(reviews)):
            failures.append("active_construction_review_identity_invalid")
        if not _active_binding_valid(artifacts.get("gate_code"), Path(__file__)):
            failures.append("active_construction_gate_code_identity_invalid")
    selected = [str(value) for value in construction.get("selected_case_keys") or []]
    selected_family = Counter(
        str(cases.get(case_key, {}).get("family") or "") for case_key in selected
    )
    if (
        len(selected) != 64
        or len(set(selected)) != 64
        or set(selected) - set(cases)
        or dict(sorted(selected_family.items())) != {"DA": 32, "MCR": 32}
        or str(construction.get("selected_case_sha256") or "")
        != canonical_sha256(sorted(selected))
        or str(provenance.get("freeze_id") or "") != str(freeze.get("freeze_id") or "")
        or str(provenance.get("source_commit") or "") != str(freeze.get("source_commit") or "")
        or str(provenance.get("gate_code_sha256") or "") != file_sha256(Path(__file__))
        or str(provenance.get("freeze_manifest_sha256") or "") != file_sha256(freeze_manifest_path)
        or str(provenance.get("freeze_cases_sha256") or "") != file_sha256(freeze_cases_path)
        or str(provenance.get("builder_rows_sha256") or "") != file_sha256(Path(annotations))
    ):
        failures.append("active_construction_provenance_invalid")
    if reviews is not None and str(provenance.get("review_rows_sha256") or "") != file_sha256(Path(reviews)):
        failures.append("active_construction_review_provenance_invalid")
    prediction_path = _active_bound_path(
        artifacts.get("prediction_rows") if isinstance(artifacts, Mapping) else None
    )
    bound_reviews_path = _active_bound_path(
        artifacts.get("review_rows") if isinstance(artifacts, Mapping) else None
    )
    if not failures and prediction_path is not None and bound_reviews_path is not None:
        with tempfile.TemporaryDirectory(prefix="active-construction-replay-") as temp_dir:
            replay = gate_active(
                freeze_dir,
                Path(annotations),
                bound_reviews_path,
                prediction_path,
                Path(temp_dir) / "gate.json",
            )
        if canonical_sha256(replay) != canonical_sha256(construction):
            failures.append("active_construction_gate_deterministic_replay_mismatch")
    return failures


def _active_selector_execution_contract_failures(
    jobs_path: Path,
    responses_path: Path,
    expected_jobs: Sequence[Mapping[str, Any]],
    *,
    stage: str,
    freeze_dir: Path,
    scientific_gate: Path,
    annotations: Path,
    selections: Path | None = None,
) -> list[str]:
    """Replay C3 immutable jobs and the audited selector raw/product lineage."""
    failures: list[str] = []
    jobs_path = Path(jobs_path)
    responses_path = Path(responses_path)
    job_manifest_path = jobs_path.with_suffix(".manifest.json")
    response_manifest_path = responses_path.parent / "selector_responses.manifest.json"
    required_paths = {
        "jobs": jobs_path,
        "job_manifest": job_manifest_path,
        "responses": responses_path,
        "response_manifest": response_manifest_path,
    }
    missing = [name for name, path in required_paths.items() if not path.is_file()]
    if missing:
        return [f"active_{stage}_{name}_missing" for name in missing]
    jobs = read_jsonl(jobs_path)
    responses = read_jsonl(responses_path)
    job_manifest = _json(job_manifest_path)
    response_manifest = _json(response_manifest_path)
    freeze_dir = Path(freeze_dir)
    freeze_manifest_path = freeze_dir / "freeze.json"
    freeze_cases_path = freeze_dir / "cases.jsonl"
    freeze = _json(freeze_manifest_path) if freeze_manifest_path.is_file() else {}
    freeze_cases = read_jsonl(freeze_cases_path)
    freeze_case_keys = sorted(str(row.get("case_key") or "") for row in freeze_cases)
    closure_runner = ROOT / "analysis/mechanism_v2/ceiling_closure_online.py"
    online_runner = ROOT / "analysis/mechanism_v2/online_runner.py"

    expected_inputs: dict[str, Path] = {
        "freeze_manifest": freeze_manifest_path,
        "freeze_cases": freeze_cases_path,
        "scientific_gate": Path(scientific_gate),
        "compiler_code": Path(__file__),
        "annotations": Path(annotations),
    }
    if selections is not None:
        expected_inputs["selections"] = Path(selections)
    input_artifacts = job_manifest.get("input_artifacts") or {}
    if not isinstance(input_artifacts, Mapping) or set(input_artifacts) != set(expected_inputs):
        failures.append(f"active_{stage}_job_input_artifact_set_invalid")
    else:
        for name, expected_path in expected_inputs.items():
            if not _active_binding_valid(input_artifacts.get(name), expected_path):
                failures.append(f"active_{stage}_job_{name}_binding_invalid")
    semantic_denominator = [
        [str(job.get("case_key") or ""), str(job.get("arm") or ""), str(job.get("stage") or "")]
        for job in jobs
    ]
    expected_arms = {"typed_policy"} if stage == "policy" else set(ACTIVE_ARMS)
    expected_case_keys = {str(job.get("case_key") or "") for job in expected_jobs}
    arms_by_case: dict[str, set[str]] = defaultdict(set)
    keys: list[tuple[str, str, str]] = []
    for index, job in enumerate(jobs):
        key = (
            str(job.get("case_key") or ""), str(job.get("arm") or ""),
            str(job.get("stage") or ""),
        )
        keys.append(key)
        arms_by_case[key[0]].add(key[1])
        if (
            job.get("component") != "active"
            or key[2] != stage
            or not isinstance(job.get("payload"), Mapping)
            or canonical_sha256(job.get("payload")) != str(job.get("payload_sha256") or "")
            or hashlib.sha256(str(job.get("prompt") or "").encode()).hexdigest()
            != str(job.get("prompt_sha256") or "")
            or _immutable_job_sha256(job) != str(job.get("job_sha256") or "")
        ):
            failures.append(f"active_{stage}_job_{index}_immutable_binding_invalid")
    if (
        len(keys) != len(set(keys))
        or set(arms_by_case) != expected_case_keys
        or any(arms != expected_arms for arms in arms_by_case.values())
        or canonical_sha256(jobs) != canonical_sha256(list(expected_jobs))
    ):
        failures.append(f"active_{stage}_job_denominator_or_reconstruction_invalid")
    expected_job_n = 64 if stage == "policy" else 64 * len(ACTIVE_ARMS)
    if (
        job_manifest.get("kind") != "immutable_job_manifest"
        or job_manifest.get("component") != "active"
        or str(job_manifest.get("stage") or "") != stage
        or str(job_manifest.get("source_commit") or "") != str(freeze.get("source_commit") or "")
        or str(job_manifest.get("generator_code_sha256") or "") != file_sha256(Path(__file__))
        or str(job_manifest.get("freeze_id") or "") != str(freeze.get("freeze_id") or "")
        or str(job_manifest.get("freeze_cases_sha256") or "") != str(freeze.get("cases_sha256") or "")
        or int(job_manifest.get("frozen_case_n") or -1) != 200
        or str(job_manifest.get("frozen_case_keys_sha256") or "") != canonical_sha256(freeze_case_keys)
        or int(job_manifest.get("job_n") or -1) != len(jobs)
        or len(jobs) != expected_job_n
        or str(job_manifest.get("jobs_sha256") or "") != canonical_sha256(jobs)
        or str(job_manifest.get("jobs_file_sha256") or "") != file_sha256(jobs_path)
        or str(job_manifest.get("semantic_denominator_sha256") or "")
        != canonical_sha256(semantic_denominator)
        or job_manifest.get("api_called") is not False
    ):
        failures.append(f"active_{stage}_job_manifest_binding_invalid")

    product_inputs = response_manifest.get("input_files") or []
    if (
        response_manifest.get("product") != "selector_responses"
        or str(response_manifest.get("source_commit") or "") != str(freeze.get("source_commit") or "")
        or str(response_manifest.get("generator_code_sha256") or "") != file_sha256(closure_runner)
        or str(response_manifest.get("model") or "") != CLOSURE_COMPARATOR_MODEL
        or int(response_manifest.get("row_n") or -1) != len(responses)
        or str(response_manifest.get("file_sha256") or "") != file_sha256(responses_path)
        or str(response_manifest.get("rows_sha256") or "") != canonical_sha256(responses)
        or len(product_inputs) != 1
        or not _active_binding_valid(product_inputs[0] if product_inputs else None, jobs_path)
    ):
        failures.append(f"active_{stage}_response_product_binding_invalid")
    stage_bindings = response_manifest.get("online_stage_manifests") or []
    if len(stage_bindings) != 1 or not isinstance(stage_bindings[0] if stage_bindings else None, Mapping):
        return failures + [f"active_{stage}_response_stage_coverage_invalid"]
    stage_binding = stage_bindings[0]
    stage_path = Path(str(stage_binding.get("path") or ""))
    if not stage_path.is_absolute():
        stage_path = response_manifest_path.parent / stage_path
    if not stage_path.is_file() or file_sha256(stage_path) != str(stage_binding.get("sha256") or ""):
        return failures + [f"active_{stage}_response_stage_binding_invalid"]
    stage_doc = _json(stage_path)
    raw_path = stage_path.parent / "raw_results.jsonl"
    raw_telemetry_path = stage_path.parent / "telemetry.jsonl"
    telemetry_summary_path = stage_path.parent / "telemetry_summary.json"
    if not raw_path.is_file() or not raw_telemetry_path.is_file() or not telemetry_summary_path.is_file():
        return failures + [f"active_{stage}_response_stage_ledger_missing"]
    raw_rows = read_jsonl(raw_path)
    raw_telemetry = read_jsonl(raw_telemetry_path)
    telemetry_summary = _json(telemetry_summary_path)
    expected_by_key = {
        (
            str(job["case_key"]), str(job["arm"]), str(job.get("stage") or "")
        ): job
        for job in expected_jobs
    }
    module = f"CeilingSelector_active_{stage}"
    expected_tasks = [
        {
            "task_id": "|".join((str(job["case_key"]), str(job["arm"]), stage)),
            "module": module,
            "prompt": job["prompt"],
            "payload": job["payload"],
        }
        for job in expected_jobs
    ]
    raw_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    raw_contract_invalid = False
    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
        _policy_job_validator,
        _selector_validator,
    )
    for raw in raw_rows:
        key = (
            str(raw.get("case_key") or ""), str(raw.get("arm") or ""),
            str(raw.get("stage") or ""),
        )
        job = expected_by_key.get(key)
        if key in raw_by_key:
            raw_contract_invalid = True
        raw_by_key[key] = raw
        if job is None:
            raw_contract_invalid = True
            continue
        task_id = "|".join(key)
        prompt_sha = hashlib.sha256(str(job["prompt"]).encode()).hexdigest()
        payload_sha = canonical_sha256(job["payload"])
        expected_cache_key = canonical_sha256({
            "schema": "mechanism_v2_online_call_v1",
            "model": CLOSURE_COMPARATOR_MODEL,
            "module": module,
            "prompt_sha256": prompt_sha,
            "payload_sha256": payload_sha,
            "temperature": 0.0,
        })
        response = raw.get("response")
        validator = (
            _policy_job_validator(job["payload"])
            if stage == "policy" else _selector_validator(job["payload"])
        )
        if (
            str(raw.get("task_id") or "") != task_id
            or raw.get("component") != "active"
            or str(raw.get("model") or "") != CLOSURE_COMPARATOR_MODEL
            or not isinstance(raw.get("success"), bool)
            or not isinstance(raw.get("cache_hit"), bool)
            or not isinstance(response, Mapping)
            or not isinstance(raw.get("error"), str)
            or str(raw.get("job_sha256") or "") != str(job.get("job_sha256") or "")
            or str(raw.get("prompt_sha256") or "") != prompt_sha
            or str(raw.get("payload_sha256") or "") != payload_sha
            or (
                bool(raw.get("success") or raw.get("cache_hit"))
                and str(raw.get("cache_key") or "") != expected_cache_key
            )
            or (
                raw.get("success") is True
                and validator(response) is not None
            )
        ):
            raw_contract_invalid = True
    if set(raw_by_key) != set(expected_by_key) or len(raw_rows) != expected_job_n or raw_contract_invalid:
        failures.append(f"active_{stage}_raw_job_or_response_contract_invalid")
    if (
        int(stage_doc.get("task_n") or -1) != expected_job_n
        or int(stage_doc.get("success_n") or 0) + int(stage_doc.get("failure_n") or 0) != expected_job_n
        or int(stage_doc.get("success_n") or 0) != sum(bool(row.get("success")) for row in raw_rows)
        or int(stage_doc.get("failure_n") or 0) != sum(not bool(row.get("success")) for row in raw_rows)
        or str(stage_doc.get("model") or "") != CLOSURE_COMPARATOR_MODEL
        or str(stage_doc.get("source_commit") or "") != str(freeze.get("source_commit") or "")
        or str(stage_doc.get("runner_code_sha256") or "") != file_sha256(closure_runner)
        or str(stage_doc.get("online_runner_code_sha256") or "") != file_sha256(online_runner)
        or str(stage_doc.get("semantic_input_sha256") or "") != canonical_sha256(expected_tasks)
        or list(stage_doc.get("prompt_sha256s") or [])
        != sorted({hashlib.sha256(str(job["prompt"]).encode()).hexdigest() for job in expected_jobs})
        or str(stage_doc.get("results_file_sha256") or "") != file_sha256(raw_path)
        or str(stage_doc.get("results_sha256") or "") != canonical_sha256(raw_rows)
        or str(stage_doc.get("telemetry_sha256") or "") != file_sha256(raw_telemetry_path)
        or aggregate_telemetry(raw_telemetry) != telemetry_summary
        or telemetry_summary != (stage_doc.get("telemetry_summary") or {})
    ):
        failures.append(f"active_{stage}_response_stage_manifest_invalid")

    expected_responses: list[dict[str, Any]] = []
    for raw in raw_rows:
        key = (
            str(raw.get("case_key") or ""), str(raw.get("arm") or ""),
            str(raw.get("stage") or ""),
        )
        job = expected_by_key.get(key)
        if job is None:
            continue
        response = raw.get("response") if isinstance(raw.get("response"), Mapping) else {}
        row = {
            "case_key": key[0],
            "family": str(job.get("family") or ""),
            "component": "active",
            "arm": key[1],
            "stage": key[2],
            "success": bool(raw.get("success")),
            "error": raw.get("error"),
            "response": response,
            ("action_id" if stage == "policy" else "champion_id"): str(
                response.get("action_id" if stage == "policy" else "champion_id") or ""
            ),
            "model": CLOSURE_COMPARATOR_MODEL,
            "cache_hit": bool(raw.get("cache_hit")),
            "cache_key": raw.get("cache_key"),
            "prompt_sha256": raw.get("prompt_sha256"),
            "payload_sha256": raw.get("payload_sha256"),
            "job_sha256": raw.get("job_sha256"),
        }
        expected_responses.append(row)
    expected_responses.sort(
        key=lambda row: (str(row.get("case_key")), str(row.get("arm")), str(row.get("stage")))
    )
    if canonical_sha256(responses) != canonical_sha256(expected_responses):
        failures.append(f"active_{stage}_raw_to_response_derivation_invalid")
    return failures


def _active_post_gate_contract_failures(
    post_gate: Mapping[str, Any],
    freeze_dir: Path,
    annotations: Path,
    selections: Path,
) -> list[str]:
    """Validate the post-policy gate and replay its transitive policy lineage."""
    failures: list[str] = []
    freeze_dir = Path(freeze_dir)
    freeze_manifest_path = freeze_dir / "freeze.json"
    freeze_cases_path = freeze_dir / "cases.jsonl"
    freeze = _json(freeze_manifest_path) if freeze_manifest_path.is_file() else {}
    case_rows = read_jsonl(freeze_cases_path)
    cases = {str(row.get("case_key") or ""): row for row in case_rows}
    provenance = post_gate.get("provenance") or {}
    artifacts = provenance.get("input_artifacts") or {}
    expected_names = {
        "freeze_manifest", "freeze_cases", "annotations", "annotation_manifest",
        "reviews", "review_manifest", "construction_gate", "policy_jobs",
        "policy_job_manifest", "policy_selections", "policy_response_manifest",
        "policy_stage_manifest", "policy_raw_results", "policy_raw_telemetry",
        "policy_telemetry_summary", "gate_code", "closure_runner_code",
        "online_runner_code",
    }
    if (
        post_gate.get("component") != "active"
        or post_gate.get("gate_stage") != "post_policy_audit"
        or not post_gate.get("passed")
        or post_gate.get("outcome_blind") is not True
    ):
        failures.append("active_post_policy_audit_gate_not_passed")
    if not isinstance(artifacts, Mapping) or set(artifacts) != expected_names:
        failures.append("active_post_gate_artifact_set_invalid")
        return failures
    for name in sorted(expected_names):
        if not _active_binding_valid(artifacts.get(name)):
            failures.append(f"active_post_gate_{name}_binding_invalid")
    if not _active_binding_valid(artifacts.get("freeze_manifest"), freeze_manifest_path):
        failures.append("active_post_gate_freeze_manifest_identity_invalid")
    if not _active_binding_valid(artifacts.get("freeze_cases"), freeze_cases_path):
        failures.append("active_post_gate_freeze_cases_identity_invalid")
    if not _active_binding_valid(artifacts.get("annotations"), Path(annotations)):
        failures.append("active_post_gate_annotation_identity_invalid")
    if not _active_binding_valid(artifacts.get("policy_selections"), Path(selections)):
        failures.append("active_post_gate_selection_identity_invalid")
    if not _active_binding_valid(artifacts.get("gate_code"), Path(__file__)):
        failures.append("active_post_gate_code_identity_invalid")
    selected = [str(value) for value in post_gate.get("selected_case_keys") or []]
    family_n = Counter(str(cases.get(case_key, {}).get("family") or "") for case_key in selected)
    selection_rows = read_jsonl(selections)
    if (
        len(selected) != 64
        or len(set(selected)) != 64
        or set(selected) - set(cases)
        or dict(sorted(family_n.items())) != {"DA": 32, "MCR": 32}
        or str(post_gate.get("selected_case_sha256") or "") != canonical_sha256(sorted(selected))
        or str(post_gate.get("policy_selection_sha256") or "") != canonical_sha256(selection_rows)
        or str(post_gate.get("policy_selection_file_sha256") or "") != file_sha256(Path(selections))
        or str(post_gate.get("construction_gate_sha256") or "")
        != str((artifacts.get("construction_gate") or {}).get("sha256") or "")
        or str(provenance.get("freeze_id") or "") != str(freeze.get("freeze_id") or "")
        or str(provenance.get("source_commit") or "") != str(freeze.get("source_commit") or "")
        or str(provenance.get("gate_code_sha256") or "") != file_sha256(Path(__file__))
    ):
        failures.append("active_post_gate_provenance_invalid")
    audit_rows = post_gate.get("case_audits") or []
    audit_by_case = {
        str(row.get("case_key") or ""): row
        for row in audit_rows if isinstance(row, Mapping)
    }
    if (
        not isinstance(audit_rows, list)
        or len(audit_rows) != 64
        or len(audit_by_case) != 64
        or set(audit_by_case) != set(selected)
        or any(
            not isinstance(row.get("arms"), Mapping)
            or set(row.get("arms") or {}) != {"typed_action", "cost_matched_random"}
            or row.get("evaluable") is not True
            for row in audit_by_case.values()
        )
    ):
        failures.append("active_post_gate_case_audit_contract_invalid")
    construction_path = _active_bound_path(artifacts.get("construction_gate"))
    reviews_path = _active_bound_path(artifacts.get("reviews"))
    policy_jobs_path = _active_bound_path(artifacts.get("policy_jobs"))
    if construction_path is not None and construction_path.is_file():
        failures.extend(_active_construction_gate_contract_failures(
            _json(construction_path), freeze_dir, Path(annotations), reviews_path,
        ))
    if policy_jobs_path is not None and policy_jobs_path.is_file():
        anns = _annotation_index(annotations)
        try:
            expected_policy_jobs = _active_policy_jobs(case_rows, anns, set(selected))
        except (KeyError, TypeError, ValueError) as exc:
            expected_policy_jobs = []
            failures.append(f"active_policy_job_reconstruction_failed:{type(exc).__name__}")
        failures.extend(_active_selector_execution_contract_failures(
            policy_jobs_path,
            Path(selections),
            expected_policy_jobs,
            stage="policy",
            freeze_dir=freeze_dir,
            scientific_gate=construction_path or Path(""),
            annotations=Path(annotations),
        ))
    if (
        not failures
        and construction_path is not None
        and reviews_path is not None
        and construction_path.is_file()
        and reviews_path.is_file()
    ):
        with tempfile.TemporaryDirectory(prefix="active-post-gate-replay-") as temp_dir:
            replay = gate_active_post(
                freeze_dir,
                Path(annotations),
                reviews_path,
                Path(selections),
                construction_path,
                Path(temp_dir) / "post_gate.json",
            )
        if canonical_sha256(replay) != canonical_sha256(post_gate):
            failures.append("active_post_gate_deterministic_replay_mismatch")
    return failures


def gate_active_post(
    freeze_dir: Path,
    annotations: Path,
    reviews: Path,
    selections: Path,
    construction_gate: Path,
    out: Path,
) -> dict[str, Any]:
    """Freeze policy-level active endpoints before any post-evidence comparator.

    The action-bank reviews are policy/outcome blind.  This function only
    projects those frozen reviews onto the selected action and its deterministic
    cost-matched control.  It never reads benchmark truth or a post outcome.
    """
    freeze_dir = Path(freeze_dir)
    freeze_manifest, case_rows, freeze_failures = _formal_freeze_validation(
        freeze_dir,
        "active",
        ACTIVE_ARMS,
        expected_case_n=200,
        expected_family_n={"DA": 100, "MCR": 100},
        expected_sources=[E5_JOINED],
    )
    construction = _json(construction_gate)
    cases = {str(row["case_key"]): row for row in case_rows}
    anns = _annotation_index(annotations)
    review_rows = read_jsonl(reviews)
    selection_rows = read_jsonl(selections)
    selected = [str(value) for value in construction.get("selected_case_keys") or []]
    failures: list[str] = list(freeze_failures)
    failures.extend(_active_construction_gate_contract_failures(
        construction, freeze_dir, Path(annotations), Path(reviews),
    ))
    if len(selected) != len(set(selected)) or set(selected) - set(cases):
        failures.append("construction_selected_case_set_invalid")
    if len({str(row.get("case_key")) for row in selection_rows}) != len(selection_rows):
        failures.append("duplicate_policy_selection")
    selection_by_case = {str(row.get("case_key")): row for row in selection_rows}
    if set(selection_by_case) != set(selected):
        failures.append("policy_selection_case_coverage_mismatch")

    selection_manifest_path = Path(selections).parent / "selector_responses.manifest.json"
    selection_manifest = _json(selection_manifest_path) if selection_manifest_path.is_file() else {}
    selection_inputs = selection_manifest.get("input_files") or []
    policy_jobs_path = (
        _active_bound_path(selection_inputs[0])
        if len(selection_inputs) == 1 else None
    )
    if policy_jobs_path is None:
        failures.append("active_policy_job_binding_missing")
    else:
        try:
            expected_policy_jobs = _active_policy_jobs(case_rows, anns, set(selected))
        except (KeyError, TypeError, ValueError) as exc:
            expected_policy_jobs = []
            failures.append(f"active_policy_job_reconstruction_failed:{type(exc).__name__}")
        failures.extend(_active_selector_execution_contract_failures(
            policy_jobs_path,
            Path(selections),
            expected_policy_jobs,
            stage="policy",
            freeze_dir=freeze_dir,
            scientific_gate=Path(construction_gate),
            annotations=Path(annotations),
        ))
    reviews_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in review_rows:
        reviews_by_case[str(row.get("case_key"))].append(row)

    agreement_groups: dict[str, list[str]] = defaultdict(list)
    case_audits: list[dict[str, Any]] = []
    unresolved_units = total_units = 0

    def consensus(case_key: str, unit: str, values: Sequence[Any]) -> Any:
        nonlocal unresolved_units, total_units
        normalized = [str(value) for value in values]
        agreement_groups[f"{case_key}|{unit}"].extend(normalized)
        total_units += 1
        value = _strict_consensus(list(values))
        unresolved_units += value is None
        return value

    for case_key in selected:
        if case_key not in cases:
            continue
        case = cases[case_key]
        ann = anns.get(case_key) or {}
        actions = {
            str(action.get("action_id")): action
            for action in ann.get("actions") or [] if action.get("status") == "performed"
        }
        candidate_ids = {str(candidate["candidate_id"]) for candidate in case["policy_candidates"]}
        reviewers = reviews_by_case.get(case_key, [])
        reviewer_ids = {str(row.get("reviewer_id")) for row in reviewers}
        reviewer_models = {str(row.get("reviewer_model")) for row in reviewers}
        if (
            len(reviewers) != 2 or len(reviewer_ids) != 2 or len(reviewer_models) != 2
            or any(row.get("panel_provenance") != "independent_model_panel" for row in reviewers)
            or any(row.get("success") is not True for row in reviewers)
        ):
            failures.append(f"{case_key}:two_successful_action_bank_reviews_required")
            continue
        audit_maps = [_active_action_audits(row) for row in reviewers]
        if any(set(index) != set(actions) for index in audit_maps):
            failures.append(f"{case_key}:action_audit_coverage_mismatch")
            continue
        audit_schema_ok = True
        boolean_fields = (
            "availability_valid", "cost_valid", "risk_valid", "relevant", "resolves_need",
            "wrong_episode_or_object_binding", "unnecessary_high_risk_action",
        )
        for index in audit_maps:
            for audit in index.values():
                if any(not isinstance(audit.get(field), bool) for field in boolean_fields):
                    audit_schema_ok = False
                information_gain = audit.get("information_gain")
                if (
                    not isinstance(information_gain, int) or isinstance(information_gain, bool)
                    or information_gain not in {0, 1, 2, 3}
                ):
                    audit_schema_ok = False
        if not audit_schema_ok:
            failures.append(f"{case_key}:action_audit_schema_invalid")
            continue
        selection = selection_by_case.get(case_key) or {}
        response = selection.get("response") if isinstance(selection.get("response"), Mapping) else selection
        action_id = str(selection.get("action_id") or response.get("action_id") or "")
        need_type = str(response.get("need_type") or "")
        top_pair = [str(value) for value in response.get("top_pair") or []]
        if (
            selection.get("success") is not True or action_id not in actions
            or len(top_pair) != 2 or len(set(top_pair)) != 2 or set(top_pair) - candidate_ids
            or need_type not in NEED_TYPES
        ):
            failures.append(f"{case_key}:invalid_policy_selection")
            continue
        chosen = actions[action_id]
        peers = [
            action for peer_id, action in actions.items()
            if peer_id != action_id and action.get("cost_band") == chosen.get("cost_band")
        ]
        if not peers:
            failures.append(f"{case_key}:cost_matched_control_missing")
            continue
        random_action = sorted(
            peers,
            key=lambda action: (stable_seed("active-random-v1", case_key, action["action_id"]), action["action_id"]),
        )[0]
        consensus_need = consensus(case_key, "need_type", [row.get("need_type") for row in reviewers])
        action_consensus: dict[str, dict[str, Any]] = {}
        for candidate_action_id, action in actions.items():
            values: dict[str, Any] = {}
            for field in (
                "availability_valid", "cost_valid", "risk_valid", "relevant", "resolves_need",
                "information_gain", "wrong_episode_or_object_binding", "unnecessary_high_risk_action",
            ):
                values[field] = consensus(
                    case_key,
                    f"{candidate_action_id}|{field}",
                    [index[candidate_action_id].get(field) for index in audit_maps],
                )
            action_consensus[candidate_action_id] = values

        def arm_record(action: Mapping[str, Any]) -> dict[str, Any]:
            action_key = str(action["action_id"])
            audit = action_consensus[action_key]
            cost = action.get("cost")
            cost_number = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else 0.0
            evaluable = (
                all(value is not None for value in audit.values())
                and audit["availability_valid"] is True and audit["cost_valid"] is True
                and audit["risk_valid"] is True and cost_number > 0
            )
            return {
                "action_id": action_key,
                "cost": cost_number,
                "evaluable": bool(evaluable),
                "relevant": audit["relevant"] if evaluable else None,
                "resolves_need": audit["resolves_need"] if evaluable else None,
                "information_gain": int(audit["information_gain"]) if evaluable else None,
                "information_gain_per_cost": (int(audit["information_gain"]) / cost_number) if evaluable else None,
                "wrong_episode_or_object_binding": audit["wrong_episode_or_object_binding"] if evaluable else None,
                "unnecessary_high_risk_action": audit["unnecessary_high_risk_action"] if evaluable else None,
            }

        typed_record = arm_record(chosen)
        random_record = arm_record(random_action)
        any_resolving = any(
            values.get("resolves_need") is True
            and values.get("availability_valid") is True
            and values.get("cost_valid") is True
            and values.get("risk_valid") is True
            for values in action_consensus.values()
        )
        case_evaluable = bool(
            consensus_need is not None and typed_record["evaluable"] and random_record["evaluable"]
        )
        if not case_evaluable:
            failures.append(f"{case_key}:policy_endpoint_not_evaluable")
        case_audits.append({
            "case_key": case_key,
            "family": case["family"],
            "policy_need_type": need_type,
            "panel_need_type": consensus_need,
            "need_type_match": (need_type == consensus_need) if consensus_need is not None else None,
            "any_resolving_action_available": bool(any_resolving),
            "evaluable": case_evaluable,
            "arms": {"typed_action": typed_record, "cost_matched_random": random_record},
        })

    raw_agreement, ac1 = _gwet_ac1(agreement_groups)
    evaluable_cases = [row for row in case_audits if row["evaluable"]]
    if len(evaluable_cases) != len(selected):
        failures.append("policy_endpoint_evaluable_rate_below_1.0")

    def endpoint_metrics(arm: str) -> dict[str, Any]:
        rows = [row for row in evaluable_cases if row["arms"][arm]["evaluable"]]
        resolved = sum(bool(row["arms"][arm]["resolves_need"] and row["need_type_match"]) for row in rows)
        recall_denominator = sum(bool(row["any_resolving_action_available"]) for row in rows)
        return {
            "n": len(rows),
            "need_resolution_precision": resolved / max(1, len(rows)),
            "need_resolution_recall": resolved / max(1, recall_denominator),
            "need_resolution_recall_denominator": recall_denominator,
            "action_relevance_rate": sum(bool(row["arms"][arm]["relevant"]) for row in rows) / max(1, len(rows)),
            "mean_information_gain_per_cost": statistics.fmean(
                float(row["arms"][arm]["information_gain_per_cost"]) for row in rows
            ) if rows else None,
            "wrong_episode_or_object_binding_rate": sum(
                bool(row["arms"][arm]["wrong_episode_or_object_binding"]) for row in rows
            ) / max(1, len(rows)),
            "unnecessary_high_risk_action_rate": sum(
                bool(row["arms"][arm]["unnecessary_high_risk_action"]) for row in rows
            ) / max(1, len(rows)),
        }

    unresolved_rate = unresolved_units / max(1, total_units)
    metrics = {
        "policy_selection_coverage": len(selection_by_case) / max(1, len(selected)),
        "policy_endpoint_evaluable_rate": len(evaluable_cases) / max(1, len(selected)),
        "post_audit_raw_agreement": raw_agreement,
        "post_audit_gwet_ac1": ac1,
        "post_audit_unresolved_rate": unresolved_rate,
        "policy_need_type_match_rate": sum(bool(row.get("need_type_match")) for row in evaluable_cases) / max(1, len(evaluable_cases)),
        "typed_action": endpoint_metrics("typed_action"),
        "cost_matched_random": endpoint_metrics("cost_matched_random"),
        "information_gain_scale": "independent two-model panel ordinal 0..3 divided by frozen builder cost",
        "need_resolution_precision_definition": "selected action resolves panel missing need and policy need matches panel / evaluable selected actions",
        "need_resolution_recall_definition": "same numerator / evaluable cases with at least one resolving performed action",
    }
    if raw_agreement < .90 or ac1 < .75:
        failures.append("post_audit_reliability_below_gate")
    if unresolved_rate > .05:
        failures.append("post_audit_unresolved_rate_above_0.05")
    gate = _gate_write(
        out,
        "active",
        not failures,
        failures,
        metrics,
        "policy-projected, two-model-panel action audit; retrospective/off-policy and not prospective diagnosis",
    )
    gate["gate_stage"] = "post_policy_audit"
    gate["construction_gate_sha256"] = file_sha256(construction_gate)
    gate["selected_case_keys"] = sorted(selected)
    gate["selected_case_sha256"] = canonical_sha256(sorted(selected))
    gate["case_audits"] = sorted(case_audits, key=lambda row: row["case_key"])
    gate["policy_selection_sha256"] = canonical_sha256(selection_rows)
    gate["policy_selection_file_sha256"] = file_sha256(Path(selections))
    gate["outcome_blind"] = True
    if policy_jobs_path is not None and selection_manifest_path.is_file():
        stage_bindings = selection_manifest.get("online_stage_manifests") or []
        policy_stage_path: Path | None = None
        if len(stage_bindings) == 1 and isinstance(stage_bindings[0], Mapping):
            policy_stage_path = Path(str(stage_bindings[0].get("path") or ""))
            if not policy_stage_path.is_absolute():
                policy_stage_path = selection_manifest_path.parent / policy_stage_path
        if policy_stage_path is not None and policy_stage_path.is_file():
            artifacts = {
                "freeze_manifest": _active_artifact_binding(freeze_dir / "freeze.json"),
                "freeze_cases": _active_artifact_binding(freeze_dir / "cases.jsonl"),
                "annotations": _active_artifact_binding(Path(annotations)),
                "annotation_manifest": _active_artifact_binding(
                    Path(annotations).parent / "active_builder_annotations.manifest.json"
                ),
                "reviews": _active_artifact_binding(Path(reviews)),
                "review_manifest": _active_artifact_binding(
                    Path(reviews).parent / "active_reviews.manifest.json"
                ),
                "construction_gate": _active_artifact_binding(Path(construction_gate)),
                "policy_jobs": _active_artifact_binding(policy_jobs_path),
                "policy_job_manifest": _active_artifact_binding(
                    policy_jobs_path.with_suffix(".manifest.json")
                ),
                "policy_selections": _active_artifact_binding(Path(selections)),
                "policy_response_manifest": _active_artifact_binding(selection_manifest_path),
                "policy_stage_manifest": _active_artifact_binding(policy_stage_path),
                "policy_raw_results": _active_artifact_binding(
                    policy_stage_path.parent / "raw_results.jsonl"
                ),
                "policy_raw_telemetry": _active_artifact_binding(
                    policy_stage_path.parent / "telemetry.jsonl"
                ),
                "policy_telemetry_summary": _active_artifact_binding(
                    policy_stage_path.parent / "telemetry_summary.json"
                ),
                "gate_code": _active_artifact_binding(Path(__file__)),
                "closure_runner_code": _active_artifact_binding(
                    ROOT / "analysis/mechanism_v2/ceiling_closure_online.py"
                ),
                "online_runner_code": _active_artifact_binding(
                    ROOT / "analysis/mechanism_v2/online_runner.py"
                ),
            }
            gate["provenance"] = {
                "freeze_id": freeze_manifest.get("freeze_id"),
                "source_commit": freeze_manifest.get("source_commit"),
                "gate_code_sha256": file_sha256(Path(__file__)),
                "input_artifacts": artifacts,
            }
    atomic_json(out, gate)
    return gate


def _snomed_map(label: str, bridge: FrozenExactSynonymBridge, concepts: Mapping[str, Any], terms: Mapping[str, Any]) -> str | None:
    concept_ids: set[str] = set()
    for term in {normalize_label(label), bridge.canonical_key(label)}:
        concept_ids.update(str(x) for x in terms.get(term, []))
    disorder_ids = {cid for cid in concept_ids if (concepts.get(cid) or {}).get("tag") == "disorder"}
    return next(iter(disorder_ids)) if len(disorder_ids) == 1 else None


def _is_a_distance(source: str, target: str, parents: Mapping[str, set[str]], limit: int = 4) -> int | None:
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    seen = {source}
    while queue:
        node, distance = queue.popleft()
        if distance >= limit:
            continue
        for parent in parents.get(node, set()):
            if parent == target:
                return distance + 1
            if parent not in seen:
                seen.add(parent)
                queue.append((parent, distance + 1))
    return None


def freeze_relation(out: Path, *, pools: Path = E4_POOLS, joined: Path = E4_JOINED, concepts_path: Path = SNOMED_CONCEPTS, terms_path: Path = SNOMED_TERMS, relations_path: Path = SNOMED_RELATIONS, bridge_path: Path = BRIDGE) -> dict[str, Any]:
    """Build the corrected strict E4 96-case/122-edge primary substrate.

    The pre-collapse inventory contains 124 candidate-ID edges. Two pairs
    encode the same within-case directed SNOMED concept pair through duplicate
    surface candidates. The frozen contract requires semantic duplicate-pair
    collapse, so those two redundant edges are removed before review or online
    selector compilation.
    """
    concepts = _json(concepts_path)
    terms = _json(terms_path)
    bridge = FrozenExactSynonymBridge(bridge_path)
    parents: dict[str, set[str]] = defaultdict(set)
    for edge in _json(relations_path):
        if edge.get("type") == "is_a":
            parents[str(edge["src"])].add(str(edge["dst"]))
    vignettes = _e4_vignettes(joined)
    rows: list[dict[str, Any]] = []
    edge_n = 0
    raw_edge_n = 0
    duplicate_concept_pair_collapsed_n = 0
    inverse_or_cycle_quarantined_n = 0
    for raw in read_jsonl(pools):
        case_key = str(raw["case_key"])
        vignette = vignettes[case_key]
        candidates = _clean_candidates(raw["pool"]["candidates"], evidence=True)
        nodes = []
        for candidate in candidates:
            concept_id = _snomed_map(candidate["label"], bridge, concepts, terms)
            citations = []
            for item in candidate["support_items"]:
                citations.extend(_spans(vignette, item))
            nodes.append({
                "candidate_id": candidate["candidate_id"], "label": candidate["label"],
                "concept_id": concept_id or "", "citations": citations,
            })
        raw_edges = []
        for source in nodes:
            for target in nodes:
                if source is target or not source["concept_id"] or not target["concept_id"]:
                    continue
                if not source["citations"] or not target["citations"]:
                    continue
                distance = _is_a_distance(source["concept_id"], target["concept_id"], parents, 4)
                if distance is not None:
                    raw_edges.append({
                        "source_id": source["candidate_id"], "target_id": target["candidate_id"],
                        "source_concept_id": source["concept_id"], "target_concept_id": target["concept_id"],
                        "relation": "is_a", "distance": distance,
                        "source_citation": source["citations"][0], "target_citation": target["citations"][0],
                    })
        raw_edge_n += len(raw_edges)

        # Reject self/cyclic or contradictory directions before semantic
        # duplicate collapse. The current strict source has none, but the
        # implementation must fail closed if a future ontology slice does.
        concept_directions = {
            (edge["source_concept_id"], edge["target_concept_id"])
            for edge in raw_edges
        }
        direction_safe = []
        for edge in raw_edges:
            pair = (edge["source_concept_id"], edge["target_concept_id"])
            if pair[0] == pair[1] or (pair[1], pair[0]) in concept_directions:
                inverse_or_cycle_quarantined_n += 1
                continue
            direction_safe.append(edge)

        # Candidate aliases may map to the same SNOMED concept. Collapse by
        # concept pair, choosing one surface realization by an outcome-blind
        # stable hash so duplicated aliases cannot receive extra graph weight.
        by_concept_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for edge in direction_safe:
            by_concept_pair[(edge["source_concept_id"], edge["target_concept_id"])].append(edge)
        edges = []
        for pair in sorted(by_concept_pair):
            options = by_concept_pair[pair]
            options.sort(key=lambda edge: (
                stable_seed(
                    "relation-concept-pair-collapse-v1", case_key,
                    edge["source_id"], edge["target_id"],
                ),
                edge["source_id"], edge["target_id"],
            ))
            edges.append(options[0])
            duplicate_concept_pair_collapsed_n += len(options) - 1
        if not edges:
            continue
        edge_n += len(edges)
        rows.append({
            "case_key": str(raw["case_key"]), "family": str(raw["family"]),
            "vignette": vignette,
            "candidates": [{"candidate_id": c["candidate_id"], "label": c["label"]} for c in candidates],
            "nodes": nodes, "relations": edges,
        })
    counts = Counter(row["family"] for row in rows)
    if (
        len(rows) != RELATION_EXPECTED_CASES
        or raw_edge_n != RELATION_PRECOLLAPSE_EDGES
        or edge_n != RELATION_EXPECTED_EDGES
        or duplicate_concept_pair_collapsed_n != RELATION_EXPECTED_DUPLICATE_COLLAPSE
        or inverse_or_cycle_quarantined_n != 0
        or dict(counts) != RELATION_EXPECTED_FAMILY
    ):
        raise AssertionError(
            "strict relation primary drift: "
            f"cases={len(rows)}, raw_edges={raw_edge_n}, edges={edge_n}, "
            f"duplicate_collapsed={duplicate_concept_pair_collapsed_n}, "
            f"inverse_or_cycle_quarantined={inverse_or_cycle_quarantined_n}, family={dict(counts)}"
        )
    # The raw JSONs do not embed RF2 release provenance.  Hashes freeze the
    # bytes, but a separate reviewer-owned provenance record is a hard gate.
    return _write_freeze(
        out, "relation", rows,
        [pools, joined, concepts_path, terms_path, relations_path, bridge_path],
        arms=list(RELATION_ARMS),
        primary_contract="case-sensitive literal citation + unique disorder mapping + semantic duplicate-pair collapse + directed is_a path <=4",
        raw_edge_n=raw_edge_n,
        edge_n=edge_n,
        duplicate_concept_pair_collapsed_n=duplicate_concept_pair_collapsed_n,
        inverse_or_cycle_quarantined_n=inverse_or_cycle_quarantined_n,
        snomed_release_provenance="unverified",
    )


def _valid_sha256(value: Any) -> bool:
    text_value = str(value or "").lower()
    return (
        len(text_value) == 64
        and any(character != "0" for character in text_value)
        and all(character in "0123456789abcdef" for character in text_value)
    )


def _snomed_provenance_metrics(freeze: Mapping[str, Any], provenance_doc: Mapping[str, Any]) -> dict[str, bool]:
    """Bind a reviewer attestation to exact SNOMED bytes and RF2 release."""
    expected_names = {
        "snomed_concepts.json", "snomed_term_index.json", "snomed_relations.json"
    }
    expected = {
        Path(str(item.get("path") or "")).name: str(item.get("sha256") or "").lower()
        for item in freeze.get("source_artifacts") or []
        if Path(str(item.get("path") or "")).name in expected_names
    }
    declared_raw = provenance_doc.get("artifact_sha256") or {}
    declared = {
        Path(str(name)).name: str(value or "").lower()
        for name, value in declared_raw.items()
    } if isinstance(declared_raw, Mapping) else {}
    artifact_hashes_bound = (
        set(expected) == expected_names
        and all(_valid_sha256(expected[name]) and declared.get(name) == expected[name] for name in expected_names)
    )
    release_match = str(provenance_doc.get("rf2_release") or "") == SNOMED_RELEASE_ID
    archive_path = Path(str(provenance_doc.get("source_archive") or ""))
    archive_name_match = archive_path.name == SNOMED_SOURCE_ARCHIVE
    archive_sha_bound = _valid_sha256(provenance_doc.get("source_archive_sha256"))
    archive_file_verified = bool(
        archive_sha_bound
        and archive_path.is_file()
        and file_sha256(archive_path) == str(provenance_doc.get("source_archive_sha256") or "").lower()
    )
    reviewer_attested = bool(
        str(provenance_doc.get("reviewer") or "").strip()
        and str(provenance_doc.get("verification_method") or "").strip()
        and provenance_doc.get("verified") is True
    )
    verified = bool(
        artifact_hashes_bound and release_match and archive_name_match
        and archive_file_verified and reviewer_attested
    )
    return {
        "provenance_artifact_hashes_bound": artifact_hashes_bound,
        "provenance_release_match": release_match,
        "provenance_archive_name_match": archive_name_match,
        "provenance_archive_sha_bound": archive_sha_bound,
        "provenance_archive_file_verified": archive_file_verified,
        "provenance_reviewer_attested": reviewer_attested,
        "provenance_verified": verified,
    }


def gate_relation(freeze_dir: Path, reviews: Path, provenance: Path, out: Path) -> dict[str, Any]:
    rows = read_jsonl(Path(freeze_dir) / "cases.jsonl")
    freeze = _json(Path(freeze_dir) / "freeze.json")
    review_rows = read_jsonl(reviews)
    provenance_doc = _json(provenance) if Path(provenance).is_file() else {}
    failures: list[str] = []
    if (
        len(rows) != RELATION_EXPECTED_CASES
        or freeze.get("raw_edge_n") != RELATION_PRECOLLAPSE_EDGES
        or freeze.get("edge_n") != RELATION_EXPECTED_EDGES
        or freeze.get("duplicate_concept_pair_collapsed_n") != RELATION_EXPECTED_DUPLICATE_COLLAPSE
        or freeze.get("inverse_or_cycle_quarantined_n") != 0
        or Counter(r["family"] for r in rows) != RELATION_EXPECTED_FAMILY
    ):
        failures.append("strict96_raw124_collapsed122_primary_drift")
    edge_keys = {(r["case_key"], e["source_id"], e["target_id"]) for r in rows for e in r["relations"]}
    reviewed_keys = {(str(r["case_key"]), str(r["source_id"]), str(r["target_id"])) for r in review_rows}
    if reviewed_keys != edge_keys:
        failures.append("all_122_edges_not_model_panel_reviewed")
    edge_reviewers: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for review in review_rows:
        key = (str(review.get("case_key")), str(review.get("source_id")), str(review.get("target_id")))
        edge_reviewers[key].append(review)
    reviewer_ids = {str(review.get("reviewer_id") or "") for review in review_rows}
    reviewer_models = {str(review.get("reviewer_model") or "") for review in review_rows}
    two_reviewer_contract = bool(
        reviewed_keys == edge_keys
        and len(review_rows) == 2 * len(edge_keys)
        and len(reviewer_ids) == 2 and "" not in reviewer_ids
        and len(reviewer_models) == 2 and "" not in reviewer_models
        and all(
            len(group) == 2
            and len({str(review.get("reviewer_id") or "") for review in group}) == 2
            and all(bool(review.get("success", True)) for review in group)
            for group in edge_reviewers.values()
        )
    )
    if not two_reviewer_contract:
        failures.append("two_independent_model_reviews_per_edge_not_satisfied")

    duplicate_pairs = inverse_pairs = concept_binding_drift = 0
    for case in rows:
        nodes = {str(node["candidate_id"]): str(node.get("concept_id") or "") for node in case["nodes"]}
        concept_pairs: list[tuple[str, str]] = []
        for edge in case["relations"]:
            source_concept = nodes.get(str(edge["source_id"]), "")
            target_concept = nodes.get(str(edge["target_id"]), "")
            if (
                source_concept != str(edge.get("source_concept_id") or "")
                or target_concept != str(edge.get("target_concept_id") or "")
            ):
                concept_binding_drift += 1
            concept_pairs.append((source_concept, target_concept))
        counts = Counter(concept_pairs)
        duplicate_pairs += sum(count - 1 for count in counts.values() if count > 1)
        pair_set = set(concept_pairs)
        inverse_pairs += sum(
            1 for source, target in pair_set
            if source == target or (target, source) in pair_set
        )
    if duplicate_pairs:
        failures.append("semantic_duplicate_relation_pair_nonzero")
    if inverse_pairs or concept_binding_drift:
        failures.append("relation_direction_or_concept_binding_drift")
    mapping_precision = statistics.fmean(bool(r.get("mapping_correct")) for r in review_rows) if review_rows else 0.0
    direction = statistics.fmean(bool(r.get("direction_correct")) for r in review_rows) if review_rows else 0.0
    citation = statistics.fmean(bool(r.get("citation_closed")) for r in review_rows) if review_rows else 0.0
    unresolved = statistics.fmean(bool(r.get("unresolved")) for r in review_rows) if review_rows else 1.0
    inverse_or_cycle = sum(bool(r.get("inverse_or_cycle")) for r in review_rows)
    groups: dict[str, list[str]] = defaultdict(list)
    for review in review_rows:
        groups[f"{review.get('case_key')}|{review.get('source_id')}|{review.get('target_id')}"] .append(str(review.get("decision") or ""))
    agreement, ac1 = _gwet_ac1(groups)
    provenance_metrics = _snomed_provenance_metrics(freeze, provenance_doc)
    metrics = {
        "mapping_precision": mapping_precision, "direction_fidelity": direction,
        "citation_closure": citation, "unresolved_rate": unresolved,
        "inverse_or_cycles": inverse_or_cycle, "raw_agreement": agreement, "gwet_ac1": ac1,
        "review_rows": len(review_rows), "expected_review_rows": 2 * len(edge_keys),
        "two_reviewer_contract": two_reviewer_contract,
        "semantic_duplicate_pairs": duplicate_pairs,
        "frozen_inverse_pairs": inverse_pairs,
        "concept_binding_drift": concept_binding_drift,
        **provenance_metrics,
    }
    checks = {"mapping_precision": .95, "direction_fidelity": .95, "citation_closure": .98, "raw_agreement": .90, "gwet_ac1": .75}
    for name, threshold in checks.items():
        if metrics[name] < threshold:
            failures.append(f"{name}_below_{threshold}")
    if unresolved > .05:
        failures.append("unresolved_rate_above_0.05")
    if inverse_or_cycle:
        failures.append("inverse_or_cycle_nonzero")
    if not provenance_metrics["provenance_artifact_hashes_bound"]:
        failures.append("snomed_artifact_hash_binding_failed")
    if not provenance_metrics["provenance_release_match"] or not provenance_metrics["provenance_archive_name_match"]:
        failures.append("snomed_release_or_archive_identity_unverified")
    if not provenance_metrics["provenance_archive_sha_bound"]:
        failures.append("snomed_source_archive_sha_unverified")
    elif not provenance_metrics["provenance_archive_file_verified"]:
        failures.append("snomed_source_archive_missing_or_hash_mismatch")
    if not metrics["provenance_verified"]:
        failures.append("snomed_release_provenance_unverified")
    return _gate_write(out, "relation", not failures, failures, metrics, "deterministic E4 strict96/raw124/collapsed122 relation-substrate test; not all relation systems")


def _gate_write(out: Path, component: str, passed: bool, failures: list[str], metrics: Mapping[str, Any], claim_scope: str) -> dict[str, Any]:
    gate = {
        "schema": SCHEMA, "kind": "gate", "component": component,
        "passed": bool(passed), "status": "GO" if passed else "NO_GO",
        "fail_closed": True, "failures": sorted(set(failures)),
        "metrics": dict(metrics), "claim_scope": claim_scope,
    }
    atomic_json(Path(out), gate)
    return gate


def gate_not_executed(
    component: str,
    freeze_dir: Path,
    upstream_decision: Path,
    operational_incident: Path,
    out: Path,
    decision_out: Path,
    *,
    admission_gate: Path | None = None,
) -> dict[str, Any]:
    """Persist an explicit operational No-Go without manufacturing endpoint values.

    This path is intentionally limited to the two closure components whose
    scientific entry gates depend on fresh annotation/review products.  It is
    not a substitute for either scientific gate: all scientific metrics remain
    null, the online stages remain unexecuted, and ``compile_run`` must reject
    the resulting gate.
    """
    if component not in {"factorization", "active"}:
        raise ValueError("not-executed gate is supported only for factorization and active")

    freeze_dir = Path(freeze_dir)
    freeze_path = freeze_dir / "freeze.json"
    cases_path = freeze_dir / "cases.jsonl"
    freeze = _json(freeze_path) if freeze_path.is_file() else {}
    cases = read_jsonl(cases_path)
    upstream = _json(upstream_decision)
    incident = _json(operational_incident)

    artifact_validation_failures: list[str] = []
    case_keys = [str(row.get("case_key") or "") for row in cases]
    if "" in case_keys or len(case_keys) != len(set(case_keys)):
        artifact_validation_failures.append("freeze_case_key_identity_invalid")
    for index, case in enumerate(cases):
        try:
            _assert_blind(case, f"freeze.cases[{index}]")
        except AssertionError:
            artifact_validation_failures.append("freeze_outcome_blinding_contract_invalid")
            break
    if freeze.get("component") != component:
        artifact_validation_failures.append("freeze_component_mismatch")
    if int(freeze.get("case_n") or -1) != len(cases):
        artifact_validation_failures.append("freeze_case_count_mismatch")
    if str(freeze.get("cases_sha256") or "") != canonical_sha256(cases):
        artifact_validation_failures.append("freeze_cases_hash_mismatch")
    if freeze.get("schema") != SCHEMA or freeze.get("kind") != "freeze" or not bool(freeze.get("outcome_blind")):
        artifact_validation_failures.append("freeze_contract_identity_invalid")
    expected_family = {"DA": 100, "MCR": 100}
    observed_family = dict(sorted(Counter(str(row.get("family")) for row in cases).items()))
    if len(cases) != 200 or observed_family != expected_family or freeze.get("family_n") != expected_family:
        artifact_validation_failures.append("freeze_expected_cohort_contract_invalid")
    expected_arms = list(FACTORIZATION_ARMS if component == "factorization" else ACTIVE_ARMS)
    if freeze.get("arms") != expected_arms:
        artifact_validation_failures.append("freeze_arm_contract_invalid")
    recomputed_freeze = {key: value for key, value in freeze.items() if key != "freeze_id"}
    if str(freeze.get("freeze_id") or "") != canonical_sha256(recomputed_freeze):
        artifact_validation_failures.append("freeze_id_mismatch")
    if (
        not str(freeze.get("source_commit") or "")
        or str(freeze.get("generator_code_sha256") or "") != file_sha256(Path(__file__))
    ):
        artifact_validation_failures.append("freeze_generator_code_binding_invalid")
    source_artifacts = freeze.get("source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        artifact_validation_failures.append("freeze_source_artifacts_missing")
    else:
        declared_source_map: dict[Path, str] = {}
        for index, artifact in enumerate(source_artifacts):
            if not isinstance(artifact, Mapping):
                artifact_validation_failures.append(f"freeze_source_artifact_{index}_invalid")
                continue
            source_path = Path(str(artifact.get("path") or ""))
            if not source_path.is_absolute():
                source_path = ROOT / source_path
            source_path = source_path.resolve()
            declared_source_map[source_path] = str(artifact.get("sha256") or "")
            if (
                not source_path.is_file()
                or file_sha256(source_path) != str(artifact.get("sha256") or "")
            ):
                artifact_validation_failures.append(f"freeze_source_artifact_{index}_hash_mismatch")
        expected_source_paths = (
            [E5_JOINED, BRIDGE] if component == "factorization" else [E5_JOINED]
        )
        expected_source_map = {
            Path(path).resolve(): file_sha256(Path(path).resolve())
            for path in expected_source_paths
        }
        if declared_source_map != expected_source_map:
            artifact_validation_failures.append("freeze_expected_source_identity_invalid")

    c0_status = str(upstream.get("release_status") or upstream.get("status") or "")
    c0_reliability = upstream.get("reliability_gate") or {}
    c0_is_no_go = (
        c0_status == "NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY"
        and not bool(c0_reliability.get("pass"))
        and upstream.get("clinical_width_outputs_released") is False
    )
    if not c0_is_no_go:
        artifact_validation_failures.append("c0_no_go_binding_not_verified")
    incident_class = str(incident.get("observed_error_class") or "")
    incident_provider = str(incident.get("provider_gateway") or "")
    credit_exhaustion_verified = (
        incident_provider == "OpenRouter" and incident_class == "HTTP_402_INSUFFICIENT_CREDITS"
    )
    if not credit_exhaustion_verified:
        artifact_validation_failures.append("openrouter_credit_exhaustion_binding_not_verified")

    c1_status = "NOT_APPLICABLE"
    c1_gate: dict[str, Any] = {}
    if component == "factorization":
        if admission_gate is None:
            artifact_validation_failures.append("c1_admission_gate_binding_missing")
            c1_status = "UNVERIFIED"
        else:
            c1_gate = _json(admission_gate)
            c1_status = str(c1_gate.get("status") or c1_gate.get("decision") or "")
            if c1_gate.get("component") != "admission" or bool(c1_gate.get("passed")):
                artifact_validation_failures.append("c1_admission_no_go_binding_not_verified")

    if component == "factorization":
        unexecuted_stages = {
            "factorizer_and_modifier_annotation": "NOT_EXECUTED",
            "independent_two_model_map_review": "NOT_EXECUTED",
            "five_arm_selector": "NOT_COMPILED_OR_EXECUTED",
        }
        scientific_metrics: dict[str, Any] = {
            "grouped_pair_precision": None,
            "modifier_axis_precision": None,
            "unsafe_synonym_merges": None,
            "reviewed_group_pair_n": None,
            "reviewed_modifier_axis_n": None,
            "unresolved_rate": None,
            "candidate_coverage": None,
            "modifier_citation_closure": None,
            "modifier_evidence_support_rate": None,
            "nontrivial_corruption_case_rate": None,
            "raw_agreement": None,
            "gwet_ac1": None,
            "expected_group_pair_unit_n": None,
            "expected_modifier_axis_unit_n": None,
            "reviewer_model_n": None,
            "flat_ita_complete_rate": None,
            "exact_identity_ita_complete_rate": None,
            "factorized_lattice_ita_complete_rate": None,
            "structure_sham_ita_complete_rate": None,
            "corrupted_modifier_mapping_ita_complete_rate": None,
            "flat_service_rate": None,
            "exact_identity_service_rate": None,
            "factorized_lattice_service_rate": None,
            "structure_sham_service_rate": None,
            "corrupted_modifier_mapping_service_rate": None,
            "flat_complete_exposure_rate": None,
            "exact_identity_complete_exposure_rate": None,
            "factorized_lattice_complete_exposure_rate": None,
            "structure_sham_complete_exposure_rate": None,
            "corrupted_modifier_mapping_complete_exposure_rate": None,
            "flat_modifier_hallucination_rate": None,
            "exact_identity_modifier_hallucination_rate": None,
            "factorized_lattice_modifier_hallucination_rate": None,
            "structure_sham_modifier_hallucination_rate": None,
            "corrupted_modifier_mapping_modifier_hallucination_rate": None,
            "clinical_complete_effect_vs_flat": None,
            "clinical_complete_effect_vs_flat_bootstrap_95_lower": None,
            "clinical_complete_effect_vs_structure_sham": None,
            "clinical_complete_effect_vs_structure_sham_bootstrap_95_lower": None,
            "clinical_complete_effect_vs_corrupted_mapping": None,
            "clinical_complete_effect_vs_corrupted_mapping_bootstrap_95_lower": None,
            "complete_rescues": None,
            "scope_compressions": None,
            "catastrophic_substitutions": None,
            "modifier_hallucinations": None,
            "combined_harm_cases": None,
            "scope_compression_or_hallucination_or_catastrophic_cases": None,
            "net_rescue_minus_scope_compression": None,
            "net_rescue_minus_modifier_hallucination": None,
            "net_rescue_minus_catastrophic": None,
            "net_rescue_minus_combined_harm": None,
        }
        for arm in FACTORIZATION_ARMS:
            for endpoint in (
                "intended_n", "served_n", "complete_n",
                "modifier_hallucination_evaluable_n",
            ):
                scientific_metrics[f"{arm}_{endpoint}"] = None
        scope = (
            "C2 gold-exposed E5 base4 conditional-conversion design frozen; the only permitted "
            "scope without a passed C1 gate is an isolated topology probe, and that probe was not executed"
        )
    else:
        unexecuted_stages = {
            "builder_annotation": "NOT_EXECUTED",
            "independent_two_model_action_review": "NOT_EXECUTED",
            "pre_release_prediction": "NOT_EXECUTED",
            "typed_policy": "NOT_COMPILED_OR_EXECUTED",
            "post_release_clinical_arms": "NOT_COMPILED_OR_EXECUTED",
        }
        scientific_metrics = {
            "builder_validity_rate": None,
            "action_availability_rate": None,
            "raw_agreement": None,
            "gwet_ac1": None,
            "historical_action_availability_rate": None,
            "action_cost_defined_rate": None,
            "action_risk_defined_rate": None,
            "direct_answer_leakage_rate": None,
            "missing_need_macro_f1": None,
            "typed_action_relevance_precision": None,
            "reviewed_historical_availability_rate": None,
            "reviewed_cost_validity_rate": None,
            "reviewed_risk_validity_rate": None,
            "direct_answer_leak_reviews": None,
            "construction_raw_agreement": None,
            "construction_gwet_ac1": None,
            "construction_unresolved_rate": None,
            "policy_selection_coverage": None,
            "policy_endpoint_evaluable_rate": None,
            "post_audit_raw_agreement": None,
            "post_audit_gwet_ac1": None,
            "post_audit_unresolved_rate": None,
            "policy_need_type_match_rate": None,
            "need_resolution_precision": None,
            "need_resolution_recall": None,
            "action_relevance_rate": None,
            "mean_information_gain_per_cost": None,
            "wrong_episode_or_object_binding_rate": None,
            "unnecessary_high_risk_action_rate": None,
            "typed_action_audit_coverage": None,
            "cost_matched_control_availability_rate": None,
            "post_policy_raw_agreement": None,
            "post_policy_gwet_ac1": None,
            "typed_action_audit_n": None,
            "typed_action_need_resolution_precision": None,
            "typed_action_need_resolution_recall": None,
            "typed_action_need_resolution_recall_denominator": None,
            "typed_action_action_relevance_rate": None,
            "typed_action_mean_information_gain_per_cost": None,
            "typed_action_wrong_episode_or_object_binding_rate": None,
            "typed_action_unnecessary_high_risk_action_rate": None,
            "cost_matched_random_audit_n": None,
            "cost_matched_random_need_resolution_precision": None,
            "cost_matched_random_need_resolution_recall": None,
            "cost_matched_random_need_resolution_recall_denominator": None,
            "cost_matched_random_action_relevance_rate": None,
            "cost_matched_random_mean_information_gain_per_cost": None,
            "cost_matched_random_wrong_episode_or_object_binding_rate": None,
            "cost_matched_random_unnecessary_high_risk_action_rate": None,
            "no_acquisition_complete_exposure_rate": None,
            "no_acquisition_ita_complete_rate": None,
            "typed_action_complete_exposure_rate": None,
            "typed_action_ita_complete_rate": None,
            "cost_matched_random_complete_exposure_rate": None,
            "cost_matched_random_ita_complete_rate": None,
            "no_acquisition_service_rate": None,
            "typed_action_service_rate": None,
            "cost_matched_random_service_rate": None,
            "post_release_clinical_complete_effect": None,
            "typed_vs_no_acquisition_difference": None,
            "typed_vs_no_acquisition_bootstrap_95_lower": None,
            "typed_vs_cost_matched_random_difference": None,
            "typed_vs_cost_matched_random_bootstrap_95_lower": None,
        }
        for arm in ACTIVE_ARMS:
            for endpoint in (
                "intended_n", "served_n", "complete_n", "service_rate",
                "ita_complete_rate", "complete_exposure_rate",
                "action_relevance_rate", "need_resolution_rate",
                "mean_information_gain_per_cost",
                "wrong_episode_or_object_binding_rate",
                "unnecessary_high_risk_action_rate",
            ):
                scientific_metrics[f"{arm}_{endpoint}"] = None
        scope = (
            "C3 retrospective off-policy active-evidence design frozen; construction, policy and "
            "post-policy endpoints were not executed or evaluated"
        )

    output_root = Path(out).parent
    expected_execution_products = (
        [
            output_root / "annotations" / "annotations.jsonl",
            output_root / "reviews" / "reviews.jsonl",
            output_root / "jobs.jsonl",
            output_root / "run" / "responses.jsonl",
            output_root / "analysis.json",
        ]
        if component == "factorization"
        else [
            output_root / "builder" / "annotations.jsonl",
            output_root / "reviews" / "reviews.jsonl",
            output_root / "predictions" / "predictions.jsonl",
            output_root / "policy_jobs.jsonl",
            output_root / "policy_run" / "responses.jsonl",
            output_root / "post_gate.json",
            output_root / "post_jobs.jsonl",
            output_root / "post_run" / "responses.jsonl",
            output_root / "analysis.json",
        ]
    )
    present_execution_products = [path for path in expected_execution_products if path.is_file()]
    present_execution_telemetry = sorted(output_root.rglob("telemetry.jsonl"))
    execution_ledger_patterns = (
        "raw_results.jsonl",
        "manifest.json",
        "*.manifest.json",
        "telemetry_summary.json",
    )
    present_execution_ledgers = sorted({
        path
        for pattern in execution_ledger_patterns
        for path in output_root.rglob(pattern)
        if path.is_file()
    } | {
        path for path in output_root.rglob("cache/*.json") if path.is_file()
    })
    if present_execution_products:
        artifact_validation_failures.append("official_execution_product_present")
    if present_execution_telemetry:
        artifact_validation_failures.append("official_execution_telemetry_present")
    if present_execution_ledgers:
        artifact_validation_failures.append("official_execution_ledger_or_cache_present")

    operational_blockers = [
        "c0_reliability_context_no_go",
        "openrouter_credit_exhausted",
        "required_annotation_product_not_executed",
        "required_independent_review_product_not_executed",
    ]
    if component == "factorization":
        operational_blockers.append("c1_admission_gate_not_passed")
    failures = sorted(set(operational_blockers + artifact_validation_failures))

    def binding(path: Path) -> dict[str, str]:
        resolved = Path(path).resolve()
        try:
            display = str(resolved.relative_to(ROOT))
        except ValueError:
            display = str(resolved)
        return {"path": display, "sha256": file_sha256(resolved)}

    gate = {
        "schema": SCHEMA,
        "kind": "gate",
        "component": component,
        "gate_stage": "not_executed_operational",
        "passed": False,
        "status": "NOT_EXECUTED_OPERATIONAL_NO_GO",
        "decision_class": "operational_no_go",
        "fail_closed": True,
        "failures": failures,
        "operational_blockers": operational_blockers,
        "artifact_validation_failures": artifact_validation_failures,
        "frozen_design_validated": not artifact_validation_failures,
        "execution_state": "NOT_EXECUTED",
        "unexecuted_stages": unexecuted_stages,
        "scientific_result": "NOT_EVALUATED",
        "scientific_endpoint_evaluated": False,
        "scientific_negative": False,
        "scientific_effect_interpretation_allowed": False,
        "metrics": {
            "frozen_case_n": len(cases),
            "frozen_family_n": observed_family,
            "completed_annotation_case_n": 0,
            "completed_independent_review_row_n": 0,
            "compiled_selector_job_n": 0,
            "online_call_n": None,
            "scientific": scientific_metrics,
        },
        "execution_evidence": {
            "execution_start_state": "NOT_STARTED_DUE_TO_PREREQUISITE",
            "official_execution_products_present": bool(present_execution_products),
            "checked_official_execution_products": [
                str(path.relative_to(output_root)) for path in expected_execution_products
            ],
            "present_official_execution_products": [
                str(path.relative_to(output_root)) for path in present_execution_products
            ],
            "runner_or_provider_telemetry_present": bool(present_execution_telemetry),
            "present_execution_telemetry": [
                str(path.relative_to(output_root)) for path in present_execution_telemetry
            ],
            "execution_ledger_or_cache_present": bool(present_execution_ledgers),
            "present_execution_ledgers_or_caches": [
                str(path.relative_to(output_root)) for path in present_execution_ledgers
            ],
            "recorded_calls_in_official_execution_products": 0,
            "evidence_class": (
                "design-state and official-product absence; not a provider-account usage log"
            ),
        },
        "claim_scope": scope,
        "isolated_topology_probe": component == "factorization",
        "isolated_topology_probe_execution": (
            "NOT_EXECUTED" if component == "factorization" else "NOT_APPLICABLE"
        ),
        "deployment_integration_eligible": False,
        "c0_context_status": c0_status,
        "c1_admission_gate_status": c1_status,
        "online_capacity_status": (
            "OPENROUTER_HTTP_402_INSUFFICIENT_CREDITS"
            if credit_exhaustion_verified
            else "UNVERIFIED"
        ),
        "provenance": {
            "gate_code": binding(Path(__file__)),
            "freeze_manifest": binding(freeze_path),
            "freeze_cases": binding(cases_path),
            "upstream_c0_decision": binding(upstream_decision),
            "operational_incident": binding(operational_incident),
            "freeze_id": freeze.get("freeze_id"),
            "source_commit": freeze.get("source_commit"),
        },
    }
    if component == "factorization" and admission_gate is not None:
        gate["provenance"]["upstream_c1_admission_gate"] = binding(admission_gate)
    atomic_json(Path(out), gate)
    decision = {
        "schema": "ceiling_closure_operational_decision_v1",
        "kind": "decision",
        "component": component,
        "decision": gate["status"],
        "decision_class": gate["decision_class"],
        "gate_sha256": file_sha256(Path(out)),
        "freeze_id": freeze.get("freeze_id"),
        "source_commit": freeze.get("source_commit"),
        "scientific_result": "NOT_EVALUATED",
        "scientific_negative": False,
        "scientific_effect_interpretation_allowed": False,
        "isolated_topology_probe_execution": gate["isolated_topology_probe_execution"],
        "c1_admission_gate_status": c1_status,
        "deployment_integration_eligible": False,
        "online_call_n": None,
        "execution_evidence_class": gate["execution_evidence"]["evidence_class"],
        "next_permitted_action": (
            "resume the frozen annotation and independent-review identities only after capacity is restored; "
            "then rerun the preregistered scientific gate without changing sample, models, arms or thresholds"
        ),
    }
    atomic_json(Path(decision_out), decision)
    return gate


def _require_gate(path: Path, component: str) -> dict[str, Any]:
    gate = _json(path)
    if gate.get("component") != component or not gate.get("passed"):
        raise RuntimeError(f"{component} run blocked by fail-closed gate: {gate.get('failures')}")
    return gate


def compile_run(component: str, freeze_dir: Path, gate_path: Path, out: Path, *, annotations: Path | None = None, stage: str = "selector", selections: Path | None = None) -> list[dict[str, Any]]:
    """Compile immutable online jobs; this function performs no API calls."""
    gate = _require_gate(gate_path, component)
    freeze_dir = Path(freeze_dir)
    freeze_manifest_path = freeze_dir / "freeze.json"
    freeze_cases_path = freeze_dir / "cases.jsonl"
    freeze_manifest = _json(freeze_manifest_path)
    cases = read_jsonl(freeze_cases_path)
    if component == "factorization":
        provenance = gate.get("provenance") or {}
        if (
            str(provenance.get("gate_code_sha256") or "") != file_sha256(Path(__file__))
            or str(provenance.get("freeze_id") or "") != str(freeze_manifest.get("freeze_id") or "")
            or str(provenance.get("freeze_manifest_sha256") or "") != file_sha256(freeze_manifest_path)
            or str(provenance.get("freeze_cases_sha256") or "") != file_sha256(freeze_cases_path)
            or annotations is None
            or str(provenance.get("annotation_rows_sha256") or "") != file_sha256(Path(annotations))
        ):
            raise RuntimeError("factorization run gate/freeze/annotation provenance mismatch")
    if component == "active":
        if annotations is None:
            raise ValueError("active run requires --annotations")
        _, _, freeze_failures = _formal_freeze_validation(
            freeze_dir,
            "active",
            ACTIVE_ARMS,
            expected_case_n=200,
            expected_family_n={"DA": 100, "MCR": 100},
            expected_sources=[E5_JOINED],
        )
        if stage == "policy":
            active_contract_failures = _active_construction_gate_contract_failures(
                gate, freeze_dir, Path(annotations),
            )
        elif stage == "post":
            if selections is None:
                raise ValueError("active post run requires --selections")
            active_contract_failures = _active_post_gate_contract_failures(
                gate, freeze_dir, Path(annotations), Path(selections),
            )
        else:
            raise ValueError("active --stage must be policy or post")
        if freeze_failures or active_contract_failures:
            raise RuntimeError(
                "active run gate/freeze/input provenance mismatch: "
                f"{freeze_failures + active_contract_failures}"
            )
    jobs: list[dict[str, Any]] = []
    if component == "admission":
        for case in cases:
            for arm in ADMISSION_ARMS:
                state = json.loads(json.dumps(case["arms"][arm]))
                payload = {"case_key": case["case_key"], "vignette": case["vignette"], **state}
                if arm != "fixed_k":
                    payload["requested_object"] = case["requested_object"]
                    for ledger_name in ("main_frontier", "residual_ledger"):
                        for candidate in payload[ledger_name]:
                            candidate["object_kind"] = case["object_kind_by_id"].get(candidate["candidate_id"], "unresolved")
                jobs.append(_job(component, arm, case, PROMPTS[component][arm], payload))
    elif component == "factorization":
        if annotations is None:
            raise ValueError("factorization run requires --annotations")
        anns = _annotation_index(annotations)
        bridge = FrozenExactSynonymBridge(BRIDGE)
        for case in cases:
            payloads = _factor_payloads(case, anns[case["case_key"]], bridge)
            for arm in FACTORIZATION_ARMS:
                payload = {"case_key": case["case_key"], "vignette": case["vignette"], **payloads[arm]}
                jobs.append(_job(component, arm, case, PROMPTS[component][arm], payload))
    elif component == "active":
        anns = _annotation_index(annotations)
        selected = set(_json(gate_path).get("selected_case_keys") or [])
        if stage == "policy":
            jobs.extend(_active_policy_jobs(cases, anns, selected))
        elif stage == "post":
            selected_actions = {str(r["case_key"]): r for r in read_jsonl(selections)}
            jobs.extend(_active_post_jobs(cases, anns, selected_actions, selected))
    elif component == "relation":
        for case in cases:
            inverse = [
                {
                    **edge,
                    "source_id": edge["target_id"], "target_id": edge["source_id"],
                    "source_concept_id": edge["target_concept_id"], "target_concept_id": edge["source_concept_id"],
                    "source_citation": edge["target_citation"], "target_citation": edge["source_citation"],
                }
                for edge in case["relations"]
            ]
            sham = [{**edge, "relation": "none"} for edge in case["relations"]]
            if any(
                not (
                    original["source_id"] == corrupted["target_id"]
                    and original["target_id"] == corrupted["source_id"]
                    and original["source_concept_id"] == corrupted["target_concept_id"]
                    and original["target_concept_id"] == corrupted["source_concept_id"]
                    and original["source_citation"] == corrupted["target_citation"]
                    and original["target_citation"] == corrupted["source_citation"]
                )
                for original, corrupted in zip(case["relations"], inverse)
            ):
                raise AssertionError(f"{case['case_key']}: inverse-corrupted placebo drift")
            edge_by_arm = {"no_relation": [], "validated_relation": case["relations"], "inverse_corrupted": inverse, "node_only_sham": sham}
            for arm in RELATION_ARMS:
                payload = {"case_key": case["case_key"], "vignette": case["vignette"], "candidates": case["candidates"], "nodes": case["nodes"], "relations": edge_by_arm[arm]}
                jobs.append(_job(component, arm, case, PROMPTS[component][arm], payload))
    else:
        raise ValueError(component)
    write_jsonl(out, jobs)
    def input_binding(path: Path) -> dict[str, str]:
        resolved = Path(path).resolve()
        try:
            display = str(resolved.relative_to(ROOT))
        except ValueError:
            display = str(resolved)
        return {"path": display, "sha256": file_sha256(resolved)}

    input_artifacts = {
        "freeze_manifest": input_binding(freeze_manifest_path),
        "freeze_cases": input_binding(freeze_cases_path),
        "scientific_gate": input_binding(gate_path),
        "compiler_code": input_binding(Path(__file__)),
    }
    if annotations is not None:
        input_artifacts["annotations"] = input_binding(annotations)
    if selections is not None:
        input_artifacts["selections"] = input_binding(selections)
    atomic_json(Path(out).with_suffix(".manifest.json"), {
        "schema": SCHEMA,
        "kind": "immutable_job_manifest",
        "component": component,
        "stage": stage,
        "source_commit": source_commit(),
        "generator_code_sha256": file_sha256(Path(__file__)),
        "freeze_id": freeze_manifest.get("freeze_id"),
        "freeze_cases_sha256": freeze_manifest.get("cases_sha256"),
        "frozen_case_n": len(cases),
        "frozen_case_keys_sha256": canonical_sha256(sorted(str(case["case_key"]) for case in cases)),
        "input_artifacts": input_artifacts,
        "job_n": len(jobs),
        "jobs_sha256": canonical_sha256(jobs),
        "jobs_file_sha256": file_sha256(Path(out)),
        "semantic_denominator_sha256": canonical_sha256([
            [str(job["case_key"]), str(job["arm"]), str(job.get("stage") or "selector")]
            for job in jobs
        ]),
        "api_called": False,
    })
    return jobs


def _job(component: str, arm: str, case: Mapping[str, Any], prompt: str, payload: Mapping[str, Any], *, stage: str = "selector") -> dict[str, Any]:
    _assert_blind(payload)
    _assert_prompt_blind(prompt)
    job = {
        "schema": SCHEMA, "component": component, "stage": stage,
        "case_key": case["case_key"], "family": case["family"], "arm": arm,
        "prompt": prompt, "payload": dict(payload),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "payload_sha256": canonical_sha256(payload),
    }
    job["job_sha256"] = _immutable_job_sha256(job)
    return job


def _immutable_job_sha256(job: Mapping[str, Any]) -> str:
    """Hash every compiled job field except the self-referential hash."""
    return canonical_sha256({key: value for key, value in job.items() if key != "job_sha256"})


def _truth(path: Path) -> dict[tuple[str, str], str]:
    output: dict[tuple[str, str], str] = {}
    for row in read_jsonl(path):
        # ``root_relation`` remains a read-only compatibility alias for older
        # artifacts.  New files and every output use neutral provenance-aware
        # names and never upgrade model-panel labels to human-root truth.
        relation = str(
            row.get("adjudicated_relation")
            or row.get("reference_relation")
            or row.get("relation")
            or row.get("root_relation")
            or "U"
        ).upper()
        if relation not in RELATION_CODES:
            raise ValueError(f"bad adjudicated relation {relation}")
        key = (str(row["case_key"]), str(row["candidate_id"]))
        if key in output:
            raise ValueError(f"duplicate adjudicated relation {key}")
        output[key] = relation
    return output


def _paired_bootstrap_lower(rows: list[dict[str, Any]], treatment: str, control: str, replicates: int = 2000) -> float:
    by_case: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        by_case[row["case_key"]][row["arm"]] = float(row["complete"])
    pairs = [(v[treatment], v[control]) for v in by_case.values() if treatment in v and control in v]
    if not pairs:
        return -1.0
    effects = []
    for replicate in range(replicates):
        sample = [pairs[stable_seed("ita-bootstrap-v1", treatment, control, replicate, i) % len(pairs)] for i in range(len(pairs))]
        effects.append(statistics.fmean(a - b for a, b in sample))
    effects.sort()
    return effects[max(0, math.floor(.025 * len(effects)) - 1)]


def _paired_transitions(rows: list[dict[str, Any]], treatment: str, control: str) -> dict[str, int]:
    """Provenance-explicit paired transitions; missing service remains U."""
    by_case: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        by_case[row["case_key"]][row["arm"]] = str(row["adjudicated_relation"])
    rescue = catastrophic = compression = 0
    for arms in by_case.values():
        if treatment not in arms or control not in arms:
            continue
        treated, baseline = arms[treatment], arms[control]
        rescue += baseline != "C" and treated == "C"
        catastrophic += baseline == "C" and treated in {"X", "M", "N"}
        compression += baseline == "C" and treated == "P"
    return {
        "complete_rescues": rescue,
        "catastrophic_substitutions": catastrophic,
        "scope_compressions": compression,
        "net_rescue_minus_catastrophic": rescue - catastrophic,
    }


def _factorization_transition_endpoints(
    rows: Sequence[Mapping[str, Any]],
    treatment: str = "factorized_lattice",
    control: str = "flat",
) -> dict[str, int]:
    by_case: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_case[str(row["case_key"])][str(row["arm"])] = row
    rescue = compression = catastrophic = hallucination = harm_union = 0
    for arms in by_case.values():
        if treatment not in arms or control not in arms:
            continue
        treated, baseline = arms[treatment], arms[control]
        treated_relation = str(treated["adjudicated_relation"])
        baseline_relation = str(baseline["adjudicated_relation"])
        is_rescue = baseline_relation != "C" and treated_relation == "C"
        is_compression = baseline_relation == "C" and treated_relation == "P"
        is_catastrophic = baseline_relation == "C" and treated_relation in {"X", "M", "N"}
        is_hallucination = treated.get("modifier_hallucination") is True
        rescue += is_rescue
        compression += is_compression
        catastrophic += is_catastrophic
        hallucination += is_hallucination
        harm_union += is_compression or is_catastrophic or is_hallucination
    return {
        "complete_rescues": rescue,
        "scope_compressions": compression,
        "catastrophic_substitutions": catastrophic,
        "modifier_hallucinations": hallucination,
        "scope_compression_or_hallucination_or_catastrophic_cases": harm_union,
        "net_rescue_minus_scope_compression": rescue - compression,
        "net_rescue_minus_modifier_hallucination": rescue - hallucination,
        "net_rescue_minus_catastrophic": rescue - catastrophic,
        "net_rescue_minus_combined_harm": rescue - harm_union,
    }


def _factorization_analysis_contract_failures(
    jobs_path: Path,
    jobs: Sequence[Mapping[str, Any]],
    responses_path: Path,
    responses: Sequence[Mapping[str, Any]],
    truth_path: Path,
    truth_rows: Sequence[Mapping[str, Any]],
    truth_manifest_path: Path | None,
) -> list[str]:
    """Verify C2 denominator and file/row/job hash bindings before analysis."""
    failures: list[str] = []
    jobs_path = Path(jobs_path)
    responses_path = Path(responses_path)
    truth_path = Path(truth_path)
    job_manifest_path = jobs_path.with_suffix(".manifest.json")
    response_manifest_path = responses_path.parent / "selector_responses.manifest.json"
    job_manifest = _json(job_manifest_path) if job_manifest_path.is_file() else {}
    response_manifest = _json(response_manifest_path) if response_manifest_path.is_file() else {}
    truth_manifest = (
        _json(truth_manifest_path)
        if truth_manifest_path is not None and Path(truth_manifest_path).is_file()
        else {}
    )

    semantic_denominator = [
        [str(job.get("case_key")), str(job.get("arm")), str(job.get("stage") or "selector")]
        for job in jobs
    ]
    bound_artifacts = job_manifest.get("input_artifacts") or {}
    bound_docs: dict[str, Path] = {}
    for name in ("freeze_manifest", "freeze_cases", "scientific_gate", "compiler_code", "annotations"):
        entry = bound_artifacts.get(name) if isinstance(bound_artifacts, Mapping) else None
        if not isinstance(entry, Mapping):
            failures.append(f"factorization_job_{name}_binding_missing")
            continue
        path = Path(str(entry.get("path") or ""))
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or file_sha256(path) != str(entry.get("sha256") or ""):
            failures.append(f"factorization_job_{name}_binding_invalid")
            continue
        bound_docs[name] = path
    frozen_case_keys: set[str] = set()
    if {"freeze_manifest", "freeze_cases", "scientific_gate", "compiler_code", "annotations"} <= set(bound_docs):
        bound_freeze = _json(bound_docs["freeze_manifest"])
        bound_cases = read_jsonl(bound_docs["freeze_cases"])
        bound_gate = _json(bound_docs["scientific_gate"])
        bound_gate_provenance = bound_gate.get("provenance") or {}
        frozen_case_keys = {str(row.get("case_key") or "") for row in bound_cases}
        if (
            bound_freeze.get("component") != "factorization"
            or int(bound_freeze.get("case_n") or -1) != 200
            or bound_freeze.get("family_n") != {"DA": 100, "MCR": 100}
            or bound_freeze.get("arms") != list(FACTORIZATION_ARMS)
            or canonical_sha256(bound_cases) != str(bound_freeze.get("cases_sha256") or "")
            or str(bound_freeze.get("freeze_id") or "") != str(job_manifest.get("freeze_id") or "")
            or str(bound_freeze.get("cases_sha256") or "")
            != str(job_manifest.get("freeze_cases_sha256") or "")
            or len(frozen_case_keys) != 200
            or "" in frozen_case_keys
            or bound_gate.get("component") != "factorization"
            or not bool(bound_gate.get("passed"))
            or str(bound_gate_provenance.get("freeze_id") or "")
            != str(bound_freeze.get("freeze_id") or "")
            or str(bound_gate_provenance.get("freeze_manifest_sha256") or "")
            != file_sha256(bound_docs["freeze_manifest"])
            or str(bound_gate_provenance.get("freeze_cases_sha256") or "")
            != file_sha256(bound_docs["freeze_cases"])
            or str(bound_gate_provenance.get("annotation_rows_sha256") or "")
            != file_sha256(bound_docs["annotations"])
            or file_sha256(bound_docs["compiler_code"])
            != str(job_manifest.get("generator_code_sha256") or "")
        ):
            failures.append("factorization_job_frozen_design_binding_invalid")
    if not job_manifest:
        failures.append("factorization_job_manifest_missing")
    elif (
        job_manifest.get("component") != "factorization"
        or str(job_manifest.get("stage") or "selector") != "selector"
        or int(job_manifest.get("frozen_case_n") or -1) != 200
        or str(job_manifest.get("frozen_case_keys_sha256") or "")
        != canonical_sha256(sorted(frozen_case_keys))
        or str(job_manifest.get("generator_code_sha256") or "") != file_sha256(Path(__file__))
        or int(job_manifest.get("job_n") or -1) != len(jobs)
        or len(jobs) != 200 * len(FACTORIZATION_ARMS)
        or str(job_manifest.get("jobs_sha256") or "") != canonical_sha256(jobs)
        or str(job_manifest.get("jobs_file_sha256") or "") != file_sha256(jobs_path)
        or str(job_manifest.get("semantic_denominator_sha256") or "")
        != canonical_sha256(semantic_denominator)
    ):
        failures.append("factorization_job_manifest_binding_invalid")

    keys: set[tuple[str, str, str]] = set()
    arms_by_case: dict[str, set[str]] = defaultdict(set)
    for index, job in enumerate(jobs):
        key = (
            str(job.get("case_key") or ""), str(job.get("arm") or ""),
            str(job.get("stage") or "selector"),
        )
        if key in keys:
            failures.append("factorization_job_denominator_duplicate")
        keys.add(key)
        arms_by_case[key[0]].add(key[1])
        payload = job.get("payload")
        if (
            job.get("component") != "factorization"
            or key[2] != "selector"
            or not isinstance(payload, Mapping)
            or canonical_sha256(payload) != str(job.get("payload_sha256") or "")
            or hashlib.sha256(str(job.get("prompt") or "").encode()).hexdigest()
            != str(job.get("prompt_sha256") or "")
            or _immutable_job_sha256(job) != str(job.get("job_sha256") or "")
        ):
            failures.append(f"factorization_job_{index}_immutable_binding_invalid")
    if (
        not jobs
        or set(arms_by_case) != frozen_case_keys
        or any(arms != set(FACTORIZATION_ARMS) for arms in arms_by_case.values())
    ):
        failures.append("factorization_job_arm_denominator_invalid")
    expected_truth_keys = {
        (str(job.get("case_key") or ""), str(candidate.get("candidate_id") or ""))
        for job in jobs
        for candidate in (
            (job.get("payload") or {}).get("candidates")
            if isinstance(job.get("payload"), Mapping) else []
        ) or []
        if isinstance(candidate, Mapping)
    }
    observed_truth_keys = {
        (str(row.get("case_key") or ""), str(row.get("candidate_id") or ""))
        for row in truth_rows
    }
    if (
        not expected_truth_keys
        or len(observed_truth_keys) != len(truth_rows)
        or observed_truth_keys != expected_truth_keys
    ):
        failures.append("factorization_truth_candidate_coverage_invalid")

    if not response_manifest:
        failures.append("factorization_response_manifest_missing")
    elif (
        response_manifest.get("product") != "selector_responses"
        or str(response_manifest.get("model") or "") != CLOSURE_COMPARATOR_MODEL
        or int(response_manifest.get("row_n") or -1) != len(responses)
        or str(response_manifest.get("file_sha256") or "") != file_sha256(responses_path)
        or str(response_manifest.get("rows_sha256") or "") != canonical_sha256(responses)
        or file_sha256(jobs_path) not in _manifest_input_hashes(response_manifest)
        or str(response_manifest.get("generator_code_sha256") or "")
        != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
        or str(response_manifest.get("source_commit") or "")
        != str(job_manifest.get("source_commit") or "")
    ):
        failures.append("factorization_response_manifest_binding_invalid")

    response_stage_bindings = response_manifest.get("online_stage_manifests") or []
    if len(response_stage_bindings) != 1:
        failures.append("factorization_response_stage_manifest_coverage_invalid")
    else:
        stage_binding = response_stage_bindings[0]
        stage_path = (
            responses_path.parent / str(stage_binding.get("path") or "")
            if isinstance(stage_binding, Mapping) else Path()
        )
        if (
            not isinstance(stage_binding, Mapping)
            or not stage_path.is_file()
            or file_sha256(stage_path) != str(stage_binding.get("sha256") or "")
        ):
            failures.append("factorization_response_stage_manifest_binding_invalid")
        else:
            stage_doc = _json(stage_path)
            raw_path = stage_path.parent / "raw_results.jsonl"
            telemetry_path = stage_path.parent / "telemetry.jsonl"
            telemetry_summary_path = stage_path.parent / "telemetry_summary.json"
            raw_rows = read_jsonl(raw_path) if raw_path.is_file() else []
            telemetry_rows = read_jsonl(telemetry_path) if telemetry_path.is_file() else []
            telemetry_summary = (
                _json(telemetry_summary_path) if telemetry_summary_path.is_file() else {}
            )
            contracts: list[dict[str, Any]] = []
            contract_by_task: dict[str, dict[str, Any]] = {}
            job_by_task: dict[str, Mapping[str, Any]] = {}
            for job in jobs:
                stage = str(job.get("stage") or "selector")
                task_id = "|".join((str(job.get("case_key")), str(job.get("arm")), stage))
                contract = _online_task_contract(
                    task_id=task_id,
                    module=f"CeilingSelector_factorization_{stage}",
                    prompt=str(job.get("prompt") or ""),
                    payload=job.get("payload") or {},
                    model=CLOSURE_COMPARATOR_MODEL,
                    metadata={
                        "case_key": str(job.get("case_key")),
                        "arm": str(job.get("arm")),
                        "stage": stage,
                        "component": "factorization",
                        "job_sha256": str(job.get("job_sha256") or ""),
                    },
                )
                contracts.append(contract)
                contract_by_task[task_id] = contract
                job_by_task[task_id] = job
            raw_task_ids = [str(row.get("task_id") or "") for row in raw_rows]
            if (
                str(stage_doc.get("model") or "") != CLOSURE_COMPARATOR_MODEL
                or int(stage_doc.get("task_n") or -1) != len(jobs)
                or int(stage_doc.get("success_n") or 0)
                + int(stage_doc.get("failure_n") or 0) != len(jobs)
                or sum(row.get("success") is True for row in raw_rows)
                != int(stage_doc.get("success_n") or 0)
                or sum(row.get("success") is False for row in raw_rows)
                != int(stage_doc.get("failure_n") or 0)
                or sum(row.get("cache_hit") is True for row in raw_rows)
                != int(stage_doc.get("cache_hit_n") or 0)
                or len(raw_rows) != len(jobs)
                or len(raw_task_ids) != len(set(raw_task_ids))
                or set(raw_task_ids) != set(contract_by_task)
                or not raw_path.is_file()
                or not telemetry_path.is_file()
                or not telemetry_summary_path.is_file()
                or file_sha256(raw_path) != str(stage_doc.get("results_file_sha256") or "")
                or canonical_sha256(raw_rows) != str(stage_doc.get("results_sha256") or "")
                or file_sha256(telemetry_path) != str(stage_doc.get("telemetry_sha256") or "")
                or aggregate_telemetry(telemetry_rows) != telemetry_summary
                or telemetry_summary != (stage_doc.get("telemetry_summary") or {})
                or str(stage_doc.get("semantic_input_sha256") or "")
                != _online_semantic_input_sha256(contracts)
                or list(stage_doc.get("prompt_sha256s") or [])
                != sorted({str(row["prompt_sha256"]) for row in contracts})
                or str(stage_doc.get("runner_code_sha256") or "")
                != file_sha256(ROOT / "analysis/mechanism_v2/ceiling_closure_online.py")
                or str(stage_doc.get("online_runner_code_sha256") or "")
                != file_sha256(ROOT / "analysis/mechanism_v2/online_runner.py")
                or str(stage_doc.get("source_commit") or "")
                != str(response_manifest.get("source_commit") or "")
            ):
                failures.append("factorization_response_stage_product_binding_invalid")
            for raw_row in raw_rows:
                task_id = str(raw_row.get("task_id") or "")
                contract = contract_by_task.get(task_id)
                job = job_by_task.get(task_id)
                if contract is None or job is None:
                    continue
                if not _online_raw_identity_valid(
                    raw_row, contract, model=CLOSURE_COMPARATOR_MODEL
                ):
                    failures.append(f"factorization_response_raw_identity_invalid:{task_id}")
                    continue
                if raw_row.get("success") is True:
                    from analysis.mechanism_v2.ceiling_closure_online import (  # noqa: PLC0415
                        _selector_validator,
                    )

                    if _selector_validator(
                        job.get("payload") or {}, require_modifier_hallucination=True
                    )(raw_row.get("response") or {}) is not None:
                        failures.append(f"factorization_response_raw_schema_invalid:{task_id}")
            raw_by_task = {str(row.get("task_id") or ""): row for row in raw_rows}
            expected_product_rows: list[dict[str, Any]] = []
            for job in jobs:
                stage = str(job.get("stage") or "selector")
                task_id = "|".join((str(job.get("case_key")), str(job.get("arm")), stage))
                raw_row = raw_by_task.get(task_id)
                if raw_row is None:
                    continue
                response_body = raw_row.get("response") or {}
                expected_product_rows.append({
                    "case_key": str(job.get("case_key")),
                    "family": str(job.get("family") or ""),
                    "component": "factorization",
                    "arm": str(job.get("arm")),
                    "stage": stage,
                    "success": bool(raw_row.get("success")),
                    "error": str(raw_row.get("error") or ""),
                    "response": response_body,
                    "champion_id": str(response_body.get("champion_id") or ""),
                    "model": CLOSURE_COMPARATOR_MODEL,
                    "cache_hit": bool(raw_row.get("cache_hit")),
                    "cache_key": str(raw_row.get("cache_key") or ""),
                    "prompt_sha256": str(raw_row.get("prompt_sha256") or ""),
                    "payload_sha256": str(raw_row.get("payload_sha256") or ""),
                    "job_sha256": str(raw_row.get("job_sha256") or ""),
                })
            expected_product_rows.sort(
                key=lambda row: (
                    str(row.get("case_key")), str(row.get("arm")), str(row.get("stage"))
                )
            )
            if canonical_sha256(responses) != canonical_sha256(expected_product_rows):
                failures.append("factorization_response_raw_derivation_binding_invalid")

    truth_file_hash = file_sha256(truth_path)
    truth_semantic_hash = canonical_sha256(truth_rows)
    if not truth_manifest:
        failures.append("factorization_truth_manifest_missing")
    elif (
        int(truth_manifest.get("row_n") or -1) != len(truth_rows)
        or str(
            truth_manifest.get("truth_file_sha256")
            or truth_manifest.get("file_sha256")
            or ""
        ) != truth_file_hash
        or str(
            truth_manifest.get("truth_rows_sha256")
            or truth_manifest.get("rows_sha256")
            or ""
        ) != truth_semantic_hash
        or not str(
            truth_manifest.get("truth_provenance")
            or truth_manifest.get("endpoint_provenance")
            or truth_manifest.get("adjudication_provenance")
            or ""
        ).strip()
    ):
        failures.append("factorization_truth_manifest_binding_invalid")
    return failures


def _active_analysis_contract_failures(
    jobs_path: Path,
    jobs: Sequence[Mapping[str, Any]],
    responses_path: Path,
    truth_path: Path,
    truth_rows: Sequence[Mapping[str, Any]],
    truth_manifest_path: Path | None,
    post_gate_path: Path | None,
) -> list[str]:
    """Fail closed unless the complete frozen C3 post-policy lineage replays."""
    failures: list[str] = []
    if post_gate_path is None or not Path(post_gate_path).is_file():
        return ["active_post_policy_audit_gate_missing"]
    post_gate_path = Path(post_gate_path)
    post_gate = _json(post_gate_path)
    provenance = post_gate.get("provenance") or {}
    artifacts = provenance.get("input_artifacts") or {}
    freeze_manifest_path = _active_bound_path(
        artifacts.get("freeze_manifest") if isinstance(artifacts, Mapping) else None
    )
    annotations_path = _active_bound_path(
        artifacts.get("annotations") if isinstance(artifacts, Mapping) else None
    )
    selections_path = _active_bound_path(
        artifacts.get("policy_selections") if isinstance(artifacts, Mapping) else None
    )
    if freeze_manifest_path is None or annotations_path is None or selections_path is None:
        return ["active_post_gate_analysis_artifact_binding_missing"]
    freeze_dir = freeze_manifest_path.parent
    failures.extend(_active_post_gate_contract_failures(
        post_gate, freeze_dir, annotations_path, selections_path,
    ))
    freeze_cases_path = freeze_dir / "cases.jsonl"
    case_rows = read_jsonl(freeze_cases_path)
    anns = _annotation_index(annotations_path)
    selection_rows = read_jsonl(selections_path)
    selection_by_case = {
        str(row.get("case_key") or ""): row for row in selection_rows
    }
    selected = {str(value) for value in post_gate.get("selected_case_keys") or []}
    try:
        expected_jobs = _active_post_jobs(case_rows, anns, selection_by_case, selected)
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        expected_jobs = []
        failures.append(f"active_post_job_reconstruction_failed:{type(exc).__name__}")
    failures.extend(_active_selector_execution_contract_failures(
        Path(jobs_path),
        Path(responses_path),
        expected_jobs,
        stage="post",
        freeze_dir=freeze_dir,
        scientific_gate=post_gate_path,
        annotations=annotations_path,
        selections=selections_path,
    ))
    if len(jobs) != 64 * len(ACTIVE_ARMS):
        failures.append("active_post_immutable_denominator_not_64x3")

    truth_path = Path(truth_path)
    truth_manifest = (
        _json(truth_manifest_path)
        if truth_manifest_path is not None and Path(truth_manifest_path).is_file()
        else {}
    )
    truth_keys = [
        (str(row.get("case_key") or ""), str(row.get("candidate_id") or ""))
        for row in truth_rows
    ]
    expected_truth_keys = {
        (str(job.get("case_key") or ""), str(candidate.get("candidate_id") or ""))
        for job in expected_jobs
        for candidate in (job.get("payload") or {}).get("candidates") or []
        if isinstance(candidate, Mapping)
    }
    if (
        not expected_truth_keys
        or len(truth_keys) != len(set(truth_keys))
        or "" in {value for key in truth_keys for value in key}
        or not expected_truth_keys.issubset(set(truth_keys))
        or any(
            str(
                row.get("relation")
                or row.get("adjudicated_relation")
                or row.get("root_relation")
                or "U"
            ) not in RELATION_CODES
            for row in truth_rows
        )
    ):
        failures.append("active_truth_candidate_coverage_invalid")
    if not truth_manifest:
        failures.append("active_truth_manifest_missing")
    elif (
        int(truth_manifest.get("row_n") or -1) != len(truth_rows)
        or str(
            truth_manifest.get("truth_file_sha256")
            or truth_manifest.get("file_sha256")
            or ""
        ) != file_sha256(truth_path)
        or str(
            truth_manifest.get("truth_rows_sha256")
            or truth_manifest.get("rows_sha256")
            or ""
        ) != canonical_sha256(truth_rows)
        or not str(
            truth_manifest.get("truth_provenance")
            or truth_manifest.get("endpoint_provenance")
            or truth_manifest.get("adjudication_provenance")
            or ""
        ).strip()
    ):
        failures.append("active_truth_manifest_binding_invalid")
    return failures


def analyse(
    component: str,
    run_jobs: Path,
    responses: Path,
    truth: Path,
    out: Path,
    *,
    truth_provenance: str | None = None,
    truth_manifest: Path | None = None,
    active_post_gate: Path | None = None,
) -> dict[str, Any]:
    """ITA analysis: every frozen job remains; missing/invalid is incorrect."""
    manifest_provenance = ""
    if truth_manifest is not None:
        manifest = _json(truth_manifest)
        manifest_provenance = str(
            manifest.get("truth_provenance")
            or manifest.get("endpoint_provenance")
            or manifest.get("adjudication_provenance")
            or ""
        ).strip()
    provenance = str(truth_provenance or manifest_provenance or DEFAULT_TRUTH_PROVENANCE).strip()
    if not provenance:
        raise ValueError("truth provenance must be non-empty")
    jobs = read_jsonl(run_jobs)
    response_rows = read_jsonl(responses)
    truth_rows = read_jsonl(truth)
    truth_index = _truth(truth)
    pre_analysis_failures: list[str] = []
    if component == "factorization":
        pre_analysis_failures.extend(_factorization_analysis_contract_failures(
            Path(run_jobs), jobs, Path(responses), response_rows, Path(truth), truth_rows,
            Path(truth_manifest) if truth_manifest is not None else None,
        ))
    active_gate_doc: dict[str, Any] = {}
    active_case_audits: dict[str, dict[str, Any]] = {}
    if component == "active":
        pre_analysis_failures.extend(_active_analysis_contract_failures(
            Path(run_jobs),
            jobs,
            Path(responses),
            Path(truth),
            truth_rows,
            Path(truth_manifest) if truth_manifest is not None else None,
            Path(active_post_gate) if active_post_gate is not None else None,
        ))
        if active_post_gate is None or not Path(active_post_gate).is_file():
            pass
        else:
            active_gate_doc = _json(active_post_gate)
            if (
                not active_gate_doc.get("passed") or active_gate_doc.get("component") != "active"
                or active_gate_doc.get("gate_stage") != "post_policy_audit"
            ):
                pass
            audit_rows = active_gate_doc.get("case_audits") or []
            if not isinstance(audit_rows, list) or not all(isinstance(row, Mapping) for row in audit_rows):
                pre_analysis_failures.append("active_case_audits_invalid")
            else:
                active_case_audits = {str(row.get("case_key")): dict(row) for row in audit_rows}
                if len(active_case_audits) != len(audit_rows):
                    pre_analysis_failures.append("active_case_audits_duplicate")
                job_cases = {str(job["case_key"]) for job in jobs}
                if set(active_case_audits) != job_cases:
                    pre_analysis_failures.append("active_case_audit_job_coverage_mismatch")
    job_index = {
        (str(job["case_key"]), str(job["arm"]), str(job.get("stage") or "selector")): job
        for job in jobs
    }
    response_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str, str]] = set()
    hash_invalid: set[tuple[str, str, str]] = set()
    for row in response_rows:
        key = (str(row["case_key"]), str(row["arm"]), str(row.get("stage") or "selector"))
        if key in response_index:
            duplicates.add(key)
        response_index[key] = row
        if component in {"factorization", "active"}:
            prefix = component
            job = job_index.get(key)
            if job is None:
                pre_analysis_failures.append(f"unexpected_{prefix}_response:{'|'.join(key)}")
                hash_invalid.add(key)
            elif not isinstance(row.get("success"), bool):
                pre_analysis_failures.append(
                    f"{prefix}_response_success_contract_invalid:{'|'.join(key)}"
                )
                hash_invalid.add(key)
            elif (
                str(row.get("job_sha256") or "") != str(job.get("job_sha256") or "")
                or str(row.get("payload_sha256") or "") != str(job.get("payload_sha256") or "")
                or str(row.get("prompt_sha256") or "") != str(job.get("prompt_sha256") or "")
            ):
                pre_analysis_failures.append(f"{prefix}_response_hash_mismatch:{'|'.join(key)}")
                hash_invalid.add(key)
    ledger: list[dict[str, Any]] = []
    for job in jobs:
        key = (job["case_key"], job["arm"], job.get("stage") or "selector")
        response = response_index.get(key) or {}
        champion = str(response.get("champion_id") or (response.get("response") or {}).get("champion_id") or "")
        candidate_ids = {str(c["candidate_id"]) for c in job["payload"].get("candidates", job["payload"].get("main_frontier", []))}
        response_body = response.get("response") if isinstance(response.get("response"), Mapping) else response
        modifier_contract_valid = (
            component != "factorization"
            or isinstance(response_body.get("modifier_hallucination"), bool)
        )
        if component == "factorization" and response and not modifier_contract_valid:
            pre_analysis_failures.append(
                f"factorization_modifier_hallucination_contract_invalid:{'|'.join(map(str, key))}"
            )
        served = (
            key not in duplicates
            and key not in hash_invalid
            and response.get("success") is True
            and bool(champion)
            and champion in candidate_ids
            and modifier_contract_valid
        )
        relation = truth_index.get((job["case_key"], champion), "U") if served else "U"
        exposure_ids = candidate_ids
        active_arm_audit: Mapping[str, Any] | None = None
        if component == "active":
            if job["arm"] == "no_acquisition":
                active_arm_audit = {
                    "relevant": False,
                    "resolves_need": False,
                    "information_gain_per_cost": 0.0,
                    "wrong_episode_or_object_binding": False,
                    "unnecessary_high_risk_action": False,
                }
            else:
                active_arm_audit = (
                    (active_case_audits.get(str(job["case_key"])) or {}).get("arms") or {}
                ).get(str(job["arm"]))
        ledger.append({
            "case_key": job["case_key"], "family": job["family"], "arm": job["arm"],
            "served": served, "champion_id": champion if served else "", "adjudicated_relation": relation,
            "complete": bool(served and relation == "C"), "ita": True,
            "complete_exposed": any(truth_index.get((job["case_key"], cid)) == "C" for cid in exposure_ids),
            "modifier_hallucination": (
                response_body["modifier_hallucination"]
                if component == "factorization" and served and modifier_contract_valid
                else None
            ),
            "action_relevant": active_arm_audit.get("relevant") if active_arm_audit is not None else None,
            "need_resolved": active_arm_audit.get("resolves_need") if active_arm_audit is not None else None,
            "information_gain_per_cost": active_arm_audit.get("information_gain_per_cost") if active_arm_audit is not None else None,
            "wrong_episode_or_object_binding": active_arm_audit.get("wrong_episode_or_object_binding") if active_arm_audit is not None else None,
            "unnecessary_high_risk_action": active_arm_audit.get("unnecessary_high_risk_action") if active_arm_audit is not None else None,
            "failure": (
                "duplicate_response" if key in duplicates
                else "response_hash_mismatch" if key in hash_invalid
                else "" if served else "missing_or_invalid_response"
            ),
        })
    write_jsonl(Path(out).with_suffix(".ledger.jsonl"), ledger)
    metrics: dict[str, Any] = {}

    def optional_rate(subset: Sequence[Mapping[str, Any]], field: str) -> float | None:
        values = [row.get(field) for row in subset]
        return statistics.fmean(bool(value) for value in values) if values and all(value is not None for value in values) else None

    for arm in sorted({r["arm"] for r in ledger}):
        subset = [r for r in ledger if r["arm"] == arm]
        metrics[arm] = {
            "intended_n": len(subset), "served_n": sum(r["served"] for r in subset),
            "service_rate": sum(r["served"] for r in subset) / max(1, len(subset)),
            "complete_n": sum(r["complete"] for r in subset),
            "ita_complete_rate": sum(r["complete"] for r in subset) / max(1, len(subset)),
            "complete_exposure_rate": sum(r["complete_exposed"] for r in subset) / max(1, len(subset)),
            "modifier_hallucination_rate": (
                optional_rate(subset, "modifier_hallucination")
                if component == "factorization" else 0.0
            ),
            "modifier_hallucination_evaluable_n": sum(
                r["modifier_hallucination"] is not None for r in subset
            ),
            "action_relevance_rate": optional_rate(subset, "action_relevant"),
            "need_resolution_rate": optional_rate(subset, "need_resolved"),
            "mean_information_gain_per_cost": statistics.fmean(
                float(r["information_gain_per_cost"]) for r in subset
            ) if subset and all(r["information_gain_per_cost"] is not None for r in subset) else None,
            "wrong_episode_or_object_binding_rate": optional_rate(subset, "wrong_episode_or_object_binding"),
            "unnecessary_high_risk_action_rate": optional_rate(subset, "unnecessary_high_risk_action"),
        }
    failures = pre_analysis_failures + [f"{arm}:service_below_0.98" for arm, value in metrics.items() if value["service_rate"] < .98]
    contrasts: dict[str, Any] = {}
    if component == "admission":
        pairs = (("qualified_frontier", "fixed_k"), ("qualified_frontier", "sham_qualification"))
        for treatment, control in pairs:
            effect = metrics[treatment]["ita_complete_rate"] - metrics[control]["ita_complete_rate"]
            lower = _paired_bootstrap_lower(ledger, treatment, control)
            contrasts[f"{treatment}_vs_{control}"] = {"difference": effect, "bootstrap_95_lower": lower}
        q_sham = contrasts["qualified_frontier_vs_sham_qualification"]
        q_fixed = contrasts["qualified_frontier_vs_fixed_k"]
        if metrics["qualified_frontier"]["complete_exposure_rate"] < metrics["fixed_k"]["complete_exposure_rate"]:
            failures.append("qualified_complete_exposure_lower_than_fixed")
        transition = _paired_transitions(ledger, "qualified_frontier", "fixed_k")
        contrasts["qualified_frontier_vs_fixed_k"].update(transition)
        if transition["catastrophic_substitutions"] > transition["complete_rescues"]:
            failures.append("catastrophic_substitution_exceeds_object_rescue")
        if q_sham["difference"] < .03 or q_sham["bootstrap_95_lower"] <= 0:
            failures.append("qualified_not_3pp_and_positive_lower_bound_over_equal_width_sham")
    elif component == "factorization":
        for control in ("flat", "structure_sham", "corrupted_modifier_mapping"):
            effect = metrics["factorized_lattice"]["ita_complete_rate"] - metrics[control]["ita_complete_rate"]
            lower = _paired_bootstrap_lower(ledger, "factorized_lattice", control)
            contrasts[f"factorized_lattice_vs_{control}"] = {"difference": effect, "bootstrap_95_lower": lower}
        if any(v["difference"] < .03 or v["bootstrap_95_lower"] <= 0 for v in contrasts.values()):
            failures.append("factorization_not_3pp_and_positive_lower_bound_over_all_controls")
        factor_transition = _factorization_transition_endpoints(ledger)
        contrasts["factorized_lattice_vs_flat"].update(factor_transition)
        if any(
            metrics[arm]["modifier_hallucination_rate"] is None
            for arm in FACTORIZATION_ARMS
        ):
            failures.append("modifier_hallucination_not_evaluable_for_every_arm")
        elif metrics["factorized_lattice"]["modifier_hallucination_rate"] > metrics["flat"]["modifier_hallucination_rate"]:
            failures.append("modifier_hallucination_increased")
        rescue_n = factor_transition["complete_rescues"]
        if rescue_n <= factor_transition["scope_compressions"]:
            failures.append("factorization_rescue_not_greater_than_scope_compression")
        if rescue_n <= factor_transition["modifier_hallucinations"]:
            failures.append("factorization_rescue_not_greater_than_modifier_hallucination")
        if rescue_n <= factor_transition["catastrophic_substitutions"]:
            failures.append("factorization_rescue_not_greater_than_catastrophic_substitution")
        if rescue_n <= factor_transition["scope_compression_or_hallucination_or_catastrophic_cases"]:
            failures.append("factorization_rescue_not_greater_than_combined_harm")
    elif component == "active":
        for control in ("no_acquisition", "cost_matched_random"):
            effect = metrics["typed_action"]["ita_complete_rate"] - metrics[control]["ita_complete_rate"]
            lower = _paired_bootstrap_lower(ledger, "typed_action", control)
            contrasts[f"typed_action_vs_{control}"] = {"difference": effect, "bootstrap_95_lower": lower}
        random_contrast = contrasts["typed_action_vs_cost_matched_random"]
        if random_contrast["difference"] < .15 or random_contrast["bootstrap_95_lower"] <= 0:
            failures.append("typed_action_not_15pp_and_positive_lower_bound_over_cost_matched_random")
        if metrics["typed_action"]["wrong_episode_or_object_binding_rate"] is None:
            failures.append("wrong_episode_or_object_binding_not_evaluable")
        elif metrics["typed_action"]["wrong_episode_or_object_binding_rate"] > .02:
            failures.append("wrong_episode_or_object_binding_above_0.02")
        if metrics["typed_action"]["unnecessary_high_risk_action_rate"] is None:
            failures.append("unnecessary_high_risk_action_not_evaluable")
        elif metrics["typed_action"]["unnecessary_high_risk_action_rate"] > .05:
            failures.append("unnecessary_high_risk_action_above_0.05")
        for endpoint in ("action_relevance_rate", "need_resolution_rate", "mean_information_gain_per_cost"):
            if metrics["typed_action"][endpoint] is None:
                failures.append(f"typed_action_{endpoint}_not_evaluable")
    elif component == "relation":
        for control in ("no_relation", "inverse_corrupted", "node_only_sham"):
            effect = metrics["validated_relation"]["ita_complete_rate"] - metrics[control]["ita_complete_rate"]
            lower = _paired_bootstrap_lower(ledger, "validated_relation", control)
            contrasts[f"validated_relation_vs_{control}"] = {"difference": effect, "bootstrap_95_lower": lower}
        if contrasts["validated_relation_vs_inverse_corrupted"]["difference"] <= 0 or contrasts["validated_relation_vs_inverse_corrupted"]["bootstrap_95_lower"] <= 0:
            failures.append("validated_not_separated_from_inverse_corrupted_salience")
        relation_transition = _paired_transitions(ledger, "validated_relation", "no_relation")
        contrasts["validated_relation_vs_no_relation"].update(relation_transition)
        if relation_transition["catastrophic_substitutions"] > relation_transition["complete_rescues"]:
            failures.append("relation_catastrophic_substitution_exceeds_rescue")
    else:
        raise ValueError(component)
    result = {
        "schema": SCHEMA, "kind": "analysis", "component": component,
        "truth_provenance": provenance,
        "estimand": f"{provenance} clinical-complete ITA; missing/schema/service failures are incorrect",
        "metrics": metrics, "contrasts": contrasts,
        "active_policy_endpoints": active_gate_doc.get("metrics") if component == "active" else None,
        "active_policy_endpoint_provenance": (
            "policy-projected independent two-model action-bank audit" if component == "active" and active_gate_doc else None
        ),
        "factorization_analysis_bindings": ({
            "immutable_job_manifest": {
                "path": _portable_artifact_path(Path(run_jobs).with_suffix(".manifest.json")),
                "sha256": file_sha256(Path(run_jobs).with_suffix(".manifest.json"))
                if Path(run_jobs).with_suffix(".manifest.json").is_file() else None,
            },
            "response_product_manifest": {
                "path": _portable_artifact_path(Path(responses).parent / "selector_responses.manifest.json"),
                "sha256": file_sha256(Path(responses).parent / "selector_responses.manifest.json")
                if (Path(responses).parent / "selector_responses.manifest.json").is_file() else None,
            },
            "truth_manifest": {
                "path": _portable_artifact_path(Path(truth_manifest)) if truth_manifest is not None else None,
                "sha256": file_sha256(Path(truth_manifest))
                if truth_manifest is not None and Path(truth_manifest).is_file() else None,
            },
            "immutable_job_n": len(jobs),
            "immutable_denominator_sha256": canonical_sha256([
                [str(job.get("case_key")), str(job.get("arm")), str(job.get("stage") or "selector")]
                for job in jobs
            ]),
        } if component == "factorization" else None),
        "active_analysis_bindings": ({
            "post_policy_gate": _active_artifact_binding(Path(active_post_gate))
            if active_post_gate is not None else None,
            "immutable_job_manifest": _active_artifact_binding(
                Path(run_jobs).with_suffix(".manifest.json")
            ),
            "response_product_manifest": _active_artifact_binding(
                Path(responses).parent / "selector_responses.manifest.json"
            ),
            "truth_manifest": _active_artifact_binding(Path(truth_manifest))
            if truth_manifest is not None else None,
            "immutable_job_n": len(jobs),
            "immutable_denominator_sha256": canonical_sha256([
                [str(job.get("case_key")), str(job.get("arm")), str(job.get("stage") or "post")]
                for job in jobs
            ]),
        } if component == "active" else None),
        "passed": not failures, "status": "GO" if not failures else "NO_GO",
        "failures": failures, "common_served_is_sensitivity_only": True,
    }
    atomic_json(out, result)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    components = parser.add_subparsers(dest="component", required=True)
    for component in ("admission", "factorization", "active", "relation"):
        cp = components.add_parser(component)
        actions = cp.add_subparsers(dest="action", required=True)
        freeze = actions.add_parser("freeze")
        freeze.add_argument("--out", type=Path, required=True)
        freeze.add_argument("--typing", type=Path)
        freeze.add_argument("--k", type=int, default=4)
        gate = actions.add_parser("gate")
        gate.add_argument("--freeze", type=Path, required=True)
        gate.add_argument("--out", type=Path, required=True)
        gate.add_argument("--annotations", type=Path)
        gate.add_argument("--reviews", type=Path)
        gate.add_argument("--predictions", type=Path)
        gate.add_argument("--admission-gate", type=Path)
        gate.add_argument("--provenance", type=Path)
        if component == "admission":
            operational_gate = actions.add_parser("operational-gate")
            operational_gate.add_argument("--freeze", type=Path, required=True)
            operational_gate.add_argument("--typing-dir", type=Path, required=True)
            operational_gate.add_argument("--readiness-gate", type=Path, required=True)
            operational_gate.add_argument("--c0-analysis", type=Path, required=True)
            operational_gate.add_argument("--operational-incident", type=Path, required=True)
            operational_gate.add_argument("--out", type=Path, required=True)
            operational_gate.add_argument("--report", type=Path)
            operational_gate.add_argument("--decision-out", type=Path)
        if component == "active":
            post_gate = actions.add_parser("post-gate")
            post_gate.add_argument("--freeze", type=Path, required=True)
            post_gate.add_argument("--annotations", type=Path, required=True)
            post_gate.add_argument("--reviews", type=Path, required=True)
            post_gate.add_argument("--selections", type=Path, required=True)
            post_gate.add_argument("--construction-gate", type=Path, required=True)
            post_gate.add_argument("--out", type=Path, required=True)
        if component in {"factorization", "active"}:
            not_executed = actions.add_parser(
                "not-executed-gate",
                help="record a capacity-blocked operational No-Go with null scientific metrics",
            )
            not_executed.add_argument("--freeze", type=Path, required=True)
            not_executed.add_argument("--upstream-decision", type=Path, required=True)
            not_executed.add_argument("--operational-incident", type=Path, required=True)
            if component == "factorization":
                not_executed.add_argument("--admission-gate", type=Path, required=True)
            not_executed.add_argument("--out", type=Path, required=True)
            not_executed.add_argument("--decision-out", type=Path, required=True)
        run = actions.add_parser("run")
        run.add_argument("--freeze", type=Path, required=True)
        run.add_argument("--gate", type=Path, required=True)
        run.add_argument("--out", type=Path, required=True)
        run.add_argument("--annotations", type=Path)
        run.add_argument("--stage", default="selector")
        run.add_argument("--selections", type=Path)
        ana = actions.add_parser("analyse")
        ana.add_argument("--run-jobs", type=Path, required=True)
        ana.add_argument("--responses", type=Path, required=True)
        ana.add_argument("--truth", type=Path, required=True)
        ana.add_argument("--truth-manifest", type=Path)
        ana.add_argument("--active-post-gate", type=Path)
        ana.add_argument(
            "--truth-provenance",
            default=None,
            help=f"endpoint label provenance (default: {DEFAULT_TRUTH_PROVENANCE})",
        )
        ana.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "freeze":
        if args.component == "admission":
            freeze_admission(args.out, typing=args.typing, k=args.k)
        elif args.component == "factorization":
            freeze_factorization(args.out)
        elif args.component == "active":
            freeze_active(args.out)
        else:
            freeze_relation(args.out)
    elif args.action == "not-executed-gate":
        gate_not_executed(
            args.component,
            args.freeze,
            args.upstream_decision,
            args.operational_incident,
            args.out,
            args.decision_out,
            admission_gate=getattr(args, "admission_gate", None),
        )
    elif args.action == "gate":
        if args.component == "admission":
            gate_admission(args.freeze, args.out)
        elif args.component == "factorization":
            if not all((args.annotations, args.reviews, args.admission_gate)):
                raise SystemExit("factorization gate requires --annotations --reviews --admission-gate")
            gate_factorization(args.freeze, args.annotations, args.reviews, args.admission_gate, args.out)
        elif args.component == "active":
            if not all((args.annotations, args.reviews, args.predictions)):
                raise SystemExit("active gate requires --annotations --reviews --predictions")
            gate_active(args.freeze, args.annotations, args.reviews, args.predictions, args.out)
        else:
            if not all((args.reviews, args.provenance)):
                raise SystemExit("relation gate requires --reviews --provenance")
            gate_relation(args.freeze, args.reviews, args.provenance, args.out)
    elif args.action == "operational-gate":
        gate_admission_operational(
            args.freeze,
            args.typing_dir,
            args.readiness_gate,
            args.c0_analysis,
            args.operational_incident,
            args.out,
            report=args.report,
            decision_out=args.decision_out,
        )
    elif args.action == "post-gate":
        gate_active_post(
            args.freeze,
            args.annotations,
            args.reviews,
            args.selections,
            args.construction_gate,
            args.out,
        )
    elif args.action == "run":
        compile_run(args.component, args.freeze, args.gate, args.out, annotations=args.annotations, stage=args.stage, selections=args.selections)
    else:
        analyse(
            args.component,
            args.run_jobs,
            args.responses,
            args.truth,
            args.out,
            truth_provenance=args.truth_provenance,
            truth_manifest=args.truth_manifest,
            active_post_gate=args.active_post_gate,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
