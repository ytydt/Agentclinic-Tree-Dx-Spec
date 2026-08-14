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
from collections import Counter, defaultdict, deque
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
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed  # noqa: E402


SCHEMA = "ceiling_breakthrough_experiments_v1"
E4_POOLS = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/canonical_pools.jsonl"
E4_JOINED = ROOT / "analysis/mechanism_v2/results/E4_fixed_pool_crossover/E4_JOINED_RESULTS.tar.gz"
E5_JOINED = ROOT / "analysis/mechanism_v2/results/E5_candidate_interference/E5_JOINED_RESULTS.tar.gz"
BRIDGE = ROOT / "data/knowledge_raw/disease_name_bridge.json"
SNOMED_CONCEPTS = ROOT / "data/knowledge_raw/snomed_concepts.json"
SNOMED_TERMS = ROOT / "data/knowledge_raw/snomed_term_index.json"
SNOMED_RELATIONS = ROOT / "data/knowledge_raw/snomed_relations.json"

ADMISSION_ARMS = ("fixed_k", "typed_fixed_k", "qualified_frontier", "sham_qualification")
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
RELATION_EXPECTED_EDGES = 124
RELATION_EXPECTED_FAMILY = {"DA": 53, "MCR": 43}
DEFAULT_TRUTH_PROVENANCE = "three_model_adjudicated_panel_sensitivity"

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

PROMPTS = {
    "admission": {
        # The four membership treatments use a byte-identical comparator.
        # Neither the treatment name nor the admission rule is disclosed.
        arm: "Compare only the supplied main candidate frontier. The residual ledger preserves coverage and must not participate in this first-pass decision.\n"
        + COMMON_SELECTOR_CONTRACT
        for arm in ADMISSION_ARMS
    },
    "factorization": {
        "flat": "Compare the supplied candidate labels.\n" + COMMON_SELECTOR_CONTRACT,
        "exact_identity": "Aggregate only confirmed exact/frozen synonyms before comparing.\n" + COMMON_SELECTOR_CONTRACT,
        "factorized_lattice": "First choose a core entity, then select an existing member whose explicit modifiers are supported. Never fill a missing modifier.\n" + COMMON_SELECTOR_CONTRACT,
        "structure_sham": "Read the supplied singleton structured records, then compare candidates.\n" + COMMON_SELECTOR_CONTRACT,
        "corrupted_modifier_mapping": "Use the supplied structured records and their modifier obligations.\n" + COMMON_SELECTOR_CONTRACT,
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
    manifest = {
        "schema": SCHEMA,
        "kind": "freeze",
        "component": component,
        "source_commit": source_commit(),
        "source_artifacts": [
            {"path": str(path.relative_to(ROOT)), "sha256": file_sha256(path)} for path in sources
        ],
        "case_n": len(rows),
        "family_n": dict(sorted(Counter(str(r.get("family")) for r in rows).items())),
        "cases_sha256": canonical_sha256(rows),
        "outcome_blind": True,
        **extra,
    }
    manifest["freeze_id"] = canonical_sha256(manifest)
    atomic_json(out / "freeze.json", manifest)
    return manifest


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


def freeze_admission(out: Path, *, pools: Path = E4_POOLS, joined: Path = E4_JOINED, typing: Path | None = None, k: int = 4) -> dict[str, Any]:
    """Freeze four admission arms without consulting candidate/reference truth."""
    typings = _load_typing(typing)
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
        typed_eligible_ids = [c["candidate_id"] for c in candidates if requested_kind and type_by_id.get(c["candidate_id"]) == requested_kind]
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
    return _write_freeze(out, "admission", rows, [pools, joined] + ([typing] if typing else []), arms=list(ADMISSION_ARMS), k=k)


def gate_admission(freeze_dir: Path, out: Path) -> dict[str, Any]:
    rows = read_jsonl(Path(freeze_dir) / "cases.jsonl")
    freeze_path = Path(freeze_dir) / "freeze.json"
    freeze = _json(freeze_path) if freeze_path.is_file() else {}
    k = int(freeze.get("k") or 4)
    failures: list[str] = []
    if not freeze_path.is_file():
        failures.append("freeze_manifest_missing")
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
    }, "online architecture test only; final admission efficacy gate is owned by analyse")


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
            "core_id": str(mapped["core_id"]), "core_label": str(mapped["core_label"]),
            "object_kind": str(mapped["object_kind"]),
            "relation_to_core": str(mapped["relation_to_core"]),
            "modifiers": {axis: list((mapped.get("modifiers") or {}).get(axis) or []) for axis in MODIFIER_AXES},
        })
    # Deterministic cyclic derangement; modifiers move but node/group topology,
    # field count and candidate order stay fixed.
    order = sorted(range(len(factorized)), key=lambda i: (stable_seed("modifier-corrupt-v1", case["case_key"], factorized[i]["candidate_id"]), i))
    rotated = order[1:] + order[:1]
    source_for = {target: source for target, source in zip(order, rotated)}
    corrupt = [{**row, "modifiers": factorized[source_for[i]]["modifiers"]} for i, row in enumerate(factorized)]
    sham = [{**row, "core_id": f"S-{row['candidate_id']}", "core_label": row["label"], "relation_to_core": "singleton"} for row in factorized]
    return {
        "flat": {"candidates": candidates},
        "exact_identity": {"candidates": [{**c, "core_id": exact_core[c["candidate_id"]]} for c in candidates]},
        "factorized_lattice": {"requested_object": ann["requested_object"], "candidates": factorized},
        "structure_sham": {"requested_object": ann["requested_object"], "candidates": sham},
        "corrupted_modifier_mapping": {"requested_object": ann["requested_object"], "candidates": corrupt},
    }


def _review_metrics(reviews: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "grouped_pair_precision": statistics.fmean(bool(r.get("grouped_correct")) for r in reviews) if reviews else 0.0,
        "modifier_axis_precision": statistics.fmean(bool(r.get("modifier_correct")) for r in reviews) if reviews else 0.0,
        "unsafe_synonym_merges": float(sum(bool(r.get("unsafe_synonym_merge")) for r in reviews)),
    }


def gate_factorization(freeze_dir: Path, annotations: Path, reviews: Path, admission_gate: Path, out: Path) -> dict[str, Any]:
    cases = read_jsonl(Path(freeze_dir) / "cases.jsonl")
    anns = _annotation_index(annotations)
    review_rows = read_jsonl(reviews)
    upstream = _json(admission_gate)
    bridge = FrozenExactSynonymBridge(BRIDGE)
    failures: list[str] = []
    if not upstream.get("passed"):
        failures.append("upstream_admission_gate_not_passed")
    unresolved = 0
    total = 0
    modifier_claim_n = 0
    modifier_grounded_n = 0
    nontrivial_corrupt_cases = 0
    for case in cases:
        ann = anns.get(case["case_key"])
        if not ann:
            failures.append(f"{case['case_key']}:missing_annotation")
            continue
        expected = {c["candidate_id"] for c in case["candidates"]}
        mapped = ann.get("candidates") or []
        if {str(x.get("candidate_id")) for x in mapped} != expected or len(mapped) != len(expected):
            failures.append(f"{case['case_key']}:candidate_coverage")
            continue
        if str((ann.get("requested_object") or {}).get("kind") or "") in {"", "unresolved"}:
            failures.append(f"{case['case_key']}:requested_object")
        total += len(mapped)
        unresolved += sum(bool(x.get("unresolved")) for x in mapped)
        for mapped_candidate in mapped:
            unknown_axes = set((mapped_candidate.get("modifiers") or {}).keys()) - set(MODIFIER_AXES)
            if unknown_axes:
                failures.append(f"{case['case_key']}:{mapped_candidate.get('candidate_id')}:unknown_modifier_axis")
            for values in (mapped_candidate.get("modifiers") or {}).values():
                for modifier in values or []:
                    modifier_claim_n += 1
                    support_spans = modifier.get("support_spans") or []
                    if support_spans and all(_valid_segment(case["vignette"], span) for span in support_spans):
                        modifier_grounded_n += 1
        try:
            payloads = _factor_payloads(case, ann, bridge)
        except (KeyError, TypeError, ValueError) as exc:
            failures.append(f"{case['case_key']}:schema:{exc}")
            continue
        source_mods = [x["modifiers"] for x in payloads["factorized_lattice"]["candidates"]]
        corrupt_mods = [x["modifiers"] for x in payloads["corrupted_modifier_mapping"]["candidates"]]
        if source_mods != corrupt_mods:
            nontrivial_corrupt_cases += 1
        if Counter(canonical_sha256(x) for x in source_mods) != Counter(canonical_sha256(x) for x in corrupt_mods):
            failures.append(f"{case['case_key']}:corruption_not_bijection")
    metrics = _review_metrics(review_rows)
    metrics["unresolved_rate"] = unresolved / max(1, total)
    metrics["candidate_coverage"] = 1 - sum("candidate_coverage" in x or "missing_annotation" in x for x in failures) / max(1, len(cases))
    metrics["modifier_citation_closure"] = modifier_grounded_n / max(1, modifier_claim_n)
    metrics["nontrivial_corruption_case_rate"] = nontrivial_corrupt_cases / max(1, len(cases))
    review_groups: dict[str, list[str]] = defaultdict(list)
    for review in review_rows:
        key = f"{review.get('case_key')}|{review.get('left_id')}|{review.get('right_id')}"
        review_groups[key].append(str(review.get("decision") or (bool(review.get("grouped_correct")), bool(review.get("modifier_correct")))))
    metrics["raw_agreement"], metrics["gwet_ac1"] = _gwet_ac1(review_groups)
    if metrics["grouped_pair_precision"] < .95:
        failures.append("grouped_pair_precision_below_0.95")
    if metrics["modifier_axis_precision"] < .90:
        failures.append("modifier_axis_precision_below_0.90")
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
    return _gate_write(out, "factorization", not failures, failures, metrics, "conditional conversion only on gold-conditioned E5 base4; no recall/open-diagnosis claim")


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
    cases = {r["case_key"]: r for r in read_jsonl(Path(freeze_dir) / "cases.jsonl")}
    anns = _annotation_index(annotations)
    review_rows = read_jsonl(reviews)
    predictions_by_case = {str(r["case_key"]): r for r in read_jsonl(predictions)}
    failures: list[str] = []
    valid_by_family: dict[str, list[str]] = defaultdict(list)
    availability_ok = 0
    action_n = 0
    for case_key, case in cases.items():
        ann = anns.get(case_key)
        if not ann:
            failures.append(f"{case_key}:missing_builder_annotation")
            continue
        raw = case["builder_payload"]["raw_vignette"]
        initial = str(ann.get("initial_text") or "")
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
                interval = (int(segment["start"]), int(segment["end"]))
                intervals.append(interval)
                if segment["text"] in initial:
                    failures.append(f"{case_key}:{action.get('action_id')}:result_visible_initially")
                valid_actions.append(action)
        if any(a[0] < b[1] and b[0] < a[1] for i, a in enumerate(intervals) for b in intervals[i + 1 :]):
            failures.append(f"{case_key}:overlapping_results")
        if len(valid_actions) >= 3 and len({str(a.get("action_type")) for a in valid_actions}) >= 2:
            valid_by_family[case["family"]].append(case_key)
    by_review_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in review_rows:
        by_review_case[str(row["case_key"])].append(row)
    need_groups = {key: [str(r.get("need_type")) for r in rows] for key, rows in by_review_case.items()}
    agreement, ac1 = _gwet_ac1(need_groups)
    adjudicated_need = {key: str(_majority(values)) for key, values in need_groups.items()}
    pred_need = {key: str(row.get("need_type")) for key, row in predictions_by_case.items()}
    f1 = _macro_f1(adjudicated_need, pred_need)
    relevance_hits = relevance_n = leakage = 0
    for case_key, prediction in predictions_by_case.items():
        reviews_for_case = by_review_case.get(case_key, [])
        action_id = str(prediction.get("action_id"))
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
        "direct_answer_leak_reviews": leakage,
    }
    thresholds = {
        "action_availability_rate": 1.0, "raw_agreement": .90, "gwet_ac1": .75,
        "missing_need_macro_f1": .70, "typed_action_relevance_precision": .75,
    }
    for name, threshold in thresholds.items():
        if metrics[name] < threshold:
            failures.append(f"{name}_below_{threshold}")
    if leakage:
        failures.append("direct_answer_leak_nonzero")
    selected: list[str] = []
    for family in ("DA", "MCR"):
        ranked = sorted(valid_by_family[family], key=lambda x: (stable_seed("active64-v1", x), x))
        if len(ranked) < 32:
            failures.append(f"{family}:fewer_than_32_builder_valid")
        selected.extend(ranked[:32])
    gate = _gate_write(out, "active", not failures, failures, metrics, "benchmark construction / retrospective off-policy capability only; not end-to-end ceiling breakthrough")
    gate["selected_case_keys"] = sorted(selected)
    gate["selected_case_sha256"] = canonical_sha256(sorted(selected))
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
    """Build the preregistered strict E4 96-case/124-edge primary substrate."""
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
    for raw in read_jsonl(pools):
        vignette = vignettes[str(raw["case_key"])]
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
        edges = []
        for source in nodes:
            for target in nodes:
                if source is target or not source["concept_id"] or not target["concept_id"]:
                    continue
                if not source["citations"] or not target["citations"]:
                    continue
                distance = _is_a_distance(source["concept_id"], target["concept_id"], parents, 4)
                if distance is not None:
                    edges.append({
                        "source_id": source["candidate_id"], "target_id": target["candidate_id"],
                        "relation": "is_a", "distance": distance,
                        "source_citation": source["citations"][0], "target_citation": target["citations"][0],
                    })
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
    if len(rows) != RELATION_EXPECTED_CASES or edge_n != RELATION_EXPECTED_EDGES or dict(counts) != RELATION_EXPECTED_FAMILY:
        raise AssertionError(f"strict relation primary drift: cases={len(rows)}, edges={edge_n}, family={dict(counts)}")
    # The raw JSONs do not embed RF2 release provenance.  Hashes freeze the
    # bytes, but a separate reviewer-owned provenance record is a hard gate.
    return _write_freeze(out, "relation", rows, [pools, joined, concepts_path, terms_path, relations_path, bridge_path], arms=list(RELATION_ARMS), primary_contract="case-sensitive literal citation + unique disorder mapping + directed is_a path <=4", edge_n=edge_n, snomed_release_provenance="unverified")


def gate_relation(freeze_dir: Path, reviews: Path, provenance: Path, out: Path) -> dict[str, Any]:
    rows = read_jsonl(Path(freeze_dir) / "cases.jsonl")
    freeze = _json(Path(freeze_dir) / "freeze.json")
    review_rows = read_jsonl(reviews)
    provenance_doc = _json(provenance) if Path(provenance).is_file() else {}
    failures: list[str] = []
    if len(rows) != 96 or freeze.get("edge_n") != 124 or Counter(r["family"] for r in rows) != RELATION_EXPECTED_FAMILY:
        failures.append("strict96_124_primary_drift")
    edge_keys = {(r["case_key"], e["source_id"], e["target_id"]) for r in rows for e in r["relations"]}
    reviewed_keys = {(str(r["case_key"]), str(r["source_id"]), str(r["target_id"])) for r in review_rows}
    if reviewed_keys != edge_keys:
        failures.append("all_124_edges_not_model_panel_reviewed")
    mapping_precision = statistics.fmean(bool(r.get("mapping_correct")) for r in review_rows) if review_rows else 0.0
    direction = statistics.fmean(bool(r.get("direction_correct")) for r in review_rows) if review_rows else 0.0
    citation = statistics.fmean(bool(r.get("citation_closed")) for r in review_rows) if review_rows else 0.0
    unresolved = statistics.fmean(bool(r.get("unresolved")) for r in review_rows) if review_rows else 1.0
    inverse_or_cycle = sum(bool(r.get("inverse_or_cycle")) for r in review_rows)
    groups: dict[str, list[str]] = defaultdict(list)
    for review in review_rows:
        groups[f"{review.get('case_key')}|{review.get('source_id')}|{review.get('target_id')}"] .append(str(review.get("decision") or ""))
    agreement, ac1 = _gwet_ac1(groups)
    metrics = {
        "mapping_precision": mapping_precision, "direction_fidelity": direction,
        "citation_closure": citation, "unresolved_rate": unresolved,
        "inverse_or_cycles": inverse_or_cycle, "raw_agreement": agreement, "gwet_ac1": ac1,
        "provenance_verified": bool(provenance_doc.get("rf2_release") and provenance_doc.get("reviewer") and provenance_doc.get("verified")),
    }
    checks = {"mapping_precision": .95, "direction_fidelity": .97, "citation_closure": 1.0, "raw_agreement": .90, "gwet_ac1": .75}
    for name, threshold in checks.items():
        if metrics[name] < threshold:
            failures.append(f"{name}_below_{threshold}")
    if unresolved > .05:
        failures.append("unresolved_rate_above_0.05")
    if inverse_or_cycle:
        failures.append("inverse_or_cycle_nonzero")
    if not metrics["provenance_verified"]:
        failures.append("snomed_release_provenance_unverified")
    return _gate_write(out, "relation", not failures, failures, metrics, "deterministic E4 strict96/124 relation-substrate test; not all relation systems")


def _gate_write(out: Path, component: str, passed: bool, failures: list[str], metrics: Mapping[str, Any], claim_scope: str) -> dict[str, Any]:
    gate = {
        "schema": SCHEMA, "kind": "gate", "component": component,
        "passed": bool(passed), "status": "GO" if passed else "NO_GO",
        "fail_closed": True, "failures": sorted(set(failures)),
        "metrics": dict(metrics), "claim_scope": claim_scope,
    }
    atomic_json(Path(out), gate)
    return gate


def _require_gate(path: Path, component: str) -> dict[str, Any]:
    gate = _json(path)
    if gate.get("component") != component or not gate.get("passed"):
        raise RuntimeError(f"{component} run blocked by fail-closed gate: {gate.get('failures')}")
    return gate


def compile_run(component: str, freeze_dir: Path, gate_path: Path, out: Path, *, annotations: Path | None = None, stage: str = "selector", selections: Path | None = None) -> list[dict[str, Any]]:
    """Compile immutable online jobs; this function performs no API calls."""
    _require_gate(gate_path, component)
    cases = read_jsonl(Path(freeze_dir) / "cases.jsonl")
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
        if annotations is None:
            raise ValueError("active run requires --annotations")
        anns = _annotation_index(annotations)
        selected = set(_json(gate_path).get("selected_case_keys") or [])
        if stage == "policy":
            for case in cases:
                if case["case_key"] not in selected:
                    continue
                ann = anns[case["case_key"]]
                menu = [{k: a[k] for k in ("action_id", "action_type", "action_name", "cost", "cost_band", "delay", "risk") if k in a} for a in ann["actions"] if a.get("status") == "performed"]
                payload = {"case_key": case["case_key"], "initial_vignette": ann["initial_text"], "candidates": case["policy_candidates"], "action_menu": menu}
                jobs.append(_job(component, "typed_policy", case, PROMPTS["active_policy"], payload, stage="policy"))
        elif stage == "post":
            if selections is None:
                raise ValueError("active post run requires --selections")
            selected_actions = {str(r["case_key"]): r for r in read_jsonl(selections)}
            for case in cases:
                if case["case_key"] not in selected:
                    continue
                ann = anns[case["case_key"]]
                action_by_id = {str(a["action_id"]): a for a in ann["actions"] if a.get("status") == "performed"}
                chosen = str((selected_actions.get(case["case_key"]) or {}).get("action_id") or "")
                if chosen not in action_by_id:
                    raise RuntimeError(f"invalid/missing typed action for {case['case_key']}")
                typed = action_by_id[chosen]
                peers = [a for aid, a in action_by_id.items() if aid != chosen and a.get("cost_band") == typed.get("cost_band")]
                if not peers:
                    raise RuntimeError(f"no cost-matched random action for {case['case_key']}")
                random_action = sorted(peers, key=lambda a: (stable_seed("active-random-v1", case["case_key"], a["action_id"]), a["action_id"]))[0]
                released = {"no_acquisition": None, "typed_action": typed, "cost_matched_random": random_action}
                for arm, action in released.items():
                    evidence = None if action is None else {"action_id": action["action_id"], "action_type": action["action_type"], "result": action["result_span"]["text"]}
                    payload = {"case_key": case["case_key"], "vignette": ann["initial_text"], "candidates": case["policy_candidates"], "released_evidence": evidence}
                    jobs.append(_job(component, arm, case, PROMPTS["active_post"][arm], payload, stage="post"))
        else:
            raise ValueError("active --stage must be policy or post")
    elif component == "relation":
        for case in cases:
            inverse = [
                {
                    **edge,
                    "source_id": edge["target_id"], "target_id": edge["source_id"],
                    "source_citation": edge["target_citation"], "target_citation": edge["source_citation"],
                }
                for edge in case["relations"]
            ]
            sham = [{"source_id": edge["source_id"], "target_id": edge["target_id"], "relation": "none", "distance": edge["distance"], "source_citation": edge["source_citation"], "target_citation": edge["target_citation"]} for edge in case["relations"]]
            edge_by_arm = {"no_relation": [], "validated_relation": case["relations"], "inverse_corrupted": inverse, "node_only_sham": sham}
            for arm in RELATION_ARMS:
                payload = {"case_key": case["case_key"], "vignette": case["vignette"], "candidates": case["candidates"], "nodes": case["nodes"], "relations": edge_by_arm[arm]}
                jobs.append(_job(component, arm, case, PROMPTS[component][arm], payload))
    else:
        raise ValueError(component)
    write_jsonl(out, jobs)
    atomic_json(Path(out).with_suffix(".manifest.json"), {"schema": SCHEMA, "component": component, "stage": stage, "job_n": len(jobs), "jobs_sha256": canonical_sha256(jobs), "api_called": False})
    return jobs


def _job(component: str, arm: str, case: Mapping[str, Any], prompt: str, payload: Mapping[str, Any], *, stage: str = "selector") -> dict[str, Any]:
    _assert_blind(payload)
    _assert_prompt_blind(prompt)
    return {
        "schema": SCHEMA, "component": component, "stage": stage,
        "case_key": case["case_key"], "family": case["family"], "arm": arm,
        "prompt": prompt, "payload": dict(payload),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "payload_sha256": canonical_sha256(payload),
    }


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


def analyse(
    component: str,
    run_jobs: Path,
    responses: Path,
    truth: Path,
    out: Path,
    *,
    truth_provenance: str | None = None,
    truth_manifest: Path | None = None,
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
    truth_index = _truth(truth)
    response_index: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicates: set[tuple[str, str, str]] = set()
    for row in response_rows:
        key = (str(row["case_key"]), str(row["arm"]), str(row.get("stage") or "selector"))
        if key in response_index:
            duplicates.add(key)
        response_index[key] = row
    ledger: list[dict[str, Any]] = []
    for job in jobs:
        key = (job["case_key"], job["arm"], job.get("stage") or "selector")
        response = response_index.get(key) or {}
        champion = str(response.get("champion_id") or (response.get("response") or {}).get("champion_id") or "")
        candidate_ids = {str(c["candidate_id"]) for c in job["payload"].get("candidates", job["payload"].get("main_frontier", []))}
        served = key not in duplicates and bool(response.get("success", True)) and bool(champion) and champion in candidate_ids
        relation = truth_index.get((job["case_key"], champion), "U") if served else "U"
        response_body = response.get("response") if isinstance(response.get("response"), Mapping) else response
        exposure_ids = candidate_ids
        ledger.append({
            "case_key": job["case_key"], "family": job["family"], "arm": job["arm"],
            "served": served, "champion_id": champion if served else "", "adjudicated_relation": relation,
            "complete": bool(served and relation == "C"), "ita": True,
            "complete_exposed": any(truth_index.get((job["case_key"], cid)) == "C" for cid in exposure_ids),
            "modifier_hallucination": bool(response_body.get("modifier_hallucination")),
            "wrong_episode_or_object_binding": bool(response_body.get("wrong_episode_or_object_binding")),
            "unnecessary_high_risk_action": bool(response_body.get("unnecessary_high_risk_action")),
            "failure": "duplicate_response" if key in duplicates else ("" if served else "missing_or_invalid_response"),
        })
    write_jsonl(Path(out).with_suffix(".ledger.jsonl"), ledger)
    metrics: dict[str, Any] = {}
    for arm in sorted({r["arm"] for r in ledger}):
        subset = [r for r in ledger if r["arm"] == arm]
        metrics[arm] = {
            "intended_n": len(subset), "served_n": sum(r["served"] for r in subset),
            "service_rate": sum(r["served"] for r in subset) / max(1, len(subset)),
            "complete_n": sum(r["complete"] for r in subset),
            "ita_complete_rate": sum(r["complete"] for r in subset) / max(1, len(subset)),
            "complete_exposure_rate": sum(r["complete_exposed"] for r in subset) / max(1, len(subset)),
            "modifier_hallucination_rate": sum(r["modifier_hallucination"] for r in subset) / max(1, len(subset)),
            "wrong_episode_or_object_binding_rate": sum(r["wrong_episode_or_object_binding"] for r in subset) / max(1, len(subset)),
            "unnecessary_high_risk_action_rate": sum(r["unnecessary_high_risk_action"] for r in subset) / max(1, len(subset)),
        }
    failures = [f"{arm}:service_below_0.98" for arm, value in metrics.items() if value["service_rate"] < .98]
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
        factor_transition = _paired_transitions(ledger, "factorized_lattice", "flat")
        contrasts["factorized_lattice_vs_flat"].update(factor_transition)
        if metrics["factorized_lattice"]["modifier_hallucination_rate"] > metrics["flat"]["modifier_hallucination_rate"]:
            failures.append("modifier_hallucination_increased")
        if factor_transition["catastrophic_substitutions"] > factor_transition["complete_rescues"]:
            failures.append("factorization_catastrophic_substitution_exceeds_rescue")
    elif component == "active":
        for control in ("no_acquisition", "cost_matched_random"):
            effect = metrics["typed_action"]["ita_complete_rate"] - metrics[control]["ita_complete_rate"]
            lower = _paired_bootstrap_lower(ledger, "typed_action", control)
            contrasts[f"typed_action_vs_{control}"] = {"difference": effect, "bootstrap_95_lower": lower}
        random_contrast = contrasts["typed_action_vs_cost_matched_random"]
        if random_contrast["difference"] < .15 or random_contrast["bootstrap_95_lower"] <= 0:
            failures.append("typed_action_not_15pp_and_positive_lower_bound_over_cost_matched_random")
        if metrics["typed_action"]["wrong_episode_or_object_binding_rate"] > .02:
            failures.append("wrong_episode_or_object_binding_above_0.02")
        if metrics["typed_action"]["unnecessary_high_risk_action_rate"] > .05:
            failures.append("unnecessary_high_risk_action_above_0.05")
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
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
